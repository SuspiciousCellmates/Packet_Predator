# Roadmap

Milestones are sequential. A later milestone cannot begin until the preceding milestone is reviewed and closed through repository metadata and, where required, an ADR.

## Now — Foundation and scope control

Milestone ID: `foundation-protocol-workbench` (active).

- Preserve the exact experimental web-simulator snapshot and tag.
- Establish the standalone draft Protocol Contract and v0 evidence.
- Document Packet Predator as a developer packet workbench.
- Quarantine game, Game Master Console-like, and autonomous-simulation behavior.
- Enforce runtime hashes, known architecture exceptions, protocol ownership, and repository hygiene.
- Make no runtime, endpoint, frontend, dependency, or wire-format changes.

Exit requires both repository checks to pass and human review of this checkpoint.

## Next — Inventory review

1. Review and approve the component/message inventory with Packet Predator, Game Controller, Game Master Console, and node stakeholders. System roles plus Player Node and Task Node semantics were recorded on 2026-07-20; Environment Node and the exact message inventory remain to be reviewed. Resolve each row by acceptance, removal, or explicit ownership and requirements. Do not design/freeze v1 during the review itself.

## Later — Fixed order after inventory approval

2. Design and freeze the smallest viable protocol v1.
3. Add a reference codec and cross-language conformance fixtures.
4. Refactor Packet Predator into protocol, transport, service, and thin web layers; replace the foundation runtime manifest through an accepted ADR.
5. Replace the game simulator with deterministic replay/fake transport.
6. Validate capture and transmission through one selected physical adapter.
7. Build Game Controller and Game Master Console as distinct deployed roles against the shared contract; a console platform or presentation components may be shared without sharing production capabilities.
