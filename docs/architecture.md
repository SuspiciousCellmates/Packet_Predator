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
| Physical adapter | `packet_predator/adapters/nrf905.py`, `packet_predator/adapters/nrf905_linux.py`, `packet_predator/nrf905_transport.py` | Configure and move opaque fixed frames through an explicitly selected nRF905; isolate Linux SPI/GPIO imports and know no message semantics |
| Physical receiver | `packet_predator/receiver.py` | Own the configured adapter's receive lifecycle, wait for frames independently of browsers, and hand opaque frames to the service |
| Deployment profile | `packet_predator/nrf905_profile.py`, `config/` | Strictly validate local SPI, GPIO, and radio settings without making them shared protocol constants |
| Pi service deployment | `packet_predator/systemd.py`, `packaging/`, `scripts/*systemd*` | Render and install one profile-explicit, loopback-only service as the ordinary Pi user |
| Workbench service | `packet_predator/service.py` | Turn fixture, pasted, replay-delivered, or physically received bytes into inspectable observations |
| Presentation model | `packet_predator/model.py` | Retain the newest 100 immutable observations, receiver state, monotonic revisions, and subscriber notifications |
| Thin web layer | `packet_predator/web.py` | Own application lifespan, validate HTTP inputs, expose model snapshots/events, and serve static files |
| Browser UI | `workbench_web/` | Observe model state; fork immutable observations into local drafts; present fixture browsing, editable Fields/Bytes, synchronized diffs/history, validation feedback, and byte drill-down without driving physical receive |

The physical-validation editor boundary is defined in
[`editor-api-v1.md`](editor-api-v1.md). ADR 0007 requires composition through
the wire adapter/reference codec, immutable source observations, explicit
process/build identity, and duplicate-safe validation-client transmit IDs.

Dependency direction is web → service → model / receiver / replay catalogue / transport / wire adapter. For live capture, the application-lifecycle receiver waits on the physical transport, the service inspects each opaque frame, and the model publishes the resulting observation. The browser reads a snapshot and subscribes to model-revision events; browser timing never calls or backpressures the radio. The replay catalogue resolves examples through an injected wire-adapter operation, then gives opaque frames to the transport. The nRF905 transport accepts only complete fixed frames; it does not decode their fields. Linux-specific imports are confined to `packet_predator/adapters/nrf905_linux.py`. The wire adapter alone loads the sibling reference codec. The supported runtime imports none of the archived modules.

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
- `driver/nrf905.py`: retain only as experimental archive evidence and never import it into the supported runtime. The isolated replacement under `packet_predator/adapters/` was physically validated on the original HATs in both directions on 2026-07-24.
- `driver/virtual_airwaves.py`: replace with deterministic fake/replay transport.
- `web_app.py`: later split into protocol, transport, workbench service, and thin web layers; remove production game/controller/Game Master Console concerns from supported scope.
- `web/`: retain packet-workbench views where useful; quarantine map and game controls.
- `simulator.py`: quarantine completely; preserve in Git until deterministic scenario replacement exists elsewhere.

## Completed physical-validation boundary

ADR 0005, ADR 0006, and `.foundation/runtime-baseline.json` authorize one explicitly configured nRF905 adapter while retaining the old hash manifest as an archive-preservation check. Inspect-only remains the default. With a profile, application lifespan starts a signal-driven receiver before any browser is required and stops it before GPIO/SPI close. Receive, transmit, and close are serialized; codec-invalid frames remain visible without stopping capture. The adapter may capture a frame or execute one confirmed manual transmit request; it cannot construct responses, emulate a node, branch on message meaning, or implement Game Controller policy. Deterministic replay remains available under the ADR 0004 constraints.

Packet Predator may impersonate a Game Controller or another participant only in an isolated bench environment. For integration testing it should drive a real Game Controller through an intentional test interface. A future shared console platform does not merge these deployed roles: the production Game Master Console must lack raw-frame injection, endpoint impersonation, and direct-node access in its backend permissions and network reach, not merely hide those controls.
