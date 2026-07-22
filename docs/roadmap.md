# Roadmap

Milestones are sequential. A later milestone cannot begin until the preceding milestone is reviewed and closed through repository metadata and, where required, an ADR.

## Completed

- `foundation-protocol-workbench`: prototype archived, shared ownership established, scope and runtime guardrails accepted.
- Component/message inventory reviewed and approved in the sibling Protocol Contract repository.
- Smallest viable protocol v1 frozen as `1.0.0`.
- Reference codec and cross-language conformance suite released as Protocol Contract `1.0.1`.
- `layered-local-workbench`: hardware-free browser inspector, explicit inspect-only carrier, and layered supported entrypoint reviewed and accepted.

## Now — Deterministic replay and fake transport

Milestone ID: `deterministic-replay-fake-transport` (active).

- Add validated recording files containing only explicit, ordered frame references and timing.
- Add a fake transport that moves opaque frames through the same receive boundary intended for later adapters.
- Provide play, pause, step, reset, and controlled-speed operations with exact deterministic tests.
- Journal each delivered frame with recording, direction, sequence, and scheduled-time provenance.
- Make recording selection explicit; retain inspect-only startup and prohibit implicit fake actors.
- Add no game state, policy, decisions, random behavior, node emulation, or packet transmission.

Exit requires exact clock-controlled replay tests, malformed-recording rejection tests, browser/API verification without hardware, both repository checks, a clean architecture scan, and human review.

## Next — Physical adapter validation

1. Validate capture and transmission through one selected physical adapter.

## Later — Fixed order

2. Build Game Controller and Game Master Console as distinct deployed roles against the shared contract; a console platform or presentation components may be shared without sharing production capabilities.
