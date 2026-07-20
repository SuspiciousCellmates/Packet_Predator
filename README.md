# Packet Predator

Packet Predator is an experimental developer packet workbench for Suspicious Cellmates. Its intended responsibility is to inspect, construct, capture, replay, and validate protocol messages through selectable transports. It is not the shared application shell.

## Current status

The current code is an archived web-simulator prototype preserved by tag `packet-predator-v0-experimental`. The active `foundation/protocol-workbench` milestone adds documentation and mechanical guardrails only: runtime source, endpoints, frontend behavior, and wire behavior remain frozen.

Shared protocol ownership lives in the standalone sibling [Protocol Contract repository](../Protocol_Contract/README.md). The local Python constants and codec are v0 evidence under quarantine, not an authority for future protocol changes.

## Prototype startup notes

For historical reproduction, create a Python environment, install `requirements.txt`, and run:

```sh
python -m uvicorn web_app:app --reload
```

The prototype may initialize autonomous simulated nodes and a coordinator automatically when Raspberry Pi radio modules are unavailable. Those game, map, difficulty, meeting, kill, sabotage, and rules-engine workflows are unsupported quarantined behavior; do not use them as Packet Predator product requirements.

## Mission

- Decode and inspect captured frames with exact bytes and provenance.
- Manually construct and transmit messages for development and diagnostics.
- Replay deterministic captures and validate contract conformance.
- Isolate physical, fake, file, and replay transports behind adapter boundaries.
- Make ambiguity and malformed data visible without making game decisions.

## Non-goals

- Defining protocol constants or wire layouts locally.
- Owning game state, rules, difficulty, penalties, or automatic decisions.
- Hosting God Tool workflows or privileged operator actions.
- Running autonomous scenario actors as an implicit application mode.
- Committing to nRF905 as the platform transport.

## Required reading and checks

Contributors and agents must follow [AGENTS.md](AGENTS.md), beginning with the prescribed document order. Before completion run:

```sh
./scripts/check
```
