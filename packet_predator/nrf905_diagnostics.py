"""Command-line two-bench validation for the nRF905 physical adapter."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from .adapters.nrf905 import Nrf905Error
from .nrf905_profile import Nrf905ProfileError, load_nrf905_profile
from .nrf905_transport import open_nrf905_transport
from .wire_adapter import AuthorityError, InspectionError, WireAdapter


def _print(value: dict[str, Any]) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def _fixed_example(wire: WireAdapter, identifier: str) -> tuple[bytes, dict[str, Any]]:
    resolved = wire.resolve_example(identifier, "fixed")
    frame = bytes.fromhex(resolved["frame_hex"])
    return frame, resolved


def run(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Probe one nRF905 or validate an exact released frame between two Packet Predator benches."
    )
    parser.add_argument("--profile", type=Path, required=True, help="Path to a local nRF905 JSON profile")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("profile", help="Validate and show the profile without opening hardware")
    subparsers.add_parser("probe", help="Open SPI/GPIO and verify exact configuration readback")
    send = subparsers.add_parser("send", help="Transmit one released 32-byte example")
    send.add_argument("--fixture", required=True, help="Released fixture id, such as v1-controller-beacon")
    receive = subparsers.add_parser("receive", help="Wait for one exact released 32-byte example")
    receive.add_argument("--expect-fixture", required=True, help="Released fixture id expected over the air")
    receive.add_argument("--timeout", type=float, default=30.0, help="Seconds to wait (default: 30)")
    args = parser.parse_args(arguments)

    transport = None
    try:
        profile = load_nrf905_profile(args.profile)
        if args.command == "profile":
            _print({"ok": True, "stage": "profile", "profile": profile.public_summary()})
            return 0

        wire = WireAdapter()
        transport = open_nrf905_transport(profile)
        if args.command == "probe":
            _print({"ok": True, "stage": "probe", "carrier": transport.status()})
            return 0

        if args.command == "send":
            frame, resolved = _fixed_example(wire, args.fixture)
            sent = transport.send(frame)
            _print(
                {
                    "ok": True,
                    "stage": "over-air-send",
                    "fixture": resolved,
                    "frame_hex": sent.frame.hex(),
                    "note": sent.note,
                }
            )
            return 0

        if args.timeout <= 0 or args.timeout > 600:
            raise Nrf905ProfileError("RECEIVE_TIMEOUT", "--timeout must be greater than 0 and no more than 600 seconds.")
        expected, resolved = _fixed_example(wire, args.expect_fixture)
        deadline = time.monotonic() + args.timeout
        while time.monotonic() < deadline:
            received = transport.poll()
            if received:
                actual = received[0].frame
                if actual != expected:
                    _print(
                        {
                            "ok": False,
                            "stage": "over-air-receive",
                            "error": "RECEIVED_FRAME_MISMATCH",
                            "expected_fixture": args.expect_fixture,
                            "expected_hex": expected.hex(),
                            "received_hex": actual.hex(),
                        }
                    )
                    return 2
                decoded = wire.inspect(actual.hex(), "fixed")
                _print(
                    {
                        "ok": True,
                        "stage": "over-air-receive",
                        "fixture": resolved,
                        "frame_hex": actual.hex(),
                        "decoded_name": decoded["meaning"]["name"],
                    }
                )
                return 0
            time.sleep(0.010)
        _print(
            {
                "ok": False,
                "stage": "over-air-receive",
                "error": "RECEIVE_TIMEOUT",
                "message": f"No complete frame arrived within {args.timeout:g} seconds.",
            }
        )
        return 2
    except (Nrf905Error, Nrf905ProfileError, AuthorityError, InspectionError) as exc:
        code = getattr(exc, "code", exc.__class__.__name__)
        _print({"ok": False, "error": code, "message": str(exc)})
        return 2
    except Exception as exc:
        if hasattr(exc, "as_dict"):
            _print({"ok": False, "error": exc.as_dict()})
            return 2
        raise
    finally:
        if transport is not None:
            transport.close()


def main() -> int:
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
