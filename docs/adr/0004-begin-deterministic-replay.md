# ADR 0004: Begin deterministic recording replay

- Status: Accepted
- Date: 2026-07-22
- Supersedes: the active milestone boundary in ADR 0003 after human review of the laptop inspector

## Context

The layered local workbench now consumes Protocol Contract `1.0.1`, runs without hardware, presents all released examples in a browser, keeps a process-local inspection journal, and passes its architectural and conformance checks. The user reviewed that checkpoint and authorized the next ordered milestone.

The archived prototype's virtual airwaves cannot be reused. They are coupled to autonomous threaded actors, random choices, game state, and rules. A useful hardware-free transport must reproduce the same bytes and order on every run without deciding what any participant should do.

## Decision

Begin milestone `deterministic-replay-fake-transport`. Extend the supported baseline rather than replacing its layers.

- Recording files under `recordings/` contain an ordered timetable of references to released Protocol Contract examples, optional scenario-local endpoint addresses, direction, and explanatory notes. They contain no state machine, condition, branch, random choice, or rule.
- `packet_predator/replay.py` validates recording structure and asks the existing wire adapter to resolve each reference into a complete frame. It does not define shared message values or layouts.
- `packet_predator/transport.py` publishes a small receive-side transport boundary and adds a deterministic replay implementation. The transport moves opaque complete frames and knows no message semantics.
- Playback advances only through explicit play, pause, step, reset, speed, and poll operations. It has no autonomous actors or background thread. An injectable monotonic clock makes scheduling tests exact.
- `packet_predator/service.py` remains responsible for decoding delivered frames and adding capture metadata to the inspection journal.
- The browser exposes an explicit recording player. Inspect-only remains the startup mode; selecting a recording is required before the fake transport becomes active.

The recordings are developer demonstrations, not authoritative game scenarios. Their notes describe the frames being replayed and cannot assert unobserved Game Controller reasoning.

## Migration and rollback

There is no persistent data migration. Existing manual inspection routes and UI remain available. The new recording catalogue is read at service startup, and replay journal entries remain process-local.

Rollback is commit `54a5416`, the completed layered local workbench. The archived experimental prototype remains separately reconstructable through `packet-predator-v0-experimental`.

## Consequences

Developers can reproduce an ordered packet exchange on a laptop, inspect it one frame at a time, and test timing controls without radio hardware. A future physical adapter can implement the same opaque-frame receive boundary. This milestone does not authorize packet transmission, Game Controller logic, node emulation, conversation inference, or production simulation.
