"""Explicit opaque-frame carrier boundary for the supported workbench."""

from __future__ import annotations

import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable


class TransportError(RuntimeError):
    """A requested carrier operation is unavailable or invalid."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.detail}


@dataclass(frozen=True)
class CarrierFrame:
    """One complete opaque frame plus capture provenance."""

    sequence: int
    at_ms: int
    direction: str
    frame: bytes
    frame_mode: str
    recording_id: str
    fixture_id: str
    note: str


class ReceiveTransport(ABC):
    """Small receive-side boundary shared by fake and later physical adapters."""

    @abstractmethod
    def status(self) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def poll(self) -> list[CarrierFrame]:
        raise NotImplementedError


class InspectOnlyTransport(ReceiveTransport):
    """A truthful no-hardware carrier: it can neither receive nor transmit."""

    def status(self) -> dict[str, Any]:
        return {
            "mode": "inspect-only",
            "label": "Local inspection",
            "connected": False,
            "can_receive": False,
            "can_transmit": False,
            "description": "No radio, replay, or fake nodes are active. Frames come only from examples or text you paste.",
        }

    def poll(self) -> list[CarrierFrame]:
        return []


class DeterministicReplayTransport(ReceiveTransport):
    """Release prevalidated opaque frames against an injectable monotonic clock."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.RLock()
        self._identifier: str | None = None
        self._title: str | None = None
        self._frames: tuple[CarrierFrame, ...] = ()
        self._duration_ms = 0
        self._cursor = 0
        self._position_ms = 0.0
        self._speed = 1.0
        self._state = "idle"
        self._anchor_clock = 0.0
        self._anchor_position_ms = 0.0

    def load(
        self,
        identifier: str,
        title: str,
        duration_ms: int,
        frames: tuple[CarrierFrame, ...],
    ) -> None:
        if not frames:
            raise TransportError("REPLAY_EMPTY", "A recording needs at least one frame.")
        if frames[-1].at_ms > duration_ms:
            raise TransportError("REPLAY_DURATION", "Recording duration ends before its final frame.")
        with self._lock:
            self._identifier = identifier
            self._title = title
            self._frames = frames
            self._duration_ms = duration_ms
            self._cursor = 0
            self._position_ms = 0.0
            self._speed = 1.0
            self._state = "ready"
            self._anchor_clock = 0.0
            self._anchor_position_ms = 0.0

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "mode": "deterministic-replay",
                "label": "Deterministic recording",
                "connected": self._identifier is not None,
                "can_receive": self._identifier is not None,
                "can_transmit": False,
                "description": "Frames come only from the selected finite recording; no actors or game logic are running.",
                "recording_id": self._identifier,
                "recording_title": self._title,
                "state": self._state,
                "cursor": self._cursor,
                "frame_count": len(self._frames),
                "position_ms": round(self._position_ms),
                "duration_ms": self._duration_ms,
                "speed": self._speed,
            }

    def play(self) -> list[CarrierFrame]:
        with self._lock:
            self._require_loaded()
            if self._state == "complete":
                raise TransportError("REPLAY_COMPLETE", "Reset the recording before playing it again.")
            if self._state == "playing":
                return self._advance_unlocked()
            self._state = "playing"
            self._anchor_clock = self._clock()
            self._anchor_position_ms = self._position_ms
            return self._advance_unlocked()

    def pause(self) -> list[CarrierFrame]:
        with self._lock:
            self._require_loaded()
            delivered = self._advance_unlocked()
            if self._state == "playing":
                self._state = "paused"
            return delivered

    def reset(self) -> list[CarrierFrame]:
        with self._lock:
            self._require_loaded()
            self._cursor = 0
            self._position_ms = 0.0
            self._state = "ready"
            self._anchor_clock = 0.0
            self._anchor_position_ms = 0.0
            return []

    def step(self) -> list[CarrierFrame]:
        with self._lock:
            self._require_loaded()
            if self._state == "playing":
                raise TransportError("REPLAY_PLAYING", "Pause the recording before stepping.")
            if self._cursor >= len(self._frames):
                raise TransportError("REPLAY_COMPLETE", "Reset the recording before stepping again.")
            item = self._frames[self._cursor]
            self._cursor += 1
            self._position_ms = float(item.at_ms)
            self._state = "complete" if self._cursor == len(self._frames) else "paused"
            return [item]

    def set_speed(self, speed: float) -> list[CarrierFrame]:
        if speed not in {0.25, 0.5, 1.0, 2.0, 4.0}:
            raise TransportError("REPLAY_SPEED", "Replay speed must be 0.25, 0.5, 1, 2, or 4.")
        with self._lock:
            self._require_loaded()
            delivered = self._advance_unlocked()
            self._speed = speed
            if self._state == "playing":
                self._anchor_clock = self._clock()
                self._anchor_position_ms = self._position_ms
            return delivered

    def poll(self) -> list[CarrierFrame]:
        with self._lock:
            return self._advance_unlocked()

    def _require_loaded(self) -> None:
        if self._identifier is None:
            raise TransportError("REPLAY_NOT_SELECTED", "Choose a recording before using playback controls.")

    def _advance_unlocked(self) -> list[CarrierFrame]:
        if self._state != "playing":
            return []
        elapsed_ms = max(0.0, self._clock() - self._anchor_clock) * 1000.0 * self._speed
        target = min(float(self._duration_ms), self._anchor_position_ms + elapsed_ms)
        self._position_ms = target
        delivered = []
        while self._cursor < len(self._frames) and self._frames[self._cursor].at_ms <= target + 1e-6:
            delivered.append(self._frames[self._cursor])
            self._cursor += 1
        if self._cursor == len(self._frames):
            self._position_ms = float(self._duration_ms)
            self._state = "complete"
        return delivered
