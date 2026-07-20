# ADR 0001: Freeze the foundation runtime

- Status: Accepted
- Date: 2026-07-20

## Context

The experimental prototype mixes useful packet-workbench behavior with protocol authority, game policy, privileged actions, and autonomous simulation. Refactoring before the shared inventory and contract decisions would risk changing undocumented behavior and losing evidence.

## Decision

The runtime files listed in `.foundation/runtime-freeze.sha256` are frozen at the `packet-predator-v0-experimental` snapshot for the entire `foundation-protocol-workbench` milestone. Foundation changes are limited to documentation, metadata, validation tooling, tests, and CI.

Runtime hash checks and an archive-tag comparison must fail on any runtime, API, frontend, dependency, asset, or wire-behavior change. Current architecture violations are allowed only through the explicit baseline in `.foundation/architecture-exceptions.json` and are not endorsements.

## Replacement rule

A later runtime-refactor milestone may replace the manifest only through a new accepted ADR that names the replacement baseline, explains migration and rollback, updates `.foundation/milestone.json`, and removes or reclassifies affected exceptions. Disabling a check or editing an exception solely to pass CI is not an accepted replacement.

## Consequences

Known prototype defects remain intact during foundation. Git and the annotated archive tag preserve them; documentation and quarantine prevent them from being treated as supported Packet Predator behavior.
