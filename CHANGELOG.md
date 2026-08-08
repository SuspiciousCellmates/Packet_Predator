# Changelog

## 2026-08-08

- `walk-fixed` and `walk-carried` output (status lines, final report, and
  waypoints file entries) now carries a UTC `timestamp` field, for lining up
  a `walk-carried` log against a `walk-fixed` log -- or field notes -- taken
  at the same time on a different Pi.

## 2026-08-01

- Added a tracked, host-rendered systemd service and install/status commands
  for loopback-only unattended physical Packet Predator startup on a Pi.
