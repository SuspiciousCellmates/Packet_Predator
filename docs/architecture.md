# Architecture

## Current prototype

| Area | Current module(s) | Current coupling |
|---|---|---|
| Web/UI | `web_app.py`, `web/` | API, static UI, SSE, radio, protocol, game control, and simulation share one process |
| Protocol | `packet/`, `decoder.py`, `nodes/node.py`, constants in `web_app.py` | Local Python authority conflicts with STM32 and contains contextual decoding |
| Transport | `driver/nrf905.py`, `driver/virtual_airwaves.py` | Hardware fallback and fake routing are selected implicitly |
| Scenario/game | `simulator.py`, `GameCoordinator` and rules in `web_app.py` | Autonomous random actors and game policy run inside the workbench |
| Tests | `tests/` | Packet characterization and coupled simulator behavior |

The complete current runtime is frozen by `.foundation/runtime-freeze.sha256`. Quarantined behavior is enumerated in `.foundation/quarantine.json`.

## Target boundaries

| Boundary | Responsibility | Allowed dependency direction |
|---|---|---|
| Shared Protocol Contract | Versioned constants, layouts, semantic definitions, fixtures, future reference codec/bindings | Runtime components depend on a released contract; the contract depends on none |
| Packet Predator protocol adapter | Consume a released contract and expose decode/encode/conformance operations | Depends on contract only |
| Transport adapters | Send/receive opaque complete frames through physical, fake, file, or replay media | Depend on small workbench transport interfaces, not message semantics |
| Workbench service | Capture, manual construction, validation, replay, and explicit transmit requests | Depends on protocol and transport interfaces; never game policy |
| Thin web layer | Present workbench service operations and results | Depends on workbench service only |
| Game Controller | Authoritative game state, rules, timing, and automatic decisions | Separate application consuming the contract |
| God Tool | Explicit privileged operator workflows | Separate application consuming contract and authorized controller interfaces |
| Scenario simulation | Deterministic scenarios and fake/replay transport | Separate test component consuming published interfaces |

## Existing-module disposition

- `packet/`, `decoder.py`, and `nodes/node.py`: retain only as v0 evidence; replace with a future contract-owned reference codec/binding after v1.
- `driver/nrf905.py`: retain as experimental evidence; later adapt behind a transport interface and validate physically.
- `driver/virtual_airwaves.py`: replace with deterministic fake/replay transport.
- `web_app.py`: later split into protocol, transport, workbench service, and thin web layers; remove game/controller/God Tool concerns from supported scope.
- `web/`: retain packet-workbench views where useful; quarantine map and game controls.
- `simulator.py`: quarantine completely; preserve in Git until deterministic scenario replacement exists elsewhere.

## Foundation constraint

This document describes a target but does not authorize refactoring. The active `Now` milestone permits no runtime, endpoint, frontend, dependency, or wire-format change. An accepted ADR must explicitly replace the runtime-freeze manifest when the ordered refactor milestone begins.
