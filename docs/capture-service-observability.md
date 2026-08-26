# Physical capture service observability

**Software status:** Host-tested on 2026-08-27.

**Physical status:** No installed Raspberry Pi kernel or over-air burst was tested
for this change. The measurements below make that run observable. They do not
replace it.

Packet Predator keeps the direct physical capture path accepted by ADR 0006.
One receiver thread owns the nRF905 receive path. It drains available frames,
decodes each frame through Protocol Contract, and publishes it into the bounded
workbench model. No capture mailbox or second consumer has been added.

## How timing moves through the service

The Linux GPIO backend requests rising-edge timestamps from the kernel's
monotonic clock. It still checks the current `DR` level before and after the
bounded edge wait, so a level that is already high is not missed. An
already-high level has no invented edge timestamp.

The timestamp and exact frame bytes then move through these owners:

1. `nrf905_linux.py` reads the kernel edge event and its monotonic timestamp.
2. `nrf905.py` returns that timestamp with the bounded `DR` wait result and
   records payload-read and receive-mode re-entry completion.
3. `nrf905_transport.py` serializes access to the physical adapter and attaches
   capture timing to the opaque 32-byte frame.
4. `receiver.py` drains the ready batch without a browser and records the drain
   span.
5. `service.py` decodes through Protocol Contract and publishes the immutable
   observation.
6. `model.py` retains bounded timing samples and exposes summaries through
   `/api/status` and `/api/workbench/state`.

The browser remains a reader of model state and revision events. It never calls
the physical receive path.

## Receiver timing fields

`receiver.service.spans` contains one summary for every measured span:

| Span | Start and end |
|---|---|
| `edge_to_lock_ms` | Kernel monotonic `DR` edge to physical operation-lock acquisition |
| `edge_to_payload_read_ms` | Kernel monotonic `DR` edge to completed 32-byte SPI read |
| `payload_read_to_receive_reentry_ms` | Completed SPI read to receive-mode pin reassertion |
| `batch_drain_ms` | Start to end of the direct pre-decode drain pass |
| `decode_ms` | Start to end of Protocol Contract decoding |
| `model_publication_ms` | Start to end of immutable model publication |
| `receiver_service_ms` | Receiver handoff to service return, including decode, publication, and timing-record update |

Each summary reports:

- `median_ms`, `p95_ms`, and `p99_ms` over the newest retained samples;
- `worst_ms`, the process-wide high value even if its sample later rolls out;
- `sample_count`, the number of samples still retained for percentile work;
- `discarded_count`, the number removed by bounded metric retention; and
- `total_observed_count`, retained plus discarded samples.

The model keeps the newest 1,024 samples for each span.
`receiver_service_high_water_ms` repeats the process-wide worst
`receiver_service_ms` value for a quick admission check.

`edge_or_frame_during_processing_count` increments when `DR` becomes ready
after the receiver drained the current batch but before decode and publication
finish. A nonzero value proves that capture work overlapped a later arrival. It
does not count frames the nRF905 may already have overwritten before software
could read them.

`physical_adapter.receive_wait.spurious_wake_count` reports an edge wake that
did not leave `DR` high for a payload read. A transmit-completion edge can cause
this. `level_ready_without_edge_timestamp_count` reports captures found through
the persistent-level check when no kernel edge event remained to timestamp.
Those frames remain captured, but edge-based spans are absent for them.

## Retention loss

The `journal` object now reports:

- `first_retained_journal_sequence`;
- `latest_journal_sequence`; and
- `discarded_count`.

The journal still keeps the newest 100 observations and clears on process
restart. A `discarded_count` above zero means the snapshot is not the complete
capture for that process. Save important snapshots and exact bytes during the
run.

## Transmit and receive re-entry evidence

A transmitted observation carries three separate timing values under
`capture.timing`:

- `tx_completion_ms`, from the transmit pulse to `DR` reporting completion;
- `receive_mode_reentry_ms`, from the transmit pulse to receive-mode pin
  reassertion; and
- `tx_completion_to_receive_mode_reentry_ms`, the gap between those events.

The second value proves the software reasserted the receive-mode pins after the
transmit attempt. It does not prove the installed radio or kernel was ready to
capture at that instant. Only physical follow-up traffic can establish that.
The profile transmit permission, one-shot request confirmation, exact bytes,
and absence of automatic retry remain unchanged.

## Controlled burst evidence

On the prepared Pi, run the normal repository check and start the explicit
physical profile:

```sh
cd ~/Suspicious_Cellmates/Packet_Predator
./scripts/check
./scripts/run-rpi config/nrf905-bench.local.json
```

After the controlled sender finishes its admitted burst, save the model from a
second terminal on that Pi:

```sh
curl --fail --silent --show-error \
  http://127.0.0.1:8000/api/workbench/state \
  --output packet-predator-capture-state.json
```

A retained burst report must include the sender's admitted minimum frame
interval, every relevant span's median, p95, p99, worst, `sample_count`, and
`discarded_count`, plus journal discards, receiver `fault_count`,
`edge_or_frame_during_processing_count`, exact frame sequences, and the Packet
Predator build identity.

Do not describe the run as complete if metric samples or journal entries rolled
over without separately retained evidence. Do not describe host tests as proof
of installed-kernel GPIO timing.

The direct path remains the supported path until measured evidence says
otherwise. If `receiver_service_high_water_ms` can bridge the admitted minimum
frame interval, or if frames arrive during processing, the follow-up design must
derive a capture mailbox capacity and overflow policy from the observed arrival
rate and service distribution. A guessed queue size is not acceptable.

## Walk indicator

`walk-carried` still requests one 50 ms LED indication for each received fixed
beacon. A dedicated LED worker now performs the on, wait, and off operations,
so the 50 ms visible hold does not consume the radio receive slot. Device,
permission, and write failures remain fatal and appear as explicit `LED_*`
errors.
