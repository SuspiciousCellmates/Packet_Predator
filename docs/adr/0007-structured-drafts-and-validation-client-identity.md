# ADR 0007: Contract-backed packet drafts and validation-client identity

- Status: Accepted
- Date: 2026-07-26
- Refines: the manual construction and physical-validation boundary in ADR 0005

## Context

Physical Game Controller validation currently requires an operator to alter a
complete hexadecimal frame. That is error-prone even when the intended change
is one address or one registered field. A laptop-hosted validation harness also
needs to distinguish one Packet Predator process from another and must never
repeat RF because an HTTP result was lost.

The Protocol Contract reference codec already owns structural encoding.
Captured observations are immutable evidence and the process-local model is
bounded. Packet Predator must not acquire Controller state, scenario decisions,
or locally copied protocol layouts to make editing convenient.

## Decision

Add a versioned editor interface to the supported workbench:

- expose UI-safe message and field metadata derived directly from the released
  registry;
- compose a named message from source, destination, and payload through the
  released reference codec;
- return canonical logical bytes, fixed-adapter bytes, and ordinary inspection;
- fork a draft from a fixture or observation without mutating its source;
- retain copied base bytes and provenance so bounded journal eviction cannot
  change the draft;
- expose stable workbench interface, process-instance, application-version,
  build, and Contract identities; and
- accept a client transmit request ID, cache its result for the current
  process, and reject conflicting reuse.

The browser remains a presentation and explicit-input surface. The server owns
composition and transmit idempotency. The validation client never retries an
uncertain transmit automatically; a Packet Predator process change makes an
unrecovered earlier outcome explicitly unknown.

The initial editor transmits only codec-valid frames. A future malformed-frame
mode requires a separate reviewed safety decision.

## Consequences

Operators can change a field without hand-rebuilding the whole frame, while
exact bytes and validation remain contract-backed. The same server interface
can later support the Hardware Validation Console without embedding scenarios
or Game Controller policy in Packet Predator.

This work remains inside the active physical-adapter validation milestone
because it directly supports the assigned re-hello and follow-up receive
acceptance exchange.
