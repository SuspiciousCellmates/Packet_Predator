"""Linux spidev and GPIO character-device backends for Raspberry Pi 5."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .nrf905 import Nrf905Error
from ..nrf905_profile import Nrf905Profile


class LinuxSpiPort:
    def __init__(self, profile: Nrf905Profile) -> None:
        device = Path(profile.spi.device)
        if not device.exists():
            raise Nrf905Error(
                "NRF905_SPI_DEVICE_MISSING",
                f"{device} does not exist. Enable SPI and confirm the profile's spi.device.",
            )
        try:
            import spidev
        except ImportError as exc:
            raise Nrf905Error(
                "NRF905_SPI_DEPENDENCY",
                "The spidev Python package is missing. Run ./scripts/setup-rpi.",
            ) from exc
        try:
            self._device = spidev.SpiDev()
            self._device.open_path(str(device))
            self._device.mode = 0
            self._device.bits_per_word = 8
            self._device.max_speed_hz = profile.spi.speed_hz
        except (OSError, PermissionError) as exc:
            raise Nrf905Error("NRF905_SPI_OPEN", f"Cannot open {device}: {exc}") from exc

    def exchange(self, outgoing: bytes) -> bytes:
        try:
            return bytes(self._device.xfer2(list(outgoing)))
        except OSError as exc:
            raise Nrf905Error("NRF905_SPI_EXCHANGE", f"SPI exchange failed: {exc}") from exc

    def close(self) -> None:
        self._device.close()


class LinuxDigitalLines:
    _outputs = ("pwr_up", "trx_ce", "tx_en")
    _inputs = ("carrier_detect", "address_match", "data_ready")

    def __init__(self, profile: Nrf905Profile) -> None:
        chip = Path(profile.gpio.chip)
        if not chip.exists():
            raise Nrf905Error(
                "NRF905_GPIO_DEVICE_MISSING",
                f"{chip} does not exist. Confirm the Raspberry Pi GPIO chip path.",
            )
        try:
            import gpiod
            from gpiod.line import Bias, Direction, Value
        except ImportError as exc:
            raise Nrf905Error(
                "NRF905_GPIO_DEPENDENCY",
                "The official gpiod Python package is missing. Run ./scripts/setup-rpi.",
            ) from exc
        self._value = Value
        self._offsets = profile.gpio.named_lines()
        output_offsets = tuple(self._offsets[name] for name in self._outputs)
        input_offsets = tuple(self._offsets[name] for name in self._inputs)
        try:
            self._request = gpiod.request_lines(
                str(chip),
                consumer="packet-predator-nrf905",
                config={
                    output_offsets: gpiod.LineSettings(
                        direction=Direction.OUTPUT,
                        output_value=Value.INACTIVE,
                    ),
                    input_offsets: gpiod.LineSettings(
                        direction=Direction.INPUT,
                        bias=Bias.DISABLED,
                    ),
                },
            )
        except (OSError, PermissionError) as exc:
            raise Nrf905Error("NRF905_GPIO_OPEN", f"Cannot request lines from {chip}: {exc}") from exc

    def set(self, name: str, active: bool) -> None:
        if name not in self._outputs:
            raise Nrf905Error("NRF905_GPIO_DIRECTION", f"{name} is not an output signal.")
        self._request.set_value(
            self._offsets[name], self._value.ACTIVE if active else self._value.INACTIVE
        )

    def get(self, name: str) -> bool:
        if name not in self._inputs:
            raise Nrf905Error("NRF905_GPIO_DIRECTION", f"{name} is not an input signal.")
        return self._request.get_value(self._offsets[name]) == self._value.ACTIVE

    def close(self) -> None:
        self._request.release()


def open_linux_backends(profile: Nrf905Profile) -> tuple[Any, Any]:
    spi = LinuxSpiPort(profile)
    try:
        lines = LinuxDigitalLines(profile)
    except Exception:
        spi.close()
        raise
    return spi, lines
