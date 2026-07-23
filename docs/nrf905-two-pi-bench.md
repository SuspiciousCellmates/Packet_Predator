# nRF905 two-Raspberry-Pi validation bench

This is the first physical Packet Predator adapter checkpoint. Each Raspberry Pi 5 runs the complete workbench and can be managed over SSH. One known 32-byte contract frame is sent from Pi A to Pi B, then a different known frame is sent from Pi B to Pi A. Packet Predator compares exact bytes and decodes the received frame; it never invents a reply.

The nRF905 is experimental. Passing this bench proves these two modules and this profile can exchange frames. It does not commit the project to nRF905 or approve a frequency for every venue.

## Before wiring

- Identify the labels on the actual module: `VCC`, `GND`, `CSN`, `SCK`, `MOSI`, `MISO`, `PWR_UP`, `TRX_CE`, `TX_EN`, `CD`, `AM`, and `DR` are expected. Stop if its labels or supply requirements differ.
- Fit the correct antenna before transmitting.
- The nRF905 silicon operates from 1.9–3.6 V and Raspberry Pi GPIO is 3.3 V. The table below uses the Pi's 3.3 V rail. Do not apply 5 V to an unverified module or any Pi GPIO.
- The example radio channel is inherited only as a non-transmitting register-test value. Review the locally permitted frequency before changing `transmit_enabled` to `true`.

## Proposed wiring

The SPI0 pins are fixed by the Pi. The six control/status GPIO choices are simply a documented bench allocation and can be changed in the profile if necessary.

| nRF905 module | Raspberry Pi signal | Physical header pin |
|---|---|---:|
| `VCC` | 3.3 V | 1 |
| `GND` | ground | 6 |
| `SCK` | GPIO11 / SPI0 SCLK | 23 |
| `MOSI` | GPIO10 / SPI0 MOSI | 19 |
| `MISO` | GPIO9 / SPI0 MISO | 21 |
| `CSN` | GPIO8 / SPI0 CE0 | 24 |
| `PWR_UP` | GPIO25 | 22 |
| `TRX_CE` | GPIO24 | 18 |
| `TX_EN` | GPIO23 | 16 |
| `CD` | GPIO5 | 29 |
| `AM` | GPIO6 | 31 |
| `DR` | GPIO22 | 15 |

Wire both benches the same way. Power each Pi down while changing wiring.

## Prepare each Pi

Give the Pis distinct hostnames such as `packet-predator-a` and `packet-predator-b`, enable SSH, and put both repositories beside one another. Raspberry Pi OS exposes a hostname through mDNS as, for example, `packet-predator-a.local`; `hostname -I` prints the current IP address.

Enable SPI:

```sh
sudo raspi-config
```

Choose **Interface Options → SPI → Yes**, finish, and reboot. Then, in Packet Predator:

```sh
sudo apt install python3-venv python3-dev gcc
./scripts/setup-rpi
cp config/nrf905-bench.example.json config/nrf905-bench.local.json
./scripts/nrf905-diagnose --profile config/nrf905-bench.local.json profile
./scripts/nrf905-diagnose --profile config/nrf905-bench.local.json probe
```

The profile command performs no hardware access. The probe opens `/dev/spidev0.0` and the configured GPIO chip, writes all ten nRF905 configuration bytes, reads them back, and fails if any byte differs. The local profile is ignored by Git.

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

When a profile is active, the browser shows a physical-adapter panel and polls for received frames. Transmission requires both `transmit_enabled: true` in the profile and a one-shot confirmation checkbox in the page. These are accident barriers, not authentication.

## Failure meanings

- `PROFILE_*`: the JSON is incomplete, malformed, or contains an unsupported setting.
- `NRF905_SPI_DEVICE_MISSING` / `NRF905_GPIO_DEVICE_MISSING`: Linux has not exposed the configured device path.
- `NRF905_SPI_OPEN` / `NRF905_GPIO_OPEN`: the process lacks access or another process owns the device/lines.
- `NRF905_REGISTER_MISMATCH`: SPI is active but the radio did not return the bytes written; recheck power, `CSN`, SCK, MOSI, and MISO.
- `NRF905_TRANSMIT_TIMEOUT`: the radio did not raise `DR` after the transmit pulse; recheck `PWR_UP`, `TRX_CE`, `TX_EN`, `DR`, and the crystal/module.
- `RECEIVE_TIMEOUT`: no CRC-valid frame with the configured physical address arrived.
- `RECEIVED_FRAME_MISMATCH`: RF delivery occurred, but it was not the expected contract fixture.

Primary hardware references: [Nordic nRF905 Product Specification 1.5](https://docs-be.nordicsemi.com/bundle/nRF9-Series/raw/resource/enus/nRF905_PS_v1.5.pdf), [Raspberry Pi remote access](https://www.raspberrypi.com/documentation/computers/remote-access.html), and [Raspberry Pi hardware communication configuration](https://www.raspberrypi.com/documentation/computers/configuration.html#hardware-communication).
