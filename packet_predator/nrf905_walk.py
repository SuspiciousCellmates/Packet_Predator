"""Range-walk instrument for the experimental nRF905 adapter, on Raspberry Pi.

This ports the measurement design of Player_Node_Firmware's rf-tool-suite
Tool 2 (see ../Player_Node_Firmware/docs/rf-tool-suite.md) onto the Pi bench:
the same 32-byte beacon layout and the same idea -- alternating one-way
beacons, no turnaround deadline, each side counts what arrives from its
partner -- so a capture from either platform means the same thing.

Two things are deliberately not a straight port, because a straight port
would measure the wrong thing here:

- **Loss is derived from the beacon's sequence number, not from whether a
  frame arrived inside a timed slot window.** The ESP32 image owns a
  dedicated core and can hold slot timing tightly; this runs under the Linux
  scheduler with SPI transactions and GC in the way, so a frame that arrived
  a few milliseconds late would read as "missed" under slot-gating. That is
  exactly the failure the original design killed the echo-based measurement
  over (a fixed turnaround deadline reading as loss). Counting distinct
  sequence numbers across the whole burst and reading gaps in that set has
  the same property the sequence field was already carrying: it is immune to
  when a frame happened to arrive.

- **Uplink is the delta of the partner's reported total, not its maximum.**
  The ESP32 tool resets both nodes' counters together at every station via a
  button press on each. Here the fixed node is a long-running process started
  once, so its own "received" counter never resets across stations. The
  carried node instead samples that counter at the start and end of its own
  burst and reports the difference -- correct at any station, at any time
  into a multi-hour walk.

The wire layout (magic, role, station, sequence, received_count, all in the
same byte positions) is unchanged, so a Pi could stand in for either end of
the badge walk, given one spare nRF905 module and a hard solder.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from .adapters.nrf905 import Nrf905Device, Nrf905Error

WALK_FRAME_SIZE = 32
# Matches kWalkFrameMagic in Player_Node_Firmware/tools/rf-tool-suite/main/walk_frame.hpp
WALK_FRAME_MAGIC = b"RFWK"

ROLE_FIXED = 0
ROLE_CARRIED = 1
_ROLES = (ROLE_FIXED, ROLE_CARRIED)


class WalkFrameError(ValueError):
    """A WalkFrame field does not fit the wire layout."""


@dataclass(frozen=True)
class WalkFrame:
    role: int
    station: int
    sequence: int
    received_count: int

    def __post_init__(self) -> None:
        if self.role not in _ROLES:
            raise WalkFrameError(f"role must be one of {_ROLES}, not {self.role}")
        for name, value in (
            ("station", self.station),
            ("sequence", self.sequence),
            ("received_count", self.received_count),
        ):
            if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 0xFFFF:
                raise WalkFrameError(f"{name} must be an integer from 0 to 65535, not {value!r}")

    def encode(self) -> bytes:
        body = (
            WALK_FRAME_MAGIC
            + bytes([self.role])
            + self.station.to_bytes(2, "big")
            + self.sequence.to_bytes(2, "big")
            + self.received_count.to_bytes(2, "big")
        )
        return body.ljust(WALK_FRAME_SIZE, b"\x00")


def decode_walk_frame(frame: bytes) -> Optional[WalkFrame]:
    """Decode a walk beacon, or None if this is not one.

    The magic check matters operationally, not just structurally: the badge
    protocol can share this same address and channel, so an ordinary game
    frame can physically arrive at a walk-test node. Treating it as a beacon
    would corrupt the measurement in a way nobody would notice afterwards.
    """

    if len(frame) != WALK_FRAME_SIZE or frame[:4] != WALK_FRAME_MAGIC:
        return None
    role = frame[4]
    if role not in _ROLES:
        return None
    return WalkFrame(
        role=role,
        station=int.from_bytes(frame[5:7], "big"),
        sequence=int.from_bytes(frame[7:9], "big"),
        received_count=int.from_bytes(frame[9:11], "big"),
    )


def percent_of(part: int, whole: int) -> int:
    """Round-to-nearest percentage, 0 when whole is 0, capped at 100."""

    if whole <= 0:
        return 0
    scaled = (part * 100 + whole // 2) // whole
    return max(0, min(scaled, 100))


def _distinct_gap_stats(sequences: set[int]) -> tuple[int, int, int]:
    """(received, longest_miss_run, span) from a set of distinct sequences seen.

    span is the inclusive range between the lowest and highest sequence
    observed -- how many beacons should have arrived in that window by the
    sender's own count, independent of our transmit timing. This is the
    denominator for downlink loss, and is what makes the measurement immune
    to scheduler jitter: a frame's arrival time is never consulted, only
    which sequence numbers showed up at all.
    """

    if not sequences:
        return 0, 0, 0
    low, high = min(sequences), max(sequences)
    span = high - low + 1
    longest = 0
    current = 0
    for value in range(low, high + 1):
        if value in sequences:
            current = 0
        else:
            current += 1
            longest = max(longest, current)
    return len(sequences), longest, span


@dataclass(frozen=True)
class BurstResult:
    station: int
    slots_run: int
    slots_void: int
    downlink_received: int
    downlink_span: int
    longest_miss_run: int
    uplink_delivered: int
    uplink_denominator: int
    carrier_samples: int
    carrier_busy: int

    @property
    def downlink_loss_percent(self) -> int:
        if self.downlink_span == 0:
            return 0
        return percent_of(self.downlink_span - self.downlink_received, self.downlink_span)

    @property
    def uplink_loss_percent(self) -> int:
        if self.uplink_denominator <= 0:
            return 0
        delivered = max(0, min(self.uplink_delivered, self.uplink_denominator))
        return percent_of(self.uplink_denominator - delivered, self.uplink_denominator)

    @property
    def carrier_busy_percent(self) -> int:
        return percent_of(self.carrier_busy, self.carrier_samples)

    @property
    def trustworthy(self) -> bool:
        # Same threshold as the ESP32 tool: a burst dominated by local faults
        # is not a measurement, and the miss-run figure in particular is only
        # meaningful across slots we actually learned something from.
        return self.slots_run != 0 and self.slots_void * 4 < self.slots_run

    def as_dict(self) -> dict[str, object]:
        return {
            "station": self.station,
            "slots_run": self.slots_run,
            "slots_void": self.slots_void,
            "downlink_received": self.downlink_received,
            "downlink_span": self.downlink_span,
            "downlink_loss_percent": self.downlink_loss_percent,
            "longest_miss_run": self.longest_miss_run,
            "uplink_delivered": max(0, self.uplink_delivered),
            "uplink_denominator": self.uplink_denominator,
            "uplink_loss_percent": self.uplink_loss_percent,
            "carrier_busy_percent": self.carrier_busy_percent,
            "trustworthy": self.trustworthy,
        }


class SysfsLed:
    """An onboard status LED exposed by Raspberry Pi OS at /sys/class/leds.

    This is the only field feedback the carried node has while walking
    untethered -- there is no screen. A device that exists but cannot be
    driven is therefore a failure, not something to fall back silently past:
    the same gate-discipline rule as everywhere else in this project. List
    candidates with `ls /sys/class/leds`; the Zero 2 W's is typically "ACT",
    the Pi 5's "ACT" or "PWR" depending on OS version.
    """

    def __init__(self, name: str) -> None:
        base = Path(f"/sys/class/leds/{name}")
        self._brightness = base / "brightness"
        if not self._brightness.exists():
            raise Nrf905Error(
                "LED_DEVICE_MISSING",
                f"{base} does not exist. List candidates with `ls /sys/class/leds`.",
            )
        try:
            (base / "trigger").write_text("none")
            self._max = int((base / "max_brightness").read_text().strip())
        except OSError as exc:
            raise Nrf905Error(
                "LED_PERMISSION",
                f"Cannot prepare {base}: {exc}. Run as root or add the needed udev rule.",
            ) from exc
        self.off()

    def on(self) -> None:
        self._write(self._max)

    def off(self) -> None:
        self._write(0)

    def blink(self, seconds: float = 0.05, sleeper: Callable[[float], None] = time.sleep) -> None:
        self.on()
        sleeper(seconds)
        self.off()

    def _write(self, value: int) -> None:
        try:
            self._brightness.write_text(str(value))
        except OSError as exc:
            raise Nrf905Error("LED_WRITE", f"Cannot write {self._brightness}: {exc}") from exc


def run_carried_burst(
    device: Nrf905Device,
    led: SysfsLed,
    station: int,
    slots: int = 100,
    interval_s: float = 0.100,
    sleeper: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> BurstResult:
    """Walk to a spot, stop, run this once. It measures one station and returns.

    Each interval this node transmits its own beacon, then spends the rest of
    the interval listening for the fixed node's. The LED blinks once per
    *received* downlink frame, not per transmit of our own -- our own transmit
    succeeding is a local event that happens regardless of range, so it can't
    tell you anything about the link. Gating the blink on reception instead
    means walking out of range makes it visibly stop, and walking back makes
    it visibly resume: "walk until it stops, walk back until it starts."
    """

    fixed_sequences: set[int] = set()
    first_fixed_count: Optional[int] = None
    last_fixed_count: Optional[int] = None
    slots_run = 0
    slots_void = 0
    carrier_samples = 0
    carrier_busy = 0
    own_sequence = 0

    for _ in range(slots):
        slot_start = monotonic()
        slots_run += 1
        try:
            device.transmit(
                WalkFrame(
                    role=ROLE_CARRIED,
                    station=station,
                    sequence=own_sequence,
                    received_count=len(fixed_sequences),
                ).encode()
            )
            own_sequence = (own_sequence + 1) % 0x10000
        except Nrf905Error:
            slots_void += 1

        # Sampled once in the idle gap after our own transmit settles and
        # before the next one -- never mid-transmit, where a high reading
        # would just be our own traffic.
        try:
            busy = device.pin_status()["carrier_detect"]
        except Nrf905Error:
            pass
        else:
            carrier_samples += 1
            if busy:
                carrier_busy += 1

        deadline = slot_start + interval_s
        while True:
            remaining = deadline - monotonic()
            if remaining <= 0:
                break
            if not device.wait_data_ready(remaining):
                continue
            frame = device.receive()
            if frame is None:
                continue
            decoded = decode_walk_frame(frame)
            if decoded is None or decoded.role != ROLE_FIXED:
                continue
            led.blink(sleeper=sleeper)
            fixed_sequences.add(decoded.sequence)
            if first_fixed_count is None:
                first_fixed_count = decoded.received_count
            last_fixed_count = decoded.received_count

    received, longest_miss_run, span = _distinct_gap_stats(fixed_sequences)
    if first_fixed_count is None or last_fixed_count is None:
        uplink_delivered = 0
    else:
        uplink_delivered = last_fixed_count - first_fixed_count

    return BurstResult(
        station=station,
        slots_run=slots_run,
        slots_void=slots_void,
        downlink_received=received,
        downlink_span=span,
        longest_miss_run=longest_miss_run,
        uplink_delivered=uplink_delivered,
        uplink_denominator=slots_run - slots_void,
        carrier_samples=carrier_samples,
        carrier_busy=carrier_busy,
    )


def run_carried_loop(
    device: Nrf905Device,
    led: SysfsLed,
    start_station: int = 1,
    slots: int = 100,
    interval_s: float = 0.100,
    stop: Optional[threading.Event] = None,
    on_result: Optional[Callable[[BurstResult], None]] = None,
    sleeper: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> list[BurstResult]:
    """Run consecutive bursts back to back, auto-incrementing the station
    number, until stopped -- for walking continuously rather than re-invoking
    the command by hand at every stop.

    Each burst still measures and reports independently; this only removes
    the need for a button or a fresh SSH session between stations. There is
    still no way for the instrument to know where you physically were, so
    note wall-clock time or the printed station number against your position
    in your own notebook, same as ever.

    A stop request is only checked between bursts, not mid-burst, so expect
    up to one burst's length of delay after asking this to stop.
    """

    stop = stop if stop is not None else threading.Event()
    station = start_station
    results: list[BurstResult] = []
    while not stop.is_set():
        result = run_carried_burst(
            device, led, station=station, slots=slots, interval_s=interval_s,
            sleeper=sleeper, monotonic=monotonic,
        )
        results.append(result)
        if on_result is not None:
            on_result(result)
        station = (station + 1) % 0x10000
    return results


def run_fixed_loop(
    device: Nrf905Device,
    interval_s: float = 0.100,
    stop: Optional[threading.Event] = None,
    max_iterations: Optional[int] = None,
    on_status: Optional[Callable[[int, int], None]] = None,
    sleeper: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> int:
    """Beacon and count, forever, from the base station. Start this once.

    The returned/reported count is a plain running total of valid Carried
    beacons received -- incremented once per frame, never reset, never
    deduplicated by sequence. It is deliberately not station-scoped: a
    carried node's burst recovers "how many of my beacons arrived here" as
    the delta of this value across its own window, which is well-defined no
    matter how many stations came before or how long this has been running.
    """

    stop = stop if stop is not None else threading.Event()
    received = 0
    own_sequence = 0
    iterations = 0
    while not stop.is_set():
        if max_iterations is not None and iterations >= max_iterations:
            break
        iterations += 1
        slot_start = monotonic()
        try:
            device.transmit(
                WalkFrame(
                    role=ROLE_FIXED,
                    station=0,
                    sequence=own_sequence,
                    received_count=received,
                ).encode()
            )
            own_sequence = (own_sequence + 1) % 0x10000
        except Nrf905Error:
            pass

        deadline = slot_start + interval_s
        while True:
            remaining = deadline - monotonic()
            if remaining <= 0:
                break
            if not device.wait_data_ready(remaining):
                continue
            frame = device.receive()
            if frame is None:
                continue
            decoded = decode_walk_frame(frame)
            if decoded is not None and decoded.role == ROLE_CARRIED:
                received += 1

        if on_status is not None:
            on_status(iterations, received)

    return received
