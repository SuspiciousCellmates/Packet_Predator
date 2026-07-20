# File: nrf905.py
import time
import struct
import logging
from typing import Optional

spidev = None
GPIO = None
HARDWARE_IMPORT_ERROR = None

try:
    import spidev
    import RPi.GPIO as GPIO
    HAS_HARDWARE = True
except (ModuleNotFoundError, RuntimeError, ImportError) as e:
    HAS_HARDWARE = False
    HARDWARE_IMPORT_ERROR = e

logger = logging.getLogger("nrf905")

DEFAULT_CONFIG = {
    'CH_NO': 0x6C,
    'AUTO_RETRAN': 0,
    'RX_RED_PWR': 0,
    'PA_PWR': 3,
    'HFREQ_PLL': 0,
    'CH_NO_MSB': 0,
    'RX_AFW': 4,
    'TX_AFW': 4,
    'TX_PW': 32,
    'RX_PW': 32,
    'RX_ADDRESS': 0xDEADBEEF,
    'CRC_MODE': 0,
    'CRC_EN': 0,
    'XOF': 3,
    'UP_CLK_EN': 0,
    'UP_CLK_FREQ': 0,
}

RX_PAYLOAD = 0x24
TX_PAYLOAD = 0x20

class NRF905:
    def __init__(self, config, csn=8, pwr=21, ce=7, txen=23, dr=17, use_dr=True, am=22, use_am=True, cd=18, use_cd=False):
        global HAS_HARDWARE, HARDWARE_IMPORT_ERROR

        self.csn = csn
        self.pwr = pwr
        self.ce = ce
        self.txen = txen
        self.dr = dr
        self.am = am
        self.cd = cd
        self.spi = None
        self.has_hardware = HAS_HARDWARE
        self.current_mode = 'rx'
        self.config = bytearray(10)
        self._simulation_config = DEFAULT_CONFIG.copy()
        self.use_dr = use_dr
        self.use_am = use_am
        self.use_cd = use_cd
        
        self.radio_configured = False
        self._virtual_address = None

        if self.has_hardware:
            try:
                self.spi = spidev.SpiDev()
                self.setup()
            except (OSError, RuntimeError) as exc:
                logger.warning("Hardware initialization failed; using simulator mode: %s", exc)
                if self.spi is not None:
                    self.spi.close()
                self.spi = None
                self.has_hardware = False
                HAS_HARDWARE = False
                HARDWARE_IMPORT_ERROR = exc
        else:
            logger.info("Hardware modules unavailable; using simulator mode: %s", HARDWARE_IMPORT_ERROR)

        self.write_config(config)

    @property
    def virtual_address(self) -> Optional[int]:
        return self._virtual_address

    @virtual_address.setter
    def virtual_address(self, val: Optional[int]):
        from driver.virtual_airwaves import airwaves
        if self._virtual_address is not None:
            airwaves.unregister(self._virtual_address)
        self._virtual_address = val
        if val is not None:
            airwaves.register(val)


    def setup(self):
        if not self.has_hardware:
            self.radio_configured = True
            return

        # Initialize SPI
        self.spi.open(0, 0)  # Bus 0, device 0
        self.spi.max_speed_hz = 125000
        self.spi.mode = 0
        
        # Initialize GPIO
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        #GPIO.setup(self.csn, GPIO.OUT)
        #GPIO.output(self.csn, GPIO.HIGH)  # CSN high to start
        
        GPIO.setup(self.pwr, GPIO.OUT, initial=0)
        
        
        GPIO.setup(self.ce, GPIO.OUT)
        GPIO.setup(self.txen, GPIO.OUT)
        
        if self.use_dr == True:
            GPIO.setup(self.dr, GPIO.IN)
            
        if self.use_am:
            GPIO.setup(self.am, GPIO.IN)
                
        if self.use_cd:
            GPIO.setup(self.cd, GPIO.IN)
        
        # don't use this yet    
        # self.config = NRF905Config()
        
        self.set_power_mode('up')

            
###############################################################################
#   Config functions
###############################################################################

    def read_config_binary(self, length):
        if not self.has_hardware:
            return self.config[:length]
        data = self.spi.xfer2([0x10] + [0x00] * length)
        return data[1:]  # Ignore the status byte

    def read_config_human(self):
        if not self.has_hardware:
            return self._simulation_config.copy()
        config = self.read_config_binary(10)
        return {
            'CH_NO': config[0],
            'AUTO_RETRAN': (config[1] >> 5) & 0x01,
            'RX_RED_PWR': (config[1] >> 4) & 0x01,
            'PA_PWR': (config[1] >> 2) & 0x03,
            'HFREQ_PLL': (config[1] >> 1) & 0x01,
            'CH_NO_MSB': config[1] & 0x01,
            'TX_AFW': (config[2] >> 4) & 0x0F,
            'RX_AFW': config[2] & 0x0F,
            'RX_PW': config[3],
            'TX_PW': config[4],
            'RX_ADDRESS': config[5] |
                (config[6] << 8) |
                (config[7] << 16) |
                (config[8] << 24),
            'CRC_MODE': (config[9] >> 7) & 0x01,
            'CRC_EN': (config[9] >> 6) & 0x01,
            'XOF': (config[9] >> 3) & 0x07,
            'UP_CLK_EN': (config[9] >> 2) & 0x01,
            'UP_CLK_FREQ': config[9] & 0x03
        }

    def write_config(self, config_values=None, print_values=False):
        config = DEFAULT_CONFIG.copy()
        if config_values:
            config.update(config_values)

        if self.has_hardware:
            self.set_mode('idle')
        
        if print_values:
            logger.info("Going to store: %s", config)
        
        # Build configuration byte array
        self.config = bytearray(10)
        self.config[0] = config['CH_NO']
        self.config[1] = (config['AUTO_RETRAN'] << 5 |
                        config['RX_RED_PWR'] << 4 |
                        config['PA_PWR'] << 2 |
                        config['HFREQ_PLL'] << 1 |
                        config['CH_NO_MSB'])
        self.config[2] = config['TX_AFW'] << 4 | config['RX_AFW']
        self.config[3] = config['RX_PW']
        self.config[4] = config['TX_PW']
        self.config[5:9] = config['RX_ADDRESS'].to_bytes(4, 'little')
        self.config[9] = (config['CRC_MODE'] << 7 |
                        config['CRC_EN'] << 6 |
                        config['XOF'] << 3 |
                        config['UP_CLK_EN'] << 2 |
                        config['UP_CLK_FREQ'])

        if not self.has_hardware:
            self._simulation_config = config
            self.radio_configured = True
            return self.config
        
        # Write configuration
        self.spi.xfer2([0x00] + list(self.config))
        
        # Read back configuration to verify
        self.config = self.read_config_binary(10)
        if print_values:
            logger.info("Config written and read back: %s", self.config)
        self.radio_configured = True
        return self.config

        
###############################################################################
#   TX functions
###############################################################################

    def read_tx_address(self):
        tx_address = self.spi.xfer2([0x23] + [0x00] * 4)
        return tx_address[1:]
        
    def write_tx_address(self, address):
        self.spi.xfer2([0x22] + list(address))
        
    def read_tx_payload(self, length):
        data = self.spi.xfer2([0x21] + [0x00] * length)
        return data[1:]

    # load into register, dont send yet
    def write_tx_payload(self, data):
        self.spi.xfer2([0x20] + data)

    def tx(self, data, address, max_retries=20, retry_delay=0.1):
        if not self.has_hardware:
            from driver.virtual_airwaves import airwaves
            src_addr = self.virtual_address if self.virtual_address is not None else 0x0000
            airwaves.transmit(data, src_addr)
            return True

        TX_OK = False
        # Check for valid length
        if len(data) > 32:
            logger.error("Packet too large")
            return TX_OK
        
        self.set_mode('idle')
        self.write_tx_address(address)
        self.write_tx_payload(data)
        self.set_mode('tx')
        start_time = time.monotonic()
        while not GPIO.input(self.dr):
            if time.monotonic() - start_time > 0.1: # 100ms timeout
                logger.error("TX timeout waiting for DR pin")
                break
            time.sleep(0.001)
        else:
            TX_OK = True
        GPIO.output(self.ce, GPIO.LOW)
        GPIO.output(self.txen, GPIO.LOW)
        self.set_mode('rx')
        return TX_OK
          
###############################################################################
#   RX functions
###############################################################################   
    def rx(self):
        if not self.has_hardware:
            from driver.virtual_airwaves import airwaves
            if self.virtual_address is not None:
                airwaves.register(self.virtual_address)
                packet = airwaves.receive(self.virtual_address)
                if packet:
                    return True, packet
            # Sleep slightly to prevent high CPU load in the background sniff loop
            time.sleep(0.01)
            return False, None

        self.set_mode('rx')
        response = []
        RX_OK = False
        if GPIO.input(self.am) == 1:
            if GPIO.input(self.dr) == 1:
                #test_response = self.spi.xfer2([RX_PAYLOAD] + [0x00] * 36)
                #length_response = self.spi.xfer2([RX_PAYLOAD, 0x00, 0x00]) # xfer2 consumes bytes, read the 2 bytes we encoded length as
                #packet_length = struct.unpack('H', bytes(length_response[1:3]))[0]
                #if packet_length > 32:
                #    return RX_OK, None
                #response += length_response[1:]
                response += self.spi.xfer2([0x24] + [0x00] * 32)[1:] # trim the response byte from the spi read operation
                RX_OK = True
                self.set_mode('idle')
        return RX_OK, bytes(response)
    
###############################################################################
#   Chip Management functions
###############################################################################    
    def set_power_mode(self, mode):
        if not self.has_hardware:
            return
        if mode == 'down':
            GPIO.output(self.pwr, GPIO.LOW)
        elif mode == 'up':
            GPIO.output(self.pwr, GPIO.HIGH)
        else:
            raise ValueError("Invalid power mode. Use 'up' or 'down'")
            
    def set_mode(self, mode):
        if not self.has_hardware:
            self.current_mode = mode
            return
        if self.current_mode != mode:
            if mode == 'tx':
                GPIO.output(self.txen, GPIO.HIGH)
                GPIO.output(self.ce, GPIO.HIGH)
            elif mode == 'idle':
                GPIO.output(self.txen, GPIO.LOW)
                GPIO.output(self.ce, GPIO.LOW) 
            elif mode == 'rx':
                GPIO.output(self.txen, GPIO.LOW)
                GPIO.output(self.ce, GPIO.HIGH)
            elif mode == 'power_down':
                GPIO.output(self.ce, GPIO.LOW)
            self.current_mode = mode
        
    def cleanup(self):
        if not self.has_hardware:
            self.virtual_address = None
            return
        if self.spi is not None:
            self.spi.close()
        GPIO.cleanup()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()
