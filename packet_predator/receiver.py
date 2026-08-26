"""Lifecycle-managed physical receive worker."""

from __future__ import annotations

import threading
import time
from typing import Any, Callable

from .adapters.nrf905 import Nrf905Error
from .nrf905_transport import Nrf905Transport
from .transport import CarrierFrame


class PhysicalReceiver:
    """Continuously move physical frames into the workbench service."""

    def __init__(
        self,
        transport: Nrf905Transport,
        consume: Callable[[CarrierFrame], dict[str, Any]],
        set_state: Callable[[str, dict[str, Any] | None], dict[str, Any]],
        record_metrics: Callable[..., dict[str, Any]],
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._transport = transport
        self._consume = consume
        self._set_state = set_state
        self._record_metrics = record_metrics
        self._monotonic = monotonic
        self._stop = threading.Event()
        self._lock = threading.RLock()
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            self._set_state("starting", None)
            self._thread = threading.Thread(
                target=self._run,
                name="PacketPredatorPhysicalReceiver",
                daemon=False,
            )
            self._thread.start()

    def stop(self, timeout_s: float = 2.0) -> None:
        with self._lock:
            thread = self._thread
            if thread is None:
                self._set_state("stopped", None)
                return
            self._stop.set()
        thread.join(timeout_s)
        if thread.is_alive():
            raise RuntimeError("The physical receiver did not stop within the shutdown deadline.")
        with self._lock:
            self._thread = None

    def _run(self) -> None:
        faulted = False
        pending: list[CarrierFrame] = []
        self._set_state("listening", None)
        try:
            while not self._stop.is_set():
                if pending:
                    batch = pending
                    pending = []
                else:
                    item = self._transport.wait_for_frame(self._stop)
                    if item is None:
                        continue
                    batch = [item]

                drain_started = self._monotonic()
                while not self._stop.is_set():
                    available = self._transport.poll()
                    if not available:
                        break
                    batch.extend(available)
                self._record_metrics(
                    {"batch_drain_ms": (self._monotonic() - drain_started) * 1000.0}
                )

                processing_started_ns = round(self._monotonic() * 1_000_000_000)
                for captured in batch:
                    if self._stop.is_set():
                        break
                    service_started = self._monotonic()
                    self._consume(captured)
                    self._record_metrics(
                        {
                            "receiver_service_ms": (
                                self._monotonic() - service_started
                            )
                            * 1000.0
                        }
                    )
                processing_completed_ns = round(self._monotonic() * 1_000_000_000)

                if self._stop.is_set():
                    continue
                pending = self._transport.poll()
                if pending:
                    overlap_count = sum(
                        1
                        for item in pending
                        if self._arrived_during_processing(
                            item,
                            processing_started_ns,
                            processing_completed_ns,
                        )
                    )
                    if overlap_count:
                        self._record_metrics(
                            edge_or_frame_during_processing=overlap_count
                        )
        except Nrf905Error as exc:
            faulted = True
            self._set_state("faulted", exc.as_dict())
        except Exception as exc:
            faulted = True
            self._set_state(
                "faulted",
                {"code": "PHYSICAL_RECEIVER_FAILED", "message": str(exc)},
            )
        finally:
            if not faulted:
                self._set_state("stopped", None)

    @staticmethod
    def _arrived_during_processing(
        item: CarrierFrame,
        started_ns: int,
        completed_ns: int,
    ) -> bool:
        timing = item.timing or {}
        edge_ns = timing.get("edge_monotonic_ns")
        if isinstance(edge_ns, int):
            return started_ns <= edge_ns <= completed_ns
        # The pre-decode drain had already observed DR low. A later level-only
        # capture is therefore the frame form of the same overlap evidence,
        # although it has no surviving kernel edge timestamp for exact spans.
        return timing.get("ready_source") == "level"
