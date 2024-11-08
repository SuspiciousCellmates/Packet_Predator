"""
nRF905 Configuration
AUTO_RETRAN = 0   # 0=No 1=Yes retransmission
RX_RED_PWR = 1    # 0=Normal RX power, 1=Low RX power
PA_PWR = 0        # 0=-10dBm 1=-2dBm 2=+6dBm 3=+10dBm, TX power (9mA to 30mA)
HFREQ_PLL = 0     # 0=433 MHz band, 1=868/915MHz band
CH_NO_MSB = 0     # 0 or 1
CH_NO = 0x6C      # 0x6C=433.2MHz, channel seperation = 100KHz, ie 0x6D=433.3MHz
                # fRF = ( 422.4 + (CH_NO/10))*(1+HFREQ_PLL) MHz
TX_AFW = 4        # TX address field width, 4 bytes or 1 byte 
RX_AFW = 4        # RX address field width, 4 bytes or 1 byte 
TX_PW = 32        # Payload number of bytes, usually 32
RX_PW = 32        # Payload number of bytes, usually 32
CRC_MODE = 0      # 0=8 bit CRC, 1=16 bit CRC
CRC_EN = 0        # 0=disable, 1=enable CRC check
XOF = 3           # 0=4MHz 1=8MHz 2=12MHz 3=16MHz 4=20 MHz Crystal Frequency
UP_CLK_EN = 0     # 0=No 1=Yes External clock signal
UP_CLK_FREQ = 0   # 0=4MHz  1=2MHz  2=1MHz  3=500kHz External clock Frequency

#example nRF905 Dictionary Definition
RX_Address = bytearray((0xE7,0xE7,0xE7,0xE7))
bufsize = 32
"""

class NRF905Config:
    def __init__(self, auto_retran=1, rx_red_pwr=0, pa_pwr=0, hfreq_pll=0, ch_no_msb=0,
                 ch_no=0x6C, tx_afw=4, rx_afw=4, tx_pw=32, rx_pw=32,
                 rx_address=[0x22, 0x22, 0x21, 0x18], crc_mode=1, crc_en=0, xof=3,
                 up_clk_en=0, up_clk_freq=0):
        self.cfg = {
            'AUTO_RETRAN': auto_retran, 'RX_RED_PWR': rx_red_pwr,
            'PA_PWR': pa_pwr, 'HFREQ_PLL': hfreq_pll, 'CH_NO_MSB': ch_no_msb,
            'CH_NO': ch_no, 'TX_AFW': tx_afw, 'RX_AFW': rx_afw,
            'TX_PW': tx_pw, 'RX_PW': rx_pw,
            'RX_Address': rx_address,
            'CRC_MODE': crc_mode, 'CRC_EN': crc_en, 'XOF': xof,
            'UP_CLK_EN': up_clk_en, 'UP_CLK_FREQ': up_clk_freq
        }

    def get_config_values(self):
        cfg = self.cfg
        config_reg = bytearray(10)
        config_reg[0] = cfg['CH_NO']
        config_reg[1] = (cfg['AUTO_RETRAN'] << 5 | cfg['RX_RED_PWR'] << 4 |
                         cfg['PA_PWR'] << 2 | cfg['HFREQ_PLL'] << 1 | cfg['CH_NO_MSB'])
        config_reg[2] = cfg['TX_AFW'] << 4 | cfg['RX_AFW']
        config_reg[3] = cfg['TX_PW']
        config_reg[4] = cfg['RX_PW']
        config_reg[5:9] = cfg['RX_Address']  # Ensure RX_Address is always a list of 4 items
        config_reg[9] = (cfg['CRC_MODE'] << 7 | cfg['CRC_EN'] << 6 |
                         cfg['XOF'] << 3 | cfg['UP_CLK_EN'] << 2 | cfg['UP_CLK_FREQ'])
        return list(config_reg)
    
    def reconfigure(self, auto_retran=1, rx_red_pwr=0, pa_pwr=2, hfreq_pll=1, ch_no_msb=0,
                 ch_no=0x6C, tx_afw=4, rx_afw=4, tx_pw=32, rx_pw=32,
                 rx_address=[22, 220, 210, 18], crc_mode=1, crc_en=1, xof=3,
                 up_clk_en=0, up_clk_freq=0):
        self.cfg = {
            'AUTO_RETRAN': auto_retran, 'RX_RED_PWR': rx_red_pwr,
            'PA_PWR': pa_pwr, 'HFREQ_PLL': hfreq_pll, 'CH_NO_MSB': ch_no_msb,
            'CH_NO': ch_no, 'TX_AFW': tx_afw, 'RX_AFW': rx_afw,
            'TX_PW': tx_pw, 'RX_PW': rx_pw,
            'RX_Address': rx_address,
            'CRC_MODE': crc_mode, 'CRC_EN': crc_en, 'XOF': xof,
            'UP_CLK_EN': up_clk_en, 'UP_CLK_FREQ': up_clk_freq
        }