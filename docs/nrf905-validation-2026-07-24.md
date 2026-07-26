# nRF905 physical validation result — 2026-07-24

Status: passed in both directions on the two available Raspberry Pi 5 and original Packet Predator nRF905 HAT benches.

Continuous-receive follow-up status: physically accepted on 2026-07-26 through
the retained Hardware Validation Console evidence described below.

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

## Continuous-receive follow-up — accepted 2026-07-26

The first browser integration serviced the receive FIFO only when the page made
a request every 50 ms. Later testing missed a follow-up frame, so the successful
single-frame evidence above does not validate burst or follow-up capture.

ADR 0006 replaces that browser-paced path with an application-lifecycle
receiver waiting on the nRF905 `DR` signal. Frames enter a thread-safe
process-local model before any browser presentation. Software tests now prove
ordered queued follow-ups without a browser, immediate transmit-to-receive
handoff, continued capture after a codec-invalid frame, visible adapter faults,
subscriber resynchronization, and idempotent shutdown.

The full cross-product acceptance was subsequently run through the laptop
Hardware Validation Console. Its retained capability bundle,
`20260726-133147-controller-capability-ready-e92a95`, passed all 14 reviewed
steps and the read-only verifier over its exact 34-file evidence set. Its
separate discovery bundle,
`20260726-133317-controller-discovery-capability-request-08435d`, passed all
12 reviewed steps and retained 30 hash-checked evidence files.

Both runs used clean Packet Predator `83dfac6`, Game Controller `eaec282`,
Radio Gateway `fed17fb`, Protocol Contract `78ab6a8`, and Hardware Validation
Console `92d9447` worktrees. In the verified capability run, Packet Predator
captured `HELLO_RESULT(CAPABILITIES_REQUIRED)` at journal sequence 18 and
`CAPABILITY_REQUEST` at sequence 19, 21 ms apart. The independent discovery
run captured the same pair at sequences 25 and 26, 18 ms apart. Both captures
were physical nRF905 observations while the receiver remained listening; no
browser polling, transmitter delay, or RF retry was introduced.

The capability chunk was correlated to request `1` and fingerprint
`1662968791`; the Controller independently recorded one validated cache entry
and `READY_FOR_SNAPSHOT` for serial `16909060` at endpoint `1`, with a
quiescent outbox. The complete run directories remain ignored local evidence.
Their manifest SHA-256 values are, respectively,
`427508c334adaf43974a1b7d00d8454e5ce515e7e85b1d32706dbf6bfd6d864e`
and `2036e83a55f262957fa32545b2484eb6ff712c3aa149e8a389b669f57ccdea08`.

This closes the continuous-receive acceptance required by ADR 0006 and the
physical-adapter milestone. It does not establish range, contention tolerance,
long-duration reliability, or a transmit-spacing policy.

Controlled-gap tests may follow as a separate characterization exercise after
the unchanged exchange passes. They are not part of this acceptance gate and do
not establish a production transmit-spacing policy.

The repeatable setup and full diagnostic walkthrough remain in [the two-Pi bench guide](nrf905-two-pi-bench.md).
