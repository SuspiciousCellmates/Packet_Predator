# Roadmap

Milestones are sequential. A later milestone cannot begin until the preceding milestone is reviewed and closed through repository metadata and, where required, an ADR.

## Completed

- `foundation-protocol-workbench`: prototype archived, shared ownership established, scope and runtime guardrails accepted.
- Component/message inventory reviewed and approved in the sibling Protocol Contract repository.
- Smallest viable protocol v1 frozen as `1.0.0`.
- Reference codec and cross-language conformance suite released as Protocol Contract `1.0.1`.
- `layered-local-workbench`: hardware-free browser inspector, explicit inspect-only carrier, and layered supported entrypoint reviewed and accepted.
- `deterministic-replay-fake-transport`: finite recording replay, fake opaque-frame transport, exact clock controls, and capture provenance reviewed and accepted.
- `nrf905-physical-adapter-validation`: completed on 2026-07-26. The isolated
  adapter retained inspect-only startup by default, validated profile/readback
  and exact released fixtures in both RF directions, and gained a
  signal-driven receiver whose capture is independent of the browser. The
  structured editor and duplicate-safe deliberate transmit identity supported
  the real Controller exchange without adding Controller policy. The retained
  Hardware Validation Console capability run proved the naturally consecutive
  `HELLO_RESULT(CAPABILITIES_REQUIRED)` / `CAPABILITY_REQUEST` pair and a
  correlated capability transfer through `READY_FOR_SNAPSHOT`. See the
  [physical validation record](nrf905-validation-2026-07-24.md).

## Next — Game Controller authoritative state reconstruction

The Game Controller's discovery/enrollment slice is physically accepted through
capability transfer and `READY_FOR_SNAPSHOT`. Its next milestone reconstructs
authoritative no-session and component state, sends atomic snapshots, and
requires `STATE_APPLIED`.

Packet Predator remains supporting inspection and validation tooling. It does
not absorb Game Controller policy or Game Master Console workflows.

## Later — Fixed order

- Build the Game Master Console as a distinct privileged application against
  reviewed Game Controller APIs.
- Validate additional transport adapters only when a concrete need justifies them.
