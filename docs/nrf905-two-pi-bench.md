# nRF905 two-Raspberry-Pi validation bench

This is the first physical Packet Predator adapter checkpoint. Each Raspberry Pi 5 runs the complete workbench and can be managed over SSH. One known 32-byte contract frame is sent from Pi A to Pi B, then a different known frame is sent from Pi B to Pi A. Packet Predator compares exact bytes and decodes the received frame; it never invents a reply.

The nRF905 is experimental. Passing this bench proves these two modules and this profile can exchange frames. It does not commit the project to nRF905 or approve a frequency for every venue.

The original Packet Predator HAT configuration passed this test in both directions on 2026-07-24. The exact evidence and recovered configuration are recorded in [the physical validation result](nrf905-validation-2026-07-24.md).

## Original Packet Predator HAT wiring

- Fit the correct antenna before transmitting.
- The original HAT routes the nRF905 to the header as shown below. Do not move those connections in software merely because another example uses different GPIO numbers.
- For a bare module or different PCB, identify `VCC`, `GND`, `CSN`, `SCK`, `MOSI`, `MISO`, `PWR_UP`, `TRX_CE`, `TX_EN`, `CD`, `AM`, and `DR` and create a separate profile matching its real wiring.
- The nRF905 silicon operates from 1.9–3.6 V and Raspberry Pi GPIO is 3.3 V. Do not apply 5 V to an unverified module or any Pi GPIO.
- The example radio channel is inherited only as a non-transmitting register-test value. Review the locally permitted frequency before changing `transmit_enabled` to `true`.

| nRF905 module | Raspberry Pi signal | Physical header pin |
|---|---|---:|
| `VCC` | 3.3 V | 1 |
| `GND` | ground | 6 |
| `SCK` | GPIO11 / SPI0 SCLK | 23 |
| `MOSI` | GPIO10 / SPI0 MOSI | 19 |
| `MISO` | GPIO9 / SPI0 MISO | 21 |
| `CSN` | GPIO8 / SPI0 CE0 | 24 |
| `PWR_UP` | GPIO21 | 40 |
| `TRX_CE` | GPIO7 | 26 |
| `TX_EN` | GPIO23 | 16 |
| `CD` | GPIO18 | 12 |
| `AM` | GPIO22 | 15 |
| `DR` | GPIO17 | 11 |

The historical driver preserved this mapping and used 125 kHz SPI. The physical test confirmed the pinout on both available HATs, first at that historical speed and then again at 1 MHz. The shipped example profile now represents the proven 1 MHz configuration. Power a Pi down before fitting or removing a HAT.

### Why the Pi 5 needs a one-chip-select overlay

The HAT is physically wired with `TRX_CE` on GPIO7. Raspberry Pi OS normally reserves GPIO7 as SPI0's second chip-select, `CE1`, even though this HAT communicates over the first chip-select, `CE0`, on GPIO8.

Two settings therefore have different jobs:

- `dtoverlay=spi0-1cs` tells Linux that SPI0 uses only `CE0`, releasing GPIO7 for ordinary GPIO use.
- `gpio.trx_ce: 7` in the Packet Predator profile tells the application to use that released GPIO7 for the radio's `TRX_CE` signal.

Neither setting replaces the other. The overlay controls Linux pin ownership; the profile describes the PCB connection.

## Prepare each Pi

Give the Pis distinct hostnames such as `packet-predator-a` and `packet-predator-b`, enable SSH, and put both repositories beside one another. Raspberry Pi OS exposes a hostname through mDNS as, for example, `packet-predator-a.local`; `hostname -I` prints the current IP address.

Enable SPI:

```sh
sudo raspi-config
```

Choose **Interface Options → SPI → Yes** and finish. Then edit `/boot/firmware/config.txt`. In its existing `[pi5]` section, add:

```ini
dtoverlay=spi0-1cs
```

Leave unrelated default lines such as `dtoverlay=nospi10` unchanged. Reboot, then verify the result:

```sh
ls -l /dev/spidev0.*
gpioinfo | grep -E 'line +(7|8|17|18|21|22|23):'
```

`/dev/spidev0.0` should exist, `/dev/spidev0.1` should not exist, GPIO8 should remain owned by `spi0 CS0`, and GPIO7 should no longer be owned by `spi0 CS1`.

Then, in Packet Predator:

```sh
sudo apt install python3-venv python3-dev gcc
./scripts/setup-rpi
cp config/nrf905-bench.example.json config/nrf905-bench.local.json
./scripts/nrf905-diagnose --profile config/nrf905-bench.local.json profile
./scripts/nrf905-diagnose --profile config/nrf905-bench.local.json probe
```

The profile command performs no hardware access. The probe opens `/dev/spidev0.0` and the configured GPIO chip, writes all ten nRF905 configuration bytes, reads them back, and fails if any byte differs. The local profile is ignored by Git.

The example uses the subsequently validated 1 MHz SPI clock. This is only the short wired conversation between the Pi and radio while loading registers and a frame; it does not set the RF frequency or over-air data rate. The initial successful exchange used the historical 125 kHz baseline, then the complete send/receive test passed again in both directions at 1 MHz. If later hardware has marginal wiring or signal integrity, 125 kHz remains a useful diagnostic fallback rather than the normal profile.

If `/dev/gpiochip0` is not the user-header GPIO chip on the installed Raspberry Pi OS image, inspect `gpioinfo` and change only `gpio.chip`. If the SPI device is absent, recheck that SPI was enabled and the Pi rebooted.

## Run the exact two-way RF test

Both local profiles must have the same band, channel, physical address, crystal, CRC, and payload settings. After reviewing the RF setting, change `radio.transmit_enabled` to `true` on both Pis and rerun `probe`.

First, prepare Pi B to receive a controller-originated example:

```sh
./scripts/nrf905-diagnose \
  --profile config/nrf905-bench.local.json \
  receive --expect-fixture v1-controller-beacon --timeout 30
```

While that waits, send from Pi A:

```sh
./scripts/nrf905-diagnose \
  --profile config/nrf905-bench.local.json \
  send --fixture v1-controller-beacon
```

A passing receiver prints `ok: true`, the exact 32-byte hex, and decoded name `CONTROLLER_BEACON`.

Now reverse the radios. Prepare Pi A:

```sh
./scripts/nrf905-diagnose \
  --profile config/nrf905-bench.local.json \
  receive --expect-fixture v1-node-status --timeout 30
```

Send from Pi B:

```sh
./scripts/nrf905-diagnose \
  --profile config/nrf905-bench.local.json \
  send --fixture v1-node-status
```

This time the expected decoded name is `NODE_STATUS`. Save both successful receiver outputs for milestone review.

## What the test actually does

The diagnostic is a chain of small, checkable operations rather than one unexplained radio action.

1. **Load the local hardware profile.** Packet Predator validates the JSON before touching hardware. This supplies the SPI device, six GPIO connections, RF channel, physical radio address, CRC mode, and explicit permission to transmit.
2. **Load the shared Protocol Contract.** Packet Predator opens the sibling repository's stable registry, reference codec, and released fixtures. The radio adapter itself never learns what `CONTROLLER_BEACON` means.
3. **Resolve the requested fixture.** For `send --fixture v1-controller-beacon`, the wire adapter finds that official example, decodes it through the reference codec, then re-encodes it from the registered message schema. Requesting fixed mode adds zero padding to exactly 32 bytes.
4. **Probe the radio.** The nRF905 adapter converts the deployment profile into the chip's ten configuration bytes, writes them over SPI, reads them back, and requires an exact match.
5. **Transmit opaque bytes.** The adapter loads the four-byte physical radio address and exact 32-byte frame into the nRF905 FIFOs, changes `TX_EN` and `TRX_CE`, and waits for the hardware `DR` line. A successful `DR` signal produced the reported transmission-completion time.
6. **Receive opaque bytes.** The other nRF905 first checks its physical address and hardware CRC. When `DR` says a complete frame is ready, Packet Predator reads exactly 32 bytes from the receive FIFO.
7. **Compare before interpreting.** The receive diagnostic compares all 32 received bytes with the selected released fixture. A single different byte returns `RECEIVED_FRAME_MISMATCH`; no decoder guess can turn it into a pass.
8. **Decode through the contract.** Only after the exact comparison passes does the reference codec read the four-byte logical envelope, use the registered message type to select the payload layout, decode little-endian field values, and verify that all remaining fixed-frame padding is zero.

The nRF905 hardware CRC is added and checked by the radios outside the 32-byte application frame. It is therefore important protection on air, but it does not appear in the printed hexadecimal frame.

### Reading the successful controller beacon by hand

The successful frame was:

```text
4c 06 00 01 07 00 e8 03 00 00 d0 07 00 00 02 00
00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
```

| Bytes | Meaning |
|---|---|
| `4c` | Wire generation 1 in the upper two bits and payload length 12 in the lower six bits |
| `06` | Registered message type 6: `CONTROLLER_BEACON` |
| `00` | Logical source 0: Game Controller |
| `01` | Logical destination 1: node endpoint 1 |
| `07 00` | Beacon sequence 7 |
| `e8 03 00 00` | Controller/game tick 1000 |
| `d0 07 00 00` | Authority valid-until tick 2000 |
| `02 00` | Global-state revision 2 |
| final 16 zero bytes | Blank padding added for the nRF905's fixed 32-byte payload |

The physical radio address `A7C35E19` is not one of these bytes. The nRF905 uses it first to decide whether to receive the radio transmission. The source and destination inside the frame are the transport-neutral logical participants interpreted by the protocol.

## Update a prepared Pi

Treat each Pi as a deployment target and make source changes on the development computer. Once both sibling repositories have Git remotes and tracking branches configured, update either Pi with:

```sh
cd ~/Suspicious_Cellmates/Packet_Predator
./scripts/update-rpi
```

The updater first refuses dirty, detached, untracked, or diverged repository states. It then fetches both repositories, applies fast-forward-only updates, refreshes Raspberry Pi dependencies only when needed, and runs the complete Packet Predator check. Ignored local radio profiles are preserved. Restart a running workbench deliberately after the update.

## Use the browser

On either Pi, localhost remains the safe default:

```sh
./scripts/run-rpi config/nrf905-bench.local.json
```

For a bench that has already passed its manual probe, the tracked
[systemd deployment](systemd-deployment.md) can start this same loopback-only,
profile-explicit command automatically at boot. Do not run both forms at once.

From your normal computer, forward a local port through SSH:

```sh
ssh -L 8001:127.0.0.1:8000 your-user@packet-predator-a.local
```

Open `http://127.0.0.1:8001`. For the second Pi use another local port, such as 8002.

Direct LAN access is also available:

```sh
./scripts/run-rpi config/nrf905-bench.local.json --lan
```

Then open `http://PI_ADDRESS:8000`. The workbench currently has no login. Use direct LAN binding only on a trusted development network and do not expose it to the internet.

When a profile is active, application startup begins a dedicated receiver that
waits on the nRF905 `DR` signal and writes observations into the process-local
workbench model. It runs before and independently of any browser connection.
The browser reads the current model, then uses a server-sent event stream to
learn when it changed; it never polls the radio. A slow or reconnecting page
cannot apply backpressure to capture.

Transmission requires both `transmit_enabled: true` in the profile and a
one-shot confirmation checkbox in the page. Receive, transmit, and shutdown
operations are serialized, and the adapter returns to receive mode immediately
after a transmit attempt. These are accident barriers, not authentication.

### Continuous-receive follow-up still required

The original exact one-frame exchange passed on 2026-07-24. After that test,
browser-driven 50 ms receive polling was found to miss a follow-up frame. ADR
0006 removes that window in software and adds deterministic queued-frame and
transmit-to-receive tests.

Follow the copy-paste commands and evidence checklist in
[continuous-receive physical revalidation](continuous-receive-revalidation.md).

Before closing the physical milestone, use Packet Predator to send the
enrolled endpoint's `NODE_HELLO` through the real Radio Gateway to the Game
Controller. Packet Predator must capture both naturally consecutive Controller
responses: `HELLO_RESULT(CAPABILITIES_REQUIRED)`, then
`CAPABILITY_REQUEST`. Run with the receiving browser unopened, open, and
reconnecting. Do not add transmitter delay, retry, or scheduling behavior.
Record the exact frame order, byte equality, sample count, and any loss in the
dated validation result. Until that run is recorded, do not describe
continuous follow-up reception as physically passed.

Controlled inter-packet gaps may be characterized separately after the unchanged
exchange passes. Such measurements do not authorize production transmit
spacing or retry behavior.

## Failure meanings

- `PROFILE_*`: the JSON is incomplete, malformed, or contains an unsupported setting.
- `NRF905_SPI_DEVICE_MISSING` / `NRF905_GPIO_DEVICE_MISSING`: Linux has not exposed the configured device path.
- `NRF905_SPI_OPEN` / `NRF905_GPIO_OPEN`: the process lacks access or another process owns the device/lines.
- `NRF905_REGISTER_MISMATCH`: SPI is active but the radio did not return the bytes written; recheck power, `CSN`, SCK, MOSI, and MISO.
- `NRF905_TRANSMIT_TIMEOUT`: the radio did not raise `DR` after the transmit pulse; recheck `PWR_UP`, `TRX_CE`, `TX_EN`, `DR`, and the crystal/module.
- `RECEIVE_TIMEOUT`: no CRC-valid frame with the configured physical address arrived.
- `RECEIVED_FRAME_MISMATCH`: RF delivery occurred, but it was not the expected contract fixture.

Primary hardware references: [Nordic nRF905 Product Specification 1.5](https://docs-be.nordicsemi.com/bundle/nRF9-Series/raw/resource/enus/nRF905_PS_v1.5.pdf), [Raspberry Pi remote access](https://www.raspberrypi.com/documentation/computers/remote-access.html), and [Raspberry Pi hardware communication configuration](https://www.raspberrypi.com/documentation/computers/configuration.html#hardware-communication).
