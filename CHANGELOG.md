# Changelog

## 2026-08-31

- Updated the supported workbench and its three finite recordings to consume
  stable Protocol Contract 1.2.0 through the existing reference-codec boundary.
  The workbench can structurally inspect the new core-2 `TRANSITION_OUTCOME`
  examples without producing an outcome or acquiring game authority. This
  changes no Packet Predator interface, transport behavior, or physical result.

## 2026-08-28

- Walk LED feedback now coalesces into at most one active pulse and one waiting
  notification. Shutdown discards the waiting notification instead of draining
  a frame-count-sized backlog, while LED failures remain explicit.
- Manual transmit failures now attempt receive-mode re-entry exactly once
  without retrying RF transmission. A failed re-entry stops the receiver and
  publishes `NRF905_RECEIVE_REENTRY_FAILED` instead of reporting that the radio
  is listening.

## 2026-08-27

- Physical receiver snapshots now retain bounded summaries for kernel edge to
  adapter lock, payload read, receive-mode re-entry, batch drain, Protocol
  decode, model publication, and total receiver service. They also report
  processing-overlap events, spurious wakes, level-only readiness, and receiver
  faults. This is host-tested instrumentation, not a claim about installed Pi
  kernel or over-air timing.
- The newest-100 journal now reports its first and latest retained sequence and
  discarded count. Metric samples have their own explicit 1,024-sample bound
  and discarded count.
- Transmit evidence separates hardware `DR` completion from receive-mode pin
  re-entry. `walk-carried` moves its 50 ms LED hold to a dedicated worker while
  keeping LED failures fatal.

## 2026-08-24

- Updated the supported workbench and finite recordings to consume stable
  Protocol Contract 1.1.0 through the existing reference-codec boundary. This
  changes no Packet Predator interface, transport behavior, or physical result.

## 2026-08-08

- `walk-fixed` and `walk-carried` output (status lines, final report, and
  waypoints file entries) now carries a UTC `timestamp` field, for lining up
  a `walk-carried` log against a `walk-fixed` log -- or field notes -- taken
  at the same time on a different Pi.
- `walk-fixed` now rejects a `radio.transmit_enabled: false` profile before
  touching hardware, tracks transmit failures as `transmit_void`, surfaces
  that count in every status line and the final report, and exits non-zero
  once void transmits pass the same 25%-of-run threshold `walk-carried`
  already used. Previously a broken or disabled transmitter beaconed nothing
  for an entire walk while reporting success throughout (#8).
- A range-walk burst that never gets a single successful carrier-detect read
  now reports `carrier_busy_percent: null` and `trustworthy: false` instead
  of a confirmed `0`, and `carrier_samples`/`carrier_void` are surfaced in
  the result so partial sampling failure is visible too (#11).

## 2026-08-01

- Added a tracked, host-rendered systemd service and install/status commands
  for loopback-only unattended physical Packet Predator startup on a Pi.
