import unittest

import driver.nrf905 as nrf905_module
from decoder import decode_packet
from driver.virtual_airwaves import airwaves
from nodes.node import NodeType
from packet.packet import Packet, PayloadType
from packet.payload_values import EVENT_TYPES
from simulator import VirtualPlayerNode, VirtualTaskNode, decode_payload


class SimulatorTests(unittest.TestCase):
    def setUp(self):
        self.original_hardware_state = nrf905_module.HAS_HARDWARE
        nrf905_module.HAS_HARDWARE = False
        self.nodes = []

    def tearDown(self):
        for node in self.nodes:
            node.stop()
        airwaves.unregister((NodeType.GAME_CONTROLLER.value << 8) | 1)
        nrf905_module.HAS_HARDWARE = self.original_hardware_state

    def test_player_routes_check_in_to_matching_task_node(self):
        task = VirtualTaskNode(node_id=3, task_name="O2 Keypad")
        player = VirtualPlayerNode(node_id=9, friendly_name="Tester", is_impostor=False)
        self.nodes.extend((task, player))
        player.active_task = "O2"

        player.arrive_at_target()
        received = airwaves.receive(task.address)

        self.assertIsNotNone(received)
        self.assertEqual(decode_payload(received[6:])[0], EVENT_TYPES.CHECK_IN.value)

    def test_task_sends_queued_event_before_heartbeat(self):
        controller_address = (NodeType.GAME_CONTROLLER.value << 8) | 1
        airwaves.register(controller_address)
        task = VirtualTaskNode(node_id=2, task_name="Guitar Hero")
        self.nodes.append(task)
        event = Packet(
            src_address=task.address,
            dest_address=controller_address,
            payload_type=PayloadType.EVENT,
            timestamp=0,
        )
        event.stage_payload(0, EVENT_TYPES.TASK_FAIL.value)
        event.stage_payload(1, 4)
        task.tx_queue.append(event.encode())

        task.respond_to_poll(PayloadType.SYNC, b"")
        decoded = decode_packet(airwaves.receive(controller_address))

        self.assertEqual(decoded["payload"]["event"], "TASK_FAIL")
        self.assertEqual(decoded["payload"]["key_1"], 4)
        self.assertEqual(task.tx_queue, [])

    def test_task_processes_broadcast_state_changes(self):
        task = VirtualTaskNode(node_id=5, task_name="Reactor B")
        self.nodes.append(task)
        controller_address = (NodeType.GAME_CONTROLLER.value << 8) | 1
        start = Packet(
            src_address=controller_address,
            dest_address=0xFFFF,
            payload_type=PayloadType.START,
            timestamp=0,
        )
        sabotage = Packet(
            src_address=controller_address,
            dest_address=0xFFFF,
            payload_type=PayloadType.EVENT,
            timestamp=0,
        )
        sabotage.stage_payload(0, EVENT_TYPES.SABOTAGE.value)

        task.handle_packet(start.encode())
        task.handle_packet(sabotage.encode())

        self.assertTrue(task.game_started)
        self.assertEqual(task.status, 3)

    def test_meeting_does_not_resurrect_dead_player(self):
        player = VirtualPlayerNode(node_id=8, friendly_name="Ghost", is_impostor=False)
        self.nodes.append(player)
        player.state = "DEAD"

        player.begin_meeting()
        player.end_meeting()

        self.assertEqual(player.state, "DEAD")


if __name__ == "__main__":
    unittest.main()
