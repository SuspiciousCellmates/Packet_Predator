"""Render a host-specific Packet Predator systemd service safely."""

from __future__ import annotations

import grp
import os
import pwd
import re
from pathlib import Path

from .nrf905_profile import Nrf905ProfileError, load_nrf905_profile


SERVICE_NAME = "suspicious-cellmates-packet-predator.service"
SERVICE_PATH = Path("/etc/systemd/system") / SERVICE_NAME
TEMPLATE_PATH = (
    Path(__file__).resolve().parents[1]
    / "packaging/suspicious-cellmates-packet-predator.service.in"
)
_ACCOUNT = re.compile(r"[A-Za-z_][A-Za-z0-9_-]{0,63}")
_TOKEN = re.compile(r"@[A-Z_]+@")


class SystemdServiceError(ValueError):
    """A permanent service cannot be rendered safely."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def _account(value: str, label: str) -> str:
    if _ACCOUNT.fullmatch(value) is None:
        raise SystemdServiceError(
            "SERVICE_ACCOUNT",
            f"{label} {value!r} cannot be represented safely in a systemd unit.",
        )
    return value


def _quoted_path(value: Path, label: str) -> str:
    path = value.absolute()
    text = str(path)
    if not path.is_absolute() or any(ord(character) < 32 for character in text):
        raise SystemdServiceError(
            "SERVICE_PATH",
            f"{label} must be an absolute path without control characters.",
        )
    escaped = text.replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%")
    return f'"{escaped}"'


def _directive_path(value: Path, label: str) -> str:
    """Encode a path for directives that do not accept shell-style quoting."""
    path = value.absolute()
    text = str(path)
    if not path.is_absolute() or any(ord(character) < 32 for character in text):
        raise SystemdServiceError(
            "SERVICE_PATH",
            f"{label} must be an absolute path without control characters.",
        )
    safe = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789/._-"
    encoded: list[str] = []
    for byte in text.encode("utf-8"):
        if byte in safe:
            encoded.append(chr(byte))
        elif byte == ord("%"):
            encoded.append("%%")
        else:
            encoded.append(f"\\x{byte:02x}")
    return "".join(encoded)


def current_account() -> tuple[str, str]:
    record = pwd.getpwuid(os.getuid())
    return record.pw_name, grp.getgrgid(record.pw_gid).gr_name


def render_service(
    repo_root: Path,
    profile_path: Path,
    *,
    user: str,
    group: str,
    template_path: Path = TEMPLATE_PATH,
) -> str:
    root = repo_root.resolve()
    profile = profile_path.resolve()
    python = root / ".venv/bin/python"
    runner = root / "scripts/run-rpi"
    if not root.is_dir():
        raise SystemdServiceError(
            "SERVICE_REPOSITORY", f"Repository does not exist: {root}"
        )
    if root not in profile.parents:
        raise SystemdServiceError(
            "SERVICE_PROFILE",
            "The system service profile must be inside the Packet Predator repository.",
        )
    try:
        load_nrf905_profile(profile)
    except Nrf905ProfileError as exc:
        raise SystemdServiceError(exc.code, exc.detail) from exc
    if not python.is_file():
        raise SystemdServiceError(
            "SERVICE_ENVIRONMENT",
            f"Packet Predator Python environment is missing: {python}. "
            "Run ./scripts/setup-rpi.",
        )
    if not runner.is_file() or not os.access(runner, os.X_OK):
        raise SystemdServiceError(
            "SERVICE_RUNNER", f"Packet Predator runner is not executable: {runner}"
        )
    try:
        template = template_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SystemdServiceError(
            "SERVICE_TEMPLATE", f"Cannot read systemd template {template_path}: {exc}"
        ) from exc

    replacements = {
        "@USER@": _account(user, "User"),
        "@GROUP@": _account(group, "Group"),
        "@WORKING_DIRECTORY@": _directive_path(root, "Repository"),
        "@RUNNER@": _quoted_path(runner, "Runner"),
        "@PROFILE@": _quoted_path(profile, "Profile"),
    }
    for token, value in replacements.items():
        template = template.replace(token, value)
    unresolved = sorted(set(_TOKEN.findall(template)))
    if unresolved:
        raise SystemdServiceError(
            "SERVICE_TEMPLATE", f"Systemd template has unresolved tokens: {unresolved}."
        )
    return template
