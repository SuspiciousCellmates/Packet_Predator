import logging
from queue import Empty, Queue
from threading import RLock
from typing import Dict, Optional

logger = logging.getLogger("virtual_airwaves")

class VirtualAirwaves:
    """
    In-memory broker that simulates sub-GHz airwaves.
    Allows mock NRF905 nodes to transmit and receive 32-byte packets based on Layer 3 addresses.
    """
    def __init__(self):
        self.queues: Dict[int, Queue] = {}
        self._lock = RLock()

    def register(self, address: int):
        """Register a node address to listen for incoming packets."""
        with self._lock:
            if address not in self.queues:
                self.queues[address] = Queue()
                logger.info("Registered virtual node address: %s", hex(address))

    def unregister(self, address: int):
        """Deregister a node address."""
        with self._lock:
            if address in self.queues:
                del self.queues[address]
                logger.info("Deregistered virtual node address: %s", hex(address))

    def transmit(self, data: bytes, src_address: int):
        """
        Transmit a packet onto the virtual airwaves.
        Extracts the destination address from the packet header (first 2 bytes, little-endian).
        """
        if len(data) != 32:
            logger.error("Attempted to transmit non-32-byte packet on virtual airwaves.")
            return

        import struct
        # Parse the destination address from the header (first two bytes)
        dest_address = struct.unpack("<H", data[0:2])[0]
        
        # Broadcast routing
        if dest_address == 0xFFFF:
            with self._lock:
                recipients = list(self.queues.items())
            for addr, q in recipients:
                if addr != src_address: # Don't receive own broadcasts
                    q.put(data)
            logger.debug("Broadcast packet routed from %s", hex(src_address))
        else:
            # Unicast routing
            with self._lock:
                destination_queue = self.queues.get(dest_address)
            if destination_queue is not None:
                destination_queue.put(data)
                logger.debug("Packet routed from %s to destination %s", hex(src_address), hex(dest_address))
            else:
                logger.warning("Packet dropped: Destination address %s is offline/unregistered", hex(dest_address))

    def receive(self, address: int) -> Optional[bytes]:
        """Check if there is a pending packet for this node address."""
        with self._lock:
            queue = self.queues.get(address)
        if queue is None:
            return None
        try:
            return queue.get_nowait()
        except Empty:
            return None

# Singleton global instance representing the local environment airwaves
airwaves = VirtualAirwaves()
