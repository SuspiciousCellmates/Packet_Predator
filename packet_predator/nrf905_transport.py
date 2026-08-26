"""Opaque 32-byte transport wrapper around the experimental nRF905 device."""

from __future__ import annotations

import atexit
import threading
import time
from typing import Callable

from .adapters.nrf905 import DataReadyWait, Nrf905Device, Nrf905Error
from .adapters.nrf905_linux import open_linux_backends
from .nrf905_profile import Nrf905Profile
from .transport import CarrierFrame, ReceiveTransport


class Nrf905Transport(ReceiveTransport):
    def __init__(
        self,
        profile: Nrf905Profile,
        device: Nrf905Device,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.profile = profile
        self.device = device
        self._monotonic = monotonic
        self._started_at = monotonic()
        self._sequence = 0
        self._closed = False
        self._operation_lock = threading.RLock()
        self._wait_activity_lock = threading.Lock()
        self._spurious_wake_count = 0
        self._level_ready_without_edge_timestamp_count = 0
        self._probe = device.start()

    @property
    def monotonic(self) -> Callable[[], float]:
        return self._monotonic

    def status(self) -> dict[str, object]:
        with self._operation_lock:
            pins: dict[str, bool] = {}
            status_error: dict[str, str] | None = None
            if not self._closed:
                try:
                    pins = self.device.pin_status()
                except Nrf905Error as exc:
                    status_error = exc.as_dict()
                except Exception as exc:
                    status_error = {
                        "code": "NRF905_STATUS_FAILED",
                        "message": str(exc),
                    }
            return {
                "mode": "nrf905",
                "label": "nRF905 physical adapter",
                "connected": not self._closed,
                "can_receive": not self._closed,
                "can_transmit": not self._closed and self.profile.radio.transmit_enabled,
                "description": "A configured nRF905 is listening for complete 32-byte frames; it never responds automatically.",
                "profile": self.profile.public_summary(),
                "configuration_hex": self._probe["configuration_hex"],
                "pins": pins,
                "status_error": status_error,
                "receive_wait": self._receive_wait_status(),
            }

    def poll(self) -> list[CarrierFrame]:
        if self._closed:
            return []
        wait = self.device.wait_data_ready(0.0)
        if not wait:
            self._record_wait_activity(wait)
            return []
        item = self._capture_after_wait(wait)
        return [] if item is None else [item]

    def wait_for_frame(self, stop: threading.Event, wait_s: float = 0.100) -> CarrierFrame | None:
        """Wait for receive readiness; the timeout exists only for cancellation."""
        while not stop.is_set():
            wait = self.device.wait_data_ready(wait_s)
            if not wait:
                self._record_wait_activity(wait)
                continue
            item = self._capture_after_wait(wait, stop)
            if item is not None:
                return item
        return None

    def send(self, frame: bytes) -> CarrierFrame:
        with self._operation_lock:
            result = self.device.transmit(frame)
            return self._carrier_frame(
                frame,
                "sent",
                (
                    "nRF905 reported transmit completion after "
                    f"{result['tx_completion_ms']} ms; receive-mode pins were reasserted "
                    f"after {result['receive_mode_reentry_ms']} ms."
                ),
                timing={
                    "tx_completion_ms": result["tx_completion_ms"],
                    "receive_mode_reentry_ms": result["receive_mode_reentry_ms"],
                    "tx_completion_to_receive_mode_reentry_ms": result[
                        "tx_completion_to_receive_mode_reentry_ms"
                    ],
                },
            )

    def close(self) -> None:
        with self._operation_lock:
            if self._closed:
                return
            self.device.close()
            self._closed = True

    def _capture_after_wait(
        self,
        wait: DataReadyWait,
        stop: threading.Event | None = None,
    ) -> CarrierFrame | None:
        lock_requested_ns = self._monotonic_ns()
        with self._operation_lock:
            lock_acquired_ns = self._monotonic_ns()
            if self._closed or (stop is not None and stop.is_set()):
                return None
            received = self.device.receive_with_timing()
            if received is None:
                self._record_wait_activity(
                    DataReadyWait(
                        ready=False,
                        edge_monotonic_ns=wait.edge_monotonic_ns,
                        source="ready-level-cleared-before-payload",
                    )
                )
                return None

        self._record_wait_activity(wait)
        timing: dict[str, object] = {
            "ready_source": wait.source,
            "edge_monotonic_ns": wait.edge_monotonic_ns,
            "receive_lock_wait_ms": self._milliseconds(
                lock_requested_ns,
                lock_acquired_ns,
            ),
            "payload_read_to_receive_reentry_ms": self._milliseconds(
                received.read_completed_monotonic_ns,
                received.reentry_completed_monotonic_ns,
            ),
        }
        if wait.edge_monotonic_ns is not None:
            timing["edge_to_lock_ms"] = self._milliseconds(
                wait.edge_monotonic_ns,
                lock_acquired_ns,
            )
            timing["edge_to_payload_read_ms"] = self._milliseconds(
                wait.edge_monotonic_ns,
                received.read_completed_monotonic_ns,
            )
        else:
            timing["edge_to_lock_ms"] = None
            timing["edge_to_payload_read_ms"] = None

        return self._carrier_frame(
            received.frame,
            "received",
            "Valid address and hardware CRC received by nRF905.",
            timing=timing,
        )

    def _carrier_frame(
        self,
        frame: bytes,
        direction: str,
        note: str,
        timing: dict[str, object] | None = None,
    ) -> CarrierFrame:
        item = CarrierFrame(
            sequence=self._sequence,
            at_ms=round((self._monotonic() - self._started_at) * 1000),
            direction=direction,
            frame=frame,
            frame_mode="fixed",
            recording_id="",
            fixture_id="",
            note=note,
            timing=timing,
        )
        self._sequence += 1
        return item

    def _record_wait_activity(self, wait: DataReadyWait) -> None:
        with self._wait_activity_lock:
            if wait.ready and wait.edge_monotonic_ns is None:
                self._level_ready_without_edge_timestamp_count += 1
            elif not wait.ready and wait.source != "timeout":
                self._spurious_wake_count += 1

    def _receive_wait_status(self) -> dict[str, int]:
        with self._wait_activity_lock:
            return {
                "spurious_wake_count": self._spurious_wake_count,
                "level_ready_without_edge_timestamp_count": (
                    self._level_ready_without_edge_timestamp_count
                ),
            }

    def _monotonic_ns(self) -> int:
        return round(self._monotonic() * 1_000_000_000)

    @staticmethod
    def _milliseconds(start_ns: int, end_ns: int) -> float:
        return round(max(0, end_ns - start_ns) / 1_000_000, 3)


def open_nrf905_transport(profile: Nrf905Profile) -> Nrf905Transport:
    spi, lines = open_linux_backends(profile)
    device = Nrf905Device(profile, spi, lines)
    try:
        transport = Nrf905Transport(profile, device)
    except Exception:
        device.close()
        raise
    atexit.register(transport.close)
    return transport
