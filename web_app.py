import os
import asyncio
import logging
import threading
import time
from collections import deque
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# Import local protocol and driver modules
from driver.nrf905 import NRF905
from packet.packet import Packet, PayloadType
from packet.payload_values import EVENT_TYPES
from decoder import decode_packet, format_address
from nodes.node import NodeType

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("web_app")

# Global node registry definition (fully decoupled from the CustomTkinter GUI)
DEFAULT_NODES = [
    {"node_type": "TASK", "friendly_name": "Simon Says", "address": 1, "config_settings": ["round_count", "round_difficulty", "num_settings"]},
    {"node_type": "TASK", "friendly_name": "Guitar Hero", "address": 2, "config_settings": ["guitar_count", "round_difficulty", "num_settings"]},
    {"node_type": "TASK", "friendly_name": "O2 Keypad", "address": 3, "config_settings": ["round_count", "round_difficulty", "num_settings"]},
    {"node_type": "TASK", "friendly_name": "Reactor A", "address": 4, "config_settings": ["round_count", "round_difficulty", "num_settings"]},
    {"node_type": "TASK", "friendly_name": "Reactor B", "address": 5, "config_settings": ["round_count", "round_difficulty", "num_settings"]},
    {"node_type": "PLAYER", "friendly_name": "Player 1", "address": 1, "config_settings": ["number_of_others", "imposter", "player_strings"]},
    {"node_type": "PLAYER", "friendly_name": "Player 2", "address": 2, "config_settings": ["number_of_others", "imposter", "player_strings"]},
]

# Map settings to their numeric indices
SETTINGS_INDEX_MAP = {
    "round_count": 1,
    "round_difficulty": 2,
    "num_settings": 3,
    "guitar_count": 1,
    "number_of_others": 1,
    "imposter": 2,
    "player_strings": 3
}

class RadioManager:
    """
    Thread-safe manager for the nRF905 transceiver.
    Orchestrates the background sniffing loop and serializes SPI hardware access.
    """
    def __init__(self):
        self.radio = NRF905(config=None)
        # Assign virtual address for the Game Controller radio (0x0201)
        self.radio.virtual_address = (NodeType.GAME_CONTROLLER.value << 8) | 1
        self.lock = threading.Lock()
        self.packet_history = deque(maxlen=100)
        self.listeners: List[asyncio.Queue] = []
        self.running = False
        self.sniff_thread: Optional[threading.Thread] = None

    def start(self):
        if self.running:
            return
        self.running = True
        self.sniff_thread = threading.Thread(target=self._sniff_loop, name="RadioSniffer", daemon=True)
        self.sniff_thread.start()
        logger.info("RadioManager started background sniffing thread.")

    def stop(self):
        self.running = False
        if self.sniff_thread:
            self.sniff_thread.join(timeout=2.0)
            self.sniff_thread = None
            logger.info("RadioManager background thread stopped.")

    def _sniff_loop(self):
        while self.running:
            try:
                # Synchronize SPI access for the rx call
                with self.lock:
                    rx_ok, raw_packet = self.radio.rx()
                
                if rx_ok and raw_packet:
                    decoded = decode_packet(raw_packet)
                    if decoded:
                        logger.info(f"Sniffed packet from {decoded['source_address']} to {decoded['destination_address']}")
                        self.packet_history.append(decoded)
                        
                        # Disseminate packet to active SSE listeners
                        for listener in list(self.listeners):
                            # Put packet in listener queue asynchronously
                            asyncio.run_coroutine_threadsafe(listener.put(decoded), loop=main_loop)
                            
                        # Rules Engine: Process TASK_FAIL events to execute player screen lockout downlinks
                        if decoded.get("payload_type") == "EVENT":
                            event_name = decoded["payload"].get("event")
                            if event_name == "TASK_FAIL":
                                player_id = decoded["payload"].get("key_1")
                                if player_id is not None:
                                    difficulty = getattr(app.state, "difficulty", "medium")
                                    if difficulty == "easy":
                                        penalty = 0
                                    elif difficulty == "hard":
                                        penalty = 15
                                    else:
                                        penalty = 5
                                        
                                    if penalty > 0:
                                        logger.info(f"RulesEngine: Player {player_id} failed task. Sending CONFIG penalty of {penalty}s (Mode: {difficulty})")
                                        p_pen = Packet(
                                            src_address=(NodeType.GAME_CONTROLLER.value << 8) | 1,
                                            dest_address=(NodeType.PLAYER.value << 8) | player_id,
                                            payload_type=PayloadType.CONFIG,
                                            timestamp=0
                                        )
                                        p_pen.stage_payload(index=3, value=penalty) # key 3 = penalty_time
                                        # Use self.transmit directly (it has lock synchronization)
                                        self.transmit(p_pen.encode(), (0xDEADBEEF).to_bytes(4, 'little'))
                            elif event_name == "SABOTAGE":
                                logger.info("RulesEngine: relaying sabotage event to all spoke nodes")
                                sabotage = Packet(
                                    src_address=(NodeType.GAME_CONTROLLER.value << 8) | 1,
                                    dest_address=0xFFFF,
                                    payload_type=PayloadType.EVENT,
                                    timestamp=0
                                )
                                sabotage.stage_payload(index=0, value=EVENT_TYPES.SABOTAGE.value)
                                self.transmit(sabotage.encode(), (0xDEADBEEF).to_bytes(4, 'little'))
            except Exception as e:
                logger.error(f"Error in radio sniffing loop: {e}", exc_info=True)
                time.sleep(1.0) # Prevent tight CPU spin on errors

    def get_config(self) -> Dict[str, Any]:
        with self.lock:
            return self.radio.read_config_human()

    def set_config(self, values: Dict[str, Any]):
        with self.lock:
            self.radio.write_config(values)
        logger.info(f"Updated radio configuration: {values}")

    def transmit(self, packet_bytes: bytes, physical_address: bytes) -> bool:
        with self.lock:
            success = self.radio.tx(packet_bytes, physical_address)
            if success:
                # If in simulation mode, broadcast and controller unicasts aren't received by the local receiver queue.
                # To ensure the Operator Console UI sniffer captures our outgoing commands, we manually decode and push them.
                from driver.nrf905 import HAS_HARDWARE
                if not HAS_HARDWARE:
                    decoded = decode_packet(packet_bytes)
                    if decoded:
                        # Skip adding SYNC polling packets to UI sniffer to avoid spamming the log table
                        if decoded["payload_type"] != "SYNC":
                            logger.info(f"Sniffed outgoing controller packet to {decoded['destination_address']}")
                            self.packet_history.append(decoded)
                            for listener in list(self.listeners):
                                asyncio.run_coroutine_threadsafe(listener.put(decoded), loop=main_loop)
            return success

# Initialize global managers
radio_manager = RadioManager()
main_loop: Optional[asyncio.AbstractEventLoop] = None

class GameCoordinator:
    """
    Central Game Controller coordinator loop (only active in Simulation Mode).
    Issues command/polling sweeps to player and task spoke nodes, requesting
    telemetry status updates and check-in logs.
    """
    def __init__(self):
        self.running = False
        self.thread: Optional[threading.Thread] = None

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._coord_loop, name="GameCoordinator", daemon=True)
        self.thread.start()
        logger.info("GameCoordinator sweep loop started.")

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)
            self.thread = None
            logger.info("GameCoordinator sweep loop stopped.")

    def _coord_loop(self):
        while self.running:
            try:
                if not hasattr(app.state, "sim_nodes") or not app.state.sim_nodes:
                    time.sleep(0.5)
                    continue
                
                # Copy list to prevent threading mutation conflicts
                nodes = list(app.state.sim_nodes)
                for node in nodes:
                    if not self.running:
                        break
                    
                    # Create controller poll sweep packet (SYNC type)
                    p = Packet(
                        src_address=(NodeType.GAME_CONTROLLER.value << 8) | 1,
                        dest_address=node.address,
                        payload_type=PayloadType.SYNC,
                        timestamp=0
                    )
                    
                    # Poll the spoke node
                    radio_manager.transmit(p.encode(), (0xDEADBEEF).to_bytes(4, 'little'))
                    
                    # 10ms gap between polling sweeps to give airwaves time to clear
                    time.sleep(0.01)
                    
            except Exception as e:
                logger.error(f"Error in GameCoordinator loop: {e}", exc_info=True)
                time.sleep(1.0)

# Initialize FastAPI App
app = FastAPI(
    title="Packet Predator Operator Console",
    description="REST API and Event Stream for monitoring and testing the Among Us IRL radio comms system."
)

# Pydantic schemas for request validation
class RadioConfigUpdate(BaseModel):
    CH_NO: int = Field(..., ge=0, le=255, description="Channel Number (0-255)")
    AUTO_RETRAN: int = Field(..., ge=0, le=1, description="Auto Retransmit (0 or 1)")
    RX_RED_PWR: int = Field(..., ge=0, le=1, description="Reduced Rx Power (0 or 1)")
    PA_PWR: int = Field(..., ge=0, le=3, description="PA Output Power (0-3)")
    HFREQ_PLL: int = Field(..., ge=0, le=1, description="Frequency Band Selection (0 or 1)")
    TX_AFW: int = Field(..., ge=1, le=4, description="Tx Address Field Width (1-4 bytes)")
    RX_AFW: int = Field(..., ge=1, le=4, description="Rx Address Field Width (1-4 bytes)")
    TX_PW: int = Field(..., ge=1, le=32, description="Tx Payload Width (1-32 bytes)")
    RX_PW: int = Field(..., ge=1, le=32, description="Rx Payload Width (1-32 bytes)")
    RX_ADDRESS: str = Field(..., pattern="^[0-9a-fA-F]{2,8}$", description="Physical Address in Hex (e.g. DEADBEEF)")
    CRC_MODE: int = Field(..., ge=0, le=1, description="CRC Mode (0=8-bit, 1=16-bit)")
    CRC_EN: int = Field(..., ge=0, le=1, description="CRC Enable (0 or 1)")
    XOF: int = Field(..., ge=0, le=4, description="Crystal Frequency Option (0-4)")
    UP_CLK_EN: int = Field(..., ge=0, le=1, description="External Clock Output Enable (0 or 1)")
    UP_CLK_FREQ: int = Field(..., ge=0, le=3, description="Clock Output Frequency (0-3)")

class SpoofPacketRequest(BaseModel):
    dest_node_type: str = Field(..., description="Destination node type enum string (e.g. TASK, PLAYER, BROADCAST)")
    dest_node_id: int = Field(..., ge=0, le=255)
    src_node_type: str = Field(..., description="Source node type enum string (e.g. GAME_CONTROLLER)")
    src_node_id: int = Field(..., ge=0, le=255)
    payload_type: str = Field(..., description="Payload Type enum name (e.g. CONFIG, EVENT, START)")
    payload_data: Dict[str, Any] = Field(default_factory=dict, description="Key-value mapping of payload data settings or event variables")

@app.on_event("startup")
async def startup_event():
    global main_loop
    main_loop = asyncio.get_running_loop()
    
    # Auto-initialize virtual spoke nodes if in simulator mode
    from driver.nrf905 import HAS_HARDWARE
    if not HAS_HARDWARE:
        from simulator import VirtualPlayerNode, VirtualTaskNode
        logger.info("Initializing virtual spoke nodes for simulation...")
        sim_nodes = [
            VirtualTaskNode(node_id=1, task_name="Simon Says"),
            VirtualTaskNode(node_id=2, task_name="Guitar Hero"),
            VirtualTaskNode(node_id=3, task_name="O2 Keypad"),
            VirtualTaskNode(node_id=4, task_name="Reactor A"),
            VirtualTaskNode(node_id=5, task_name="Reactor B"),
            VirtualPlayerNode(node_id=1, friendly_name="Alice (Impostor)", is_impostor=True),
            VirtualPlayerNode(node_id=2, friendly_name="Bob (Crewmate)", is_impostor=False),
            VirtualPlayerNode(node_id=3, friendly_name="Charlie (Crewmate)", is_impostor=False),
        ]
        for node in sim_nodes:
            node.start()
        app.state.sim_nodes = sim_nodes
        logger.info(f"Started {len(sim_nodes)} virtual spoke nodes in simulation background.")
        
        # Start game coordinator polling loop
        app.state.coordinator = GameCoordinator()
        app.state.coordinator.start()
        
        # Initialize default difficulty profile
        app.state.difficulty = "medium"
        
    radio_manager.start()

@app.on_event("shutdown")
async def shutdown_event():
    if hasattr(app.state, "coordinator"):
        app.state.coordinator.stop()
    if hasattr(app.state, "sim_nodes"):
        logger.info("Stopping virtual spoke nodes...")
        for node in app.state.sim_nodes:
            node.stop()
    radio_manager.stop()

@app.get("/api/nodes")
def get_nodes():
    """Returns the registered game nodes for configuration dropdowns."""
    return DEFAULT_NODES

@app.get("/api/config")
def get_config():
    """Fetches the active physical radio configuration from registers."""
    try:
        cfg = radio_manager.get_config()
        # Convert numeric values to nice formats for the API
        cfg["RX_ADDRESS"] = f"{cfg['RX_ADDRESS']:08X}"
        return cfg
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read radio config: {e}")

@app.post("/api/config")
def set_config(cfg: RadioConfigUpdate):
    """Updates the physical radio configuration registers."""
    try:
        update_dict = cfg.model_dump()
        update_dict["RX_ADDRESS"] = int(update_dict["RX_ADDRESS"], 16)
        update_dict["CH_NO_MSB"] = (update_dict["CH_NO"] >> 8) & 0x01
        update_dict["CH_NO"] = update_dict["CH_NO"] & 0xFF
        
        radio_manager.set_config(update_dict)
        return {"status": "success", "message": "Configuration written successfully."}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid address format. Must be hex string.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to write radio config: {e}")

@app.post("/api/spoof")
def spoof_packet(req: SpoofPacketRequest):
    """Constructs and transmits a spoofed radio packet over the air."""
    try:
        # 1. Resolve Enums
        try:
            dest_type = NodeType[req.dest_node_type] if req.dest_node_type != "BROADCAST" else None
            src_type = NodeType[req.src_node_type]
            p_type = PayloadType[req.payload_type]
        except KeyError as e:
            raise HTTPException(status_code=400, detail=f"Invalid Enum Selection: {e}")
            
        # 2. Build Header values
        dest_addr = 0xFFFF if req.dest_node_type == "BROADCAST" else (dest_type.value << 8) | req.dest_node_id
        src_addr = (src_type.value << 8) | req.src_node_id
        
        # 3. Create Packet Instance
        p = Packet(
            src_address=src_addr,
            dest_address=dest_addr,
            payload_type=p_type,
            timestamp=69 # Standard default sequence number
        )
        
        # 4. Stage Payload values based on type
        if p_type == PayloadType.EVENT:
            event_name = req.payload_data.get("event")
            if not event_name:
                raise HTTPException(status_code=400, detail="EVENT packets require an 'event' key in payload_data.")
            try:
                event_val = EVENT_TYPES[event_name].value
            except KeyError:
                raise HTTPException(status_code=400, detail=f"Invalid EVENT_TYPE: {event_name}")
            p.stage_payload(index=0, value=event_val)
            
        elif p_type == PayloadType.CONFIG:
            for setting_key, val in req.payload_data.items():
                if setting_key not in SETTINGS_INDEX_MAP:
                    raise HTTPException(status_code=400, detail=f"Unknown setting: {setting_key}")
                index = SETTINGS_INDEX_MAP[setting_key]
                # Convert numeric strings
                if isinstance(val, str) and val.isdigit():
                    val = int(val)
                p.stage_payload(index=index, value=val)
                
        # 5. Serialize and Transmit
        packet_bytes = p.encode()
        physical_address = (0xDEADBEEF).to_bytes(4, 'little')
        
        tx_success = radio_manager.transmit(packet_bytes, physical_address)
        if tx_success:
            return {"status": "success", "packet": str(p), "hex": packet_bytes.hex()}
        else:
            raise HTTPException(status_code=500, detail="Radio transmission failed (transceiver was busy).")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Transmission error: {e}")

@app.post("/api/game/start")
def start_game():
    """Broadcasts a START packet (dest 0xFFFF) from Game Controller to all nodes."""
    try:
        p = Packet(
            src_address=(NodeType.GAME_CONTROLLER.value << 8) | 1,
            dest_address=0xFFFF,
            payload_type=PayloadType.START,
            timestamp=0
        )
        packet_bytes = p.encode()
        physical_address = (0xDEADBEEF).to_bytes(4, 'little')
        tx_success = radio_manager.transmit(packet_bytes, physical_address)
        if tx_success:
            return {"status": "success", "message": "Broadcast START transmitted."}
        else:
            raise HTTPException(status_code=500, detail="Radio transmission failed.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/game/stop")
def stop_game():
    """Broadcasts a STOP packet (dest 0xFFFF) from Game Controller to all nodes."""
    try:
        p = Packet(
            src_address=(NodeType.GAME_CONTROLLER.value << 8) | 1,
            dest_address=0xFFFF,
            payload_type=PayloadType.STOP,
            timestamp=0
        )
        packet_bytes = p.encode()
        physical_address = (0xDEADBEEF).to_bytes(4, 'little')
        tx_success = radio_manager.transmit(packet_bytes, physical_address)
        if tx_success:
            return {"status": "success", "message": "Broadcast STOP transmitted."}
        else:
            raise HTTPException(status_code=500, detail="Radio transmission failed.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/stream")
async def get_packet_stream(request: Request):
    """Server-Sent Events (SSE) stream pushing packets to UI in real-time."""
    listener_queue = asyncio.Queue()
    radio_manager.listeners.append(listener_queue)
    logger.info(f"Web UI listener connected. Total clients: {len(radio_manager.listeners)}")

    async def event_generator():
        try:
            # 1. Send recent history to let the UI catch up immediately
            for packet in list(radio_manager.packet_history):
                yield f"data: {import_json(packet)}\n\n"
                
            # 2. Wait for new packets
            while True:
                # Check if client disconnected
                if await request.is_disconnected():
                    break
                packet = await listener_queue.get()
                yield f"data: {import_json(packet)}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            radio_manager.listeners.remove(listener_queue)
            logger.info(f"Web UI listener disconnected. Total clients: {len(radio_manager.listeners)}")

    def import_json(data: Any) -> str:
        import json
        return json.dumps(data)

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.get("/api/sim/map")
def get_sim_map():
    """Returns the coordinates and state parameters of all active simulated nodes."""
    if not hasattr(app.state, "sim_nodes"):
        return []
    
    from simulator import VirtualPlayerNode, VirtualTaskNode
    nodes_data = []
    for node in app.state.sim_nodes:
        data = {
            "address": f"0x{node.address:04X}",
            "node_id": node.node_id,
            "node_type": node.node_type.name,
            "x": round(node.x, 1),
            "y": round(node.y, 1),
            "battery": node.battery_pct,
            "voltage": node.voltage_mv,
            "status_mask": node.status_mask
        }
        if isinstance(node, VirtualPlayerNode):
            data["name"] = node.friendly_name
            data["state"] = node.state
            data["is_impostor"] = node.is_impostor
            data["cooldown"] = node.kill_cooldown
            data["active_task"] = node.active_task
            data["penalty_seconds"] = round(max(0.0, node.penalty_timer), 1)
        elif isinstance(node, VirtualTaskNode):
            data["name"] = node.task_name
            data["status"] = node.status
        nodes_data.append(data)
    return nodes_data

class SimResetRequest(BaseModel):
    crew_count: int = Field(..., ge=1, le=5)
    impostor_count: int = Field(..., ge=1, le=2)

@app.post("/api/sim/reset")
def reset_simulation(req: SimResetRequest):
    """Stops existing virtual node threads and starts a new custom batch of players/tasks."""
    import random
    try:
        # 1. Stop existing nodes
        if hasattr(app.state, "sim_nodes"):
            logger.info("Stopping existing simulation nodes for reset...")
            for node in app.state.sim_nodes:
                node.stop()
        
        # 2. Re-register and instantiate new nodes
        from simulator import VirtualPlayerNode, VirtualTaskNode
        logger.info(f"Regenerating simulation nodes: Crewmates: {req.crew_count}, Impostors: {req.impostor_count}")
        
        new_nodes = [
            VirtualTaskNode(node_id=1, task_name="Simon Says"),
            VirtualTaskNode(node_id=2, task_name="Guitar Hero"),
            VirtualTaskNode(node_id=3, task_name="O2 Keypad"),
            VirtualTaskNode(node_id=4, task_name="Reactor A"),
            VirtualTaskNode(node_id=5, task_name="Reactor B"),
        ]
        
        names_pool = ["Alice", "Bob", "Charlie", "David", "Eve", "Frank"]
        random.shuffle(names_pool)
        
        node_id_counter = 1
        
        # Add Impostor player node(s)
        for i in range(req.impostor_count):
            name = names_pool.pop(0) if names_pool else f"Player {node_id_counter}"
            new_nodes.append(VirtualPlayerNode(node_id=node_id_counter, friendly_name=f"{name} (Impostor)", is_impostor=True))
            node_id_counter += 1
            
        # Add Crewmate player node(s)
        for i in range(req.crew_count):
            name = names_pool.pop(0) if names_pool else f"Player {node_id_counter}"
            new_nodes.append(VirtualPlayerNode(node_id=node_id_counter, friendly_name=f"{name} (Crewmate)", is_impostor=False))
            node_id_counter += 1
            
        # 3. Start all the new nodes
        for node in new_nodes:
            node.start()
            
        app.state.sim_nodes = new_nodes
        return {"status": "success", "message": f"Simulation reset. Started {len(new_nodes)} nodes."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Reset failed: {e}")

class SimDifficultyRequest(BaseModel):
    difficulty: str = Field(..., description="Difficulty profile: easy, medium, hard")

@app.post("/api/sim/difficulty")
def set_simulation_difficulty(req: SimDifficultyRequest):
    """Updates the simulated game mode/difficulty profile."""
    if req.difficulty not in ["easy", "medium", "hard"]:
        raise HTTPException(status_code=400, detail="Invalid difficulty level.")
    app.state.difficulty = req.difficulty
    logger.info(f"Simulation difficulty updated to: {req.difficulty}")
    return {"status": "success", "difficulty": req.difficulty}

class SimTriggerRequest(BaseModel):
    action: str = Field(..., description="Action to trigger (meeting, kill, sabotage, complete_task)")
    target_id: Optional[int] = Field(None, ge=0, le=255, description="Target Node ID for player or task actions")

@app.post("/api/sim/trigger")
def trigger_simulation_action(req: SimTriggerRequest):
    """Forces an interactive state transition on a node or the global simulation."""
    if not hasattr(app.state, "sim_nodes"):
        raise HTTPException(status_code=400, detail="Simulation is not active.")
        
    try:
        from simulator import VirtualPlayerNode, VirtualTaskNode
        
        if req.action == "meeting":
            # Broadcast Emergency Meeting
            p = Packet(
                src_address=(NodeType.GAME_CONTROLLER.value << 8) | 1,
                dest_address=0xFFFF,
                payload_type=PayloadType.EVENT,
                timestamp=0
            )
            p.stage_payload(index=0, value=EVENT_TYPES.MEETING_START.value)
            radio_manager.transmit(p.encode(), (0xDEADBEEF).to_bytes(4, 'little'))
            
            # Instantly teleport all active players to Cafeteria and set state to MEETING
            for node in app.state.sim_nodes:
                if isinstance(node, VirtualPlayerNode):
                    if node.state in ["ALIVE", "DEAD", "GHOST", "LOBBY"]:
                        node.begin_meeting()
            return {"status": "success", "message": "Emergency Meeting signal broadcasted."}
            
        elif req.action == "kill":
            for node in app.state.sim_nodes:
                if isinstance(node, VirtualPlayerNode) and node.node_id == req.target_id:
                    node.state = "DEAD"
                    # Broadcast kill event to notify controller/players
                    p = Packet(
                        src_address=node.address,
                        dest_address=0xFFFF,
                        payload_type=PayloadType.EVENT,
                        timestamp=0
                    )
                    p.stage_payload(index=0, value=EVENT_TYPES.PLAYER_DEATH.value) # Dead state code
                    radio_manager.transmit(p.encode(), (0xDEADBEEF).to_bytes(4, 'little'))
                    return {"status": "success", "message": f"{node.friendly_name} has been eliminated."}
            raise HTTPException(status_code=404, detail="Player ID not found.")
            
        elif req.action == "sabotage":
            for node in app.state.sim_nodes:
                if isinstance(node, VirtualPlayerNode) and node.is_impostor:
                    node.queue_sabotage()
                    return {"status": "success", "message": f"Sabotage event triggered by {node.friendly_name}."}
            raise HTTPException(status_code=400, detail="No active impostors to execute sabotage.")
            
        elif req.action == "complete_task":
            for node in app.state.sim_nodes:
                if isinstance(node, VirtualPlayerNode) and node.node_id == req.target_id:
                    if node.active_task:
                        node.task_timer = 0.01 # Solves on next tick
                        return {"status": "success", "message": f"Task completed for {node.friendly_name}."}
                    else:
                        return {"status": "error", "message": "Player is not currently working on any task."}
            raise HTTPException(status_code=404, detail="Player ID not found.")
            
        raise HTTPException(status_code=400, detail=f"Unsupported action: {req.action}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Mount frontend files folder
web_dir = os.path.join(os.path.dirname(__file__), "web")
if os.path.exists(web_dir):
    app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")
else:
    logger.warning("Frontend directory '/web' not found. Static files serving disabled.")

if __name__ == "__main__":
    import uvicorn
    logger.info("Starting web server on http://localhost:8000")
    uvicorn.run("web_app:app", host="0.0.0.0", port=8000, reload=True)
