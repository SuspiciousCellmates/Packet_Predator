"""Validation and resolution of finite deterministic recording data."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .transport import CarrierFrame


class RecordingError(RuntimeError):
    """A recording file is malformed or cannot be resolved."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.detail}


@dataclass(frozen=True)
class Recording:
    identifier: str
    title: str
    description: str
    duration_ms: int
    frames: tuple[CarrierFrame, ...]
    schedule: tuple[dict[str, Any], ...]

    def summary(self) -> dict[str, Any]:
        return {
            "id": self.identifier,
            "title": self.title,
            "description": self.description,
            "duration_ms": self.duration_ms,
            "frame_count": len(self.frames),
            "schedule": list(self.schedule),
        }


class RecordingCatalog:
    """Load static recording JSON and resolve its released example references."""

    def __init__(
        self,
        root: Path,
        authority_version: str,
        resolver: Callable[..., dict[str, Any]],
    ) -> None:
        self.root = root.resolve()
        self.authority_version = authority_version
        self.resolver = resolver
        self._recordings = self._load_all()

    def list(self) -> list[dict[str, Any]]:
        return [item.summary() for item in self._recordings.values()]

    def get(self, identifier: str) -> Recording:
        item = self._recordings.get(identifier)
        if item is None:
            raise RecordingError("RECORDING_NOT_FOUND", f"No recording is named {identifier!r}.")
        return item

    def _load_all(self) -> dict[str, Recording]:
        paths = sorted(self.root.glob("*.json")) if self.root.is_dir() else []
        if not paths:
            raise RecordingError("RECORDING_CATALOG_EMPTY", f"No recording JSON files exist in {self.root}.")
        result = {}
        for path in paths:
            item = self._load(path)
            if item.identifier in result:
                raise RecordingError("RECORDING_ID_DUPLICATE", f"Duplicate recording id {item.identifier!r}.")
            result[item.identifier] = item
        return result

    def _load(self, path: Path) -> Recording:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RecordingError("RECORDING_JSON", f"Cannot read {path}: {exc}") from exc
        if not isinstance(data, dict):
            raise RecordingError("RECORDING_SHAPE", f"{path}: root must be an object.")
        required = {
            "schema_version",
            "id",
            "title",
            "description",
            "authority_version",
            "frame_mode",
            "duration_ms",
            "entries",
        }
        if set(data) != required:
            raise RecordingError(
                "RECORDING_FIELDS",
                f"{path}: expected fields {sorted(required)}, found {sorted(data)}.",
            )
        if data["schema_version"] != 1:
            raise RecordingError("RECORDING_SCHEMA", f"{path}: schema_version must be 1.")
        identifier = data["id"]
        if not isinstance(identifier, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", identifier):
            raise RecordingError("RECORDING_ID", f"{path}: id must be lowercase kebab-case.")
        if path.stem != identifier:
            raise RecordingError("RECORDING_ID", f"{path}: filename must match id {identifier!r}.")
        for key in ("title", "description"):
            if not isinstance(data[key], str) or not data[key].strip():
                raise RecordingError("RECORDING_TEXT", f"{path}: {key} must be non-empty text.")
        if data["authority_version"] != self.authority_version:
            raise RecordingError(
                "RECORDING_AUTHORITY_VERSION",
                f"{path}: expects authority {data['authority_version']!r}, loaded {self.authority_version!r}.",
            )
        if data["frame_mode"] not in {"logical", "fixed"}:
            raise RecordingError("RECORDING_MODE", f"{path}: frame_mode must be logical or fixed.")
        duration_ms = data["duration_ms"]
        if not isinstance(duration_ms, int) or isinstance(duration_ms, bool) or not 0 <= duration_ms <= 300_000:
            raise RecordingError("RECORDING_DURATION", f"{path}: duration_ms must be an integer from 0 to 300000.")
        entries = data["entries"]
        if not isinstance(entries, list) or not entries:
            raise RecordingError("RECORDING_ENTRIES", f"{path}: entries must be a non-empty array.")

        frames = []
        schedule = []
        previous_at = -1
        entry_fields = {"at_ms", "fixture_id", "source", "destination", "direction", "note"}
        for sequence, entry in enumerate(entries):
            if not isinstance(entry, dict) or set(entry) != entry_fields:
                raise RecordingError(
                    "RECORDING_ENTRY_FIELDS",
                    f"{path}: entry {sequence} must contain exactly {sorted(entry_fields)}.",
                )
            at_ms = entry["at_ms"]
            if not isinstance(at_ms, int) or isinstance(at_ms, bool) or at_ms < previous_at:
                raise RecordingError(
                    "RECORDING_ORDER",
                    f"{path}: entry {sequence} at_ms must be an integer in nondecreasing order.",
                )
            if at_ms > duration_ms:
                raise RecordingError("RECORDING_DURATION", f"{path}: entry {sequence} exceeds duration_ms.")
            if entry["direction"] not in {"received", "sent"}:
                raise RecordingError("RECORDING_DIRECTION", f"{path}: entry {sequence} direction is invalid.")
            if not isinstance(entry["note"], str) or not entry["note"].strip():
                raise RecordingError("RECORDING_TEXT", f"{path}: entry {sequence} needs a note.")
            for address_key in ("source", "destination"):
                value = entry[address_key]
                if value is not None and (
                    not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 255
                ):
                    raise RecordingError(
                        "RECORDING_ADDRESS",
                        f"{path}: entry {sequence} {address_key} must be null or a u8 integer.",
                    )
            try:
                resolved = self.resolver(
                    entry["fixture_id"],
                    data["frame_mode"],
                    entry["source"],
                    entry["destination"],
                )
            except Exception as exc:
                raise RecordingError(
                    "RECORDING_FRAME",
                    f"{path}: entry {sequence} cannot resolve {entry['fixture_id']!r}: {exc}",
                ) from exc
            frames.append(
                CarrierFrame(
                    sequence=sequence,
                    at_ms=at_ms,
                    direction=entry["direction"],
                    frame=bytes.fromhex(resolved["frame_hex"]),
                    frame_mode=resolved["frame_mode"],
                    recording_id=identifier,
                    fixture_id=entry["fixture_id"],
                    note=entry["note"],
                )
            )
            schedule.append(
                {
                    "sequence": sequence,
                    "at_ms": at_ms,
                    "direction": entry["direction"],
                    "fixture_id": entry["fixture_id"],
                    "display_name": resolved["display_name"],
                    "source": resolved["source"],
                    "source_label": resolved["source_label"],
                    "destination": resolved["destination"],
                    "destination_label": resolved["destination_label"],
                    "note": entry["note"],
                }
            )
            previous_at = at_ms

        return Recording(
            identifier=identifier,
            title=data["title"].strip(),
            description=data["description"].strip(),
            duration_ms=duration_ms,
            frames=tuple(frames),
            schedule=tuple(schedule),
        )
