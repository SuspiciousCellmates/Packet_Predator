# Packet Predator

Packet Predator is an experimental developer packet workbench for Suspicious Cellmates. Its intended responsibility is to inspect, construct, capture, replay, and validate protocol messages through selectable transports. It is not the shared application shell.

## Current status

The supported application is now a layered, hardware-free browser workbench. It uses the sibling Protocol Contract `1.0.1` reference codec to inspect all 38 conformance frames or hexadecimal bytes you paste. It never starts a radio, fake node, game coordinator, or autonomous scenario.

The old web-simulator remains reconstructable at tag `packet-predator-v0-experimental`; its files are immutable, unsupported evidence. Shared protocol ownership lives in the standalone sibling [Protocol Contract repository](../Protocol_Contract/README.md). Packet Predator reads that authority and does not redefine its values.

## Use it on a Linux laptop

Keep `Packet_Predator` and `Protocol_Contract` beside one another, then run:

```sh
cd Packet_Predator
./scripts/setup-local
./scripts/run-local
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000) in a browser. Choose an official example in the left-hand library or paste frame hex. The result starts with a plain-language route and meaning, with separate field and byte views for deeper inspection. Recent inspections are held in memory only and disappear when the server stops.

This setup installs only FastAPI and Uvicorn. It does not install the Raspberry Pi, SPI, GPIO, or nRF905 dependencies in the historical `requirements.txt`. See [the laptop workbench guide](docs/laptop-workbench.md) for troubleshooting and the optional environment settings.

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
