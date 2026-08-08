# Changelog

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
