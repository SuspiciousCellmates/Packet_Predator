# Unattended Packet Predator startup

This procedure makes the physical Packet Predator workbench start
automatically when its Raspberry Pi boots. An SSH session is not required
after installation. The installed HTTP service remains on Pi loopback and is
reached through the HVC-managed SSH tunnel.

The repository tracks the source unit at
`packaging/suspicious-cellmates-packet-predator.service.in`. The installer
renders the actual checkout path, profile path, user, and group on the Pi; no
machine-specific values need to be committed.

## Before installation

From the Packet Predator checkout on the Pi:

```sh
./scripts/check
./scripts/nrf905-diagnose \
  --profile config/nrf905-bench.local.json \
  probe
```

The probe must succeed. Stop any manually started Packet Predator process
before installation because only one process can own the nRF905 and port 8000.

## Install and start

```sh
./scripts/install-systemd-service config/nrf905-bench.local.json
```

The script runs the repository checks, then validates the profile,
repository-local paths, `.venv`, rendered unit, and systemd syntax before it
requests `sudo`. It installs only
`/etc/systemd/system/suspicious-cellmates-packet-predator.service`, enables it
for future boots, and starts it immediately.

The process runs as the user who installs it—not root—so that the same SPI and
GPIO group permissions proven by the manual probe remain in effect. Inspect
the service and its last 30 journal lines with:

```sh
./scripts/systemd-status
```

The status should be `active (running)`, and the log should show the explicit
adapter profile and `http://127.0.0.1:8000`. From the laptop,
`./scripts/bench-tunnels` should then report the Packet Predator tunnel ready.

## Safety and lifecycle

- The generated service invokes `run-rpi` without `--lan`, preserving the
  safer loopback-only HTTP bind.
- Physical startup still requires the explicit ignored nRF905 profile.
- A transmit-enabled profile permits only individually confirmed workbench
  requests; the service adds no automatic transmission or retry.
- `KillSignal=SIGINT` follows the normal graceful shutdown path so the receiver
  stops before the SPI and GPIO resources close.
- `Restart=on-failure` retries a failed process after five seconds, but an
  administrative stop remains stopped.
- Filesystem and privilege hardening leave the repository and sibling
  Protocol Contract readable while preventing service writes to them.

## Updates and routine management

To pull a clean fast-forward update safely, then restart the service
deliberately so it uses the new checkout:

```sh
./scripts/update-rpi
sudo systemctl restart suspicious-cellmates-packet-predator.service
./scripts/systemd-status
```

Other routine commands are:

```sh
sudo systemctl stop suspicious-cellmates-packet-predator.service
sudo systemctl start suspicious-cellmates-packet-predator.service
sudo systemctl disable --now suspicious-cellmates-packet-predator.service
```

Stopping or disabling the service does not remove the unit. To uninstall it,
disable it, remove only the named file under `/etc/systemd/system`, and run
`sudo systemctl daemon-reload`.
