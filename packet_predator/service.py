"""Application service for manual inspection and deterministic recording replay."""

from __future__ import annotations

import threading
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .replay import Recording, RecordingCatalog
from .transport import CarrierFrame, DeterministicReplayTransport, InspectOnlyTransport, TransportError
from .wire_adapter import WireAdapter


class WorkbenchService:
    """Coordinate wire inspection, explicit replay, and a process-local capture journal."""

    def __init__(
        self,
        wire: WireAdapter | None = None,
        carrier: InspectOnlyTransport | None = None,
        replay_carrier: DeterministicReplayTransport | None = None,
        recording_root: Path | None = None,
    ) -> None:
        self.wire = wire or WireAdapter()
        self.carrier = carrier or InspectOnlyTransport()
        self.replay_carrier = replay_carrier or DeterministicReplayTransport()
        root = recording_root or Path(__file__).resolve().parents[1] / "recordings"
        self.recordings = RecordingCatalog(root, self.wire.version, self.wire.resolve_example)
        self._active_recording: Recording | None = None
        self._entries: deque[dict[str, Any]] = deque(maxlen=100)
        self._lock = threading.RLock()

    def status(self) -> dict[str, Any]:
        with self._lock:
            count = len(self._entries)
            active = self._active_recording is not None
        return {
            "ready": True,
            "workbench": "Packet Predator",
            "carrier": self.replay_carrier.status() if active else self.carrier.status(),
            "authority": self.wire.status(),
            "journal_entries": count,
            "replay_available": True,
            "recording_count": len(self.recordings.list()),
        }

    def catalog(self) -> dict[str, Any]:
        return self.wire.catalog()

    def examples(self) -> dict[str, Any]:
        return self.wire.list_examples()

    def inspect(self, frame_text: str, mode: str, origin: str = "pasted frame") -> dict[str, Any]:
        result = self.wire.inspect(frame_text, mode)
        return self._store(result, origin.strip()[:120] or "pasted frame", None)

    def replay_catalog(self) -> dict[str, Any]:
        return {
            "recordings": self.recordings.list(),
            "count": len(self.recordings.list()),
            "active": self._active_recording.summary() if self._active_recording else None,
            "carrier": self.replay_carrier.status(),
        }

    def select_replay(self, identifier: str) -> dict[str, Any]:
        item = self.recordings.get(identifier)
        self.replay_carrier.load(item.identifier, item.title, item.duration_ms, item.frames)
        with self._lock:
            self._active_recording = item
        return self._replay_response([])

    def control_replay(self, action: str, speed: float | None = None) -> dict[str, Any]:
        delivered = []
        if speed is not None:
            delivered.extend(self.replay_carrier.set_speed(speed))
        if action == "play":
            delivered.extend(self.replay_carrier.play())
        elif action == "pause":
            delivered.extend(self.replay_carrier.pause())
        elif action == "step":
            delivered.extend(self.replay_carrier.step())
        elif action == "reset":
            delivered.extend(self.replay_carrier.reset())
        elif action == "speed":
            if speed is None:
                raise TransportError("REPLAY_SPEED", "Choose a speed before applying it.")
        else:
            raise TransportError("REPLAY_ACTION", f"Unsupported replay action {action!r}.")
        return self._replay_response(delivered)

    def replay_state(self) -> dict[str, Any]:
        return self._replay_response(self.replay_carrier.poll())

    def journal(self) -> dict[str, Any]:
        with self._lock:
            entries = [
                {
                    "id": item["id"],
                    "observed_at": item["observed_at"],
                    "origin": item["origin"],
                    "title": item["title"],
                    "summary": item["summary"],
                    "received_frame_hex": item["received_frame_hex"],
                    "family": item["family"],
                    "capture": item.get("capture"),
                }
                for item in self._entries
            ]
        return {"entries": entries, "count": len(entries), "retention": "process-local, newest 100"}

    def inspection(self, identifier: str) -> dict[str, Any] | None:
        with self._lock:
            return next((dict(item) for item in self._entries if item["id"] == identifier), None)

    def _replay_response(self, frames: list[CarrierFrame]) -> dict[str, Any]:
        delivered = [self._consume(item) for item in frames]
        with self._lock:
            active = self._active_recording.summary() if self._active_recording else None
        return {
            "carrier": self.replay_carrier.status(),
            "recording": active,
            "delivered": delivered,
        }

    def _consume(self, item: CarrierFrame) -> dict[str, Any]:
        result = self.wire.inspect(item.frame.hex(), item.frame_mode)
        capture = {
            "transport": "deterministic-replay",
            "recording_id": item.recording_id,
            "sequence": item.sequence,
            "scheduled_at_ms": item.at_ms,
            "direction": item.direction,
            "fixture_id": item.fixture_id,
            "note": item.note,
        }
        return self._store(result, f"recording: {item.recording_id}", capture)

    def _store(
        self,
        result: dict[str, Any],
        origin: str,
        capture: dict[str, Any] | None,
    ) -> dict[str, Any]:
        entry = {
            "id": uuid4().hex[:12],
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "origin": origin,
            "capture": capture,
            **result,
        }
        with self._lock:
            self._entries.appendleft(entry)
        return entry
