#!/usr/bin/env python3
"""Workbench scope, archive-preservation, and repository hygiene checks."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable


class GuardError(Exception):
    """A foundation invariant was violated."""


FORBIDDEN_IMPORT_ROOTS = {"game_controller", "god_tool", "rules_engine", "simulator"}
ARCHIVED_RUNTIME_IMPORT_ROOTS = {
    "decoder",
    "driver",
    "nodes",
    "packet",
    "simulator",
    "web_app",
}
HARDWARE_IMPORT_ROOTS = {
    "RPi",
    "gpiozero",
    "lgpio",
    "nrf905",
    "rpi_lgpio",
    "serial",
    "spidev",
    "vcgencmd",
}
HARDWARE_ADAPTER_SOURCES = {"packet_predator/adapters/nrf905_linux.py"}
LOCAL_CONTRACT_MODULES = ("packet", "nodes.node")
PROTOCOL_SYMBOLS = {
    "Packet",
    "PayloadType",
    "NodeType",
    "EVENT_TYPES",
    "VALID_CONFIG_SETTINGS",
    "SETTINGS_INDEX_MAP",
}
PROTOCOL_NAME = re.compile(
    r"(^|_)(PACKET|MESSAGE|PAYLOAD|HEADER|EVENT_TYPES?|NODE_TYPES?|PROTOCOL|SETTINGS?(_INDEX)?)(_|$)",
    re.IGNORECASE,
)
QUARANTINED_CLASSES = {"GameCoordinator", "VirtualSpokeNode", "VirtualPlayerNode", "VirtualTaskNode"}
QUARANTINED_UI_MARKERS = {
    "web/index.html": (
        "sim-map-panel",
        "sim-difficulty",
        "btn-trigger-meeting",
        "btn-trigger-sabotage",
    ),
    "web/main.js": (
        "/api/game/",
        "/api/sim/",
        "triggerSimAction('kill'",
        "triggerSimAction('meeting'",
        "triggerSimAction('sabotage'",
    ),
}
REQUIRED_QUARANTINE_IDS = {
    "coordinator",
    "autonomous-simulation",
    "map",
    "difficulty",
    "meeting",
    "kill",
    "sabotage",
    "rules-engine",
    "game-start-stop",
}


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise GuardError(
            f"{path}: malformed JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc
    if not isinstance(value, dict):
        raise GuardError(f"{path}: top-level JSON value must be an object")
    return value


def discover_runtime_files(root: Path) -> list[str]:
    files: set[str] = set()
    for path in root.glob("*.py"):
        if path.is_file():
            files.add(path.relative_to(root).as_posix())
    for directory in ("driver", "nodes", "packet", "resources", "web"):
        base = root / directory
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(root)
            if "__pycache__" in relative.parts or path.suffix in {".pyc", ".pyo"}:
                continue
            files.add(relative.as_posix())
    if (root / "requirements.txt").is_file():
        files.add("requirements.txt")
    return sorted(files)


def discover_architecture_sources(root: Path) -> list[str]:
    excluded_parts = {".git", ".venv", "__pycache__", "tests"}
    sources: list[str] = []
    for path in root.rglob("*.py"):
        relative = path.relative_to(root)
        if excluded_parts.intersection(relative.parts):
            continue
        if relative.as_posix() == "scripts/foundation_check.py":
            continue
        sources.append(relative.as_posix())
    return sorted(sources)


def parse_hash_manifest(path: Path) -> dict[str, str]:
    entries: dict[str, str] = {}
    for number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw_line.strip():
            continue
        parts = raw_line.split(maxsplit=1)
        if len(parts) != 2:
            raise GuardError(f"{path}:{number}: expected SHA-256 and relative path")
        digest, relative = parts[0], parts[1].strip()
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise GuardError(f"{path}:{number}: invalid SHA-256 digest")
        relative_path = Path(relative)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise GuardError(f"{path}:{number}: runtime path must stay inside the repository")
        if relative in entries:
            raise GuardError(f"{path}:{number}: duplicate runtime path {relative}")
        entries[relative] = digest
    if not entries:
        raise GuardError(f"{path}: runtime manifest is empty")
    return entries


def verify_runtime_hashes(root: Path, manifest_path: Path | None = None) -> None:
    manifest_path = manifest_path or root / ".foundation/runtime-freeze.sha256"
    entries = parse_hash_manifest(manifest_path)
    discovered = set(discover_runtime_files(root))
    declared = set(entries)
    missing = sorted(discovered - declared)
    stale = sorted(declared - discovered)
    if missing:
        raise GuardError("runtime files absent from freeze manifest: " + ", ".join(missing))
    if stale:
        raise GuardError("freeze manifest references missing runtime files: " + ", ".join(stale))
    changed: list[str] = []
    for relative, expected in entries.items():
        actual = hashlib.sha256((root / relative).read_bytes()).hexdigest()
        if actual != expected:
            changed.append(f"{relative} (expected {expected}, got {actual})")
    if changed:
        raise GuardError("frozen runtime hash mismatch: " + "; ".join(changed))


def git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False
    )


def verify_archive_snapshot(root: Path, milestone: dict[str, Any], runtime_files: list[str]) -> None:
    freeze = milestone["runtime_freeze"]
    tag = freeze["snapshot_tag"]
    tag_type = git(root, "cat-file", "-t", tag)
    if tag_type.returncode != 0:
        raise GuardError(f"archive snapshot tag {tag!r} is missing")
    if tag_type.stdout.strip() != "tag":
        raise GuardError(f"archive snapshot {tag!r} must be an annotated tag")
    absent_from_snapshot = []
    for relative in runtime_files:
        if git(root, "cat-file", "-e", f"{tag}:{relative}").returncode != 0:
            absent_from_snapshot.append(relative)
    if absent_from_snapshot:
        raise GuardError(
            f"runtime files were added after archival tag {tag}: " + ", ".join(absent_from_snapshot)
        )
    result = git(root, "diff", "--name-only", tag, "--", *runtime_files)
    if result.returncode != 0:
        raise GuardError(f"could not compare runtime with {tag}: {result.stderr.strip()}")
    changed = [line for line in result.stdout.splitlines() if line]
    if changed:
        raise GuardError(f"runtime differs from archival tag {tag}: " + ", ".join(changed))


def imported_modules(tree: ast.AST) -> Iterable[str]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            yield node.module


def assignment_names(body: list[ast.stmt], prefix: str = "") -> Iterable[str]:
    for node in body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    yield prefix + target.id
        elif isinstance(node, ast.ClassDef):
            yield from assignment_names(node.body, prefix + node.name + ".")


def collect_architecture_violations(root: Path, runtime_paths: Iterable[str] | None = None) -> set[str]:
    paths = sorted(runtime_paths if runtime_paths is not None else discover_architecture_sources(root))
    violations: set[str] = set()
    for relative in paths:
        path = root / relative
        if path.suffix != ".py":
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
        except SyntaxError as exc:
            raise GuardError(f"cannot scan {relative}: {exc}") from exc

        for module in imported_modules(tree):
            import_root = module.split(".", 1)[0]
            if import_root in FORBIDDEN_IMPORT_ROOTS:
                violations.add(f"forbidden-dependency|{relative}|{module}")
            if module == "nodes.node" or module == "packet" or module.startswith("packet."):
                violations.add(f"local-contract-import|{relative}|{module}")
            if relative.startswith("packet_predator/") and import_root in ARCHIVED_RUNTIME_IMPORT_ROOTS:
                violations.add(f"supported-runtime-imports-archive|{relative}|{module}")
            if (
                relative.startswith("packet_predator/")
                and import_root in HARDWARE_IMPORT_ROOTS
                and relative not in HARDWARE_ADAPTER_SOURCES
            ):
                violations.add(f"hardware-outside-adapter|{relative}|{module}")

        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            base_names = {
                base.id if isinstance(base, ast.Name) else base.attr
                for base in node.bases
                if isinstance(base, (ast.Name, ast.Attribute))
            }
            if node.name in PROTOCOL_SYMBOLS or "Enum" in base_names:
                violations.add(f"local-protocol-definition|{relative}|{node.name}")
            if node.name in QUARANTINED_CLASSES:
                violations.add(f"quarantined-symbol|{relative}|{node.name}")

        for qualified_name in assignment_names(tree.body):
            name = qualified_name.rsplit(".", 1)[-1]
            if name in PROTOCOL_SYMBOLS or PROTOCOL_NAME.search(name):
                violations.add(f"local-protocol-definition|{relative}|{qualified_name}")

        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if node.value.startswith("/api/game/") or node.value.startswith("/api/sim/"):
                    violations.add(f"quarantined-route|{relative}|{node.value}")

    for relative, markers in QUARANTINED_UI_MARKERS.items():
        path = root / relative
        if not path.is_file():
            continue
        content = path.read_text(encoding="utf-8")
        for marker in markers:
            if marker in content:
                violations.add(f"quarantined-ui|{relative}|{marker}")

    excluded_artifact_parts = {".git", ".venv", "__pycache__", "tests", "docs", ".foundation"}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if excluded_artifact_parts.intersection(relative.parts):
            continue
        lowered_parts = {part.lower() for part in relative.parts}
        stem = path.stem.lower()
        if (
            {"registry", "fixtures", "contract"}.intersection(lowered_parts)
            or re.search(r"(^|[-_])(protocol|registry|fixture|contract)([-_]|$)", stem)
        ):
            violations.add(f"local-protocol-artifact|{relative.as_posix()}")
    return violations


def architecture_exception_ids(path: Path) -> set[str]:
    data = load_json(path)
    if data.get("status") != "archived-legacy-only":
        raise GuardError(f"{path}: invalid architecture exception status")
    exceptions = data.get("exceptions")
    if not isinstance(exceptions, list):
        raise GuardError(f"{path}: exceptions must be an array")
    ids: set[str] = set()
    for index, exception in enumerate(exceptions):
        if not isinstance(exception, dict) or not isinstance(exception.get("id"), str) or not exception.get("reason"):
            raise GuardError(f"{path}: exception {index} requires id and reason")
        if exception["id"] in ids:
            raise GuardError(f"{path}: duplicate exception id {exception['id']}")
        ids.add(exception["id"])
    return ids


def compare_architecture(violations: set[str], exceptions: set[str]) -> None:
    new = sorted(violations - exceptions)
    stale = sorted(exceptions - violations)
    if new:
        raise GuardError("new architecture violations are not allowed: " + "; ".join(new))
    if stale:
        raise GuardError(
            "stale architecture exceptions must be deliberately removed with the relevant review: "
            + "; ".join(stale)
        )


def verify_architecture(root: Path, exceptions_path: Path | None = None) -> None:
    violations = collect_architecture_violations(root)
    exceptions = architecture_exception_ids(
        exceptions_path or root / ".foundation/architecture-exceptions.json"
    )
    compare_architecture(violations, exceptions)


def verify_quarantine(root: Path) -> None:
    path = root / ".foundation/quarantine.json"
    data = load_json(path)
    if data.get("status") != "unsupported-quarantined":
        raise GuardError(f"{path}: quarantine must remain unsupported-quarantined")
    entries = data.get("entries")
    if not isinstance(entries, list):
        raise GuardError(f"{path}: entries must be an array")
    ids = {entry.get("id") for entry in entries if isinstance(entry, dict)}
    if ids != REQUIRED_QUARANTINE_IDS:
        raise GuardError(
            f"{path}: quarantine ids differ; missing={sorted(REQUIRED_QUARANTINE_IDS - ids)}, "
            f"unexpected={sorted(ids - REQUIRED_QUARANTINE_IDS)}"
        )
    for entry in entries:
        if not all(entry.get(field) for field in ("id", "file", "evidence", "future_owner")):
            raise GuardError(f"{path}: every quarantine entry needs id, file, evidence, and future_owner")
        source_path = root / entry["file"]
        if not source_path.is_file():
            raise GuardError(f"{path}: quarantine source is missing: {entry['file']}")
        content = source_path.read_text(encoding="utf-8")
        missing = [marker for marker in entry["evidence"] if marker not in content]
        if missing:
            raise GuardError(f"{path}: {entry['id']} evidence missing from {entry['file']}: {missing}")


def verify_documents_and_milestone(root: Path) -> dict[str, Any]:
    required = [
        "README.md",
        "AGENTS.md",
        "docs/audit-2026-07-20.md",
        "docs/architecture.md",
        "docs/roadmap.md",
        "docs/ideas.md",
        "docs/runtime-inventory.md",
        "docs/adr/0001-foundation-runtime-freeze.md",
        "docs/adr/0003-begin-layered-workbench-runtime.md",
        "docs/adr/0004-begin-deterministic-replay.md",
        "docs/adr/0005-begin-nrf905-physical-validation.md",
        "docs/adr/0006-decouple-physical-receive-from-browser.md",
        "docs/nrf905-two-pi-bench.md",
        "config/nrf905-bench.example.json",
        "requirements-rpi.txt",
        "scripts/nrf905-diagnose",
        "scripts/run-rpi",
        "scripts/setup-rpi",
        ".foundation/milestone.json",
        ".foundation/runtime-baseline.json",
        ".foundation/runtime-freeze.sha256",
        ".foundation/architecture-exceptions.json",
        ".foundation/quarantine.json",
    ]
    missing = [relative for relative in required if not (root / relative).is_file()]
    if missing:
        raise GuardError("missing required foundation files: " + ", ".join(missing))
    milestone = load_json(root / ".foundation/milestone.json")
    expected = {
        "active_lane": "Now",
        "milestone_id": "nrf905-physical-adapter-validation",
        "status": "active",
        "runtime_changes_allowed": True,
        "protocol_authority": "../Protocol_Contract",
        "runtime_baseline": ".foundation/runtime-baseline.json",
    }
    wrong = {key: (milestone.get(key), value) for key, value in expected.items() if milestone.get(key) != value}
    if wrong:
        raise GuardError(f"active milestone metadata is invalid: {wrong}")
    freeze = milestone.get("runtime_freeze")
    if not isinstance(freeze, dict) or freeze.get("enforced") is not False:
        raise GuardError("layered milestone must retain but supersede the all-runtime freeze")
    if (
        freeze.get("replacement_requires_adr") is not True
        or freeze.get("replacement_adr") != "docs/adr/0006-decouple-physical-receive-from-browser.md"
        or freeze.get("legacy_files_remain_immutable") is not True
    ):
        raise GuardError("archived runtime preservation rule is invalid")

    baseline = load_json(root / milestone["runtime_baseline"])
    baseline_expected = {
        "status": "active-nrf905-validation",
        "milestone_id": "nrf905-physical-adapter-validation",
        "protocol_authority": "../Protocol_Contract",
        "supported_entrypoint": "packet_predator.web:app",
        "default_transport": "inspect-only",
        "replay_startup": "explicit-selection-only",
        "physical_startup": "explicit-profile-only",
        "physical_receive_lifecycle": "application-owned-signal-driven",
        "browser_physical_receive": "model-events-only",
        "packet_transmission_allowed": "explicit-profile-and-request-confirmation",
        "hardware_imports_allowed": ["packet_predator/adapters/nrf905_linux.py"],
        "autonomous_actors_allowed": False,
    }
    baseline_wrong = {
        key: (baseline.get(key), value)
        for key, value in baseline_expected.items()
        if baseline.get(key) != value
    }
    if baseline_wrong:
        raise GuardError(f"supported runtime baseline is invalid: {baseline_wrong}")
    if baseline.get("available_transports") != ["inspect-only", "deterministic-replay", "nrf905"]:
        raise GuardError("supported runtime baseline must keep physical access explicit and inspect-only first")
    supported = baseline.get("supported_runtime")
    if not isinstance(supported, dict) or not supported:
        raise GuardError("supported runtime baseline needs a non-empty named path allow-list")
    missing_supported = [relative for relative in supported.values() if not (root / relative).exists()]
    if missing_supported:
        raise GuardError("supported runtime baseline paths are missing: " + ", ".join(missing_supported))
    archive = baseline.get("legacy_archive")
    if not isinstance(archive, dict) or archive.get("snapshot_tag") != freeze.get("snapshot_tag"):
        raise GuardError("supported runtime baseline does not preserve the archive tag")
    if (
        archive.get("manifest") != freeze.get("manifest")
        or archive.get("policy") != "immutable-unsupported-evidence"
    ):
        raise GuardError("supported runtime baseline does not preserve the archive manifest")

    roadmap = (root / "docs/roadmap.md").read_text(encoding="utf-8")
    if "## Now — nRF905 physical adapter validation" not in roadmap or milestone["milestone_id"] not in roadmap:
        raise GuardError("docs/roadmap.md does not identify the active Now milestone")
    ordered = [
        "Reference codec and cross-language conformance suite released as Protocol Contract `1.0.1`.",
        "`layered-local-workbench`: hardware-free browser inspector, explicit inspect-only carrier, and layered supported entrypoint reviewed and accepted.",
        "`deterministic-replay-fake-transport`: finite recording replay, fake opaque-frame transport, exact clock controls, and capture provenance reviewed and accepted.",
        "## Now — nRF905 physical adapter validation",
        "## Next — Game applications",
        "1. Build Game Controller and Game Master Console as distinct deployed roles against the shared contract; a console platform or presentation components may be shared without sharing production capabilities.",
    ]
    positions = [roadmap.find(text) for text in ordered]
    if any(position < 0 for position in positions) or positions != sorted(positions):
        raise GuardError("docs/roadmap.md does not preserve the required milestone order")
    return milestone


def verify_no_tracked_generated_artifacts(root: Path) -> None:
    result = git(root, "ls-files")
    if result.returncode != 0:
        raise GuardError(f"cannot list tracked files: {result.stderr.strip()}")
    generated_parts = {"__pycache__", ".venv", ".pytest_cache", ".mypy_cache", "node_modules", ".tox"}
    generated_suffixes = {".pyc", ".pyo", ".class"}
    offenders = []
    for relative in result.stdout.splitlines():
        path = Path(relative)
        if generated_parts.intersection(path.parts) or path.suffix in generated_suffixes:
            offenders.append(relative)
    if offenders:
        raise GuardError("tracked cache/generated artifacts: " + ", ".join(offenders))


def validate(root: Path) -> None:
    milestone = verify_documents_and_milestone(root)
    verify_runtime_hashes(root)
    archived_files = sorted(parse_hash_manifest(root / milestone["runtime_freeze"]["manifest"]))
    verify_archive_snapshot(root, milestone, archived_files)
    verify_architecture(root)
    verify_quarantine(root)
    verify_no_tracked_generated_artifacts(root)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--list-violations",
        action="store_true",
        help="print normalized current architecture violations for baseline review",
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    try:
        if args.list_violations:
            print("\n".join(sorted(collect_architecture_violations(root))))
            return 0
        validate(root)
    except (GuardError, OSError) as exc:
        print(f"foundation check failed: {exc}", file=sys.stderr)
        return 1
    print("workbench checks passed: documents, archive preservation, architecture, quarantine, hygiene")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
