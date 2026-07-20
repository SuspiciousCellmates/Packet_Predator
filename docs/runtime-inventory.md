# Runtime inventory

Classification describes architectural intent, not work authorized during foundation. Every listed runtime file remains frozen.

## Keep as workbench intent

| Capability | Current location | Qualification |
|---|---|---|
| Packet capture/history and stream presentation | `web_app.py`, `web/` | Keep intent; later isolate in service/thin web layers |
| Manual packet construction and transmit | `/api/spoof`, frontend builder | Keep intent; later consume contract-owned codec and use explicit authorization |
| Decode/hex inspection | `decoder.py`, frontend packet table | Keep intent; current local codec remains v0 evidence only |
| Radio configuration/diagnostics | `/api/config`, `driver/nrf905.py` | Keep only as experimental adapter tooling |
| Exact packet characterization tests | `tests/test_packet_protocol.py`, `tests/test_v0_characterization.py` | Keep until superseded by cross-language conformance fixtures |

## Replace in ordered milestones

| Capability/module | Replacement direction |
|---|---|
| Local `PayloadType`, `EVENT_TYPES`, `NodeType`, settings, and layouts | Released shared contract binding/reference codec after v1 |
| `RadioManager` global lifecycle and direct protocol knowledge | Explicit transport interface plus workbench service |
| `driver/virtual_airwaves.py` | Deterministic fake/replay transport |
| Monolithic `web_app.py` | Protocol, transport, service, and thin web layers |
| Implicit hardware-versus-simulation selection | Explicit adapter selection with visible status |
| Random simulation tests | Deterministic scenarios and replay fixtures |

## Quarantine as unsupported Packet Predator functionality

| Behavior | Current evidence | Future owner/disposition |
|---|---|---|
| Polling coordinator | `GameCoordinator` | Game Controller, if inventory review requires polling |
| Autonomous player/task actors | `simulator.py` | Separate deterministic scenario simulation |
| Map and movement | `/api/sim/map`, map canvas/frontend | Scenario visualization outside core workbench |
| Difficulty and penalty calculation | `/api/sim/difficulty`, task-fail rule | Game Controller policy |
| Meeting workflow | simulation trigger and node state methods | Game Controller; explicit privileged action may surface through God Tool |
| Kill workflow | simulation trigger/UI button and direct state mutation | Game Controller/God Tool according to reviewed authority |
| Sabotage decisions and automatic relay | virtual player, trigger, radio rules path | Game Controller; explicit action through God Tool if approved |
| Start/stop game endpoints | `/api/game/start`, `/api/game/stop` | Game Controller/God Tool workflow, not workbench product surface |
| Embedded rules engine | task-fail penalty and sabotage relay in `RadioManager` | Game Controller |
| Default Among Us node catalog | `DEFAULT_NODES` | Component/application configuration, not Packet Predator architecture |

The mechanical source of truth for quarantine entries is `.foundation/quarantine.json`.
