import struct
from typing import Optional, Dict, Any
from packet.packet import PayloadType
from packet.payload_values import EVENT_TYPES, VALID_CONFIG_SETTINGS
from nodes.node import NodeType

def format_address(address: int) -> str:
    if address == 0xFFFF:
        return "Broadcast (0xFFFF)"
    
    node_id = address & 0xFF
    node_type_val = (address >> 8) & 0xFF
    
    try:
        node_type_name = NodeType(node_type_val).name
    except ValueError:
        node_type_name = f"UNKNOWN_TYPE_{node_type_val}"
        
    return f"{node_type_name} #{node_id} ({hex(address)})"

def decode_packet(packet_bytes: bytes) -> Optional[Dict[str, Any]]:
    # Packet must be exactly 32 bytes
    if len(packet_bytes) != 32:
        return None
        
    # Unpack the 6-byte header: Dest (2B), Src (2B), Type (1B), Timestamp (1B)
    dest_address, src_address, payload_type_val, timestamp = struct.unpack("<HHBB", packet_bytes[:6])
    
    try:
        payload_type = PayloadType(payload_type_val).name
    except ValueError:
        payload_type = f"UNKNOWN ({payload_type_val})"
        
    payload_bytes = packet_bytes[6:]
    
    # Reverse mapping for config settings to make the keys human readable
    reverse_config = {v: k for k, v in VALID_CONFIG_SETTINGS.items()}
    
    decoded_payload = {}
    
    if payload_type == "DIAGNOSTIC":
        if len(payload_bytes) >= 5:
            battery_pct = payload_bytes[0]
            voltage_mv = struct.unpack("<H", payload_bytes[1:3])[0]
            rssi = payload_bytes[3]
            status_mask = payload_bytes[4]
            decoded_payload = {
                "battery_percentage": battery_pct,
                "voltage_mv": voltage_mv,
                "rssi": rssi,
                "status_mask": status_mask,
                "status_flags": {
                    "nfc_ok": bool(status_mask & 0x01),
                    "display_ok": bool(status_mask & 0x02),
                    "radio_spi_ok": bool(status_mask & 0x04),
                    "audio_ok": bool(status_mask & 0x08),
                    "haptic_ok": bool(status_mask & 0x10)
                }
            }
    elif payload_type == "LOBBY_REGISTRATION":
        if len(payload_bytes) >= 2:
            player_id = payload_bytes[0]
            # Decode trailing string mapping
            name_bytes = payload_bytes[1:]
            name_len = 0
            for b in name_bytes:
                if b == 0:
                    break
                name_len += 1
            player_name = name_bytes[:name_len].decode("utf-8", errors="ignore")
            decoded_payload = {
                "player_id": player_id,
                "player_name": player_name
            }
    elif payload_type == "LOBBY_DISCOVERY":
        if len(payload_bytes) >= 2:
            node_id = payload_bytes[0]
            node_type_val = payload_bytes[1]
            try:
                node_type_name = NodeType(node_type_val).name
            except ValueError:
                node_type_name = f"UNKNOWN ({node_type_val})"
            decoded_payload = {
                "node_id": node_id,
                "node_type": node_type_name
            }
    else:
        # Standard Key-Value pair decoder
        i = 0
        while i < len(payload_bytes):
            key_byte = payload_bytes[i]
            
            # If we hit a null byte and all remaining bytes are null, it's just padding
            if key_byte == 0 and all(b == 0 for b in payload_bytes[i:]):
                break
                
            i += 1
            
            # In our protocol, payload values are typically packed as 2-byte integers (<H)
            if i + 2 <= len(payload_bytes):
                val = struct.unpack("<H", payload_bytes[i:i+2])[0]
                i += 2
                
                # Map key to human-readable names if applicable
                if payload_type in ["CONFIG", "SYNC"] and key_byte in reverse_config:
                    decoded_payload[reverse_config[key_byte]] = val
                elif payload_type == "EVENT" and key_byte == 0:
                    try:
                        event_name = EVENT_TYPES(val).name
                        decoded_payload["event"] = event_name
                    except ValueError:
                        decoded_payload["event"] = f"UNKNOWN_EVENT_{val}"
                else:
                    decoded_payload[f"key_{key_byte}"] = val
            else:
                # Fallback for trailing bytes
                decoded_payload[f"key_{key_byte}"] = list(payload_bytes[i:])
                break

    # Categorize traffic direction relative to the Game Controller (Hub)
    src_type_val = (src_address >> 8) & 0xFF
    dest_type_val = (dest_address >> 8) & 0xFF
    
    if dest_address == 0xFFFF:
        direction = "BROADCAST"
    elif src_type_val == NodeType.GAME_CONTROLLER.value:
        direction = "DOWNLINK"
    elif dest_type_val == NodeType.GAME_CONTROLLER.value:
        direction = "UPLINK"
    else:
        direction = "DIRECT"

    return {
        "source_address": format_address(src_address),
        "destination_address": format_address(dest_address),
        "context_address": direction,  # Repurpose this column for traffic direction!
        "payload_type": payload_type,
        "timestamp": timestamp,
        "total_len": len(packet_bytes),
        "payload": decoded_payload
    }
