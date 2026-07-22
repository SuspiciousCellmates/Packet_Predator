import json
import tempfile
import unittest
from pathlib import Path

from packet_predator.adapters.nrf905 import Nrf905Device, Nrf905Error, configuration_bytes
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

    def set(self, name, active):
        self.outputs[name] = active
        self.history.append((name, active))
        if name == "trx_ce" and active and self.outputs["tx_en"]:
            self.inputs["data_ready"] = True
        if name == "tx_en" and not active:
            self.inputs["data_ready"] = False

    def get(self, name):
        return self.inputs[name]

    def close(self):
        self.closed = True


class FakeSpi:
    def __init__(self):
        self.configuration = bytes(10)
        self.tx_address = b""
        self.tx_frame = b""
        self.rx_frame = bytes(32)
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
            return bytes([0]) + self.rx_frame[: len(outgoing) - 1]
        raise AssertionError(f"unexpected SPI command 0x{command:02x}")

    def close(self):
        self.closed = True


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


class DeviceTests(unittest.TestCase):
    def setUp(self):
        self.directory, self.profile = transmitting_profile()
        self.clock = ManualClock()
        self.spi = FakeSpi()
        self.lines = FakeLines()
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

    def test_transmit_writes_address_and_exact_frame(self):
        self.device.start()
        frame = bytes(reversed(range(32)))
        result = self.device.transmit(frame)
        self.assertEqual(self.spi.tx_address, self.profile.radio.address)
        self.assertEqual(self.spi.tx_frame, frame)
        self.assertEqual(result["frame_hex"], frame.hex())
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
        captured = transport.poll()[0]
        self.assertEqual(captured.frame, bytes(range(32)))
        self.assertEqual(captured.direction, "received")
        self.assertEqual(captured.frame_mode, "fixed")
        self.assertEqual(transport.status()["mode"], "nrf905")


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
        device = Nrf905Device(
            self.profile, self.spi, self.lines, sleeper=self.clock.sleep, monotonic=self.clock
        )
        self.transport = Nrf905Transport(self.profile, device, self.clock)
        self.wire = WireAdapter(AUTHORITY_ROOT)
        self.service = WorkbenchService(self.wire, carrier=self.transport)

    def tearDown(self):
        self.transport.close()
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

    def test_service_decodes_and_journals_exact_received_frame(self):
        expected = self.wire.resolve_example("v1-node-status", "fixed")
        self.spi.rx_frame = bytes.fromhex(expected["frame_hex"])
        self.lines.inputs["data_ready"] = True

        result = self.service.poll_physical()
        self.assertEqual(result["delivered"][0]["meaning"]["name"], "NODE_STATUS")
        self.assertEqual(result["delivered"][0]["received_frame_hex"], expected["frame_hex"])
        self.assertEqual(self.service.journal()["count"], 1)


if __name__ == "__main__":
    unittest.main()
