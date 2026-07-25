"""nRF905 register and mode control independent of Linux-specific libraries."""

from __future__ import annotations

import threading
import time
from typing import Callable, Protocol

from ..nrf905_profile import Nrf905Profile


class Nrf905Error(RuntimeError):
    """A physical adapter operation failed with a stable diagnostic code."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.detail}


class SpiPort(Protocol):
    def exchange(self, outgoing: bytes) -> bytes: ...

    def close(self) -> None: ...


class DigitalLines(Protocol):
    def set(self, name: str, active: bool) -> None: ...

    def get(self, name: str) -> bool: ...

    def wait(self, name: str, timeout_s: float) -> bool: ...

    def close(self) -> None: ...


_W_CONFIG = 0x00
_R_CONFIG = 0x10
_W_TX_FIFO = 0x20
_W_TX_ADDRESS = 0x22
_R_RX_FIFO = 0x24
_FRAME_OCTETS = 32


def configuration_bytes(profile: Nrf905Profile) -> bytes:
    """Build the nRF905's ten-byte hardware register from a deployment profile."""

    radio = profile.radio
    power_index = {-10: 0, -2: 1, 6: 2, 10: 3}[radio.transmit_power_dbm]
    band_bit = 1 if radio.band == 868 else 0
    second = (
        ((1 if radio.automatic_retransmit else 0) << 5)
        | ((1 if radio.receive_reduced_power else 0) << 4)
        | (power_index << 2)
        | (band_bit << 1)
        | ((radio.channel >> 8) & 0x01)
    )
    width_byte = (4 << 4) | 4
    crystal_index = {4: 0, 8: 1, 12: 2, 16: 3, 20: 4}[radio.crystal_mhz]
    final = ((1 if radio.crc_bits == 16 else 0) << 7) | (1 << 6) | (crystal_index << 3)
    return bytes(
        [radio.channel & 0xFF, second, width_byte, _FRAME_OCTETS, _FRAME_OCTETS]
    ) + radio.address + bytes([final])


class Nrf905Device:
    """Synchronous nRF905 control used by the physical transport and diagnostics."""

    def __init__(
        self,
        profile: Nrf905Profile,
        spi: SpiPort,
        lines: DigitalLines,
        sleeper: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.profile = profile
        self.spi = spi
        self.lines = lines
        self.sleep = sleeper
        self.monotonic = monotonic
        self._lock = threading.RLock()
        self._started = False

    def start(self) -> dict[str, object]:
        with self._lock:
            self._standby(powered=False)
            expected = configuration_bytes(self.profile)
            self._exchange(bytes([_W_CONFIG]) + expected)
            observed = self._exchange(bytes([_R_CONFIG]) + bytes(len(expected)))[1:]
            if observed != expected:
                raise Nrf905Error(
                    "NRF905_REGISTER_MISMATCH",
                    f"Configuration readback differs: wrote {expected.hex()}, read {observed.hex()}.",
                )
            self.lines.set("pwr_up", True)
            self.sleep(0.003)
            self._receive_mode()
            self._started = True
            return {
                "configuration_hex": observed.hex(),
                "status": self.pin_status(),
            }

    def pin_status(self) -> dict[str, bool]:
        with self._lock:
            return {
                "carrier_detect": self.lines.get("carrier_detect"),
                "address_match": self.lines.get("address_match"),
                "data_ready": self.lines.get("data_ready"),
            }

    def wait_data_ready(self, timeout_s: float) -> bool:
        """Wait for receive readiness without holding the SPI/mode lock."""
        self._require_started()
        if self.lines.get("data_ready"):
            return True
        return self.lines.wait("data_ready", timeout_s)

    def receive(self) -> bytes | None:
        with self._lock:
            self._require_started()
            if not self.lines.get("data_ready"):
                return None
            self.lines.set("trx_ce", False)
            frame = self._exchange(bytes([_R_RX_FIFO]) + bytes(_FRAME_OCTETS))[1:]
            if len(frame) != _FRAME_OCTETS:
                raise Nrf905Error(
                    "NRF905_RECEIVE_LENGTH", f"Expected {_FRAME_OCTETS} received bytes, got {len(frame)}."
                )
            self._receive_mode()
            return frame

    def transmit(self, frame: bytes, timeout_s: float = 0.050) -> dict[str, object]:
        if len(frame) != _FRAME_OCTETS:
            raise Nrf905Error(
                "NRF905_TRANSMIT_LENGTH", f"nRF905 validation requires exactly {_FRAME_OCTETS} bytes."
            )
        if not self.profile.radio.transmit_enabled:
            raise Nrf905Error(
                "NRF905_TRANSMIT_DISABLED",
                "This profile is receive-only. Set radio.transmit_enabled only after reviewing the bench frequency.",
            )
        with self._lock:
            self._require_started()
            self.lines.set("trx_ce", False)
            self.lines.set("tx_en", True)
            self._exchange(bytes([_W_TX_ADDRESS]) + self.profile.radio.address)
            self._exchange(bytes([_W_TX_FIFO]) + frame)
            started = self.monotonic()
            self.lines.set("trx_ce", True)
            self.sleep(0.000010)
            self.lines.set("trx_ce", False)
            while not self.lines.get("data_ready"):
                if self.monotonic() - started >= timeout_s:
                    self.lines.set("tx_en", False)
                    self._receive_mode()
                    raise Nrf905Error(
                        "NRF905_TRANSMIT_TIMEOUT",
                        f"The nRF905 did not report transmit completion within {timeout_s * 1000:.0f} ms.",
                    )
                self.sleep(0.000100)
            elapsed_ms = (self.monotonic() - started) * 1000.0
            self.lines.set("tx_en", False)
            self._receive_mode()
            return {"elapsed_ms": round(elapsed_ms, 3), "frame_hex": frame.hex()}

    def close(self) -> None:
        with self._lock:
            try:
                self._standby(powered=False)
            finally:
                self.lines.close()
                self.spi.close()
                self._started = False

    def _standby(self, powered: bool = True) -> None:
        self.lines.set("trx_ce", False)
        self.lines.set("tx_en", False)
        self.lines.set("pwr_up", powered)

    def _receive_mode(self) -> None:
        self.lines.set("tx_en", False)
        self.lines.set("pwr_up", True)
        self.lines.set("trx_ce", True)

    def _exchange(self, outgoing: bytes) -> bytes:
        incoming = self.spi.exchange(outgoing)
        if len(incoming) != len(outgoing):
            raise Nrf905Error(
                "NRF905_SPI_LENGTH",
                f"SPI returned {len(incoming)} bytes for a {len(outgoing)}-byte exchange.",
            )
        return incoming

    def _require_started(self) -> None:
        if not self._started:
            raise Nrf905Error("NRF905_NOT_STARTED", "Probe and start the nRF905 before using the RF path.")
