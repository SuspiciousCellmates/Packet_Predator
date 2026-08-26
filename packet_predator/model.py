"""Thread-safe process-local presentation model for the supported workbench."""

from __future__ import annotations

from collections import deque
from copy import deepcopy
import math
import statistics
import threading
import time
from typing import Any, Callable


class WorkbenchModel:
    """Own retained observations, receiver state, and change notifications."""

    def __init__(
        self,
        retention: int = 100,
        change_retention: int = 256,
        metric_retention: int = 1024,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if retention <= 0 or change_retention <= 0 or metric_retention <= 0:
            raise ValueError("Model retention limits must be positive integers.")
        self._entries: deque[dict[str, Any]] = deque(maxlen=retention)
        self._changes: deque[dict[str, Any]] = deque(maxlen=change_retention)
        self._metric_retention = metric_retention
        self._receiver_span_samples: dict[str, deque[float]] = {}
        self._receiver_span_discards: dict[str, int] = {}
        self._receiver_span_worst: dict[str, float] = {}
        self._condition = threading.Condition(threading.RLock())
        self._subscribers: set[Callable[[int], None]] = set()
        self._clock = clock
        self._revision = 0
        self._journal_sequence = 0
        self._journal_discarded_count = 0
        self._receiver = {
            "state": "stopped",
            "received_count": 0,
            "sent_count": 0,
            "invalid_count": 0,
            "fault_count": 0,
            "last_error": None,
            "changed_at_ms": 0,
            "service": {
                "span_sample_retention": metric_retention,
                "spans": {},
                "receiver_service_high_water_ms": None,
                "edge_or_frame_during_processing_count": 0,
            },
        }

    def publish(self, entry: dict[str, Any]) -> dict[str, Any]:
        """Retain an immutable observation snapshot and notify subscribers."""
        with self._condition:
            stored = deepcopy(entry)
            stored["journal_sequence"] = self._journal_sequence
            self._journal_sequence += 1
            if len(self._entries) == self._entries.maxlen:
                self._journal_discarded_count += 1
            self._entries.appendleft(stored)

            capture = stored.get("capture") or {}
            if capture.get("transport") == "nrf905":
                if capture.get("direction") == "received":
                    self._receiver["received_count"] += 1
                elif capture.get("direction") == "sent":
                    self._receiver["sent_count"] += 1
                if stored.get("inspection_error"):
                    self._receiver["invalid_count"] += 1

            self._record_change_unlocked("observation", stored["id"])
            return deepcopy(stored)

    def set_receiver_state(
        self,
        state: str,
        error: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Publish a receiver lifecycle change when its visible state changed."""
        with self._condition:
            normalized_error = deepcopy(error)
            if (
                self._receiver["state"] == state
                and self._receiver["last_error"] == normalized_error
            ):
                return self._receiver_unlocked()
            self._receiver["state"] = state
            self._receiver["last_error"] = normalized_error
            if state == "faulted":
                self._receiver["fault_count"] += 1
            self._receiver["changed_at_ms"] = round(self._clock() * 1000)
            self._record_change_unlocked("receiver")
            return self._receiver_unlocked()

    def record_receiver_metrics(
        self,
        spans_ms: dict[str, float | int | None] | None = None,
        *,
        edge_or_frame_during_processing: int = 0,
    ) -> dict[str, Any]:
        """Add bounded timing samples and explicit receiver-service activity."""

        if edge_or_frame_during_processing < 0:
            raise ValueError("Receiver activity increments cannot be negative.")
        normalized: dict[str, float] = {}
        for name, value in (spans_ms or {}).items():
            if value is None:
                continue
            sample = float(value)
            if not math.isfinite(sample) or sample < 0:
                raise ValueError(f"Receiver timing sample {name!r} must be finite and non-negative.")
            normalized[name] = round(sample, 3)

        with self._condition:
            for name, sample in normalized.items():
                samples = self._receiver_span_samples.setdefault(
                    name,
                    deque(maxlen=self._metric_retention),
                )
                if len(samples) == samples.maxlen:
                    self._receiver_span_discards[name] = (
                        self._receiver_span_discards.get(name, 0) + 1
                    )
                samples.append(sample)
                self._receiver_span_worst[name] = max(
                    sample,
                    self._receiver_span_worst.get(name, sample),
                )

            service = self._receiver["service"]
            service["edge_or_frame_during_processing_count"] += (
                edge_or_frame_during_processing
            )
            service["receiver_service_high_water_ms"] = self._receiver_span_worst.get(
                "receiver_service_ms"
            )
            if normalized or edge_or_frame_during_processing:
                self._record_change_unlocked("receiver")
            return deepcopy(self._receiver_unlocked()["service"])

    def journal(self) -> dict[str, Any]:
        with self._condition:
            return self._journal_unlocked()

    def inspection(self, identifier: str) -> dict[str, Any] | None:
        with self._condition:
            item = next((item for item in self._entries if item["id"] == identifier), None)
            return deepcopy(item) if item is not None else None

    def snapshot(self) -> dict[str, Any]:
        with self._condition:
            return {
                "revision": self._revision,
                "receiver": self._receiver_unlocked(),
                "journal": self._journal_unlocked(),
                "latest": deepcopy(self._entries[0]) if self._entries else None,
            }

    def changes_since(self, revision: int) -> dict[str, Any]:
        with self._condition:
            return self._changes_since_unlocked(revision)

    def subscribe(self, callback: Callable[[int], None]) -> Callable[[], None]:
        """Register a non-blocking revision notification callback."""
        with self._condition:
            self._subscribers.add(callback)

        def unsubscribe() -> None:
            with self._condition:
                self._subscribers.discard(callback)

        return unsubscribe

    def wait_for_changes(self, revision: int, timeout_s: float) -> dict[str, Any]:
        """Block a web subscriber without holding up a publisher."""
        with self._condition:
            if self._revision == revision:
                self._condition.wait_for(
                    lambda: self._revision > revision,
                    timeout=max(0.0, timeout_s),
                )
            return self._changes_since_unlocked(revision)

    def _record_change_unlocked(self, kind: str, identifier: str | None = None) -> None:
        self._revision += 1
        change = {"revision": self._revision, "kind": kind}
        if identifier is not None:
            change["observation_id"] = identifier
        self._changes.append(change)
        self._condition.notify_all()
        for subscriber in tuple(self._subscribers):
            try:
                subscriber(self._revision)
            except Exception:
                # A browser notification must never fail a model publisher.
                continue

    def _changes_since_unlocked(self, revision: int) -> dict[str, Any]:
        if revision < 0:
            revision = 0
        if revision > self._revision:
            return {
                "revision": self._revision,
                "resync": True,
                "changes": [],
            }
        oldest_replayable = self._changes[0]["revision"] - 1 if self._changes else self._revision
        if revision < oldest_replayable:
            return {
                "revision": self._revision,
                "resync": True,
                "changes": [],
            }
        return {
            "revision": self._revision,
            "resync": False,
            "changes": [
                deepcopy(change) for change in self._changes if change["revision"] > revision
            ],
        }

    def _journal_unlocked(self) -> dict[str, Any]:
        entries = [self._summary(item) for item in self._entries]
        return {
            "entries": entries,
            "count": len(entries),
            "retention": f"process-local, newest {self._entries.maxlen}",
            "first_retained_journal_sequence": (
                self._entries[-1]["journal_sequence"] if self._entries else None
            ),
            "latest_journal_sequence": (
                self._entries[0]["journal_sequence"] if self._entries else None
            ),
            "discarded_count": self._journal_discarded_count,
        }

    def _receiver_spans_unlocked(self) -> dict[str, dict[str, float | int]]:
        summaries: dict[str, dict[str, float | int]] = {}
        for name, samples in self._receiver_span_samples.items():
            ordered = sorted(samples)
            discarded = self._receiver_span_discards.get(name, 0)
            summaries[name] = {
                "median_ms": round(statistics.median(ordered), 3),
                "p95_ms": self._nearest_rank(ordered, 0.95),
                "p99_ms": self._nearest_rank(ordered, 0.99),
                "worst_ms": self._receiver_span_worst[name],
                "sample_count": len(ordered),
                "discarded_count": discarded,
                "total_observed_count": len(ordered) + discarded,
            }
        return summaries

    def _receiver_unlocked(self) -> dict[str, Any]:
        receiver = deepcopy(self._receiver)
        receiver["service"]["spans"] = self._receiver_spans_unlocked()
        return receiver

    @staticmethod
    def _nearest_rank(ordered: list[float], proportion: float) -> float:
        index = max(0, math.ceil(proportion * len(ordered)) - 1)
        return ordered[index]

    @staticmethod
    def _summary(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": item["id"],
            "journal_sequence": item["journal_sequence"],
            "observed_at": item["observed_at"],
            "origin": item["origin"],
            "title": item["title"],
            "summary": item["summary"],
            "received_frame_hex": item["received_frame_hex"],
            "family": deepcopy(item["family"]),
            "capture": deepcopy(item.get("capture")),
            "inspection_error": deepcopy(item.get("inspection_error")),
        }
