# ADR 0002: Game Master Console terminology and capability boundary

- Status: Accepted
- Date: 2026-07-20
- Supersedes: “God Tool” terminology and any implied deployment relationship in earlier foundation documents

## Context

The live operator tool exists so a trusted Game Master can address cheating, recover from faults, pause or end play, and deliberately activate or resolve effects. Packet Predator arose partly to create development conditions around physical nodes, which made its capabilities easy to conflate with both that operator tool and the Game Controller.

## Decision

The live operator role is named **Game Master Console**. It sends privileged high-level requests through the authoritative Game Controller. Packet Predator remains an isolated developer workbench: it may impersonate protocol participants on a test bench, or drive a real Game Controller through an explicit test interface.

The two roles may share a broader console platform or presentation components, but production deployment must enforce different backend permissions and network reach. Game Master Console has no raw packet injection, endpoint impersonation, or direct-node control.

## Consequences

Quarantined prototype buttons do not become supported live-console functionality. Any reusable UI is separated from authorization and transport capabilities. Protocol-level details remain owned by the sibling Protocol Contract.
