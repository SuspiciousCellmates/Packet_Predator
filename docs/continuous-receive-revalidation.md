# Game Controller follow-up receive revalidation

Use this runbook to reproduce the exchange that exposed Packet Predator's old
browser-paced receive gap:

```text
Packet Predator sends NODE_HELLO
  → Radio Gateway forwards it
  → Game Controller applies discovery/enrollment logic
  → Game Controller sends HELLO_RESULT(CAPABILITIES_REQUIRED)
  → Game Controller immediately follows with CAPABILITY_REQUEST
  → Packet Predator must capture both responses
```

This is the open physical acceptance test for Packet Predator ADR 0006 and the
Game Controller's discovery/enrollment milestone. The Controller's existing
outbox behavior determines the natural interval between its two responses.
Do not add a sleep, radio-spacing rule, retry, or other scheduling change.

## Roles and assumptions

- **Packet Predator Pi:** impersonates the released example Player Node and is
  the receiver under test.
- **Radio Gateway Pi:** runs the real nRF905 gateway.
- **Controller laptop:** runs the real Game Controller.
- All radios use the same reviewed band, channel, physical address, CRC, and
  payload settings, with suitable antennas fitted.
- Transmission is explicitly enabled in the Packet Predator and Radio Gateway
  local nRF905 profiles.
- `radio.automatic_retransmit` remains `false` in both profiles.
- The Controller test uses a fresh state database so the released example
  serial is not already enrolled or capability-cached.

The released `v1-node-hello` fixture represents permanent serial `16909060`
(`0x01020304`), Player Node class, boot generation `1`, endpoint `1`, and a
known capability fingerprint. Packet Predator first changes only its logical
source to `255` for anonymous discovery, then sends the released endpoint-1
fixture after explicit enrollment.

## 1. Verify the three repositories

On the Packet Predator Pi:

```sh
cd ~/Suspicious_Cellmates/Packet_Predator
./scripts/update-rpi
./scripts/check
./scripts/nrf905-diagnose \
  --profile config/nrf905-bench.local.json \
  profile
```

Stop Packet Predator before probing because only one process can own its radio:

```sh
./scripts/nrf905-diagnose \
  --profile config/nrf905-bench.local.json \
  probe
```

On the Radio Gateway Pi:

```sh
cd ~/Suspicious_Cellmates/Radio_Gateway
./scripts/check
./scripts/run config/gateway.local.json probe
```

If the Gateway is managed by systemd, stop it before the manual probe and
restart it afterward. Do not run a probe concurrently with the service.

On the Controller laptop:

```sh
cd ~/Suspicious_Cellmates/Game_Controller
./scripts/check
```

Require both radios to pass exact register readback before continuing.

## 2. Prepare isolated Controller evidence

Do not erase or reuse the normal Controller databases for this test. Copy the
Controller configuration:

```sh
cd ~/Suspicious_Cellmates/Game_Controller
cp config/controller.local.json \
  config/controller.pp-revalidation.local.json
```

Edit only these two fields in
`config/controller.pp-revalidation.local.json`:

```json
{
  "journal_path": "../var/controller-journal.pp-revalidation.sqlite3",
  "state_path": "../var/controller-state.pp-revalidation.sqlite3"
}
```

The copied file must retain the real isolated-link `gateway_url` and
`contract_root`. If either revalidation database already exists from an older
run, give this run new dated filenames instead of deleting or silently reusing
old state.

Validate the clean configuration:

```sh
./scripts/status config/controller.pp-revalidation.local.json
./scripts/nodes config/controller.pp-revalidation.local.json list
```

The node list must be empty. If it is not, stop and choose fresh database
filenames.

## 3. Start the physical path

Start or verify the Radio Gateway on its Pi. For a manual deployment:

```sh
cd ~/Suspicious_Cellmates/Radio_Gateway
./scripts/run config/gateway.local.json serve
```

For an installed service:

```sh
cd ~/Suspicious_Cellmates/Radio_Gateway
./scripts/systemd-status
```

Start Packet Predator on its Pi:

```sh
cd ~/Suspicious_Cellmates/Packet_Predator
./scripts/run-rpi config/nrf905-bench.local.json
```

From the Controller laptop, create a tunnel to Packet Predator:

```sh
ssh -N -L 8001:127.0.0.1:8000 \
  your-user@packet-predator-a.local
```

Start the Game Controller in another laptop terminal:

```sh
cd ~/Suspicious_Cellmates/Game_Controller
./scripts/run config/controller.pp-revalidation.local.json
```

Wait for `Controller link opened`. Without opening a Packet Predator browser,
check its model:

```sh
curl -fsS http://127.0.0.1:8001/api/status \
  | python3 -m json.tool
curl -fsS http://127.0.0.1:8001/api/workbench/state \
  | python3 -m json.tool
```

Packet Predator's receiver state must be `listening`, with `last_error` set to
`null`. These HTTP requests only read the process-local model; they do not
poll or service the radio.

## 4. Discover and enroll the released example node

Keep the Packet Predator browser closed. Send the anonymous discovery hello
from the laptop through Packet Predator:

```sh
curl -fsS http://127.0.0.1:8001/api/carrier/transmit \
  -H 'Content-Type: application/json' \
  --data '{"frame_hex":"5a01ff00040302010000000001000100011001000001d7e31e63010100000000","mode":"fixed","confirmed":true}' \
  | python3 -m json.tool
```

This is the released `NODE_HELLO` with only the logical source changed from
endpoint `1` to unassigned endpoint `255`. The Controller should discover the
device and send `HELLO_RESULT(PENDING_ENROLLMENT)`.

Inspect and enroll it from another Controller terminal:

```sh
cd ~/Suspicious_Cellmates/Game_Controller
./scripts/nodes config/controller.pp-revalidation.local.json list
./scripts/nodes config/controller.pp-revalidation.local.json show 16909060
./scripts/nodes config/controller.pp-revalidation.local.json \
  enroll 16909060 --name "PP receive revalidation"
```

Enrollment should allocate endpoint `1`. Wait until Packet Predator records
the Controller's `ENDPOINT_ASSIGNED_REHELLO` response, then capture the model
immediately before the exchange under test:

```sh
mkdir -p evidence
curl -fsS http://127.0.0.1:8001/api/workbench/state \
  -o evidence/gc-follow-up-before.json
python3 -m json.tool evidence/gc-follow-up-before.json
```

Record the starting `receiver.received_count`.

## 5. Run the HELLO → CAPABILITY_REQUEST test

Still with no Packet Predator browser ever opened, send the released
endpoint-1 `NODE_HELLO`:

```sh
curl -fsS http://127.0.0.1:8001/api/carrier/transmit \
  -H 'Content-Type: application/json' \
  --data '{"frame_hex":"5a010100040302010000000001000100011001000001d7e31e63010100000000","mode":"fixed","confirmed":true}' \
  | python3 -m json.tool
```

Do not send anything else and do not insert a delay. The running Game
Controller should naturally produce:

1. `HELLO_RESULT` with disposition `CAPABILITIES_REQUIRED`;
2. `CAPABILITY_REQUEST` for the advertised fingerprint.

Capture Packet Predator's model after both arrive:

```sh
curl -fsS http://127.0.0.1:8001/api/workbench/state \
  -o evidence/gc-follow-up-browser-never-opened.json
python3 -m json.tool \
  evidence/gc-follow-up-browser-never-opened.json
```

Pass requires:

- `receiver.received_count` increased by exactly `2`;
- both observations are present with consecutive `journal_sequence` values;
- chronological order is `HELLO_RESULT`, then `CAPABILITY_REQUEST`;
- `HELLO_RESULT.disposition` is `CAPABILITIES_REQUIRED`;
- `CAPABILITY_REQUEST.capability_fingerprint` is `1662968791`;
- neither frame is duplicated, malformed, or codec-invalid;
- receiver state remains `listening` and `last_error` remains `null`.

The journal is displayed newest-first, so the visible list shows
`CAPABILITY_REQUEST` above `HELLO_RESULT`. Use `journal_sequence`, not display
position, to prove chronological order.

With a fresh Controller database, the expected fixed frames are:

```text
HELLO_RESULT
5002000104030201000000000100030101010000000000000000000000000000

CAPABILITY_REQUEST
470300010100d7e31e63ff000000000000000000000000000000000000000000
```

The request correlation is expected to be `1` only because this procedure
requires a fresh Controller state database. The decoded message names,
disposition, fingerprint, count, and order are the primary assertions.

## 6. Prove browser independence

The first run above is the strongest check: Packet Predator captured both
responses before any page was opened.

Next open:

```text
http://127.0.0.1:8001/
```

Confirm the two previously captured frames appear. Send the same released
endpoint-1 hello again using the section 5 command. Save the result:

```sh
curl -fsS http://127.0.0.1:8001/api/workbench/state \
  -o evidence/gc-follow-up-browser-open.json
```

Close the browser tab, send the same hello once more, then reopen the page and
save:

```sh
curl -fsS http://127.0.0.1:8001/api/workbench/state \
  -o evidence/gc-follow-up-browser-reconnected.json
```

Each hello should add exactly one `HELLO_RESULT` followed by one
`CAPABILITY_REQUEST`, irrespective of browser state. Repeating the hello is
normal protocol reconciliation for this test; it is not an RF retry inserted
between the Controller's two responses.

## 7. Cross-check the Controller evidence

On the Controller laptop:

```sh
cd ~/Suspicious_Cellmates/Game_Controller
./scripts/status config/controller.pp-revalidation.local.json
./scripts/nodes config/controller.pp-revalidation.local.json show 16909060
```

The node's semantic status should be `CAPABILITIES_REQUIRED`.

Inspect the exact incoming hello observations:

```sh
sqlite3 -header -column var/controller-journal.pp-revalidation.sqlite3 \
  "SELECT
      gateway_id,
      gateway_boot_id,
      receive_sequence,
      decode_ok,
      json_extract(decoded_json, '$.message.name') AS message,
      hex(frame) AS frame
   FROM radio_observation
   ORDER BY recorded_at, gateway_id, gateway_boot_id, receive_sequence;"
```

Capture revisions:

```sh
git rev-parse HEAD
git -C ../Protocol_Contract rev-parse HEAD
git -C ../Radio_Gateway rev-parse HEAD
git -C ../Packet_Predator rev-parse HEAD
```

Record the Packet Predator model JSON, Controller status, node record, commit
IDs, local RF profile summaries, browser condition, and terminal errors in a
new dated physical-validation record.

## Stop conditions

Stop and preserve evidence rather than changing timing if:

- Packet Predator receives `HELLO_RESULT` but misses `CAPABILITY_REQUEST`;
- either response is duplicated, reversed, malformed, or byte-different;
- the result changes with browser state;
- Packet Predator leaves `listening` or reports `last_error`;
- the Controller outbox reports a failed or unknown transmission;
- the Gateway or either radio reports GPIO, SPI, timeout, or readback failure.

Do not mask any of these outcomes with transmitter spacing, sleeps, or
automatic RF retries. They are the evidence this acceptance test is intended
to collect.
