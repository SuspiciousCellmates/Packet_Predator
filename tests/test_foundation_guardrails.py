import hashlib
import tempfile
import unittest
from pathlib import Path

from scripts.foundation_check import (
    GuardError,
    collect_architecture_violations,
    compare_architecture,
    verify_runtime_hashes,
)


class FoundationGuardrailTests(unittest.TestCase):
    def test_changing_frozen_runtime_file_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = root / "workbench.py"
            runtime.write_text("original\n", encoding="utf-8")
            digest = hashlib.sha256(runtime.read_bytes()).hexdigest()
            manifest = root / "runtime-freeze.sha256"
            manifest.write_text(f"{digest}  workbench.py\n", encoding="utf-8")
            runtime.write_text("changed\n", encoding="utf-8")

            with self.assertRaisesRegex(GuardError, "frozen runtime hash mismatch"):
                verify_runtime_hashes(root, manifest)

    def test_new_forbidden_dependency_fails_architecture_baseline(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "workbench.py").write_text(
                "from game_controller import Rules\n", encoding="utf-8"
            )
            violations = collect_architecture_violations(root, ["workbench.py"])

            with self.assertRaisesRegex(GuardError, "new architecture violations"):
                compare_architecture(violations, set())

    def test_supported_runtime_cannot_import_archived_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            supported = root / "packet_predator"
            supported.mkdir()
            (supported / "service.py").write_text("from driver.nrf905 import NRF905\n", encoding="utf-8")
            violations = collect_architecture_violations(
                root, ["packet_predator/service.py"]
            )

            self.assertIn(
                "supported-runtime-imports-archive|packet_predator/service.py|driver.nrf905",
                violations,
            )

    def test_supported_runtime_cannot_import_hardware_dependency(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            supported = root / "packet_predator"
            supported.mkdir()
            (supported / "transport.py").write_text("import spidev\n", encoding="utf-8")
            violations = collect_architecture_violations(
                root, ["packet_predator/transport.py"]
            )

            self.assertIn(
                "hardware-dependency|packet_predator/transport.py|spidev",
                violations,
            )


if __name__ == "__main__":
    unittest.main()
