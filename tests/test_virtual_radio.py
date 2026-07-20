import unittest

import driver.nrf905 as nrf905_module
from driver.nrf905 import NRF905
from driver.virtual_airwaves import VirtualAirwaves
from packet.packet import Packet, PayloadType


def make_packet(source, destination):
    return Packet(
        src_address=source,
        dest_address=destination,
        payload_type=PayloadType.SYNC,
        timestamp=0,
    ).encode()


class VirtualAirwavesTests(unittest.TestCase):
    def test_unicast_routes_only_to_destination(self):
        airwaves = VirtualAirwaves()
        airwaves.register(0x0101)
        airwaves.register(0x0102)
        packet = make_packet(0x0101, 0x0102)

        airwaves.transmit(packet, 0x0101)

        self.assertIsNone(airwaves.receive(0x0101))
        self.assertEqual(airwaves.receive(0x0102), packet)

    def test_broadcast_excludes_sender(self):
        airwaves = VirtualAirwaves()
        for address in (0x0101, 0x0102, 0x0103):
            airwaves.register(address)
        packet = make_packet(0x0101, 0xFFFF)

        airwaves.transmit(packet, 0x0101)

        self.assertIsNone(airwaves.receive(0x0101))
        self.assertEqual(airwaves.receive(0x0102), packet)
        self.assertEqual(airwaves.receive(0x0103), packet)

    def test_simulated_config_updates_persist(self):
        original_hardware_state = nrf905_module.HAS_HARDWARE
        nrf905_module.HAS_HARDWARE = False
        try:
            radio = NRF905(config=None)
            radio.write_config({"CH_NO": 42, "RX_ADDRESS": 0xA1B2C3D4})

            config = radio.read_config_human()

            self.assertEqual(config["CH_NO"], 42)
            self.assertEqual(config["RX_ADDRESS"], 0xA1B2C3D4)
            self.assertEqual(config["TX_PW"], 32)
        finally:
            radio.cleanup()
            nrf905_module.HAS_HARDWARE = original_hardware_state


if __name__ == "__main__":
    unittest.main()
