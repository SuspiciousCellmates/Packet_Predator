# Packet Predator operator reference

**Status:** Current supported runtime

**Reviewed:** 2026-07-26

This is the concise technical reference for starting, checking, updating, and
diagnosing Packet Predator. The beginner-facing workflow remains in
[`USER_GUIDE.md`](../USER_GUIDE.md), while the exact two-radio procedure lives
in [`nrf905-two-pi-bench.md`](nrf905-two-pi-bench.md).

## Operating modes

| Mode | How selected | RF receive | RF transmit |
|---|---|---:|---:|
| Inspect only | `./scripts/run-local` with no adapter profile | no | no |
| Deterministic recording | Explicit browser selection | recorded frames only | no |
| Physical nRF905 | `./scripts/run-rpi PROFILE` | continuous, server-owned | only when both profile permission and one-shot confirmation are present |

The browser observes the process-local model. It does not poll or pace the
radio. Closing the page does not stop physical reception.

Valid fixtures, pasted frames, replay entries, and captured observations fork
into one browser-local editable draft. The Fields tab edits addresses, enums,
flags, numbers, and byte fields through Contract-backed compose operations.
The Bytes tab edits individual octets through a non-journaling draft decode.
Undo, redo, revert, cross-highlighting, and base-byte diffs are presentation
behavior; the selected journal observation is never modified.

Invalid drafts remain visible but cannot be transmitted. A deliberate editor
transmission includes draft/base provenance and exact changed fields/offsets
in the local cached result. This metadata never enters the radio frame.

## Scripts

| Command | Purpose | Important behavior |
|---|---|---|
| `./scripts/setup-local` | Create/reuse `.venv` and install laptop dependencies | Does not install Raspberry Pi GPIO/SPI packages |
| `./scripts/setup-rpi` | Create/reuse `.venv` and install physical-adapter dependencies | SPI and GPIO still require operating-system preparation |
| `./scripts/run-local` | Start the supported FastAPI workbench | Defaults to `127.0.0.1:8000` and inspect-only |
| `./scripts/run-rpi PROFILE` | Start with one explicit nRF905 profile | Binds to Pi localhost by default |
| `./scripts/run-rpi PROFILE --lan` | Start on all Pi interfaces | No authentication; trusted development LAN only |
| `./scripts/nrf905-diagnose --profile PROFILE profile` | Validate profile without hardware access | Safe first check |
| `./scripts/nrf905-diagnose --profile PROFILE probe` | Open hardware and verify exact nRF905 register readback | Does not itself send a protocol frame |
| `./scripts/nrf905-diagnose --profile PROFILE receive ...` | Wait for and compare one expected released frame | Bounded by the supplied timeout |
| `./scripts/nrf905-diagnose --profile PROFILE send ...` | Send one released fixture | Requires `transmit_enabled: true` |
| `./scripts/nrf905-diagnose --profile PROFILE walk-fixed` | Long-running base-station side of the range walk | Ctrl-C to stop; requires `transmit_enabled: true` |
| `./scripts/nrf905-diagnose --profile PROFILE walk-carried --station N --led NAME` | One range-walk burst at the current station | `--led` is required and fails loudly if it can't be driven; add `--continuous` to run consecutive bursts, auto-incrementing the station, until Ctrl-C; see [nrf905-walk-test.md](nrf905-walk-test.md) |
| `./scripts/update-rpi` | Fast-forward Protocol Contract and Packet Predator, refresh dependencies, run checks | Refuses dirty, detached, untracked, missing-upstream, or diverged repositories |
| `./scripts/install-systemd-service PROFILE` | Install and start the permanent physical Pi service | Renders the real local paths and always binds through `run-rpi` without `--lan` |
| `./scripts/systemd-status` | Show service state and its newest 30 journal lines | Observes the installed service without changing it |
| `./scripts/check` | Run architecture/foundation guards and unit tests | Required before completion |

Run `./scripts/nrf905-diagnose --help` and the subcommand help for the complete
diagnostic argument list.

## Server settings

`run-local` accepts these environment settings:

| Variable | Default | Meaning |
|---|---|---|
| `PACKET_PREDATOR_HOST` | `127.0.0.1` | HTTP bind address |
| `PACKET_PREDATOR_PORT` | `8000` | HTTP port |
| `PACKET_PREDATOR_ADAPTER_PROFILE` | unset | Explicit nRF905 profile path |
| `PACKET_PREDATOR_CONTRACT_ROOT` | sibling `Protocol_Contract` | Released Protocol Contract checkout |

The status page and `/api/status` distinguish inspect-only and physical
operation. A reachable webpage proves the server is running; it does not prove
that the radio is wired correctly or that another radio can hear it.

## Laptop, Pi, and tunnel ports

Packet Predator listens on port 8000 on its own host unless configured
otherwise. An SSH tunnel creates a different laptop-visible port:

```sh
ssh -L 8001:127.0.0.1:8000 USER@PACKET_PREDATOR_HOST
```

In this example:

- `127.0.0.1:8000` is the service as seen on the Pi;
- `127.0.0.1:8001` is the same service as seen on the laptop; and
- the tunnel terminal must remain open.

A failure to connect to laptop port 8001 does not by itself mean the Pi
service failed. Check the tunnel and the remote process separately.

For unattended Pi startup, follow
[`systemd-deployment.md`](systemd-deployment.md). Do not run a manual
`run-rpi` process concurrently with the installed service.

## nRF905 profile

Start from `config/nrf905-bench.example.json` and save the reviewed deployment
as an ignored `.local.json` file.

| Field | Meaning |
|---|---|
| `schema_version` | Must be `1` |
| `id` | Lowercase deployment profile identifier |
| `adapter` | Must be `nrf905` |
| `spi.device` | Linux SPI device, normally `/dev/spidev0.0` |
| `spi.speed_hz` | Pi-to-radio SPI clock, not RF frequency |
| `gpio.*` | Actual Linux GPIO chip and six distinct HAT signal lines |
| `radio.band`, `radio.channel` | nRF905 frequency selection |
| `radio.transmit_power_dbm` | One supported nRF905 power setting |
| `radio.receive_reduced_power` | Receiver power mode |
| `radio.automatic_retransmit` | Must remain `false` |
| `radio.address_hex` | Four-byte physical radio address |
| `radio.crystal_mhz` | Module crystal selection |
| `radio.crc_bits` | Hardware CRC width, `8` or `16` |
| `radio.transmit_enabled` | Explicit deployment permission to transmit |

Radio settings are deployment data, not Protocol Contract values. Both ends of
one RF test need matching physical settings.

## Model and evidence

The supported workbench retains:

- the newest 100 immutable observations;
- receiver state and counts;
- a monotonic model revision;
- a monotonic process-local `journal_sequence`; and
- the newest 256 model change notifications.

This is a bounded presentation model, not a permanent evidence store.
Restarting Packet Predator clears it. Preserve important API snapshots, exact
bytes, and the process/deployment revision as part of the validation run.

Use `journal_sequence` to order observations from one Packet Predator process.
Do not infer cross-host causal order from display timestamps.

## Transmit safety

Physical transmission requires:

1. an explicit physical profile;
2. `radio.transmit_enabled: true`;
3. a structurally valid fixed carrier frame; and
4. fresh confirmation for one request.

There is no automatic RF retry. Do not add spacing or retries to make a
validation scenario pass. A lost or uncertain transmit result must remain
visible as uncertain.

## Common failures

| Code or symptom | Meaning / next check |
|---|---|
| Contract unavailable | Confirm the sibling Contract checkout or `PACKET_PREDATOR_CONTRACT_ROOT` |
| Port already in use | Stop the prior server or choose another local port |
| `PROFILE_*` | Correct the local JSON profile before touching hardware |
| `NRF905_SPI_DEVICE_MISSING` | Enable SPI and verify the configured `/dev/spidev*` |
| `NRF905_GPIO_DEVICE_MISSING` | Verify the GPIO chip path |
| `NRF905_SPI_OPEN` / `NRF905_GPIO_OPEN` | Check permissions and competing processes |
| `NRF905_REGISTER_MISMATCH` | Check power, CSN, SCK, MOSI, MISO, and actual HAT wiring |
| `NRF905_TRANSMIT_TIMEOUT` | Check control/DR lines, module power, crystal, and profile |
| `RECEIVE_TIMEOUT` | No matching CRC-valid physical frame arrived before timeout |
| `RECEIVED_FRAME_MISMATCH` | RF delivered bytes, but they differed from the expected fixture |
| Browser says reconnecting | The page event stream is reconnecting; inspect receiver state separately |

## Files that must remain local

Do not commit `.venv`, caches, captured evidence containing private data, or
`config/*.local.json`. The archived prototype paths listed in `AGENTS.md` are
immutable evidence and are not supported runtime code.
