"""Application service for manual frame inspection."""

from __future__ import annotations

import threading
from collections import deque
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from .transport import InspectOnlyTransport
from .wire_adapter import WireAdapter


class WorkbenchService:
    """Coordinates read-only inspection and a small process-local journal."""

    def __init__(
        self,
        wire: WireAdapter | None = None,
        carrier: InspectOnlyTransport | None = None,
    ) -> None:
        self.wire = wire or WireAdapter()
        self.carrier = carrier or InspectOnlyTransport()
        self._entries: deque[dict[str, Any]] = deque(maxlen=100)
        self._lock = threading.Lock()

    def status(self) -> dict[str, Any]:
        with self._lock:
            count = len(self._entries)
        return {
            "ready": True,
            "workbench": "Packet Predator",
            "carrier": self.carrier.status(),
            "authority": self.wire.status(),
            "journal_entries": count,
        }

    def catalog(self) -> dict[str, Any]:
        return self.wire.catalog()

    def examples(self) -> dict[str, Any]:
        return self.wire.list_examples()

    def inspect(self, frame_text: str, mode: str, origin: str = "pasted frame") -> dict[str, Any]:
        result = self.wire.inspect(frame_text, mode)
        entry = {
            "id": uuid4().hex[:12],
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "origin": origin.strip()[:120] or "pasted frame",
            **result,
        }
        with self._lock:
            self._entries.appendleft(entry)
        return entry

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
                }
                for item in self._entries
            ]
        return {"entries": entries, "count": len(entries), "retention": "process-local, newest 100"}
