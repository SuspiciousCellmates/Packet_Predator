# Architecture

## Archived prototype

| Area | Current module(s) | Current coupling |
|---|---|---|
| Web/UI | `web_app.py`, `web/` | API, static UI, SSE, radio, protocol, game control, and simulation share one process |
| Protocol | `packet/`, `decoder.py`, `nodes/node.py`, constants in `web_app.py` | Local Python authority conflicts with STM32 and contains contextual decoding |
| Transport | `driver/nrf905.py`, `driver/virtual_airwaves.py` | Hardware fallback and fake routing are selected implicitly |
| Scenario/game | `simulator.py`, `GameCoordinator` and rules in `web_app.py` | Autonomous random actors and game policy run inside the workbench |
| Tests | `tests/` | Packet characterization and coupled simulator behavior |

The archived runtime remains frozen as evidence by `.foundation/runtime-freeze.sha256` and tag `packet-predator-v0-experimental`. Quarantined behavior is enumerated in `.foundation/quarantine.json`; none is reachable from the supported entrypoint.

## Supported layered runtime

| Layer | Location | Responsibility |
|---|---|---|
| Wire adapter | `packet_predator/wire_adapter.py` | Locate released Protocol Contract artifacts and expose decode/catalog/fixture operations without defining shared values |
| Replay catalogue | `packet_predator/replay.py`, `recordings/` | Validate finite recording timetables and resolve released example references without game behavior |
| Transport | `packet_predator/transport.py` | Publish the opaque-frame receive boundary; provide inspect-only and explicitly selected deterministic replay adapters |
| Workbench service | `packet_predator/service.py` | Turn fixture, pasted, or replay-delivered bytes into inspectable entries and process-local history |
| Thin web layer | `packet_predator/web.py` | Validate HTTP inputs, call the service, return JSON, and serve static files |
| Browser UI | `workbench_web/` | Fixture browsing, search, summary, field/label inspection, validation feedback, and byte drill-down |

Dependency direction is web → service → replay catalogue / transport / wire adapter. The replay catalogue resolves examples through an injected wire-adapter operation, then gives opaque frames to the transport. The transport never interprets them. The wire adapter alone loads the sibling reference codec. The supported runtime imports none of the archived modules.

## Target boundaries

| Boundary | Responsibility | Allowed dependency direction |
|---|---|---|
| Shared Protocol Contract | Versioned constants, layouts, semantic definitions, fixtures, future reference codec/bindings | Runtime components depend on a released contract; the contract depends on none |
| Packet Predator protocol adapter | Consume a released contract and expose decode/encode/conformance operations | Depends on contract only |
| Transport adapters | Send/receive opaque complete frames through physical, fake, file, or replay media | Depend on small workbench transport interfaces, not message semantics |
| Workbench service | Capture, manual construction, validation, replay, and explicit transmit requests | Depends on protocol and transport interfaces; never game policy |
| Thin web layer | Present workbench service operations and results | Depends on workbench service only |
| Game Controller | Authoritative game state, rules, timing, and automatic decisions | Separate application consuming the contract |
| Game Master Console | Explicit privileged live-operator workflows | Distinct deployed role consuming authorized Game Controller interfaces; may share console presentation/platform code but never workbench permissions |
| Voting Kiosk | Restricted local meeting/voting web workflow | Game Controller-facing web role; not a radio node or privileged console |
| Scenario simulation | Deterministic scenarios and fake/replay transport | Separate test component consuming published interfaces |

## Existing-module disposition

- `packet/`, `decoder.py`, and `nodes/node.py`: retain only as v0 evidence; replace with a future contract-owned reference codec/binding after v1.
- `driver/nrf905.py`: retain as experimental evidence; later adapt behind a transport interface and validate physically.
- `driver/virtual_airwaves.py`: replace with deterministic fake/replay transport.
- `web_app.py`: later split into protocol, transport, workbench service, and thin web layers; remove production game/controller/Game Master Console concerns from supported scope.
- `web/`: retain packet-workbench views where useful; quarantine map and game controls.
- `simulator.py`: quarantine completely; preserve in Git until deterministic scenario replacement exists elsewhere.

## Active replay constraint

ADR 0004 and `.foundation/runtime-baseline.json` authorize finite deterministic recordings and an explicit fake transport while retaining the old hash manifest as an archive-preservation check. Recordings are data, not a scenario engine: they cannot branch, react, choose, infer responses, or model component state. This milestone does not authorize a physical adapter, Game Controller policy, node emulator, or Game Master Console workflow.

Packet Predator may impersonate a Game Controller or another participant only in an isolated bench environment. For integration testing it should drive a real Game Controller through an intentional test interface. A future shared console platform does not merge these deployed roles: the production Game Master Console must lack raw-frame injection, endpoint impersonation, and direct-node access in its backend permissions and network reach, not merely hide those controls.
