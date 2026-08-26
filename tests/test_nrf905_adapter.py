from collections import deque
from datetime import timedelta
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

from packet_predator.adapters.nrf905 import (
    DataReadyWait,
    Nrf905Device,
    Nrf905Error,
    configuration_bytes,
)
from packet_predator.adapters.nrf905_linux import LinuxDigitalLines
from packet_predator.nrf905_profile import Nrf905ProfileError, load_nrf905_profile
from packet_predator.nrf905_transport import Nrf905Transport
from packet_predator.service import WorkbenchService
from packet_predator.transport import TransportError
from packet_predator.wire_adapter import WireAdapter


REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_PROFILE = REPO_ROOT / "config/nrf905-bench.example.json"
AUTHORITY_ROOT = REPO_ROOT.parent / "Protocol_Contract"


class ManualClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class FakeLines:
    def __init__(self):
        self.outputs = {"pwr_up": False, "trx_ce": False, "tx_en": False}
        self.inputs = {"carrier_detect": False, "address_match": False, "data_ready": False}
        self.history = []
        self.closed = False
        self.close_count = 0
        self.wait_error = None
        self.edge_monotonic_ns = None
        self.scripted_waits = deque()
        self.condition = threading.Condition()

    def set(self, name, active):
        previous = self.outputs[name]
        self.outputs[name] = active
        self.history.append((name, active))
        if name == "trx_ce" and active and self.outputs["tx_en"]:
            self.set_input("data_ready", True)
        if name == "tx_en" and previous and not active:
            self.set_input("data_ready", False)

    def get(self, name):
        with self.condition:
            return self.inputs[name]

    def wait(self, name, timeout_s):
        if self.wait_error is not None:
            raise self.wait_error
        if self.scripted_waits:
            return self.scripted_waits.popleft()
        with self.condition:
            self.condition.wait_for(lambda: self.inputs[name], timeout_s)
            ready = self.inputs[name]
            timestamp = self.edge_monotonic_ns
            self.edge_monotonic_ns = None
            return DataReadyWait(
                ready=ready,
                edge_monotonic_ns=timestamp,
                source=("edge" if timestamp is not None else "level") if ready else "timeout",
            )

    def set_input(self, name, active):
        with self.condition:
            self.inputs[name] = active
            self.condition.notify_all()

    def close(self):
        self.closed = True
        self.close_count += 1


class FakeSpi:
    def __init__(self):
        self.configuration = bytes(10)
        self.tx_address = b""
        self.tx_frame = b""
        self.rx_frame = bytes(32)
        self.rx_frames = deque()
        self.lines = None
        self.mismatch = False
        self.closed = False

    def exchange(self, outgoing):
        command = outgoing[0]
        if command == 0x00:
            self.configuration = bytes(outgoing[1:])
            return bytes(len(outgoing))
        if command == 0x10:
            value = bytearray(self.configuration)
            if self.mismatch:
                value[0] ^= 0x01
            return bytes([0]) + bytes(value[: len(outgoing) - 1])
        if command == 0x22:
            self.tx_address = bytes(outgoing[1:])
            return bytes(len(outgoing))
        if command == 0x20:
            self.tx_frame = bytes(outgoing[1:])
            return bytes(len(outgoing))
        if command == 0x24:
            frame = self.rx_frames.popleft() if self.rx_frames else self.rx_frame
            if self.lines is not None:
                self.lines.set_input("data_ready", bool(self.rx_frames))
            return bytes([0]) + frame[: len(outgoing) - 1]
        raise AssertionError(f"unexpected SPI command 0x{command:02x}")

    def queue_receive(self, *frames):
        self.rx_frames.extend(frames)
        if self.lines is not None:
            self.lines.set_input("data_ready", True)

    def close(self):
        self.closed = True


class FakeEdgeRequest:
    def __init__(self, levels, events=()):
        self.levels = deque(levels)
        self.events = list(events)
        self.wait_timeouts = []
        self.read_count = 0

    def get_value(self, offset):
        return self.levels.popleft()

    def wait_edge_events(self, timeout):
        self.wait_timeouts.append(timeout)
        return bool(self.events)

    def read_edge_events(self):
        self.read_count += 1
        events = self.events
        self.events = []
        return events


def transmitting_profile():
    data = json.loads(EXAMPLE_PROFILE.read_text(encoding="utf-8"))
    data["radio"]["transmit_enabled"] = True
    directory = tempfile.TemporaryDirectory()
    path = Path(directory.name) / "bench.local.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return directory, load_nrf905_profile(path)


class ProfileTests(unittest.TestCase):
    def test_example_profile_is_receive_only_and_builds_expected_register(self):
        profile = load_nrf905_profile(EXAMPLE_PROFILE)
        self.assertFalse(profile.radio.transmit_enabled)
        self.assertEqual(profile.spi.speed_hz, 1_000_000)
        self.assertEqual(
            profile.gpio.named_lines(),
            {
                "pwr_up": 21,
                "trx_ce": 7,
                "tx_en": 23,
                "carrier_detect": 18,
                "address_match": 22,
                "data_ready": 17,
            },
        )
        self.assertEqual(profile.radio.frequency_mhz, 433.2)
        self.assertEqual(configuration_bytes(profile).hex(), "6c00442020a7c35e19d8")

    def test_repeated_physical_address_byte_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            data = json.loads(EXAMPLE_PROFILE.read_text(encoding="utf-8"))
            data["radio"]["address_hex"] = "E7E7E7E7"
            path = Path(directory) / "bad.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(Nrf905ProfileError, "distinct bytes"):
                load_nrf905_profile(path)

    def test_unknown_profile_field_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            data = json.loads(EXAMPLE_PROFILE.read_text(encoding="utf-8"))
            data["radio"]["live_hopping"] = True
            path = Path(directory) / "bad.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(Nrf905ProfileError, "requires exactly"):
                load_nrf905_profile(path)

    def test_out_of_range_frequency_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            data = json.loads(EXAMPLE_PROFILE.read_text(encoding="utf-8"))
            data["radio"]["channel"] = 0
            path = Path(directory) / "bad.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(Nrf905ProfileError, "outside the nRF905 range"):
                load_nrf905_profile(path)

    def test_automatic_hardware_retransmit_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            data = json.loads(EXAMPLE_PROFILE.read_text(encoding="utf-8"))
            data["radio"]["automatic_retransmit"] = True
            path = Path(directory) / "bad.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(Nrf905ProfileError, "one-frame validation"):
                load_nrf905_profile(path)


class LinuxDigitalLinesTests(unittest.TestCase):
    def test_wait_carries_latest_kernel_edge_timestamp_after_level_recheck(self):
        lines = self._lines(
            levels=[False, True],
            events=[SimpleNamespace(timestamp_ns=1_000), SimpleNamespace(timestamp_ns=2_000)],
        )

        result = lines.wait("data_ready", 0.125)

        self.assertTrue(result)
        self.assertEqual(result.edge_monotonic_ns, 2_000)
        self.assertEqual(result.source, "edge")
        self.assertEqual(lines._request.read_count, 1)
        self.assertEqual(lines._request.wait_timeouts, [timedelta(seconds=0.125)])

    def test_wait_preserves_already_high_level_without_inventing_timestamp(self):
        lines = self._lines(levels=[True])

        result = lines.wait("data_ready", 0.125)

        self.assertTrue(result)
        self.assertIsNone(result.edge_monotonic_ns)
        self.assertEqual(result.source, "level")
        self.assertEqual(lines._request.read_count, 0)
        self.assertEqual(lines._request.wait_timeouts, [timedelta(0)])

    @staticmethod
    def _lines(levels, events=()):
        lines = LinuxDigitalLines.__new__(LinuxDigitalLines)
        lines._offsets = {"data_ready": 17}
        lines._value = SimpleNamespace(ACTIVE=True, INACTIVE=False)
        lines._request = FakeEdgeRequest(levels, events)
        return lines


class DeviceTests(unittest.TestCase):
    def setUp(self):
        self.directory, self.profile = transmitting_profile()
        self.clock = ManualClock()
        self.spi = FakeSpi()
        self.lines = FakeLines()
        self.spi.lines = self.lines
        self.device = Nrf905Device(
            self.profile,
            self.spi,
            self.lines,
            sleeper=self.clock.sleep,
            monotonic=self.clock,
        )

    def tearDown(self):
        self.directory.cleanup()

    def test_start_requires_exact_configuration_readback_and_enters_receive(self):
        result = self.device.start()
        self.assertEqual(result["configuration_hex"], "6c00442020a7c35e19d8")
        self.assertEqual(self.spi.configuration, configuration_bytes(self.profile))
        self.assertEqual(self.lines.outputs, {"pwr_up": True, "trx_ce": True, "tx_en": False})

    def test_configuration_readback_mismatch_fails_clearly(self):
        self.spi.mismatch = True
        with self.assertRaisesRegex(Nrf905Error, "readback differs") as raised:
            self.device.start()
        self.assertEqual(raised.exception.code, "NRF905_REGISTER_MISMATCH")

    def test_receive_returns_exact_32_bytes_then_reenters_receive(self):
        self.device.start()
        expected = bytes(range(32))
        self.spi.rx_frame = expected
        self.lines.inputs["data_ready"] = True
        self.assertEqual(self.device.receive(), expected)
        self.assertTrue(self.lines.outputs["trx_ce"])
        self.assertFalse(self.lines.inputs["data_ready"])

    def test_wait_propagates_kernel_monotonic_edge_timestamp(self):
        self.device.start()
        self.lines.inputs["data_ready"] = True
        self.lines.edge_monotonic_ns = 1_234_567

        result = self.device.wait_data_ready(0.1)

        self.assertTrue(result)
        self.assertEqual(result.edge_monotonic_ns, 1_234_567)
        self.assertEqual(result.source, "edge")

    def test_wait_preserves_already_high_level_without_inventing_edge_time(self):
        self.device.start()
        self.lines.inputs["data_ready"] = True

        result = self.device.wait_data_ready(0.1)

        self.assertTrue(result)
        self.assertIsNone(result.edge_monotonic_ns)
        self.assertEqual(result.source, "level")

    def test_transmit_writes_address_and_exact_frame(self):
        self.device.start()
        frame = bytes(reversed(range(32)))
        result = self.device.transmit(frame)
        self.assertEqual(self.spi.tx_address, self.profile.radio.address)
        self.assertEqual(self.spi.tx_frame, frame)
        self.assertEqual(result["frame_hex"], frame.hex())
        self.assertIn("tx_completion_ms", result)
        self.assertIn("receive_mode_reentry_ms", result)
        self.assertGreaterEqual(
            result["receive_mode_reentry_ms"],
            result["tx_completion_ms"],
        )
        self.assertEqual(self.lines.outputs, {"pwr_up": True, "trx_ce": True, "tx_en": False})

    def test_invalid_transmit_length_fails_before_spi(self):
        self.device.start()
        with self.assertRaisesRegex(Nrf905Error, "exactly 32 bytes"):
            self.device.transmit(bytes(31))

    def test_receive_only_profile_refuses_transmit(self):
        profile = load_nrf905_profile(EXAMPLE_PROFILE)
        device = Nrf905Device(profile, FakeSpi(), FakeLines(), self.clock.sleep, self.clock)
        device.start()
        with self.assertRaisesRegex(Nrf905Error, "receive-only") as raised:
            device.transmit(bytes(32))
        self.assertEqual(raised.exception.code, "NRF905_TRANSMIT_DISABLED")

    def test_transport_labels_physical_capture_without_decoding(self):
        transport = Nrf905Transport(self.profile, self.device, self.clock)
        self.spi.rx_frame = bytes(range(32))
        self.lines.inputs["data_ready"] = True
        self.lines.edge_monotonic_ns = round((self.clock.now - 0.001) * 1_000_000_000)
        captured = transport.poll()[0]
        self.assertEqual(captured.frame, bytes(range(32)))
        self.assertEqual(captured.direction, "received")
        self.assertEqual(captured.frame_mode, "fixed")
        self.assertEqual(captured.timing["edge_to_lock_ms"], 1.0)
        self.assertEqual(captured.timing["edge_to_payload_read_ms"], 1.0)
        self.assertEqual(transport.status()["mode"], "nrf905")

    def test_spurious_transmit_edge_does_not_create_a_received_frame(self):
        transport = Nrf905Transport(self.profile, self.device, self.clock)
        stop = threading.Event()
        expected = bytes(range(32))
        self.spi.rx_frame = expected
        edge_ns = round(self.clock.now * 1_000_000_000)
        self.lines.scripted_waits.extend(
            [
                DataReadyWait(False, edge_ns, "edge-without-ready-level"),
                DataReadyWait(True, edge_ns, "edge"),
            ]
        )
        self.lines.inputs["data_ready"] = True

        captured = transport.wait_for_frame(stop)

        self.assertEqual(captured.frame, expected)
        self.assertEqual(transport.status()["receive_wait"]["spurious_wake_count"], 1)

    def test_transport_status_remains_available_when_pin_read_fails(self):
        transport = Nrf905Transport(self.profile, self.device, self.clock)
        original_get = self.lines.get

        def failing_get(name):
            raise Nrf905Error("NRF905_GPIO_READ", f"cannot read {name}")

        self.lines.get = failing_get
        status = transport.status()
        self.lines.get = original_get

        self.assertEqual(status["mode"], "nrf905")
        self.assertEqual(status["pins"], {})
        self.assertEqual(status["status_error"]["code"], "NRF905_GPIO_READ")


@unittest.skipUnless(
    (AUTHORITY_ROOT / "registry/v1.json").is_file(),
    "sibling Protocol Contract checkout is required for physical service integration",
)
class PhysicalServiceTests(unittest.TestCase):
    def setUp(self):
        self.directory, self.profile = transmitting_profile()
        self.clock = ManualClock()
        self.spi = FakeSpi()
        self.lines = FakeLines()
        self.spi.lines = self.lines
        device = Nrf905Device(
            self.profile, self.spi, self.lines, sleeper=self.clock.sleep, monotonic=self.clock
        )
        self.transport = Nrf905Transport(self.profile, device, self.clock)
        self.wire = WireAdapter(AUTHORITY_ROOT)
        self.service = WorkbenchService(self.wire, carrier=self.transport)

    def tearDown(self):
        self.service.close()
        self.directory.cleanup()

    def test_service_requires_confirmation_and_sends_padded_contract_bytes(self):
        example = self.wire.resolve_example("v1-controller-beacon", "logical")
        with self.assertRaisesRegex(TransportError, "Confirm"):
            self.service.transmit(example["frame_hex"], "logical", False)

        result = self.service.transmit(example["frame_hex"], "logical", True)
        self.assertEqual(len(self.spi.tx_frame), 32)
        self.assertEqual(result["delivered"][0]["meaning"]["name"], "CONTROLLER_BEACON")
        self.assertEqual(result["delivered"][0]["capture"]["transport"], "nrf905")
        self.assertEqual(result["delivered"][0]["capture"]["direction"], "sent")
        timing = result["delivered"][0]["capture"]["timing"]
        self.assertIn("tx_completion_ms", timing)
        self.assertIn("receive_mode_reentry_ms", timing)
        self.assertIn("tx_completion_to_receive_mode_reentry_ms", timing)

    def test_service_deduplicates_named_transmit_request(self):
        example = self.wire.resolve_example("v1-controller-beacon", "logical")
        provenance = {
            "draft_id": "pp-draft-test",
            "base_identity": "fixture:v1-controller-beacon",
            "changed_fields": ["destination"],
            "changed_bytes": [3],
            "console_run_id": None,
        }
        first = self.service.transmit(
            example["frame_hex"],
            "logical",
            True,
            "validation-run-1-step-4",
            provenance,
        )
        second = self.service.transmit(
            example["frame_hex"],
            "logical",
            True,
            "validation-run-1-step-4",
            provenance,
        )

        self.assertFalse(first["replayed_result"])
        self.assertTrue(second["replayed_result"])
        self.assertEqual(first["request_id"], second["request_id"])
        self.assertEqual(first["provenance"], provenance)
        self.assertEqual(self.service.model_state()["receiver"]["sent_count"], 1)

    def test_service_rejects_conflicting_transmit_request_reuse(self):
        first = self.wire.resolve_example("v1-controller-beacon", "logical")
        second = self.wire.resolve_example("v1-node-status", "logical")
        self.service.transmit(
            first["frame_hex"],
            "logical",
            True,
            "validation-run-1-step-4",
        )

        with self.assertRaises(TransportError) as raised:
            self.service.transmit(
                second["frame_hex"],
                "logical",
                True,
                "validation-run-1-step-4",
            )
        self.assertEqual(raised.exception.code, "TRANSMIT_REQUEST_CONFLICT")

    def test_named_request_is_not_retransmitted_after_uncertain_adapter_error(self):
        example = self.wire.resolve_example("v1-controller-beacon", "logical")

        def uncertain_transmit(frame):
            raise Nrf905Error(
                "NRF905_TRANSMIT_TIMEOUT",
                "simulated uncertain transmit completion",
            )

        self.transport.device.transmit = uncertain_transmit
        initial = self.service.transmit(
            example["frame_hex"],
            "logical",
            True,
            "validation-run-1-step-uncertain",
        )
        self.assertEqual(initial["request_id"], "validation-run-1-step-uncertain")
        self.assertEqual(initial["process_instance_id"], self.service.process_instance_id)
        self.assertFalse(initial["replayed_result"])
        self.assertEqual(initial["outcome"], "unknown")
        self.assertEqual(initial["error"]["code"], "NRF905_TRANSMIT_TIMEOUT")

        recovered = self.service.transmit(
            example["frame_hex"],
            "logical",
            True,
            "validation-run-1-step-uncertain",
        )
        self.assertTrue(recovered["replayed_result"])
        self.assertEqual(recovered["outcome"], "unknown")
        self.assertEqual(
            recovered["error"]["code"],
            "NRF905_TRANSMIT_TIMEOUT",
        )

    def test_service_decodes_and_journals_exact_received_frame(self):
        expected = self.wire.resolve_example("v1-node-status", "fixed")
        self.service.start()
        self.spi.queue_receive(bytes.fromhex(expected["frame_hex"]))

        self._wait_for_journal_count(1)
        result = self.service.model_state()
        self.assertEqual(result["latest"]["meaning"]["name"], "NODE_STATUS")
        self.assertEqual(result["latest"]["received_frame_hex"], expected["frame_hex"])
        self.assertEqual(self.service.journal()["count"], 1)

    def test_receiver_captures_follow_up_frames_without_a_browser(self):
        first = self.wire.resolve_example("v1-controller-beacon", "fixed")
        second = self.wire.resolve_example("v1-node-status", "fixed")
        self.service.start()
        self.spi.queue_receive(
            bytes.fromhex(first["frame_hex"]),
            bytes.fromhex(second["frame_hex"]),
        )

        self._wait_for_journal_count(2)
        entries = self.service.journal()["entries"]
        self.assertEqual(
            [entry["received_frame_hex"] for entry in reversed(entries)],
            [first["frame_hex"], second["frame_hex"]],
        )
        self.assertEqual(self.service.model_state()["receiver"]["received_count"], 2)

    def test_receiver_reports_batch_decode_publication_and_reentry_spans(self):
        first = self.wire.resolve_example("v1-controller-beacon", "fixed")
        second = self.wire.resolve_example("v1-node-status", "fixed")
        original_inspect = self.service.wire.inspect
        original_publish = self.service.model.publish
        publish_count = 0

        def slow_inspect(frame_text, mode):
            self.clock.sleep(0.004)
            return original_inspect(frame_text, mode)

        def slow_publish(entry):
            nonlocal publish_count
            publish_count += 1
            if publish_count == 1:
                self.lines.edge_monotonic_ns = round(self.clock.now * 1_000_000_000)
                self.spi.queue_receive(bytes.fromhex(second["frame_hex"]))
            self.clock.sleep(0.006)
            return original_publish(entry)

        self.service.wire.inspect = slow_inspect
        self.service.model.publish = slow_publish
        self.lines.edge_monotonic_ns = round(self.clock.now * 1_000_000_000)
        self.service.start()
        self.spi.queue_receive(bytes.fromhex(first["frame_hex"]))

        self._wait_for_journal_count(2)
        state = self.service.model_state()
        service_metrics = state["receiver"]["service"]

        self.assertIn("batch_drain_ms", service_metrics["spans"])
        self.assertEqual(service_metrics["spans"]["decode_ms"]["median_ms"], 4.0)
        self.assertEqual(
            service_metrics["spans"]["model_publication_ms"]["median_ms"],
            6.0,
        )
        self.assertEqual(service_metrics["receiver_service_high_water_ms"], 10.0)
        self.assertEqual(service_metrics["edge_or_frame_during_processing_count"], 1)
        self.assertIn("edge_to_payload_read_ms", service_metrics["spans"])
        self.assertIn(
            "payload_read_to_receive_reentry_ms",
            service_metrics["spans"],
        )
        self.assertEqual(
            state["journal"]["latest_journal_sequence"],
            1,
        )

    def test_invalid_frame_is_retained_and_receiver_continues(self):
        valid = self.wire.resolve_example("v1-node-status", "fixed")
        self.service.start()
        self.spi.queue_receive(bytes(32), bytes.fromhex(valid["frame_hex"]))

        self._wait_for_journal_count(2)
        entries = list(reversed(self.service.journal()["entries"]))
        self.assertEqual(entries[0]["inspection_error"]["code"], "UNSUPPORTED_WIRE_GENERATION")
        self.assertEqual(entries[1]["title"], "Node status")
        self.assertEqual(self.service.model_state()["receiver"]["invalid_count"], 1)
        self.assertTrue(self.service._receiver.running)

    def test_transmit_handoff_returns_immediately_to_receive(self):
        outbound = self.wire.resolve_example("v1-controller-beacon", "logical")
        follow_up = self.wire.resolve_example("v1-node-status", "fixed")
        self.service.start()

        self.service.transmit(outbound["frame_hex"], "logical", True)
        self.spi.queue_receive(bytes.fromhex(follow_up["frame_hex"]))

        self._wait_for_journal_count(2)
        entries = list(reversed(self.service.journal()["entries"]))
        self.assertEqual([entry["capture"]["direction"] for entry in entries], ["sent", "received"])
        self.assertEqual(entries[1]["received_frame_hex"], follow_up["frame_hex"])
        self.assertEqual(self.service.model_state()["receiver"]["state"], "listening")

    def test_adapter_fault_is_published_without_a_retry_loop(self):
        self.lines.wait_error = Nrf905Error("NRF905_GPIO_WAIT", "simulated wait failure")
        self.service.start()

        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            receiver = self.service.model_state()["receiver"]
            if receiver["state"] == "faulted":
                break
            time.sleep(0.005)
        else:
            self.fail("receiver fault was not published")

        self.assertEqual(receiver["last_error"]["code"], "NRF905_GPIO_WAIT")
        self.assertEqual(receiver["fault_count"], 1)
        self.assertFalse(self.service._receiver.running)

    def test_close_is_idempotent_and_releases_hardware_once(self):
        self.service.start()
        self.service.close()
        self.service.close()
        self.assertEqual(self.lines.close_count, 1)

    def test_receiver_shutdown_is_bounded_by_the_cancellation_wait(self):
        self.service.start()
        started = time.monotonic()

        self.service.close()

        self.assertLess(time.monotonic() - started, 0.5)

    def _wait_for_journal_count(self, expected):
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            if self.service.journal()["count"] >= expected:
                return
            time.sleep(0.005)
        self.fail(f"receiver did not journal {expected} frames")


if __name__ == "__main__":
    unittest.main()
