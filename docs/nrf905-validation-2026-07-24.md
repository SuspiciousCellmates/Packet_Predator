# nRF905 physical validation result — 2026-07-24

Status: passed in both directions on the two available Raspberry Pi 5 and original Packet Predator nRF905 HAT benches.

## Purpose

This result closes the physical-evidence portion of ADR 0005. It proves that these two benches can transmit and receive exact, fixed 32-byte Protocol Contract `1.0.1` frames through the isolated nRF905 adapter. It does not make nRF905 a permanent platform choice or establish venue range, congestion, or timing limits.

## Recovered and proven HAT configuration

The first attempted profile used a newly proposed GPIO allocation. SPI register write/readback succeeded, but both radios returned `NRF905_TRANSMIT_TIMEOUT` and neither receiver observed a frame. A GPIO trace showed that the software was driving the proposed pins correctly but that `DR` never rose.

The archived prototype driver preserved the GPIO allocation used when the original HATs had previously worked. Because SPI programming remains available independently of the nRF905's `PWR_UP`, `TRX_CE`, and status connections, successful register readback had not proved that the proposed control-pin mapping matched the PCB.

The recovered configuration was:

| Purpose | BCM GPIO | Physical pin |
|---|---:|---:|
| SPI0 SCLK | 11 | 23 |
| SPI0 MOSI | 10 | 19 |
| SPI0 MISO | 9 | 21 |
| SPI0 CE0 / nRF905 `CSN` | 8 | 24 |
| nRF905 `PWR_UP` | 21 | 40 |
| nRF905 `TRX_CE` | 7 | 26 |
| nRF905 `TX_EN` | 23 | 16 |
| nRF905 `CD` | 18 | 12 |
| nRF905 `AM` | 22 | 15 |
| nRF905 `DR` | 17 | 11 |

GPIO7 is normally reserved as SPI0 CE1. Both Pi 5 systems were configured with `dtoverlay=spi0-1cs`, retaining CE0 for `/dev/spidev0.0` and releasing GPIO7 for `TRX_CE`. The existing default `dtoverlay=nospi10` line was unrelated and remained unchanged.

The validated deployment values were:

| Setting | Value |
|---|---|
| SPI device and clock | `/dev/spidev0.0`, 1 MHz |
| GPIO controller | `/dev/gpiochip0` |
| RF band/channel | 433 MHz band, channel 108, calculated 433.2 MHz |
| Physical radio address | `A7C35E19` |
| Payload size | fixed 32 bytes |
| Hardware CRC | 16-bit |
| Automatic retransmit | disabled |
| Transmit power | -10 dBm |

The first successful exchange used the archived driver's 125 kHz SPI baseline. The same exact send/receive diagnostics then passed in both directions after both local profiles were restored to 1 MHz. The shipped profile therefore uses the faster tested setting; 125 kHz remains a diagnostic fallback. SPI speed affects only wired Pi-to-radio transfers, not the RF frequency or over-air data rate.

## Exact two-way evidence

### Pi A to Pi B

- Requested fixture: `v1-controller-beacon`
- Sender: Pi A
- Sender result: nRF905 transmit completion after 6.999 ms
- Receiver: Pi B
- Received frame:

```text
4c0600010700e8030000d0070000020000000000000000000000000000000000
```

- Exact fixture comparison: passed
- Reference-codec result: `CONTROLLER_BEACON`

### Pi B to Pi A

- Requested fixture: `v1-node-status`
- Sender: Pi B
- Sender result: nRF905 transmit completion after 7.003 ms
- Receiver: Pi A
- Received frame:

```text
520501000100e80300000700020003000254be0f000000000000000000000000
```

- Exact fixture comparison: passed
- Reference-codec result: `NODE_STATUS`

Both modules therefore succeeded independently as transmitter and receiver. Both application frames survived the radio path byte-for-byte and were structurally decoded by the released sibling authority.

### 1 MHz follow-up

After capturing the detailed 125 kHz evidence above, both local profiles were changed to a 1 MHz SPI clock. The complete `CONTROLLER_BEACON` and `NODE_STATUS` send/receive diagnostics passed again in both directions. This establishes 1 MHz as the proven default for these two benches without claiming it is the maximum or universally best clock for future hardware.

## What this result does and does not prove

It proves:

- the recovered original-HAT pin mapping on both benches;
- Pi 5 SPI0 CE0 operation while GPIO7 is released through `spi0-1cs`;
- exact nRF905 register write/readback with the deployment profile;
- hardware transmit completion through each module's real `DR` signal;
- physical-address and CRC-valid reception in both directions;
- exact 32-byte fixture equality; and
- decoding through Protocol Contract `1.0.1`, rather than local Packet Predator definitions.

It does not yet prove:

- useful venue range or behaviour around people and walls;
- reliability under contention, interference, or many nodes;
- the best SPI clock, RF channel, power, antenna, retry, or timing profile;
- long-duration stability;
- interoperability with future embedded node firmware; or
- that nRF905 is the final transport choice.

The repeatable setup and full diagnostic walkthrough remain in [the two-Pi bench guide](nrf905-two-pi-bench.md).
