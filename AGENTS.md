# Agent instructions

These instructions apply to the entire Packet Predator repository.

## Required reading order

Before planning or editing, read:

1. `README.md`
2. `docs/roadmap.md`
3. `docs/architecture.md`
4. `docs/runtime-inventory.md`
5. `docs/audit-2026-07-20.md`
6. every record in `docs/adr/`, in numeric order
7. `docs/ideas.md`
8. sibling `../Protocol_Contract/README.md`, `AGENTS.md`, `docs/system-context.md`, and `docs/protocol-v0.md` when protocol behavior is relevant

## Active-scope rule

- Work only within the active `Now` milestone in `docs/roadmap.md` and `.foundation/milestone.json`.
- The current foundation milestone permits documentation, characterization tests, and guardrails only. Do not change runtime source, endpoints, frontend behavior, dependencies, or wire behavior.
- Record an out-of-scope idea as one short line in `docs/ideas.md`, then stop work on it.
- Do not treat quarantined prototype behavior as supported functionality.

## Hard boundaries

- Packet Predator is a developer packet workbench.
- Never add game policy, automatic game decisions, rules-engine behavior, difficulty behavior, or orchestration.
- Never add Game Master Console workflows or privileged live-operator actions.
- Never define or redefine shared protocol constants, layouts, event values, node types, or setting indexes in Packet Predator.
- The sibling Protocol Contract repository is the only shared protocol authority.
- nRF905 is an experimental adapter, not a platform commitment.

## Protocol changes

Make contract changes in `../Protocol_Contract`, not here. Every contract change requires an ADR, affected fixture updates, a version change, and a changelog entry. Follow the contract repository's `AGENTS.md` workflow and do not freeze v1 before the component/message inventory review.

## Completion

Run `./scripts/check` before reporting completion. Do not bypass the frozen-runtime hash check or add an architecture exception merely to make a check pass. Replacing the runtime freeze requires a later milestone plus an accepted ADR naming the replacement baseline.
