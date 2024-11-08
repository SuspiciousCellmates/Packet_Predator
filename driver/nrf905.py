# File: nrf905.py
import spidev
import RPi.GPIO as GPIO
import time
from driver.nrf905_config import NRF905Config
import struct

RX_PAYLOAD = 0x24
TX_PAYLOAD = 0x20

class NRF905:
    def __init__(self, config, csn=8, pwr=21, ce=7, txen=23, dr=17, use_dr=True, am=22, use_am=True, cd=18, use_cd=False):
        self.csn = csn
        self.pwr = pwr
        self.ce = ce
        self.txen = txen
        self.dr = dr
        self.am = am
        self.cd = cd
        self.spi = spidev.SpiDev()
        self.current_mode = 'rx'
        self.config = config
        self.use_dr = use_dr
        self.use_am = use_am
        self.use_cd = use_cd
        
        self.radio_configured = False

        self.setup()
        self.write_config(self.config)


    def setup(self):
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
        data = self.spi.xfer2([0x10] + [0x00] * length)
        return data[1:]  # Ignore the status byte

    def read_config_human(self):
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
        self.set_mode('idle')
        
        # Default configuration values
        default_config_values = {
            'CH_NO': 0x6C,'AUTO_RETRAN': 0, 'RX_RED_PWR': 0, 
            'PA_PWR': 3, 'HFREQ_PLL': 0, 'CH_NO_MSB': 0,
            'RX_AFW': 4,'TX_AFW': 4, 
            'TX_PW': 32,
            'RX_PW': 32,
            'RX_ADDRESS': 0xDEADBEEF,
            'CRC_MODE': 0, 'CRC_EN': 0, 'XOF': 3, 'UP_CLK_EN': 0, 'UP_CLK_FREQ': 0
        }

        # Use provided config_values or defaults
        config_values = config_values or default_config_values
        
        if print_values:
            print(f"Going to store: {config_values}")
        
        # Build configuration byte array
        self.config = bytearray(10)
        self.config[0] = config_values['CH_NO']
        self.config[1] = (config_values['AUTO_RETRAN'] << 5 |
                        config_values['RX_RED_PWR'] << 4 |
                        config_values['PA_PWR'] << 2 |
                        config_values['HFREQ_PLL'] << 1 |
                        config_values['CH_NO_MSB'])
        self.config[2] = config_values['TX_AFW'] << 4 | config_values['RX_AFW']
        self.config[3] = config_values['RX_PW']
        self.config[4] = config_values['TX_PW']
        self.config[5:9] = config_values['RX_ADDRESS'].to_bytes(4, 'little')
        self.config[9] = (config_values['CRC_MODE'] << 7 |
                        config_values['CRC_EN'] << 6 |
                        config_values['XOF'] << 3 |
                        config_values['UP_CLK_EN'] << 2 |
                        config_values['UP_CLK_FREQ'])
        
        # Write configuration
        self.spi.xfer2([0x00] + list(self.config))
        
        # Read back configuration to verify
        self.config = self.read_config_binary(10)
        if print_values:
            print(f"Config written and read back: {self.config}")
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
        TX_OK = False
        # Check for valid length
        if len(data) > 32:
            print("Packet too large")
            return TX_OK
        
        self.set_mode('idle')
        self.write_tx_address(address)
        self.write_tx_payload(data)
        self.set_mode('tx')
        while not GPIO.input(self.dr):
            pass
        TX_OK = True
        GPIO.output(self.ce, GPIO.LOW)
        GPIO.output(self.txen, GPIO.LOW)
        self.set_mode('rx')
        return TX_OK
          
###############################################################################
#   RX functions
###############################################################################   
    def rx(self):
        '''
        Notes: it appears that xfer2 consumes the bytes it reads, meaning once read those bytes are discarded
        from the SPI register. This makes it somewhat tricky, since we need to read the payload length from 
        the header, then use that length to correctly read the response. However the consumption means that 
        'response' gets populated without the length data, so we add it back in front of the list that is returned
        from the seconds spi read.
        
        Furthermore, the spi xfer operations seem to return a response byte (usually either 225 or 160) in the first
        read for length, it returns a tuple (response_byte, value) so we index the correct value to obtain the length keeping in mind
        the data size that payload length gets encoded as. I would prefer to encode as 2 bytes ('H'), hence we need to pull out 2 of the
        bytes
        '''
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
        if mode == 'down':
            GPIO.output(self.pwr, GPIO.LOW)
        elif mode == 'up':
            GPIO.output(self.pwr, GPIO.HIGH)
        else:
            raise ValueError("Invalid power mode. Use 'up' or 'down'")
            
    def set_mode(self, mode):
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
        self.spi.close()
        GPIO.cleanup()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()