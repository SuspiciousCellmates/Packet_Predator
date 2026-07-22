"""Read-only adapter over the sibling Protocol Contract reference codec."""

from __future__ import annotations

import importlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any


class AuthorityError(RuntimeError):
    """The released sibling authority cannot be found or loaded."""


class InspectionError(ValueError):
    """User-supplied frame text cannot be passed to the reference codec."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.detail}


def default_authority_root() -> Path:
    configured = os.environ.get("PACKET_PREDATOR_CONTRACT_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[2] / "Protocol_Contract"


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AuthorityError(f"Cannot read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise AuthorityError(f"{path} must contain a JSON object")
    return value


def _normalise_hex(value: str) -> tuple[str, bytes]:
    if not isinstance(value, str):
        raise InspectionError("HEX_TYPE", "Frame input must be hexadecimal text.")
    compact = re.sub(r"[\s:_-]+", "", value.strip())
    if compact.lower().startswith("0x"):
        compact = compact[2:]
    if not compact:
        raise InspectionError("HEX_EMPTY", "Paste a frame or choose an example first.")
    if len(compact) % 2:
        raise InspectionError("HEX_ODD_LENGTH", "Hexadecimal input needs two characters per byte.")
    if not re.fullmatch(r"[0-9a-fA-F]+", compact):
        raise InspectionError("HEX_INVALID", "Frame input contains a non-hexadecimal character.")
    return compact.lower(), bytes.fromhex(compact)


class WireAdapter:
    """Presentation-safe access to the released registry, fixtures, and decoder."""

    def __init__(self, authority_root: Path | None = None) -> None:
        self.authority_root = (authority_root or default_authority_root()).resolve()
        registry_path = self.authority_root / "registry/v1.json"
        examples_path = self.authority_root / "fixtures/v1/all-message-types.json"
        package_path = self.authority_root / "reference_codec/__init__.py"
        missing = [path for path in (registry_path, examples_path, package_path) if not path.is_file()]
        if missing:
            joined = ", ".join(str(path) for path in missing)
            raise AuthorityError(
                "The sibling Protocol Contract 1.0.1 checkout is incomplete. Missing: " + joined
            )

        authority_text = str(self.authority_root)
        if authority_text not in sys.path:
            sys.path.insert(0, authority_text)
        codec_package = importlib.import_module("reference_codec")
        loaded_from = Path(codec_package.__file__).resolve()
        if self.authority_root not in loaded_from.parents:
            raise AuthorityError(
                f"reference_codec resolved to {loaded_from}, outside {self.authority_root}"
            )

        self.registry_data = _read_object(registry_path)
        self.example_data = _read_object(examples_path)
        if self.registry_data.get("version") != "1.0.1":
            raise AuthorityError(
                "Packet Predator currently expects released Protocol Contract 1.0.1; "
                f"found {self.registry_data.get('version')!r}."
            )
        if self.registry_data.get("status") != "stable":
            raise AuthorityError("Packet Predator requires a stable released registry.")
        if self.example_data.get("version") != self.registry_data["version"]:
            raise AuthorityError("Registry and conformance example versions do not match.")

        self.codec_error = codec_package.CodecError
        self.codec = codec_package.V1Codec.from_path(registry_path)
        self.definitions = {
            item["value"]: item for item in self.registry_data.get("messages", [])
        }
        self.examples = list(self.example_data.get("fixtures", []))
        self.examples_by_id = {item["id"]: item for item in self.examples}
        if len(self.examples_by_id) != len(self.examples):
            raise AuthorityError("Conformance example identifiers must be unique.")

    @property
    def version(self) -> str:
        return str(self.registry_data["version"])

    def status(self) -> dict[str, Any]:
        return {
            "ready": True,
            "authority_version": self.version,
            "authority_status": self.registry_data["status"],
            "authority_path": str(self.authority_root),
            "wire_generation": self.registry_data["wire_generation"]["value"],
            "example_count": len(self.examples),
        }

    def catalog(self) -> dict[str, Any]:
        groups: dict[str, list[dict[str, Any]]] = {}
        for definition in self.registry_data["messages"]:
            family = self._family(definition["value"])
            groups.setdefault(family["key"], []).append(
                {
                    "value": definition["value"],
                    "hex_value": f"0x{definition['value']:02X}",
                    "name": definition["name"],
                    "display_name": self._display_name(definition["name"]),
                    "family": family,
                    "producers": definition["producers"],
                    "consumers": definition["consumers"],
                    "delivery": definition["delivery"],
                    "revision_scope": definition["revision_scope"],
                    "minimum_body_bytes": definition["payload"]["min_size"],
                    "maximum_body_bytes": definition["payload"]["max_size"],
                }
            )
        return {
            "authority_version": self.version,
            "message_count": len(self.definitions),
            "families": [
                {
                    "key": key,
                    "label": values[0]["family"]["label"],
                    "items": values,
                }
                for key, values in groups.items()
            ],
        }

    def list_examples(self) -> dict[str, Any]:
        rows = []
        for item in self.examples:
            meta = item["header"]
            family = self._family(meta["message_type"])
            rows.append(
                {
                    "id": item["id"],
                    "name": item["message_name"],
                    "display_name": self._display_name(item["message_name"]),
                    "family": family,
                    "frame_hex": item["frame_hex"],
                    "padded_frame_hex": item["padded_frame_hex"],
                    "logical_bytes": len(item["frame_hex"]) // 2,
                    "source": meta["source"],
                    "source_label": self._address_label(meta["source"], False),
                    "destination": meta["destination"],
                    "destination_label": self._address_label(meta["destination"], True),
                    "known_issues": item["known_issues"],
                    "provenance": item["provenance"],
                }
            )
        return {
            "authority_version": self.version,
            "example_count": len(rows),
            "examples": rows,
        }

    def inspect(self, frame_text: str, mode: str = "auto") -> dict[str, Any]:
        compact, raw = _normalise_hex(frame_text)
        decoded = self.codec.decode_frame(raw, mode=mode).as_dict()
        meta = decoded["header"]
        kind = decoded["message"]
        definition = self.definitions[meta["message_type"]]
        family = self._family(meta["message_type"])
        source_label = self._address_label(meta["source"], False)
        destination_label = self._address_label(meta["destination"], True)
        logical_size = len(decoded["logical_frame_hex"]) // 2

        return {
            "authority_version": self.version,
            "received_frame_hex": compact,
            "received_bytes": len(raw),
            "logical_bytes": logical_size,
            "padding_bytes": decoded["padding_length"],
            "representation": "fixed 32-byte adapter frame" if decoded["padding_length"] else "logical frame",
            "family": family,
            "title": self._display_name(kind["name"]),
            "summary": f"{source_label} sent {self._display_name(kind['name']).lower()} to {destination_label}.",
            "route": {
                "source": meta["source"],
                "source_label": source_label,
                "destination": meta["destination"],
                "destination_label": destination_label,
                "producers": definition["producers"],
                "consumers": definition["consumers"],
            },
            "envelope": {
                **meta,
                "message_type_hex": f"0x{meta['message_type']:02X}",
            },
            "meaning": {
                **kind,
                "delivery_label": self._display_name(kind["delivery"]),
                "revision_label": self._display_name(kind["revision_scope"]),
            },
            "body": decoded["payload"],
            "annotations": decoded["annotations"],
            "field_rows": self._field_rows(definition, decoded),
            "byte_rows": self._byte_rows(raw, logical_size),
        }

    def resolve_example(
        self,
        identifier: str,
        mode: str = "logical",
        source: int | None = None,
        destination: int | None = None,
    ) -> dict[str, Any]:
        item = self.examples_by_id.get(identifier)
        if item is None:
            raise InspectionError("EXAMPLE_NOT_FOUND", f"No released example is named {identifier!r}.")
        if mode not in {"logical", "fixed"}:
            raise InspectionError("EXAMPLE_MODE", "Recording examples must be logical or fixed frames.")

        decoded = self.codec.decode_frame(bytes.fromhex(item["frame_hex"]), mode="logical")
        resolved_source = decoded.source if source is None else source
        resolved_destination = decoded.destination if destination is None else destination
        raw = self.codec.encode_frame(
            decoded.message_name,
            resolved_source,
            resolved_destination,
            decoded.payload,
            padded=mode == "fixed",
        )
        return {
            "fixture_id": identifier,
            "name": decoded.message_name,
            "display_name": self._display_name(decoded.message_name),
            "frame_hex": raw.hex(),
            "frame_mode": mode,
            "source": resolved_source,
            "source_label": self._address_label(resolved_source, False),
            "destination": resolved_destination,
            "destination_label": self._address_label(resolved_destination, True),
        }

    def fixed_frame(self, frame_text: str, mode: str = "auto") -> bytes:
        """Validate through the released codec and apply its declared fixed-adapter padding."""

        compact, raw = _normalise_hex(frame_text)
        decoded = self.codec.decode_frame(raw, mode=mode)
        logical = decoded.logical_frame
        size = int(self.registry_data["envelope"]["fixed_adapter_frame_size"])
        padding = int(self.registry_data["envelope"]["fixed_adapter_padding_byte"])
        if len(logical) > size:
            raise InspectionError(
                "FIXED_FRAME_TOO_LONG", f"The released adapter frame limit is {size} bytes."
            )
        return logical + bytes([padding]) * (size - len(logical))

    def _field_rows(self, definition: dict[str, Any], decoded: dict[str, Any]) -> list[dict[str, Any]]:
        rows = []
        offset = int(self.registry_data["envelope"]["header_size"])
        for field in definition["payload"]["fields"]:
            name = field["name"]
            value = decoded["payload"][name]
            annotation = decoded["annotations"].get(name)
            primitive = self.registry_data["primitive_types"][field["type"]]
            size = primitive.get("size")
            if size is None:
                size = len(value) // 2
            rows.append(
                {
                    "name": name,
                    "label": self._display_name(name),
                    "offset": offset,
                    "size": size,
                    "type": field["type"],
                    "value": value,
                    "value_hex": self._value_hex(value, int(size)),
                    "annotation": annotation,
                }
            )
            offset += int(size)
        return rows

    def _byte_rows(self, raw: bytes, logical_size: int) -> list[dict[str, Any]]:
        envelope_labels = ["Generation + body length", "Message type", "Source", "Destination"]
        rows = []
        for offset, value in enumerate(raw):
            if offset < len(envelope_labels):
                role = envelope_labels[offset]
                section = "envelope"
            elif offset < logical_size:
                role = "Body"
                section = "body"
            else:
                role = "Adapter padding"
                section = "padding"
            rows.append({"offset": offset, "hex": f"{value:02X}", "decimal": value, "role": role, "section": section})
        return rows

    def _family(self, value: int) -> dict[str, str]:
        labels = {
            "core_lifecycle_health_timing": "Connection & health",
            "state_snapshot_transition": "State & transitions",
            "player": "Player activity",
            "task": "Task activity",
            "environment": "Room effects",
            "lobby_link_profile": "Lobby link setup",
            "future_reserved": "Reserved",
        }
        for item in self.registry_data["message_namespaces"]:
            if item["minimum"] <= value <= item["maximum"]:
                return {"key": item["name"], "label": labels.get(item["name"], self._display_name(item["name"]))}
        return {"key": "unallocated", "label": "Unallocated"}

    def _address_label(self, value: int, destination: bool) -> str:
        addressing = self.registry_data["addressing"]
        if value == addressing["game_controller"]:
            return "Game Controller"
        endpoint_range = addressing["node_endpoint_range"]
        if endpoint_range["minimum"] <= value <= endpoint_range["maximum"]:
            return f"Node endpoint {value}"
        group_range = addressing["group_destination_range"]
        if group_range["minimum"] <= value <= group_range["maximum"]:
            return f"Node group {value}"
        if destination and value == addressing["broadcast_destination"]:
            return "Every node (broadcast)"
        if not destination and value == addressing["unassigned_source"]:
            return "Unassigned node"
        return f"Address {value}"

    @staticmethod
    def _display_name(value: str) -> str:
        return value.replace("_", " ").strip().capitalize()

    @staticmethod
    def _value_hex(value: Any, size: int) -> str:
        if isinstance(value, int):
            return "0x" + value.to_bytes(size, "little").hex(" ").upper()
        if isinstance(value, str):
            return "0x" + " ".join(value[index:index + 2] for index in range(0, len(value), 2)).upper()
        return ""
