# ADR 0006: Decouple physical receive from browser presentation

- Status: Accepted
- Date: 2026-07-25
- Refines: the physical-adapter runtime boundary in ADR 0005

## Context

The first physical browser integration exposed `POST /api/carrier/poll`, and
the page called it every 50 ms. Each request checked the nRF905 `DR` signal once
and read at most one frame. Browser scheduling, HTTP latency, and whether a page
was open therefore determined when the receive FIFO was serviced.

Bench testing then missed a follow-up transmission. Making the browser timer
shorter would not remove the coupling, and the nRF905 cannot provide an
application queue for frames that software has not read.

The supported service already owns process-local inspection history, but that
history was mutated only while handling a browser or replay request. A durable
live-adapter boundary needs explicit application lifecycle and a presentation
model that browsers can observe without controlling capture.

## Decision

Within `nrf905-physical-adapter-validation`:

- FastAPI application lifespan owns a physical receiver worker whenever an
  explicit nRF905 profile is active;
- the Linux GPIO backend waits for `DR` rising edges and checks the current
  level before waiting, so physical receive is signal-driven rather than
  browser-timed;
- receive, transmit, and close operations remain serialized at the physical
  transport boundary, and receive mode is restored immediately after every
  transmit attempt;
- the workbench service decodes each delivered opaque frame and publishes an
  immutable observation into a bounded, thread-safe, process-local model;
- codec-invalid physical frames retain exact bytes, provenance, and a
  structured error without stopping the receiver;
- persistent GPIO or SPI receive failures publish a fault and stop the failing
  worker rather than entering a retry loop;
- the thin web layer exposes model snapshots and a server-sent event revision
  stream;
- the browser renders model state and never invokes physical receive; and
- the former physical poll route and 50 ms browser timer are removed.

Server-sent events carry model revision notifications rather than owning a
second copy of inspection data. A new or reconnecting browser reads a canonical
snapshot. Slow clients resynchronize from the bounded model and cannot apply
backpressure to the receiver.

Inspect-only startup remains hardware-free. Deterministic replay retains the
explicit clock-controlled polling required by ADR 0004 and does not gain a
background replay actor. Manual RF transmission still requires both deployment
profile permission and a fresh one-shot browser confirmation.

## Lifecycle and rollback

Startup validates and opens the configured radio before starting the receiver.
Shutdown signals and joins the receiver before closing GPIO and SPI. These
operations are idempotent so partial startup, tests, and the process exit
fallback cannot close hardware twice.

There is no persistent migration. The model retains the newest 100
observations in memory and disappears with the process. Rollback returns to the
request-driven capture behavior before this ADR, but that behavior is known to
miss follow-up traffic and is not an acceptable completion state for the
physical milestone.

## Consequences

Packet Predator can capture while no browser is connected, and browser
reconnect behavior no longer changes radio timing. The browser can distinguish
its own live-stream connection from the radio receiver state. Software tests
cover queued follow-ups, transmit-to-receive handoff, invalid frames, adapter
faults, model retention, subscriber resynchronization, and idempotent shutdown.

This decision does not claim lossless reception beyond the nRF905's physical
capacity. The physical Packet Predator–Radio Gateway–Game Controller exchange
still requires repeat measurement before the active milestone closes:
`NODE_HELLO`, followed naturally by the Controller's
`HELLO_RESULT(CAPABILITIES_REQUIRED)` and `CAPABILITY_REQUEST`. That
validation must not introduce transmitter spacing or retry behavior;
controlled-gap characterization is a separate later measurement.
