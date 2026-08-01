from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from packet_predator.systemd import (
    SERVICE_NAME,
    SERVICE_PATH,
    SystemdServiceError,
    render_service,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


def prepared_repository(directory: str) -> tuple[Path, Path]:
    root = Path(directory) / "Packet Predator"
    python = root / ".venv/bin/python"
    runner = root / "scripts/run-rpi"
    profile = root / "config/nrf905-bench.local.json"
    python.parent.mkdir(parents=True)
    runner.parent.mkdir()
    profile.parent.mkdir()
    python.touch()
    runner.touch(mode=0o755)
    shutil.copyfile(REPO_ROOT / "config/nrf905-bench.example.json", profile)
    return root, profile


class SystemdServiceTests(unittest.TestCase):
    def test_tracked_template_and_installer_are_validated_before_install(self):
        template = (
            REPO_ROOT
            / "packaging/suspicious-cellmates-packet-predator.service.in"
        )
        installer = (REPO_ROOT / "scripts/install-systemd-service").read_text(
            encoding="utf-8"
        )
        self.assertTrue(template.is_file())
        self.assertIn("mktemp --suffix=.service", installer)
        self.assertIn("./scripts/check", installer)
        self.assertIn('systemd-analyze verify "$temporary_unit"', installer)
        self.assertLess(
            installer.index("./scripts/check"),
            installer.index("sudo install"),
        )
        self.assertLess(
            installer.index('systemd-analyze verify "$temporary_unit"'),
            installer.index("sudo install"),
        )

    def test_service_is_loopback_profile_explicit_and_stops_radio_gracefully(self):
        with tempfile.TemporaryDirectory() as directory:
            root, profile = prepared_repository(directory)
            unit = render_service(root, profile, user="taylor", group="taylor")

        self.assertEqual(SERVICE_PATH, Path("/etc/systemd/system") / SERVICE_NAME)
        self.assertIn("User=taylor", unit)
        self.assertIn("Group=taylor", unit)
        self.assertIn("Packet\\x20Predator", unit)
        self.assertIn('/scripts/run-rpi"', unit)
        self.assertIn('/config/nrf905-bench.local.json"', unit)
        self.assertNotIn("--lan", unit)
        self.assertIn("Restart=on-failure", unit)
        self.assertIn("KillSignal=SIGINT", unit)
        self.assertIn("ProtectSystem=strict", unit)
        self.assertIn("WantedBy=multi-user.target", unit)
        self.assertNotRegex(unit, r"@[A-Z_]+@")

    def test_service_refuses_profile_outside_repository(self):
        with tempfile.TemporaryDirectory() as directory:
            root, _ = prepared_repository(directory)
            profile = Path(directory) / "outside.json"
            shutil.copyfile(REPO_ROOT / "config/nrf905-bench.example.json", profile)
            with self.assertRaisesRegex(SystemdServiceError, "inside"):
                render_service(root, profile, user="taylor", group="taylor")

    def test_service_rejects_unsafe_account_name(self):
        with tempfile.TemporaryDirectory() as directory:
            root, profile = prepared_repository(directory)
            with self.assertRaisesRegex(SystemdServiceError, "safely"):
                render_service(
                    root,
                    profile,
                    user="bad\nDirective=yes",
                    group="taylor",
                )


if __name__ == "__main__":
    unittest.main()
