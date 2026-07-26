# Roadmap

Milestones are sequential. A later milestone cannot begin until the preceding milestone is reviewed and closed through repository metadata and, where required, an ADR.

## Completed

- `foundation-protocol-workbench`: prototype archived, shared ownership established, scope and runtime guardrails accepted.
- Component/message inventory reviewed and approved in the sibling Protocol Contract repository.
- Smallest viable protocol v1 frozen as `1.0.0`.
- Reference codec and cross-language conformance suite released as Protocol Contract `1.0.1`.
- `layered-local-workbench`: hardware-free browser inspector, explicit inspect-only carrier, and layered supported entrypoint reviewed and accepted.
- `deterministic-replay-fake-transport`: finite recording replay, fake opaque-frame transport, exact clock controls, and capture provenance reviewed and accepted.

## Now — nRF905 physical adapter validation

Milestone ID: `nrf905-physical-adapter-validation` (active).

- Add a fresh isolated nRF905 adapter; never import the archived v0 driver.
- Load SPI, GPIO, RF, and transmit settings only from an explicit deployment profile.
- Prove SPI/GPIO access and exact nRF905 configuration-register readback on each Raspberry Pi 5.
- Transmit and capture exact 32-byte released contract examples from Pi A to Pi B and then Pi B to Pi A.
- Decode and journal physical frames through the existing reference-codec and service boundary.
- Retain inspect-only startup when no adapter profile is supplied; add no node emulation, automatic replies, game state, or policy.
- Decouple physical receive timing from the browser: continuously service the configured adapter into a process-local workbench model, then let the web layer observe that model without driving the radio. See [the physical receive, data model, and browser view plan](physical-receive-model-view-plan.md).
- Complete the physical-validation operator reference and define the
  contract-backed structured packet draft/editor needed to construct the
  assigned re-hello without manually rewriting a full hexadecimal frame.
- Expose stable process/build identity and duplicate-safe deliberate transmit
  request identity for laptop-hosted validation tooling, without adding
  scenario or Game Controller policy to Packet Predator.

The structured editor, immutable draft provenance, Fields/Bytes synchronization,
and duplicate-safe browser transmit identity are implemented. Physical
acceptance through the laptop Hardware Validation Console remains in the
cross-product validation phase.

Physical evidence collected on 2026-07-24: the two original Packet Predator nRF905 HAT benches delivered exact released fixtures from Pi A to Pi B and Pi B to Pi A, with both messages decoded through Protocol Contract `1.0.1`. The continuous receiver and model-driven web view were implemented in software on 2026-07-25. On 2026-07-26 the operator reported that the physical Packet Predator–Radio Gateway–Game Controller follow-up exchange was working; milestone closure still requires the saved model/journal evidence to be appended and reviewed. The required exchange is an enrolled `NODE_HELLO` followed naturally by `HELLO_RESULT(CAPABILITIES_REQUIRED)` and `CAPABILITY_REQUEST`, without transmitter spacing or retry behavior. See [the validation result](nrf905-validation-2026-07-24.md) and [the revalidation runbook](continuous-receive-revalidation.md).

Exit requires passing fake-backend adapter tests, clear malformed-profile and timeout failures, exact register readback on both Pis, exact fixture delivery in both RF directions, both repository checks, and human review of the physical evidence.

## Next — Game Controller authoritative state reconstruction

The Game Controller is already a separate application and its discovery and
enrollment slice is implemented. After that repository records physical
discovery, enrollment, capability transfer, and `READY_FOR_SNAPSHOT`, its next
milestone reconstructs authoritative no-session and component state, sends
atomic snapshots, and requires `STATE_APPLIED`.

Packet Predator remains supporting inspection and validation tooling. It does
not absorb Game Controller policy or Game Master Console workflows.

## Later — Fixed order

- Build the Game Master Console as a distinct privileged application against
  reviewed Game Controller APIs.
- Validate additional transport adapters only when a concrete need justifies them.
