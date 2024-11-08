from dataclasses import dataclass, field
from typing import Optional, Any
from datetime import datetime
from enum import Enum
from nodes.node import Node
import struct

class PacketType(Enum):
    SYNC = 0
    CONFIG = 1
    EVENT = 2   # EVENT
    START = 3   # EVENT
    STOP = 4    # EVENT
    ERROR = 5   # EVENT
    ACK = 64
    NACK = 128
     
@dataclass
class Packet:
    header_fmt = "<HHBH"

    PACKET_SIZE = 32
    HEADER_SIZE = struct.calcsize(header_fmt)
    PAYLOAD_SIZE = PACKET_SIZE - HEADER_SIZE
    
    src_address: Optional[int] = None
    dest_address: Optional[int] = None
    packet_type: Optional[PacketType] = None
    timestamp: Optional[Any] = None
    staged_payload: Optional[Any] = None
    
    def __str__(self):
        return f"Packet:\n \
dest_address={self.dest_address}\n \
src_address={self.src_address}\n \
packet_type={self.packet_type}\n \
timestamp={self.timestamp}\n \
payload={self.staged_payload}\n"
        
    def get_bytes(self, bytes) -> str:
        return(" ".join(f"{byte:02x}" for byte in bytes))
            
    def stage_payload(self, index: int, value: Any):
        if self.staged_payload is None:
            self.staged_payload = {}
            
        if isinstance(value, int):
            self.staged_payload[index] = value
        elif isinstance(value, str):
            self.staged_payload[index] = value.encode('utf-8')
        elif isinstance(value, (bytes, bytearray)):
            self.staged_payload[index] = value
        elif value is None:
            self.staged_payload.pop(index, None)
        else:
            raise TypeError("Invalid payload field type.")
            
    def unstage_payload(self):
        self.staged_payload = {}
        
    def _encode_payload(self):                    
        # Ensure payload doesn't exceed max size
        payload = bytearray()
        
        for key, value in self.staged_payload.items():
            int_key = int(key)
            if int_key > 255:
                raise ValueError("Key is too large for 1 byte")
            payload += struct.pack("<B", int_key)
            # Pack the value based on its type
            if isinstance(value, int):
                if value > 65535:
                    raise ValueError("Requested number to pack is too large")
                payload += struct.pack("<H", value)  # "<H" packs as 2 bytes (little-endian)
                    
            elif isinstance(value, str):
                # Encode the string into bytes and ensure it fits in the payload
                byte_data = value.encode('utf-8')
                payload += byte_data
                
            elif isinstance(value, (bytes, bytearray)):
                # Append bytes or bytearray directly
                payload += value
                    
            else:
                raise TypeError(f"Unsupported payload type. Got {type(value)} but it needs to be int, str, or bytes/bytearray")
                
        if len(payload) > self.PAYLOAD_SIZE:
            raise ValueError("Payload exceeds maximum allowed size")
        return payload

    def _encode_header(self) -> bytes:
        header = struct.pack(
            self.header_fmt,
            self.dest_address,
            self.src_address,
            self.packet_type.value,  # Ensure we use the enum value
            self.timestamp  # Convert datetime to a UNIX timestamp
        )
        
        return header
    
    def encode(self) -> bytearray:
        header = self._encode_header()
        payload = self._encode_payload()
        
        packet = header + payload
        
        if len(packet) > self.PACKET_SIZE:
            raise ValueError("Final packet exceeds allowed size")
        
        return packet