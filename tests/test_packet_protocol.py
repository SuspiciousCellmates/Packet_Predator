import unittest

from decoder import decode_packet
from nodes.node import NodeType
from packet.packet import Packet, PayloadType
from packet.payload_values import EVENT_TYPES


class PacketProtocolTests(unittest.TestCase):
    def test_event_round_trip(self):
        packet = Packet(
            src_address=(NodeType.TASK.value << 8) | 3,
            dest_address=(NodeType.GAME_CONTROLLER.value << 8) | 1,
            payload_type=PayloadType.EVENT,
            timestamp=7,
        )
        packet.stage_payload(0, EVENT_TYPES.TASK_FAIL.value)
        packet.stage_payload(1, 2)

        encoded = packet.encode()
        decoded = decode_packet(encoded)

        self.assertEqual(len(encoded), Packet.PACKET_SIZE)
        self.assertEqual(decoded["payload_type"], "EVENT")
        self.assertEqual(decoded["payload"]["event"], "TASK_FAIL")
        self.assertEqual(decoded["payload"]["key_1"], 2)
        self.assertEqual(decoded["context_address"], "UPLINK")

    def test_raw_diagnostic_payload_round_trip(self):
        payload = bytearray(Packet.PAYLOAD_SIZE)
        payload[0] = 84
        payload[1:3] = (4030).to_bytes(2, "little")
        payload[3] = 3
        payload[4] = 0b10101
        packet = Packet(
            src_address=(NodeType.PLAYER.value << 8) | 4,
            dest_address=(NodeType.GAME_CONTROLLER.value << 8) | 1,
            payload_type=PayloadType.DIAGNOSTIC,
            timestamp=0,
            staged_payload=payload,
        )

        decoded = decode_packet(packet.encode())

        self.assertEqual(decoded["payload"]["battery_percentage"], 84)
        self.assertEqual(decoded["payload"]["voltage_mv"], 4030)
        self.assertTrue(decoded["payload"]["status_flags"]["nfc_ok"])
        self.assertFalse(decoded["payload"]["status_flags"]["display_ok"])

    def test_payload_size_is_enforced(self):
        packet = Packet(
            src_address=1,
            dest_address=2,
            payload_type=PayloadType.CONFIG,
            timestamp=0,
            staged_payload=b"x" * (Packet.PAYLOAD_SIZE + 1),
        )

        with self.assertRaises(ValueError):
            packet.encode()


if __name__ == "__main__":
    unittest.main()
