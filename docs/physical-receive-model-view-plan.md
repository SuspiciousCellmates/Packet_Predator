# Physical receive, data model, and browser view plan

Status: implemented in software; unchanged naturally timed two-Pi follow-up
revalidation remains open within `nrf905-physical-adapter-validation`.

Date: 2026-07-25.

## Problem

The supported browser currently calls `POST /api/carrier/poll` every 50 ms. Each
request performs one nRF905 `DR` check and, at most, one receive-FIFO read. The
browser timer, HTTP scheduling, and request duration therefore determine when
the radio is serviced.

Physical testing showed that this can miss a follow-up transmission. The nRF905
has no application-level queue of received frames for a slow browser to drain,
so a later frame may replace an unread frame before the next HTTP request.
Reducing the JavaScript interval would preserve the architectural fault and
would still make capture depend on whether a page is open.

## Outcome

Packet Predator will service an explicitly configured physical adapter for the
entire application lifetime, independently of every browser connection. A
thread-safe, process-local workbench model will be the source of truth for
observations and adapter state. The HTTP layer and browser will read or
subscribe to that model; they will not advance the radio.

The resulting flow is:

```text
nRF905 DR / receive FIFO
          │
          ▼
physical receiver runtime
          │ complete opaque CarrierFrame
          ▼
workbench service ── reference-codec inspection
          │
          ▼
process-local workbench model
          │ snapshot + change notifications
          ▼
thin web API ── server-sent events ── browser view
```

Manual transmission remains a deliberate command in the opposite direction:

```text
browser confirmation → web API → service → physical transport
                                             │
                                             └→ sent observation → same model
```

## Architectural decisions

### The server owns physical receive lifecycle

- A physical receiver runtime starts only when an explicit physical-adapter
  profile successfully opens and validates.
- FastAPI lifespan startup starts the receiver after the workbench service is
  ready. Lifespan shutdown stops and joins the receiver before closing the
  transport and GPIO/SPI resources.
- Inspect-only startup creates no receiver. Deterministic replay keeps its
  explicit, clock-controlled behavior and gains no autonomous actor or
  background replay thread.
- Starting, stopping, and closing are idempotent so partial startup and test
  cleanup cannot leak a thread or hardware handle.

### Physical receive is signal-driven, not browser-timed

- Add a live-receive operation distinct from the deterministic replay
  transport's explicit `poll()` operation.
- The Linux GPIO backend will wait for nRF905 `DR` activity. It must check the
  current line level before waiting for a rising edge so a signal that arrived
  just before the wait is not lost.
- A bounded wait may be used to notice shutdown, but that timeout is a lifecycle
  cancellation bound, not the capture cadence. There will be no 50 ms
  application sampling window.
- After reading a frame, the receiver immediately checks again before waiting.
  This drains every frame the adapter can expose without inserting a browser,
  decode, or display delay between hardware checks.
- Fake backends will provide deterministic wait/wake behavior so the receiver
  loop is testable without GPIO or real time.

The nRF905 still has finite hardware capacity. This work removes the known
browser-induced gap; it does not claim lossless reception under collisions,
overlapping transmissions, or traffic beyond what the radio can physically
buffer.

### Receive and transmit share one serialized adapter

- The existing one-frame transmit confirmation and profile permission remain
  mandatory.
- Device mode changes, SPI access, receive-FIFO reads, and transmission remain
  serialized at the physical adapter boundary.
- The receiver must not interpret the transmit-complete `DR` transition as a
  received frame.
- After a transmit finishes or fails, the adapter restores receive mode and
  wakes the receiver immediately so a follow-up message is serviced without
  waiting for a browser request or cancellation timeout.
- Closing the application first stops new work, then waits for any in-flight
  adapter operation, and finally releases the device.

### A process-local model is the presentation authority

Introduce an explicit workbench model rather than treating route responses as
the application state. It owns:

- the bounded newest-100 observation journal;
- a monotonic model revision independent of transport-specific sequence
  numbers;
- receiver state such as `starting`, `listening`, `transmitting`, `faulted`,
  and `stopped`;
- the most recent adapter error and capture counters; and
- a condition/change feed used by web subscribers.

Every fixture inspection, pasted inspection, replay delivery, physical receive,
and confirmed transmit goes through one service ingestion path and is then
published to this model. The model stores immutable snapshots and returns
copies so the browser, stream subscribers, and receiver cannot mutate shared
entries.

The service remains the only layer that invokes the Protocol Contract reference
codec. The model stores inspection results; it does not define protocol
constants or interpret message semantics.

### Bad application frames remain observable

A physically received frame may pass nRF905 address and CRC checks but fail the
application codec. That failure must not terminate the receiver.

- Preserve the exact received bytes and capture provenance in the journal.
- Record a structured inspection error alongside the observation.
- Mark that observation invalid for display rather than fabricating decoded
  fields.
- Continue listening after a per-frame decode failure.
- Treat adapter I/O or GPIO failures as receiver faults: publish the fault,
  stop the failing receive loop without spinning, and keep the web application
  available for diagnosis and orderly shutdown.

### The browser observes model changes

- Remove the physical `POST /api/carrier/poll` command and the JavaScript
  `setInterval(..., 50)` loop.
- Keep read APIs for a complete current snapshot and individual retained
  observations.
- Add a one-way server-sent event stream. SSE matches this surface because the
  server sends observation/state changes while browser-to-server operations
  remain ordinary explicit HTTP commands.
- Give every event the model revision as its event ID. On initial connection or
  reconnect, the browser obtains a fresh snapshot. If its last revision is
  still retained, changes may be replayed; otherwise the server requests a
  full resynchronization.
- SSE keep-alives and reconnects concern only the web connection. They never
  call the radio or affect receiver timing.
- A slow, disconnected, or absent browser cannot block capture. The bounded
  model remains canonical and slow subscribers resynchronize rather than
  applying backpressure to the receiver.

The existing 100 ms deterministic replay state polling is a separate,
explicitly clock-controlled mechanism required by ADR 0004. It is not physical
radio polling and is outside this follow-up. It may be replaced in a later
replay-specific design, but this work must not silently give replay an
autonomous clock.

## Browser behavior

The current workbench layout and inspection tools remain intact. Only their
data flow changes.

- Startup renders a model snapshot, then opens the change stream.
- A new physical observation updates the recent-packets list and the current
  inspection using model data.
- Bursts may coalesce rendering work, but every retained observation remains in
  model order and can be opened from the journal.
- Stream connection state is visibly distinct from radio state. For example,
  reconnecting the browser stream must not imply that the radio stopped
  listening.
- An invalid physical observation shows its raw bytes, provenance, and
  structured decode failure.
- Explicit inspect, replay-control, and transmit actions remain commands.
  Command responses acknowledge the operation, while the model notification is
  the canonical update for shared journal and adapter state.

## Planned implementation slices

### 1. Extract the workbench model

Add a focused model module and move journal ownership out of
`WorkbenchService`.

- Define immutable observation summaries/full records and receiver status.
- Provide atomic publish, snapshot, lookup, and wait-for-change operations.
- Add model tests for ordering, revisions, bounded retention, immutable reads,
  invalid observations, and subscriber wake-up.
- Route current manual inspection and replay ingestion through the model before
  changing physical lifecycle.

### 2. Add the live receiver boundary

Separate live waiting from replay polling.

- Extend the physical adapter/backend boundary with cancellable `DR` waiting.
- Implement level-before-edge behavior in the Linux GPIO backend.
- Add a lifecycle-managed physical receiver that obtains opaque frames and
  hands them to the service ingestion path.
- Serialize receive, transmit, and close; re-arm receive immediately after
  transmission.
- Add fake-backend tests for a frame already ready, a later signal, multiple
  follow-up frames, transmit/receive handoff, cancellation, and adapter fault.

### 3. Bind the runtime to application lifespan

- Replace construction-only `_service()` ownership with an application
  lifespan that starts and stops the configured runtime deliberately.
- Retain clear startup failure responses for malformed profiles and hardware
  initialization errors.
- Ensure inspect-only tests start no thread and touch no Raspberry Pi imports.
- Ensure shutdown joins the receiver and closes the adapter exactly once.

### 4. Publish model snapshots and changes

- Keep the existing inspection lookup route over the new model.
- Add the model snapshot and SSE change routes.
- Define revision, resynchronization, keep-alive, and disconnect semantics.
- Remove the route that directly performs a physical receive check.
- Test initial snapshots, ordered events, reconnect from a retained revision,
  resynchronization after retention rollover, slow/disconnected clients, and
  error events.

### 5. Convert the browser to a data view

- Remove `radioTimer`, `radioBusy`, `pollRadio()`, and
  `startRadioPolling()`.
- Initialize from the model snapshot and subscribe with `EventSource`.
- Render journal, current observation, physical status, and faults only from
  snapshot/change data.
- Preserve deliberate transmission confirmation and replay controls.
- Add browser-source checks proving that no 50 ms physical poll or
  `/api/carrier/poll` dependency remains.

### 6. Validate timing and document the result

- Run a deterministic burst test that would fail under a 50 ms receiver gap.
- On the physical Packet Predator–Radio Gateway–Game Controller bench, send
  the enrolled endpoint's `NODE_HELLO` and require Packet Predator to capture
  the Controller's naturally consecutive
  `HELLO_RESULT(CAPABILITIES_REQUIRED)` and `CAPABILITY_REQUEST`, while the
  browser is unopened, open, and reconnecting. Do not add transmitter delay,
  retry, or scheduling behavior.
- Only after that unchanged exchange passes, optionally characterize controlled
  inter-packet gaps as a separate measurement that does not alter production
  transmitter behavior.
- Record exact received order, frame equality, sample count, and any observed
  loss. Do not claim traffic levels that were not tested.
- Add ADR 0006 for the durable receiver/model/view lifecycle decision.
- Update architecture, runtime inventory, README, beginner guide, bench guide,
  dated physical-validation evidence, and any affected API documentation in
  the same implementation change.

## Acceptance gates

Implementation is complete only when all of the following are true:

1. A configured radio captures and journals frames when no browser has ever
   connected.
2. Opening, closing, slowing, or reconnecting a browser does not start, stop,
   or pace physical reception.
3. The browser contains no 50 ms physical polling timer and makes no
   receive-driving HTTP request.
4. A deterministic follow-up-frame test preserves every frame and its arrival
   order through the model.
5. Manual transmission remains profile-gated, individually confirmed, and
   serialized with receive mode.
6. A codec-invalid physical frame is visible and does not stop later valid
   capture.
7. An adapter fault is visible, does not create a tight retry loop, and does
   not prevent clean shutdown.
8. Inspect-only startup remains hardware-free, and deterministic replay remains
   explicit and non-autonomous.
9. SSE reconnect produces a current, ordered view without backpressuring the
   receiver.
10. `./scripts/check` passes and the archived runtime hashes remain unchanged.
11. The naturally timed Game Controller `HELLO_RESULT` plus
    `CAPABILITY_REQUEST` follow-up exchange is recorded and reviewed before
    the active physical-adapter milestone is closed; no transmit-spacing or
    retry change is part of this acceptance gate.

## Explicit non-goals

- Connecting laptop Packet Predator to `Radio_Gateway`.
- Designing or implementing a Game Controller console or Game Master Console.
- Adding Game Controller policy, automatic replies, polling schedules, node
  emulation, or game state.
- Changing the frozen wire contract or provisional protocol timing profile.
- Making the process-local journal durable.
- Claiming lossless radio operation beyond measured nRF905 capacity.
- Redesigning the current workbench layout or visual language.

The repository roadmap already places Game Controller and Game Master Console
applications after the current physical-adapter milestone. Their transport
topology and tooling should be designed in that future application milestone,
not inferred by this receiver refactor.
