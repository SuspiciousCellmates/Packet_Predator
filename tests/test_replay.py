import json
import tempfile
import unittest
from pathlib import Path

from packet_predator.replay import RecordingCatalog, RecordingError
from packet_predator.service import WorkbenchService
from packet_predator.transport import CarrierFrame, DeterministicReplayTransport, TransportError
from packet_predator.wire_adapter import WireAdapter


REPO_ROOT = Path(__file__).resolve().parents[1]
AUTHORITY_ROOT = REPO_ROOT.parent / "Protocol_Contract"


class ManualClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def carrier_frame(sequence, at_ms):
    return CarrierFrame(
        sequence=sequence,
        at_ms=at_ms,
        direction="received",
        frame=bytes((sequence,)),
        frame_mode="logical",
        recording_id="clock-test",
        fixture_id=f"example-{sequence}",
        note=f"Frame {sequence}",
    )


class DeterministicTransportTests(unittest.TestCase):
    def setUp(self):
        self.clock = ManualClock()
        self.carrier = DeterministicReplayTransport(self.clock)
        self.frames = tuple(carrier_frame(index, at_ms) for index, at_ms in enumerate((0, 400, 1000)))
        self.carrier.load("clock-test", "Clock test", 1000, self.frames)

    def test_clock_releases_only_frames_that_are_due(self):
        self.assertEqual([item.sequence for item in self.carrier.play()], [0])
        self.clock.advance(0.399)
        self.assertEqual(self.carrier.poll(), [])
        self.clock.advance(0.001)
        self.assertEqual([item.sequence for item in self.carrier.poll()], [1])
        self.clock.advance(0.6)
        self.assertEqual([item.sequence for item in self.carrier.poll()], [2])
        self.assertEqual(self.carrier.status()["state"], "complete")

    def test_pause_freezes_position_and_speed_is_exact(self):
        self.carrier.play()
        self.clock.advance(0.2)
        self.carrier.pause()
        position = self.carrier.status()["position_ms"]
        self.clock.advance(10)
        self.assertEqual(self.carrier.poll(), [])
        self.assertEqual(self.carrier.status()["position_ms"], position)

        self.carrier.set_speed(2.0)
        self.carrier.play()
        self.clock.advance(0.1)
        self.assertEqual([item.sequence for item in self.carrier.poll()], [1])

    def test_step_reset_and_completion_are_explicit(self):
        self.assertEqual([item.sequence for item in self.carrier.step()], [0])
        self.assertEqual([item.sequence for item in self.carrier.step()], [1])
        self.assertEqual([item.sequence for item in self.carrier.step()], [2])
        with self.assertRaisesRegex(TransportError, "Reset"):
            self.carrier.step()
        self.carrier.reset()
        self.assertEqual(self.carrier.status()["cursor"], 0)
        self.assertEqual([item.sequence for item in self.carrier.step()], [0])

    def test_replay_never_claims_transmit_capability(self):
        status = self.carrier.status()
        self.assertTrue(status["can_receive"])
        self.assertFalse(status["can_transmit"])
        self.assertIn("no actors", status["description"])


class RecordingValidationTests(unittest.TestCase):
    def resolver(self, fixture_id, mode, source, destination):
        return {
            "display_name": "Resolved example",
            "frame_hex": "40010100",
            "frame_mode": mode,
            "source": 1 if source is None else source,
            "source_label": "Node endpoint 1",
            "destination": 0 if destination is None else destination,
            "destination_label": "Game Controller",
        }

    def valid_data(self):
        return {
            "schema_version": 1,
            "id": "small-recording",
            "title": "Small recording",
            "description": "A finite validation example.",
            "authority_version": "1.0.1",
            "frame_mode": "logical",
            "duration_ms": 100,
            "entries": [
                {
                    "at_ms": 100,
                    "fixture_id": "example-one",
                    "source": None,
                    "destination": None,
                    "direction": "received",
                    "note": "One explicit frame.",
                }
            ],
        }

    def write(self, root, data):
        path = root / "small-recording.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def test_valid_recording_resolves_to_opaque_carrier_frame(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write(root, self.valid_data())
            item = RecordingCatalog(root, "1.0.1", self.resolver).get("small-recording")
            self.assertEqual(item.frames[0].frame, bytes.fromhex("40010100"))
            self.assertEqual(item.frames[0].at_ms, 100)

    def test_branch_or_condition_field_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = self.valid_data()
            data["entries"][0]["condition"] = "invent a reply"
            self.write(root, data)
            with self.assertRaisesRegex(RecordingError, "must contain exactly"):
                RecordingCatalog(root, "1.0.1", self.resolver)

    def test_out_of_order_timing_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = self.valid_data()
            data["entries"].insert(0, {**data["entries"][0], "at_ms": 90})
            data["entries"][1]["at_ms"] = 80
            self.write(root, data)
            with self.assertRaisesRegex(RecordingError, "nondecreasing order"):
                RecordingCatalog(root, "1.0.1", self.resolver)

    def test_authority_version_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = self.valid_data()
            data["authority_version"] = "9.9.9"
            self.write(root, data)
            with self.assertRaisesRegex(RecordingError, "expects authority"):
                RecordingCatalog(root, "1.0.1", self.resolver)

    def test_repository_recording_shapes_validate_without_runtime_authority(self):
        catalog = RecordingCatalog(REPO_ROOT / "recordings", "1.0.1", self.resolver)
        self.assertEqual(
            {item["id"] for item in catalog.list()},
            {"node-onboarding", "retained-outcome-retry", "task-session-success"},
        )


@unittest.skipUnless(
    (AUTHORITY_ROOT / "registry/v1.json").is_file(),
    "sibling Protocol Contract checkout is required for replay integration tests",
)
class ReleasedRecordingIntegrationTests(unittest.TestCase):
    def test_all_repository_recordings_resolve_and_decode(self):
        service = WorkbenchService(WireAdapter(AUTHORITY_ROOT))
        recordings = service.replay_catalog()["recordings"]
        self.assertEqual({item["id"] for item in recordings}, {
            "node-onboarding",
            "retained-outcome-retry",
            "task-session-success",
        })
        for recording in recordings:
            service.select_replay(recording["id"])
            delivered = []
            for _ in range(recording["frame_count"]):
                delivered.extend(service.control_replay("step")["delivered"])
            self.assertEqual(len(delivered), recording["frame_count"])
            self.assertEqual(
                [item["capture"]["sequence"] for item in delivered],
                list(range(recording["frame_count"])),
            )

    def test_retry_recording_repeats_identical_adapter_bytes(self):
        service = WorkbenchService(WireAdapter(AUTHORITY_ROOT))
        service.select_replay("retained-outcome-retry")
        first = service.control_replay("step")["delivered"][0]
        second = service.control_replay("step")["delivered"][0]
        self.assertEqual(first["received_frame_hex"], second["received_frame_hex"])
        self.assertEqual(first["received_bytes"], 32)
        self.assertEqual(first["padding_bytes"], second["padding_bytes"])


if __name__ == "__main__":
    unittest.main()
