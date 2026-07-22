# ADR 0003: Begin the layered Packet Predator runtime

- Status: Accepted
- Date: 2026-07-22
- Replaces: the active runtime-freeze rule in ADR 0001 after completion of its prerequisite milestones

## Context

The foundation checkpoint, component/message inventory, frozen v1 wire contract, and reference-codec milestone are complete. Protocol Contract release `1.0.1` now provides the executable structural authority needed to refactor Packet Predator without preserving the ambiguous v0 codec.

The archived application cannot serve as the supported hardware-free workbench. When radio hardware is absent it implicitly starts autonomous game actors and a coordinator, while its web process also contains game rules, privileged actions, radio access, and packet presentation. Extending that entrypoint would keep the prohibited coupling alive.

## Decision

Begin milestone `layered-local-workbench`. Replace the active foundation runtime freeze with the baseline in `.foundation/runtime-baseline.json` and update `.foundation/milestone.json` accordingly.

The new supported runtime is added under these boundaries:

- `packet_predator/wire_adapter.py` consumes the sibling Protocol Contract reference codec and fixtures without redefining constants;
- `packet_predator/transport.py` exposes transport status through an inspect-only implementation that imports no hardware driver;
- `packet_predator/service.py` owns fixture browsing, frame inspection, and in-memory capture presentation;
- `packet_predator/web.py` is a thin FastAPI/JSON/static-file layer over the service; and
- `workbench_web/` is the supported browser interface.

The default and only supported transport in this milestone is explicitly inspect-only. It never claims that a frame was transmitted and never falls back to autonomous simulation. Physical nRF905 work remains quarantined until the physical-adapter validation milestone.

The original `web_app.py`, `web/`, `packet/`, `nodes/`, `driver/`, `decoder.py`, and `simulator.py` stay byte-for-byte preserved by the archival manifest and tag. They remain unsupported evidence and are not imported by the new runtime. The legacy architecture exceptions are reclassified as archive-only; no new implementation may depend on them.

## Migration and rollback

The supported startup command changes from historical `web_app:app` to `packet_predator.web:app`. There is no state or data migration: this first workbench keeps only process-local inspection history. Rollback is the previous foundation commit or annotated `packet-predator-v0-experimental` tag; because the archived files remain unchanged, reproduction does not depend on undoing the new runtime.

## Consequences

Packet Predator can run on an ordinary Linux laptop with no GPIO, SPI, radio, Raspberry Pi package, or autonomous actor. Later deterministic replay and physical adapters can implement the transport boundary without changing protocol interpretation or the web layer. The old foundation hash test becomes an archive-preservation test rather than a ban on all new runtime files.
