# Packet Predator

Packet Predator is an experimental developer packet workbench for Suspicious Cellmates. Its intended responsibility is to inspect, construct, capture, replay, and validate protocol messages through selectable transports. It is not the shared application shell.

**New to the project?** Start with [Packet Predator: a beginner's guide](USER_GUIDE.md). It explains the workbench through examples, gives simple operating instructions, and includes a glossary.

## Current status

The supported application is a layered browser workbench. By default it is hardware-free and uses the sibling Protocol Contract `1.0.1` reference codec to inspect all 38 conformance frames, hexadecimal bytes you paste, or frames released by a deliberately selected deterministic recording. The active physical milestone also provides an explicitly configured experimental nRF905 adapter. On 2026-07-24, two Raspberry Pi 5 and original Packet Predator HAT benches exchanged exact released frames successfully in both directions. The workbench never starts a radio without a profile, or starts a fake node, game coordinator, or autonomous scenario.

The old web-simulator remains reconstructable at tag `packet-predator-v0-experimental`; its files are immutable, unsupported evidence. Shared protocol ownership lives in the standalone sibling [Protocol Contract repository](../Protocol_Contract/README.md). Packet Predator reads that authority and does not redefine its values.

## Use it on a Linux laptop

Keep `Packet_Predator` and `Protocol_Contract` beside one another, then run:

```sh
cd Packet_Predator
./scripts/setup-local
./scripts/run-local
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000) in a browser. Choose an official example, paste frame hex, or select a finite recording and use its play, pause, step, reset, and speed controls. Each delivered frame reaches the same plain-language, field, byte, and journal views. Recent inspections are held in memory only and disappear when the server stops.

This setup installs only FastAPI and Uvicorn. It does not install the Raspberry Pi, SPI, GPIO, or nRF905 dependencies in the historical `requirements.txt`. See [the laptop workbench guide](docs/laptop-workbench.md) for troubleshooting and the optional environment settings.

For the first physical bench, follow [nRF905 two-Raspberry-Pi validation](docs/nrf905-two-pi-bench.md). It documents the proven original-HAT pinout and required Pi 5 overlay, keeps all hardware and RF settings in a local profile, verifies the radio configuration by exact readback, and tests one known 32-byte frame in each direction. The default example profile cannot transmit. The first successful evidence is preserved in [the 2026-07-24 validation result](docs/nrf905-validation-2026-07-24.md).

Recording replay is explicit and non-reactive. The files contain a fixed timetable of released contract examples; they cannot branch, make a decision, create a response, or emulate a node. See [deterministic recordings](docs/deterministic-recordings.md) for the boundary and authoring rules.

## Historical prototype

The archived prototype entrypoint is `web_app:app`. Do not use it for ordinary Packet Predator work: without Raspberry Pi radio modules it may initialize autonomous simulated nodes and a coordinator. Its game, map, difficulty, meeting, kill, sabotage, and rules-engine workflows are quarantined and are not supported product requirements.

## Mission

- Decode and inspect example, pasted, and eventually captured frames with exact bytes and provenance.
- Manually construct and transmit messages for development and diagnostics.
- Replay deterministic captures and validate contract conformance.
- Isolate physical, fake, file, and replay transports behind adapter boundaries.
- Make ambiguity and malformed data visible without making game decisions.

## Non-goals

- Defining protocol constants or wire layouts locally.
- Owning game state, rules, difficulty, penalties, or automatic decisions.
- Hosting Game Master Console workflows or privileged live-operator actions.
- Running autonomous scenario actors as an implicit application mode.
- Committing to nRF905 as the platform transport.

## Required reading and checks

Contributors and agents must follow [AGENTS.md](AGENTS.md), beginning with the prescribed document order. Before completion run:

```sh
./scripts/check
```
