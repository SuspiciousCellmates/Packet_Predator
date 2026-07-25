"""Application service for manual inspection and deterministic recording replay."""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from .model import WorkbenchModel
from .replay import Recording, RecordingCatalog
from .nrf905_transport import Nrf905Transport
from .receiver import PhysicalReceiver
from .transport import CarrierFrame, DeterministicReplayTransport, InspectOnlyTransport, ReceiveTransport, TransportError
from .wire_adapter import WireAdapter


class WorkbenchService:
    """Coordinate wire inspection, explicit replay, and a process-local capture journal."""

    def __init__(
        self,
        wire: WireAdapter | None = None,
        carrier: ReceiveTransport | None = None,
        replay_carrier: DeterministicReplayTransport | None = None,
        recording_root: Path | None = None,
        model: WorkbenchModel | None = None,
    ) -> None:
        self.wire = wire or WireAdapter()
        self.carrier = carrier or InspectOnlyTransport()
        self.replay_carrier = replay_carrier or DeterministicReplayTransport()
        self.model = model or WorkbenchModel()
        root = recording_root or Path(__file__).resolve().parents[1] / "recordings"
        self.recordings = RecordingCatalog(root, self.wire.version, self.wire.resolve_example)
        self._active_recording: Recording | None = None
        self._lock = threading.RLock()
        self._closed = False
        self._receiver = (
            PhysicalReceiver(self.carrier, self.consume_physical, self.model.set_receiver_state)
            if isinstance(self.carrier, Nrf905Transport)
            else None
        )

    def start(self) -> None:
        with self._lock:
            if self._closed:
                raise RuntimeError("A closed workbench service cannot be restarted.")
            receiver = self._receiver
        if receiver is not None:
            receiver.start()

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            receiver = self._receiver
        if receiver is not None:
            receiver.stop()
            self.carrier.close()
        with self._lock:
            self._closed = True

    def status(self) -> dict[str, Any]:
        with self._lock:
            active = self._active_recording is not None
        snapshot = self.model.snapshot()
        return {
            "ready": True,
            "workbench": "Packet Predator",
            "carrier": self.replay_carrier.status() if active else self.carrier.status(),
            "authority": self.wire.status(),
            "journal_entries": snapshot["journal"]["count"],
            "replay_available": True,
            "recording_count": len(self.recordings.list()),
            "physical_adapter": self.carrier.status() if isinstance(self.carrier, Nrf905Transport) else None,
            "receiver": snapshot["receiver"],
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

    def transmit(self, frame_text: str, mode: str, confirmed: bool) -> dict[str, Any]:
        if not confirmed:
            raise TransportError(
                "TRANSMIT_CONFIRMATION_REQUIRED",
                "Confirm this deliberate RF transmission in the workbench before sending.",
            )
        carrier = self._physical_carrier()
        frame = self.wire.fixed_frame(frame_text, mode)
        receiver_running = self._receiver is not None and self._receiver.running
        if receiver_running:
            self.model.set_receiver_state("transmitting")
        try:
            delivered = self.consume_physical(carrier.send(frame))
        finally:
            if receiver_running:
                self.model.set_receiver_state("listening")
        return {"carrier": carrier.status(), "delivered": [delivered]}

    def journal(self) -> dict[str, Any]:
        return self.model.journal()

    def inspection(self, identifier: str) -> dict[str, Any] | None:
        return self.model.inspection(identifier)

    def model_state(self) -> dict[str, Any]:
        snapshot = self.model.snapshot()
        snapshot["physical_adapter"] = (
            self.carrier.status() if isinstance(self.carrier, Nrf905Transport) else None
        )
        return snapshot

    def model_changes(self, revision: int) -> dict[str, Any]:
        return self.model.changes_since(revision)

    def subscribe_to_model(self, callback: Callable[[int], None]) -> Callable[[], None]:
        return self.model.subscribe(callback)

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

    def consume_physical(self, item: CarrierFrame) -> dict[str, Any]:
        carrier = self._physical_carrier()
        capture = {
            "transport": "nrf905",
            "profile_id": carrier.profile.identifier,
            "sequence": item.sequence,
            "observed_at_ms": item.at_ms,
            "direction": item.direction,
            "note": item.note,
        }
        try:
            result = self.wire.inspect(item.frame.hex(), "fixed")
        except self.wire.codec_error as exc:
            result = {
                "title": "Invalid physical frame",
                "summary": exc.message,
                "received_frame_hex": item.frame.hex(),
                "received_bytes": len(item.frame),
                "family": {"id": "invalid", "label": "Invalid frame"},
                "inspection_error": exc.as_dict(),
            }
        return self._store(result, f"nrf905: {carrier.profile.identifier}", capture)

    def _physical_carrier(self) -> Nrf905Transport:
        if not isinstance(self.carrier, Nrf905Transport):
            raise TransportError(
                "PHYSICAL_ADAPTER_UNAVAILABLE",
                "Start Packet Predator with an explicit nRF905 adapter profile first.",
            )
        return self.carrier

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
        return self.model.publish(entry)
