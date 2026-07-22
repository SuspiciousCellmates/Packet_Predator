"""Opaque 32-byte transport wrapper around the experimental nRF905 device."""

from __future__ import annotations

import atexit
import time
from typing import Callable

from .adapters.nrf905 import Nrf905Device
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
        self._probe = device.start()

    def status(self) -> dict[str, object]:
        return {
            "mode": "nrf905",
            "label": "nRF905 physical adapter",
            "connected": not self._closed,
            "can_receive": not self._closed,
            "can_transmit": not self._closed and self.profile.radio.transmit_enabled,
            "description": "A configured nRF905 is listening for complete 32-byte frames; it never responds automatically.",
            "profile": self.profile.public_summary(),
            "configuration_hex": self._probe["configuration_hex"],
            "pins": self.device.pin_status() if not self._closed else {},
        }

    def poll(self) -> list[CarrierFrame]:
        frame = self.device.receive()
        if frame is None:
            return []
        item = self._carrier_frame(frame, "received", "Valid address and hardware CRC received by nRF905.")
        return [item]

    def send(self, frame: bytes) -> CarrierFrame:
        result = self.device.transmit(frame)
        return self._carrier_frame(
            frame,
            "sent",
            f"nRF905 reported transmit completion after {result['elapsed_ms']} ms.",
        )

    def close(self) -> None:
        if self._closed:
            return
        self.device.close()
        self._closed = True

    def _carrier_frame(self, frame: bytes, direction: str, note: str) -> CarrierFrame:
        item = CarrierFrame(
            sequence=self._sequence,
            at_ms=round((self._monotonic() - self._started_at) * 1000),
            direction=direction,
            frame=frame,
            frame_mode="fixed",
            recording_id="",
            fixture_id="",
            note=note,
        )
        self._sequence += 1
        return item


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
