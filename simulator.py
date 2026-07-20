import math
import random
import struct
import threading
import time
import logging
from typing import Dict, List, Optional, Tuple

from driver.nrf905 import NRF905
from driver.virtual_airwaves import airwaves
from packet.packet import Packet, PayloadType
from nodes.node import NodeType
from packet.payload_values import EVENT_TYPES

logger = logging.getLogger("simulator")

def decode_payload(payload_bytes: bytes) -> Dict[int, int]:
    """Helper to parse key-value pairs from raw payload bytes."""
    decoded = {}
    i = 0
    while i < len(payload_bytes):
        key_byte = payload_bytes[i]
        # Padding check
        if key_byte == 0 and all(b == 0 for b in payload_bytes[i:]):
            break
        i += 1
        if i + 2 <= len(payload_bytes):
            val = struct.unpack("<H", payload_bytes[i:i+2])[0]
            i += 2
            decoded[key_byte] = val
        else:
            break
    return decoded

# Grid Coordinates
COORDINATES = {
    "CAFETERIA": (50.0, 50.0),
    "ELECTRICAL": (10.0, 20.0),   # Simon Says
    "SHIELDS": (90.0, 80.0),      # Guitar Hero
    "O2": (70.0, 30.0),           # O2 Keypad
    "REACTOR_A": (20.0, 80.0),
    "REACTOR_B": (30.0, 80.0)
}

TASK_NODE_IDS = {
    "ELECTRICAL": 1,
    "SHIELDS": 2,
    "O2": 3,
    "REACTOR_A": 4,
    "REACTOR_B": 5,
}

class VirtualSpokeNode:
    """Base class for all simulated spoke nodes (badges and task panels)."""
    def __init__(self, node_id: int, node_type: NodeType, x: float, y: float):
        self.node_id = node_id
        self.node_type = node_type
        self.address = (node_type.value << 8) | node_id
        self.x = x
        self.y = y
        self.running = False
        self.thread: Optional[threading.Thread] = None
        
        # Initialize virtual radio and set its Layer 3 address
        self.radio = NRF905(config=None)
        self.radio.virtual_address = self.address
        
        # Telemetry Queue (packets to send on the next poll)
        self.tx_queue: List[bytes] = []
        
        # Background health properties
        self.battery_pct = 100
        self.voltage_mv = 4100
        self.status_mask = 0x1F # All systems OK (bits 0-4)

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._run_loop, name=f"Node_{hex(self.address)}", daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)
            self.thread = None
        self.radio.cleanup()

    def _run_loop(self):
        while self.running:
            try:
                self.tick()
                # Check for incoming packets (Polls or Broadcasts)
                rx_ok, packet = self.radio.rx()
                if rx_ok and packet:
                    self.handle_packet(packet)
            except Exception as e:
                logger.error(f"Error in node {hex(self.address)} loop: {e}", exc_info=True)
                time.sleep(1.0)
            time.sleep(0.05) # 50ms tick rate

    def tick(self):
        """Override in subclasses to update local physics and states."""
        pass

    def handle_packet(self, data: bytes):
        # Extract headers
        dest_addr, src_addr, p_type_val, timestamp = struct.unpack("<HHBB", data[:6])
        
        # 1. Listen to Broadcasts
        if dest_addr == 0xFFFF:
            try:
                p_type = PayloadType(p_type_val)
                self.handle_broadcast(p_type, data[6:])
            except ValueError:
                pass
            return

        # 2. Check if packet is a Poll or command explicitly for this node
        if dest_addr == self.address:
            try:
                p_type = PayloadType(p_type_val)
                # Any packet from the Game Controller acts as a Poll response trigger
                if src_addr == (NodeType.GAME_CONTROLLER.value << 8) | 1:
                    self.respond_to_poll(p_type, data[6:])
            except ValueError:
                pass

    def handle_broadcast(self, p_type: PayloadType, payload: bytes):
        """Handle global game state changes (START, STOP, MEETING, SABOTAGE)."""
        pass

    def respond_to_poll(self, p_type: PayloadType, payload: bytes):
        """Called when polled by the controller. Transmits pending telemetry or a heartbeat."""
        if self.tx_queue:
            # Send the next event in queue
            packet_to_send = self.tx_queue.pop(0)
            self.radio.tx(packet_to_send, (NodeType.GAME_CONTROLLER.value << 8) | 1)
        else:
            # Send standard Diagnostic Heartbeat
            self.battery_pct = max(10, self.battery_pct - random.choice([0, 0, 1])) # slow discharge
            self.voltage_mv = int(3500 + (self.battery_pct / 100.0) * 700)
            
            p = Packet(
                src_address=self.address,
                dest_address=(NodeType.GAME_CONTROLLER.value << 8) | 1,
                payload_type=PayloadType.DIAGNOSTIC,
                timestamp=0
            )
            # Pack battery (1B), voltage (2B), rssi (1B), status (1B)
            p_data = bytearray(26)
            p_data[0] = self.battery_pct
            p_data[1:3] = struct.pack("<H", self.voltage_mv)
            p_data[3] = 4 # RSSI Max (4 stars)
            p_data[4] = self.status_mask
            
            p.payload = bytes(p_data)
            self.radio.tx(p.encode(), (NodeType.GAME_CONTROLLER.value << 8) | 1)

class VirtualPlayerNode(VirtualSpokeNode):
    """Simulates a Crewmate or Impostor moving on the 2D grid."""
    def __init__(self, node_id: int, friendly_name: str, is_impostor: bool):
        # Start players in the Cafeteria
        super().__init__(node_id, NodeType.PLAYER, COORDINATES["CAFETERIA"][0], COORDINATES["CAFETERIA"][1])
        self.friendly_name = friendly_name
        self.is_impostor = is_impostor
        
        # State: LOBBY, ALIVE, DEAD, GHOST, MEETING
        self.state = "LOBBY"
        self.pre_meeting_state: Optional[str] = None
        
        # Pathfinding targets
        self.target_x, self.target_y = COORDINATES["CAFETERIA"]
        self.speed = 1.5 # Units per tick
        
        # Task Tracking
        self.tasks: List[str] = ["ELECTRICAL", "SHIELDS", "O2", "REACTOR_A", "REACTOR_B"] # Nodes they must visit
        self.active_task: Optional[str] = None
        self.task_timer = 0.0
        self.penalty_timer = 0.0
        
        # Impostor specific
        self.kill_cooldown = 0
        self.sabotage_timer = 30.0 # Time until next sabotage
        
        # Registry mapping
        self.lobby_beacon_timer = random.uniform(1.0, 3.0)

    def tick(self):
        # 1. Beacons during Lobby Registration
        if self.state == "LOBBY":
            self.lobby_beacon_timer -= 0.05
            if self.lobby_beacon_timer <= 0:
                self.lobby_beacon_timer = 4.0 # send every 4 seconds
                p = Packet(
                    src_address=self.address,
                    dest_address=0xFFFF,
                    payload_type=PayloadType.LOBBY_DISCOVERY,
                    timestamp=0
                )
                p_data = bytearray(26)
                p_data[0] = self.node_id
                p_data[1] = self.node_type.value
                p.payload = bytes(p_data)
                self.radio.tx(p.encode(), 0xFFFF)
            return

        if self.state in ["DEAD", "MEETING"]:
            # Dead players or meeting players don't move or do tasks
            return
            
        # Handle lock penalty on failure
        if self.penalty_timer > 0:
            self.penalty_timer -= 0.05
            return

        # If working on a task, spend the tick working instead of walking
        if self.active_task and self.task_timer > 0:
            self.work_on_task()
            return

        # 2. Movement Interpolation
        dx = self.target_x - self.x
        dy = self.target_y - self.y
        dist = math.hypot(dx, dy)
        
        if dist > self.speed:
            self.x += (dx / dist) * self.speed
            self.y += (dy / dist) * self.speed
        else:
            self.x = self.target_x
            self.y = self.target_y
            self.arrive_at_target()

        # 3. Impostor Sabotage / Kill checks
        if self.state == "ALIVE" and self.is_impostor:
            if self.kill_cooldown > 0:
                self.kill_cooldown = max(0, self.kill_cooldown - 1)
            
            self.sabotage_timer -= 0.05
            if self.sabotage_timer <= 0:
                self.sabotage_timer = 60.0 # Sabotage every 60s
                self.queue_sabotage()

    def arrive_at_target(self):
        if self.state == "GHOST" and not self.tasks:
            return # Ghosts with no tasks just sit out-of-bounds

        # Arrived at a task
        if self.active_task and self.task_timer <= 0:
            logger.info(f"{self.friendly_name} checking into {self.active_task}")
            
            task_type = NodeType.TASK.value
            task_id = TASK_NODE_IDS[self.active_task]
            task_addr = (task_type << 8) | task_id
            
            # Transmit event directly to Task Node to update its local register
            p_task = Packet(
                src_address=self.address,
                dest_address=task_addr,
                payload_type=PayloadType.EVENT,
                timestamp=0
            )
            p_task.stage_payload(index=0, value=EVENT_TYPES.CHECK_IN.value)
            self.radio.tx(p_task.encode(), task_addr)
            
            # Start working timer (takes 4 seconds)
            self.task_timer = 4.0

    def work_on_task(self):
        if self.task_timer > 0:
            self.task_timer -= 0.05
            if self.task_timer <= 0:
                # Task finished! 90% success, 10% fail to test penalty locks
                success = random.random() > 0.1
                task_type = NodeType.TASK.value
                task_id = TASK_NODE_IDS[self.active_task]
                task_addr = (task_type << 8) | task_id
                
                # Local status for Task Node
                p_task = Packet(
                    src_address=self.address,
                    dest_address=task_addr,
                    payload_type=PayloadType.EVENT,
                    timestamp=0
                )
                
                if success:
                    logger.info(f"{self.friendly_name} completed task {self.active_task}")
                    p_task.stage_payload(index=0, value=EVENT_TYPES.COMPLETED.value)
                    self.tasks.remove(self.active_task)
                else:
                    logger.warning(f"{self.friendly_name} failed puzzle at {self.active_task}")
                    p_task.stage_payload(index=0, value=EVENT_TYPES.TASK_FAIL.value)
                    
                self.radio.tx(p_task.encode(), task_addr)
                
                self.active_task = None
                self.choose_next_action()

    def choose_next_action(self):
        if not self.tasks:
            # All tasks complete: go wander in the Cafeteria
            self.target_x, self.target_y = COORDINATES["CAFETERIA"]
            return

        # Choose next task
        self.active_task = random.choice(self.tasks)
        self.target_x, self.target_y = COORDINATES[self.active_task]

    def queue_sabotage(self):
        p = Packet(
            src_address=self.address,
            dest_address=(NodeType.GAME_CONTROLLER.value << 8) | 1,
            payload_type=PayloadType.EVENT,
            timestamp=0
        )
        # Trigger O2 Sabotage (code 3)
        p.stage_payload(index=0, value=EVENT_TYPES.SABOTAGE.value)
        self.tx_queue.append(p.encode())

    def begin_meeting(self):
        if self.state != "MEETING":
            self.pre_meeting_state = self.state
        self.state = "MEETING"
        self.x, self.y = COORDINATES["CAFETERIA"]

    def end_meeting(self):
        if self.state != "MEETING":
            return
        self.state = self.pre_meeting_state or "ALIVE"
        self.pre_meeting_state = None
        if self.state == "ALIVE":
            self.choose_next_action()

    def handle_broadcast(self, p_type: PayloadType, payload: bytes):
        if p_type == PayloadType.START:
            self.state = "ALIVE"
            self.pre_meeting_state = None
            self.choose_next_action()
        elif p_type == PayloadType.STOP:
            self.state = "LOBBY"
            self.pre_meeting_state = None
            self.target_x, self.target_y = COORDINATES["CAFETERIA"]
        elif p_type == PayloadType.EVENT:
            # Check for Emergency Meetings
            decoded = decode_payload(payload)
            event_val = decoded.get(0)
            if event_val == EVENT_TYPES.MEETING_START.value: # MEETING_START signals meeting start
                self.begin_meeting()
            elif event_val == EVENT_TYPES.MEETING_END.value: # MEETING_END signals meeting end
                self.end_meeting()

    def respond_to_poll(self, p_type: PayloadType, payload: bytes):
        # If we receive a config command to LOCK our screen (penalty)
        if p_type == PayloadType.CONFIG:
            decoded = decode_payload(payload)
            if 3 in decoded:
                val = decoded[3]
                self.penalty_timer = float(val)
                logger.info(f"{self.friendly_name} screen locked for {val} seconds.")
                
        # Run standard poll response
        super().respond_to_poll(p_type, payload)

class VirtualTaskNode(VirtualSpokeNode):
    """Simulates physical Task Nodes (Simon Says, Guitar Hero, O2 Keypad, Reactor Panels)."""
    def __init__(self, node_id: int, task_name: str):
        if task_name == "Simon Says":
            coord_key = "ELECTRICAL"
        elif task_name == "Guitar Hero":
            coord_key = "SHIELDS"
        elif task_name == "O2 Keypad":
            coord_key = "O2"
        elif task_name == "Reactor A":
            coord_key = "REACTOR_A"
        elif task_name == "Reactor B":
            coord_key = "REACTOR_B"
        else:
            coord_key = "CAFETERIA"
        super().__init__(node_id, NodeType.TASK, COORDINATES[coord_key][0], COORDINATES[coord_key][1])
        self.task_name = task_name
        self.status = 0 # 0=Idle, 1=Active, 2=Complete, 3=Locked, 4=Sabotage Target
        self.game_started = False
        
        # Lobby Discovery Timer
        self.lobby_beacon_timer = random.uniform(1.0, 3.0)

    def tick(self):
        # 1. Beacons during Lobby Registration
        if not self.game_started:
            # Send periodic discovery beacons in lobby
            self.lobby_beacon_timer -= 0.05
            if self.lobby_beacon_timer <= 0:
                self.lobby_beacon_timer = 5.0
                p = Packet(
                    src_address=self.address,
                    dest_address=0xFFFF,
                    payload_type=PayloadType.LOBBY_DISCOVERY,
                    timestamp=0
                )
                p_data = bytearray(26)
                p_data[0] = self.node_id
                p_data[1] = self.node_type.value
                p.payload = bytes(p_data)
                self.radio.tx(p.encode(), 0xFFFF)

    def handle_packet(self, data: bytes):
        dest_addr, src_addr, p_type_val, timestamp = struct.unpack("<HHBB", data[:6])
        if dest_addr == self.address:
            try:
                p_type = PayloadType(p_type_val)
                if p_type == PayloadType.EVENT:
                    decoded = decode_payload(data[6:])
                    event_val = decoded.get(0)
                    player_id = src_addr & 0xFF
                    
                    if event_val == EVENT_TYPES.CHECK_IN.value:
                        self.status = 1 # Active
                        # Queue controller telemetry report
                        p_ctrl = Packet(
                            src_address=self.address,
                            dest_address=(NodeType.GAME_CONTROLLER.value << 8) | 1,
                            payload_type=PayloadType.EVENT,
                            timestamp=0
                        )
                        p_ctrl.stage_payload(index=0, value=EVENT_TYPES.CHECK_IN.value)
                        p_ctrl.stage_payload(index=1, value=player_id)
                        self.tx_queue.append(p_ctrl.encode())
                        
                    elif event_val == EVENT_TYPES.COMPLETED.value:
                        self.status = 2 # Complete
                        # Queue controller telemetry report
                        p_ctrl = Packet(
                            src_address=self.address,
                            dest_address=(NodeType.GAME_CONTROLLER.value << 8) | 1,
                            payload_type=PayloadType.EVENT,
                            timestamp=0
                        )
                        p_ctrl.stage_payload(index=0, value=EVENT_TYPES.COMPLETED.value)
                        p_ctrl.stage_payload(index=1, value=player_id)
                        self.tx_queue.append(p_ctrl.encode())
                        
                    elif event_val == EVENT_TYPES.TASK_FAIL.value:
                        self.status = 3 # Locked
                        # Queue controller telemetry report
                        p_ctrl = Packet(
                            src_address=self.address,
                            dest_address=(NodeType.GAME_CONTROLLER.value << 8) | 1,
                            payload_type=PayloadType.EVENT,
                            timestamp=0
                        )
                        p_ctrl.stage_payload(index=0, value=EVENT_TYPES.TASK_FAIL.value)
                        p_ctrl.stage_payload(index=1, value=player_id)
                        self.tx_queue.append(p_ctrl.encode())
            except Exception as e:
                logger.error(f"Error in VirtualTaskNode.handle_packet: {e}", exc_info=True)
        super().handle_packet(data)

    def handle_broadcast(self, p_type: PayloadType, payload: bytes):
        if p_type == PayloadType.START:
            self.status = 0 # reset to idle
            self.game_started = True
        elif p_type == PayloadType.STOP:
            self.status = 0
            self.game_started = False
        elif p_type == PayloadType.EVENT:
            decoded = decode_payload(payload)
            event_val = decoded.get(0)
            if event_val == EVENT_TYPES.SABOTAGE.value:
                # Lock normal tasks during sabotages
                self.status = 3 # Locked
            elif event_val == EVENT_TYPES.MEETING_END.value: # Sabotage resolved/Meeting resume
                if self.status == 3:
                    self.status = 0 # Restore to idle

    def respond_to_poll(self, p_type: PayloadType, payload: bytes):
        # Pending state changes take priority; otherwise send the standard
        # diagnostic heartbeat used by every simulated spoke node.
        super().respond_to_poll(p_type, payload)
