import unittest

from decoder import decode_packet
from packet.packet import Packet, PayloadType


class V0CharacterizationTests(unittest.TestCase):
    def test_documented_event_frame_round_trips_exactly(self):
        frame_hex = "0102030402070008000102000000000000000000000000000000000000000000"
        frame = bytes.fromhex(frame_hex)

        decoded = decode_packet(frame)
        packet = Packet(
            src_address=0x0403,
            dest_address=0x0201,
            payload_type=PayloadType.EVENT,
            timestamp=7,
        )
        packet.stage_payload(0, 8)
        packet.stage_payload(1, 2)

        self.assertEqual(packet.encode().hex(), frame_hex)
        self.assertEqual(decoded["payload"], {"event": "TASK_FAIL", "key_1": 2})

    def test_contextual_config_key_collision_is_preserved(self):
        frame = bytes.fromhex(
            "0104010201450102000000000000000000000000000000000000000000000000"
        )

        decoded = decode_packet(frame)

        self.assertEqual(decoded["payload"], {"another_task_value": 2})
        self.assertNotIn("round_count", decoded["payload"])

    def test_invalid_frame_length_is_rejected(self):
        self.assertIsNone(decode_packet(bytes(31)))
        self.assertIsNone(decode_packet(bytes(33)))

    def test_type_five_is_python_lobby_discovery(self):
        frame = bytes.fromhex(
            "0102030405000903000000000000000000000000000000000000000000000000"
        )

        decoded = decode_packet(frame)

        self.assertEqual(decoded["payload_type"], "LOBBY_DISCOVERY")
        self.assertEqual(decoded["payload"], {"node_id": 9, "node_type": "PLAYER"})


if __name__ == "__main__":
    unittest.main()
