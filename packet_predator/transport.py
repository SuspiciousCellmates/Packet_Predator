"""Explicit carrier boundary for the supported workbench."""

from __future__ import annotations

from typing import Any


class InspectOnlyTransport:
    """A truthful no-hardware carrier: it can neither receive nor transmit."""

    def status(self) -> dict[str, Any]:
        return {
            "mode": "inspect-only",
            "label": "Local inspection",
            "connected": False,
            "can_receive": False,
            "can_transmit": False,
            "description": "No radio or fake nodes are active. Frames come only from examples or text you paste.",
        }
