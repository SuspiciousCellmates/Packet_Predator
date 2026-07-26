# Runtime inventory

The archived prototype files remain immutable evidence. The supported layered runtime is separately authorized by ADR 0003.

## Supported now

| Capability | Location | Boundary |
|---|---|---|
| v1 frame decode and fixture catalog | `packet_predator/wire_adapter.py` | Delegates to sibling Protocol Contract `1.0.1`; defines no shared values |
| Recording catalogue | `packet_predator/replay.py`, `recordings/` | Finite ordered fixture references with validated timing; no executable scenario behavior |
| Hardware-free transports | `packet_predator/transport.py` | Inspect-only startup plus explicitly selected deterministic replay; neither transmits |
| Experimental nRF905 transport | `packet_predator/adapters/`, `packet_predator/nrf905_profile.py`, `packet_predator/nrf905_transport.py` | Explicit profile only; exact register readback, signal-driven capture, and individually confirmed manual transmission; no message semantics or automatic reply |
| Physical receive lifecycle | `packet_predator/receiver.py` | Application-owned worker waits for `DR` and feeds opaque frames to the service independently of browser connections |
| Inspection history/model | `packet_predator/service.py`, `packet_predator/model.py` | Process-local newest-100 observations, receiver state, and revision notifications only; no game state |
| JSON/static application | `packet_predator/web.py`, `workbench_web/` | Thin command/snapshot/SSE routes and a browser view that never drives physical receive |
| Structured editor contract | `docs/editor-api-v1.md` | Registry-derived schema, codec-backed composition, immutable draft provenance, and explicit duplicate-safe transmit identity; completed as part of physical-adapter validation |

## Keep as archived workbench intent

| Capability | Current location | Qualification |
|---|---|---|
| Packet capture/history and stream presentation | `web_app.py`, `web/` | Keep intent; later isolate in service/thin web layers |
| Manual packet construction and transmit | `/api/spoof`, frontend builder | Keep intent; later consume contract-owned codec and use explicit authorization |
| Decode/hex inspection | `decoder.py`, frontend packet table | Keep intent; current local codec remains v0 evidence only |
| Radio configuration/diagnostics | `/api/config`, `driver/nrf905.py` | Keep only as experimental adapter tooling |
| Exact packet characterization tests | `tests/test_packet_protocol.py`, `tests/test_v0_characterization.py` | Keep until superseded by cross-language conformance fixtures |

## Replacement progress and later work

| Capability/module | Replacement direction |
|---|---|
| Local `PayloadType`, `EVENT_TYPES`, `NodeType`, settings, and layouts | Replaced in the supported entrypoint by the sibling reference codec; retained only as v0 evidence |
| `RadioManager` global lifecycle and direct protocol knowledge | Replaced for physical validation by an isolated nRF905 adapter, application-lifecycle receiver, service, and model behind the opaque-frame boundary; the archived manager remains unused |
| `driver/virtual_airwaves.py` | Replaced for supported use by the deterministic opaque-frame replay transport; legacy file retained as evidence |
| Monolithic `web_app.py` | Replaced for supported use by wire adapter, transport, service, and thin web layers |
| Implicit hardware-versus-simulation selection | Replaced by explicit visible inspect-only status; adapter selection remains later work |
| Random simulation tests | Replaced for supported use by clock-controlled recording replay tests; legacy characterization tests remain quarantined evidence |

## Quarantine as unsupported Packet Predator functionality

| Behavior | Current evidence | Future owner/disposition |
|---|---|---|
| Polling coordinator | `GameCoordinator` | Game Controller, if inventory review requires polling |
| Autonomous player/task actors | `simulator.py` | Separate deterministic scenario simulation |
| Map and movement | `/api/sim/map`, map canvas/frontend | Scenario visualization outside core workbench |
| Difficulty and penalty calculation | `/api/sim/difficulty`, task-fail rule | Game Controller policy |
| Meeting workflow | simulation trigger and node state methods | Game Controller; explicit privileged request may surface through Game Master Console |
| Kill workflow | simulation trigger/UI button and direct state mutation | Game Controller policy; correction/intervention through Game Master Console |
| Sabotage decisions and automatic relay | virtual player, trigger, radio rules path | Game Controller; explicit operator request through Game Master Console if approved |
| Start/stop game endpoints | `/api/game/start`, `/api/game/stop` | Game Controller with Game Master Console workflow, not workbench product surface |
| Embedded rules engine | task-fail penalty and sabotage relay in `RadioManager` | Game Controller |
| Default Among Us node catalog | `DEFAULT_NODES` | Component/application configuration, not Packet Predator architecture |

The mechanical source of truth for quarantine entries is `.foundation/quarantine.json`.
