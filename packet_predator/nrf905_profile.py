"""Strict deployment-profile loading for the experimental nRF905 adapter."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class Nrf905ProfileError(ValueError):
    """An adapter deployment profile is missing or unsafe to interpret."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.detail}


@dataclass(frozen=True)
class SpiSettings:
    device: str
    speed_hz: int


@dataclass(frozen=True)
class GpioSettings:
    chip: str
    pwr_up: int
    trx_ce: int
    tx_en: int
    carrier_detect: int
    address_match: int
    data_ready: int

    def named_lines(self) -> dict[str, int]:
        return {
            "pwr_up": self.pwr_up,
            "trx_ce": self.trx_ce,
            "tx_en": self.tx_en,
            "carrier_detect": self.carrier_detect,
            "address_match": self.address_match,
            "data_ready": self.data_ready,
        }


@dataclass(frozen=True)
class RadioSettings:
    band: int
    channel: int
    transmit_power_dbm: int
    receive_reduced_power: bool
    automatic_retransmit: bool
    address: bytes
    crystal_mhz: int
    crc_bits: int
    transmit_enabled: bool

    @property
    def frequency_mhz(self) -> float:
        return (422.4 + self.channel / 10.0) * (2 if self.band == 868 else 1)


@dataclass(frozen=True)
class Nrf905Profile:
    source: Path
    identifier: str
    spi: SpiSettings
    gpio: GpioSettings
    radio: RadioSettings

    def public_summary(self) -> dict[str, Any]:
        return {
            "id": self.identifier,
            "spi_device": self.spi.device,
            "gpio_chip": self.gpio.chip,
            "band": self.radio.band,
            "channel": self.radio.channel,
            "frequency_mhz": self.radio.frequency_mhz,
            "physical_address_hex": self.radio.address.hex().upper(),
            "crc_bits": self.radio.crc_bits,
            "transmit_power_dbm": self.radio.transmit_power_dbm,
            "transmit_enabled": self.radio.transmit_enabled,
        }


def _object(value: Any, label: str, fields: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise Nrf905ProfileError("PROFILE_SHAPE", f"{label} must be a JSON object.")
    if set(value) != fields:
        raise Nrf905ProfileError(
            "PROFILE_FIELDS",
            f"{label} requires exactly {sorted(fields)}; found {sorted(value)}.",
        )
    return value


def _integer(value: Any, label: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise Nrf905ProfileError(
            "PROFILE_VALUE", f"{label} must be an integer from {minimum} to {maximum}."
        )
    return value


def _boolean(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise Nrf905ProfileError("PROFILE_VALUE", f"{label} must be true or false.")
    return value


def load_nrf905_profile(path: Path) -> Nrf905Profile:
    resolved = path.expanduser().resolve()
    try:
        raw = json.loads(resolved.read_text(encoding="utf-8"))
    except OSError as exc:
        raise Nrf905ProfileError("PROFILE_UNREADABLE", f"Cannot read {resolved}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise Nrf905ProfileError(
            "PROFILE_JSON",
            f"{resolved}: malformed JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}.",
        ) from exc

    data = _object(raw, "profile", {"schema_version", "id", "adapter", "spi", "gpio", "radio"})
    if data["schema_version"] != 1:
        raise Nrf905ProfileError("PROFILE_SCHEMA", "schema_version must be 1.")
    if data["adapter"] != "nrf905":
        raise Nrf905ProfileError("PROFILE_ADAPTER", "adapter must be 'nrf905'.")
    identifier = data["id"]
    if not isinstance(identifier, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", identifier):
        raise Nrf905ProfileError("PROFILE_ID", "id must be lowercase kebab-case.")

    spi_data = _object(data["spi"], "spi", {"device", "speed_hz"})
    device = spi_data["device"]
    if not isinstance(device, str) or not device.startswith("/dev/"):
        raise Nrf905ProfileError("PROFILE_SPI_DEVICE", "spi.device must be an absolute /dev path.")
    speed_hz = _integer(spi_data["speed_hz"], "spi.speed_hz", 1_000, 10_000_000)

    gpio_fields = {
        "chip",
        "pwr_up",
        "trx_ce",
        "tx_en",
        "carrier_detect",
        "address_match",
        "data_ready",
    }
    gpio_data = _object(data["gpio"], "gpio", gpio_fields)
    chip = gpio_data["chip"]
    if not isinstance(chip, str) or not chip.startswith("/dev/gpiochip"):
        raise Nrf905ProfileError("PROFILE_GPIO_CHIP", "gpio.chip must be a /dev/gpiochip path.")
    line_values = {
        name: _integer(gpio_data[name], f"gpio.{name}", 0, 255)
        for name in gpio_fields - {"chip"}
    }
    if len(set(line_values.values())) != len(line_values):
        raise Nrf905ProfileError("PROFILE_GPIO_DUPLICATE", "Every nRF905 GPIO signal needs a distinct line.")

    radio_fields = {
        "band",
        "channel",
        "transmit_power_dbm",
        "receive_reduced_power",
        "automatic_retransmit",
        "address_hex",
        "crystal_mhz",
        "crc_bits",
        "transmit_enabled",
    }
    radio_data = _object(data["radio"], "radio", radio_fields)
    band = _integer(radio_data["band"], "radio.band", 433, 868)
    if band not in {433, 868}:
        raise Nrf905ProfileError("PROFILE_BAND", "radio.band must be 433 or 868 (the latter selects 868/915 mode).")
    channel = _integer(radio_data["channel"], "radio.channel", 0, 511)
    transmit_power = radio_data["transmit_power_dbm"]
    if transmit_power not in {-10, -2, 6, 10}:
        raise Nrf905ProfileError(
            "PROFILE_POWER", "radio.transmit_power_dbm must be -10, -2, 6, or 10."
        )
    address_hex = radio_data["address_hex"]
    if not isinstance(address_hex, str) or not re.fullmatch(r"[0-9a-fA-F]{8}", address_hex):
        raise Nrf905ProfileError("PROFILE_ADDRESS", "radio.address_hex must contain exactly four bytes.")
    address = bytes.fromhex(address_hex)
    if len(set(address)) != 4:
        raise Nrf905ProfileError(
            "PROFILE_ADDRESS",
            "radio.address_hex must use four distinct bytes to avoid a weak repeated-byte address.",
        )
    crystal = radio_data["crystal_mhz"]
    if crystal not in {4, 8, 12, 16, 20}:
        raise Nrf905ProfileError("PROFILE_CRYSTAL", "radio.crystal_mhz must be 4, 8, 12, 16, or 20.")
    crc_bits = radio_data["crc_bits"]
    if crc_bits not in {8, 16}:
        raise Nrf905ProfileError("PROFILE_CRC", "radio.crc_bits must be 8 or 16; CRC cannot be disabled in this bench.")

    automatic_retransmit = _boolean(
        radio_data["automatic_retransmit"], "radio.automatic_retransmit"
    )
    if automatic_retransmit:
        raise Nrf905ProfileError(
            "PROFILE_RETRANSMIT",
            "radio.automatic_retransmit must remain false for deliberate one-frame validation.",
        )
    frequency_mhz = (422.4 + channel / 10.0) * (2 if band == 868 else 1)
    if not 430.0 <= frequency_mhz <= 928.0:
        raise Nrf905ProfileError(
            "PROFILE_FREQUENCY",
            f"band {band} and channel {channel} calculate to {frequency_mhz:.1f} MHz, outside the nRF905 range.",
        )

    return Nrf905Profile(
        source=resolved,
        identifier=identifier,
        spi=SpiSettings(device=device, speed_hz=speed_hz),
        gpio=GpioSettings(chip=chip, **line_values),
        radio=RadioSettings(
            band=band,
            channel=channel,
            transmit_power_dbm=transmit_power,
            receive_reduced_power=_boolean(
                radio_data["receive_reduced_power"], "radio.receive_reduced_power"
            ),
            automatic_retransmit=automatic_retransmit,
            address=address,
            crystal_mhz=crystal,
            crc_bits=crc_bits,
            transmit_enabled=_boolean(radio_data["transmit_enabled"], "radio.transmit_enabled"),
        ),
    )
