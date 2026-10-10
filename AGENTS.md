# Agent instructions

These instructions apply to the entire Packet Predator repository.

## Required reading order

Before planning or editing, read:

1. `README.md`
2. `docs/architecture.md`
3. `docs/runtime-inventory.md`
4. the records in `docs/adr/` that bear on the change
5. sibling `../Protocol_Contract/README.md` and `docs/system-context.md` when protocol behavior is relevant

## Scope

- Work is scoped by the GitHub issue or request in hand.
- The supported surface is the runtime under `packet_predator/`, the isolated adapter under `packet_predator/adapters/`, deployment-profile examples under `config/`, deliberate recording data under `recordings/`, the thin frontend under `workbench_web/`, setup/run/diagnostic scripts, tests, and their documentation.
- Recording data must be finite and fully explicit: no branching, randomness, autonomous actor, inferred response, rules, or condition-driven behavior. References to released contract fixtures are preferred over copied frame definitions.
- Do not modify or import the archived prototype runtime: `web_app.py`, `web/`, `packet/`, `nodes/`, `driver/`, `decoder.py`, or `simulator.py`. Those paths remain immutable v0/quarantine evidence.
- The supported default must remain inspect-only and run without radio or Raspberry Pi hardware. Physical access requires an explicit adapter profile; replay still requires explicit selection. Neither may start autonomous actors.
- File an out-of-scope idea as a GitHub issue with the `parking-lot` label, then stop work on it.
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

## Documentation and NotebookLM

Documentation is a maintained project surface, not a retrospective task. In
the same change as any material design, behavior, interface, operational, or
hardware-validation change, update the relevant repository Markdown so a
fresh reader and the NotebookLM documentation viewer can understand the
current state without chat history or source-code archaeology.

- Keep `README.md` accurate for the supported purpose, current status, setup,
  normal use, limitations, and links to deeper documents.
- Keep the architecture, validation records, and ADRs aligned
  with the implementation. Add an ADR when a durable boundary or decision is
  changed; add a dated changelog entry for a user-visible or milestone-level
  change.
- Use standalone, human-readable Markdown: a descriptive title, clear heading
  hierarchy, short narrative explanation before dense detail, defined terms on
  first use, explicit assumptions/status/date where useful, and links to the
  authoritative sibling document rather than copied protocol values.
- Do not leave essential meaning only in JSON, fixtures, command output, a
  commit message, or an earlier conversation. Add a concise Markdown guide
  when structured data or a command needs interpretation.
- Do not churn documentation for a purely internal refactor with no changed
  behavior, boundary, operation, or decision. Never claim hardware validation
  or support that has not actually occurred.

## Validation impact

Changes to the supported workbench require repository tests for the affected
service, transport, editor, receiver, or browser boundary. If a published
inspection/transmit interface used by Hardware Validation Console changes,
update that Console's interface, scenario, failure, and evidence-verifier tests
in the same coordinated work. Packet Predator must not absorb Scenario
Simulator actors or Controller policy to make an integration test convenient.

## Completion

Run `./scripts/check` before reporting completion. Preserve the archived-runtime hashes and do not add an architecture exception merely to make a check pass. ADR 0005 and `.foundation/runtime-baseline.json` authorize the nRF905 validation boundary; changing that boundary requires another ADR.

A gate may not skip silently: if a check cannot run, that is a failure, not a
pass. See the gate-discipline convention at the top of `../.agents/WORKBOARD.txt`.

## Where work is tracked

Work lives in GitHub Issues in the repository that owns it, and every issue
appears on the org board: <https://github.com/orgs/SuspiciousCellmates/projects/2>

Look there before starting anything:

    gh issue list -R SuspiciousCellmates/Packet_Predator
    gh issue view <N> -R SuspiciousCellmates/Packet_Predator

If you do work that is not on the board, file an issue for it. The board is
only worth reading if it is complete.

After creating, reopening, or materially updating an upstream GitHub issue, or
after landing a pull request tied to an issue, run `../.agents/board-sync` from
the workspace root before reporting completion. Require a zero exit and
`failed 0`; otherwise the board may be incomplete. This reconciliation adds
missing open issues and removes retired-repository items, but does not replace
updating or closing the owning issue.

Issues track what is **to be done**. Durable decisions stay in ADRs, validation
evidence stays with the component that produced it, and the standing
conventions stay in `AGENTS.md` files like this one — none of those belong in
an issue, because none of them ever close.
