# Laptop workbench

Packet Predator's supported entrypoint is designed to be useful before any radio or Raspberry Pi is available. It starts in inspect-only mode, where the browser reads official Protocol Contract examples or hexadecimal text you supply. You may explicitly select a deterministic recording to feed a known sequence through the fake receive transport. Neither mode can transmit, and neither silently substitutes simulated players or tasks.

## First run

The two repositories should have this relationship:

```text
Suspicious_Cellmates/
├── Packet_Predator/
└── Protocol_Contract/
```

From `Packet_Predator`, run:

```sh
./scripts/setup-local
./scripts/run-local
```

Then open [http://127.0.0.1:8000](http://127.0.0.1:8000). Stop the server with `Ctrl+C` in the terminal.

`setup-local` creates or reuses `.venv` and installs the small laptop-only dependency set in `requirements-local.txt`. It deliberately does not use the historical hardware requirements.

## What to try

Select **Node hello** to see a node introduce itself to the Game Controller. The overview answers who sent it, where it went, and the delivery expectation. **Fields** shows readable enum or flag labels alongside the original numeric values and offsets. **Bytes** shows the four-byte envelope, body, and any zero padding separately.

Alternatively, choose **Node onboarding**, **Recorded task session**, or **Retained outcome retry** in the recording player. **Step** releases exactly one scheduled frame. **Play** follows the recorded timetable, while pause, reset, and the speed selector let you examine the exchange at your own pace. The timetable marks which frames have been delivered, and clicking a recent journal row reopens its complete inspection.

These recordings do not run a game. They have no conditions or virtual participants; Packet Predator merely releases the listed bytes in order. “Recorded outbound” means the capture says the frame travelled away from the workbench's viewpoint—it does not mean your laptop transmitted anything.

Switch **Interpret as** to **Fixed 32-byte adapter frame** while an example is selected to inspect the exact padded form a fixed-width adapter may carry. Choosing **Logical frame** removes that carrier padding. The shared reference codec rejects malformed lengths, unknown values, illegal routes, and non-zero padding with a named, visible error.

## Optional settings

The defaults bind only to the local laptop and use the sibling contract checkout. Override them only when necessary:

```sh
PACKET_PREDATOR_HOST=0.0.0.0 PACKET_PREDATOR_PORT=8080 ./scripts/run-local
PACKET_PREDATOR_CONTRACT_ROOT=/path/to/Protocol_Contract ./scripts/run-local
```

Binding to `0.0.0.0` makes the page reachable from other devices on the same network; use it only on a network you trust. Inspect-only mode still cannot access a radio or node.

## Troubleshooting

- **Contract unavailable:** confirm `Protocol_Contract/registry/v1.json`, `fixtures/v1/all-message-types.json`, and `reference_codec/` exist beside Packet Predator, or set `PACKET_PREDATOR_CONTRACT_ROOT`.
- **FastAPI or Uvicorn missing:** rerun `./scripts/setup-local` and check that Python 3.12 can create a virtual environment.
- **Port already in use:** choose another local port, for example `PACKET_PREDATOR_PORT=8081 ./scripts/run-local`.

The JSON routes and interactive API schema remain available at `/api/...` and `/docs` for diagnostics, but the browser workbench is the intended human interface.
