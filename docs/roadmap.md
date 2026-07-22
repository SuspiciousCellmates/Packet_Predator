# Roadmap

Milestones are sequential. A later milestone cannot begin until the preceding milestone is reviewed and closed through repository metadata and, where required, an ADR.

## Completed

- `foundation-protocol-workbench`: prototype archived, shared ownership established, scope and runtime guardrails accepted.
- Component/message inventory reviewed and approved in the sibling Protocol Contract repository.
- Smallest viable protocol v1 frozen as `1.0.0`.
- Reference codec and cross-language conformance suite released as Protocol Contract `1.0.1`.

## Now — Layered local workbench

Milestone ID: `layered-local-workbench` (active).

- Consume the sibling Protocol Contract reference codec without copying constants.
- Separate wire interpretation, transport status, workbench service, and thin web concerns.
- Provide a clear browser inspector that runs on an ordinary Linux laptop without radio hardware.
- Browse exact fixtures, paste/decode logical or padded frames, and expose labelled fields plus raw bytes.
- Keep the archived simulator, rules, map, and privileged game controls absent from the supported entrypoint.
- Retain an explicit inspect-only transport boundary for later physical adapters.

Exit requires the Packet Predator and Protocol Contract checks to pass, local browser/API verification without hardware, a clean architecture scan, and human review.

## Next — Deterministic replay and fake transport

1. Add explicit deterministic capture replay and a fake transport through the published transport interface. Do not restore autonomous game actors.

## Later — Fixed order

2. Validate capture and transmission through one selected physical adapter.
3. Build Game Controller and Game Master Console as distinct deployed roles against the shared contract; a console platform or presentation components may be shared without sharing production capabilities.
