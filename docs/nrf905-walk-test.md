# nRF905 range walk, on the Raspberry Pi bench

This is a Pi-side port of Tool 2 ("range walk") from
[`Player_Node_Firmware`'s RF tool suite](../../Player_Node_Firmware/docs/rf-tool-suite.md),
built so the range question -- can these modules and antennas cover a real
venue -- can be answered on hardware that has already passed a bidirectional
exchange (`nrf905-validation-2026-07-24.md`), ahead of the badge fixture.
Driven by `Player_Node_Firmware` #18; tracked here as `Packet_Predator` #7.
See that document for the full
rationale of the measurement itself: alternating one-way beacons instead of
an echo, no pass/fail bar, why the longest miss run matters more than a bare
loss percentage.

**Status: built and host-tested; no frame has been transmitted over the
air.** Every hardware-facing claim below is a prediction until run against
real modules.

## What's the same, and what isn't

The 32-byte beacon is byte-for-byte the same layout as
`tools/rf-tool-suite/main/walk_frame.hpp`: magic `RFWK`, then role, station,
sequence, and a piggybacked received-count, all in the same positions. A
capture from either platform decodes the same way, and a Pi could stand in
for either end of the badge walk later, given a spare nRF905 module.

Two things are deliberately not a straight port, because a straight port
would measure the wrong thing on this platform:

- **Loss is read from the beacon's sequence number, not from whether a frame
  landed inside a timed slot.** The ESP32 image owns a dedicated core and can
  hold slot timing tightly enough to gate reception on it. Python on
  Raspberry Pi OS, with SPI transactions, the interpreter and the scheduler
  in the way, cannot -- a frame that arrived a few milliseconds late would
  read as "missed" under slot-gating, which is precisely the failure the
  original design killed the echo-based measurement over (a fixed turnaround
  deadline reading as loss). Here, each burst just collects the distinct
  sequence numbers it hears over the whole window and reads gaps in that set.
  Nothing is ever gated on *when* a frame arrived, only on *which* sequence
  numbers showed up at all.

- **Uplink is a delta, not a maximum.** The ESP32 tool resets both nodes'
  counters together via a button press on each, every station. There's no
  button here: the fixed node (`walk-fixed`) is a long-running process
  started once at the base and never reset, so its own received-count only
  ever goes up. The carried node (`walk-carried`) instead samples that
  counter at the start and end of its own burst and reports the difference
  -- correct at any station, at any point into a long walk, with no
  coordination between the two ends beyond them sharing a profile.

One consequence worth knowing: **with zero reception, downlink reads as 0%
loss, not 100%.** There's no denominator without at least one received
sequence number to anchor a span against, so `downlink_span` staying `0` is
what actually tells you "nothing arrived" -- not the loss percentage.

## Before transmitting

- **Duty cycle.** This holds the radio in short bursts every interval --
  continuously, for the whole walk, if you run `walk-fixed` or
  `walk-carried --continuous` (see below), and for ten seconds per station
  otherwise (100 slots x 100 ms at the defaults). That is well beyond the
  one-shot exchange `transmit_enabled` was originally reviewed for. Re-review
  your local 433 MHz duty-cycle allowance against a whole walk, not just one
  exchange, before setting it to `true`. The CLI prints a reminder every run;
  it cannot check this for you.
- **Fit the antenna first.**
- **Use a profile with its own address.** `config/nrf905-walk.example.json`
  ships a distinct `radio.address_hex` from the bench example
  (`5C3E91A4` vs. `A7C35E19`) so walk beacons don't get ingested by a Gateway
  listening on the shared bench address. Copy it to a `.local.json` file and
  review the channel/power/crystal fields as usual before flipping
  `transmit_enabled`.
- **Put the fixed node where the Gateway will actually live**, not on an open
  bench, or you'll measure the wrong property.

## Hardware split

Two Pi 5s work, or a Zero 2 W as the carried end -- it's kinder to a power
bank (`nrf905-two-pi-bench.md`). The fixed node can sit on mains power
indefinitely; only the carried node needs a battery and the LED.

## Running it

Base station, started once, left running for the whole walk:

```sh
./scripts/nrf905-diagnose --profile config/nrf905-walk.local.json walk-fixed
```

Prints a status line periodically (`--status-every`, default every 50
intervals) and a final total on Ctrl-C. Nothing else needs to happen here.

From the carried node, either one burst per station:

```sh
./scripts/nrf905-diagnose --profile config/nrf905-walk.local.json \
  walk-carried --station 4 --led ACT --waypoints-file walk-2026-08-08.jsonl
```

which runs one ten-second burst (100 slots at the 100 ms default), prints the
result as JSON, appends the same JSON as one line to the waypoints file if
given, and exits -- you'd re-run this by hand at every stop, bumping
`--station` each time; or, to actually walk continuously without stopping to
re-run anything:

```sh
./scripts/nrf905-diagnose --profile config/nrf905-walk.local.json \
  walk-carried --continuous --station 1 --led ACT --waypoints-file walk-2026-08-08.jsonl
```

which runs consecutive bursts back to back, printing and logging each as it
completes and auto-incrementing the station number, until Ctrl-C (which takes
effect at the next burst boundary, so allow up to one burst's length to
actually stop). `--station` is just the *starting* number in this mode.
Nothing here knows your physical position either way -- note wall-clock time
or the printed station number against where you were, in your own notebook.

Single-burst exit status is `0` if trustworthy (fewer than 25% of slots void
from local faults) and `2` otherwise, the same threshold the ESP32 tool uses;
`--continuous` just exits `0` on a clean Ctrl-C.

`--led` is required and hard-fails if it can't be driven -- see below. This
is the only continuous field feedback the carried node has; walking untethered
with a silently-dead indicator would look exactly like being carried in the
wrong role, or out of range, and there would be nothing to tell them apart.

## The LED

Both the Pi 5 and the Zero 2 W expose their onboard status LED through Linux
the same way, no extra wiring:

```sh
ls /sys/class/leds
```

Pick the name that lights when you touch it (commonly `ACT` on a Zero 2 W;
`ACT` or `PWR` on a Pi 5, depending on OS version -- the Pi 5's is driven
through the RP1 companion chip rather than a raw SoC pin, so treat "it
behaves the same at the sysfs layer" as expected, not confirmed, until you've
watched it blink).

**It blinks once per received downlink frame, not per transmit of our own.**
Our own transmit succeeding is a purely local event and happens regardless of
range, so it can't tell you anything about the link; gating the blink on
actually hearing the fixed node instead means walking out of range makes it
visibly stop, and walking back makes it visibly resume -- walk until it
stops, walk back until it starts, exactly as the original brief wanted. A
dark carried node mid-walk now means either out of range or the instrument
has stopped; there's no way to tell those apart from the LED alone, only from
whether it resumes when you walk back.

If the onboard LED turns out to be inconvenient or ambiguous on a given
board, an external LED and resistor on a spare GPIO costs about the same
wiring effort and removes the question outright -- there is no code
dependency on which one you use, only on `--led` naming a working
`/sys/class/leds` entry.

## Reading the result

```json
{
  "station": 4,
  "slots_run": 100,
  "slots_void": 0,
  "downlink_received": 93,
  "downlink_span": 97,
  "downlink_loss_percent": 4,
  "longest_miss_run": 2,
  "uplink_delivered": 91,
  "uplink_denominator": 100,
  "uplink_loss_percent": 9,
  "carrier_busy_percent": 3,
  "trustworthy": true
}
```

- `downlink_*` is what the carried node measured of the fixed node's beacons:
  `downlink_span` is how many distinct fixed sequence numbers should exist
  between the lowest and highest one actually seen; `downlink_received` is how
  many of those were actually seen; `longest_miss_run` is the worst
  consecutive gap, which is the number that decides playability -- a
  scattered 5% loss is survivable where 5% arriving as one run is not.
- `uplink_*` is the fixed node's view of the carried node's beacons, recovered
  as the delta of its self-reported total across this burst.
- `carrier_busy_percent` is occupancy, not signal strength -- the nRF905 has
  no RSSI register. High loss with low carrier-busy is out of range; high
  loss with high carrier-busy is contention.
- `trustworthy` is about the instrument, not the link: it only reflects
  whether too many local faults (`slots_void`) happened during the burst. A
  burst with zero reception and zero faults is still `trustworthy` -- that is
  a legitimately measured bad link, not a broken run.

There is deliberately no pass/fail threshold here either, for the same reason
`rf-tool-suite.md` gives: venue choice and Gateway placement get decided from
the characterization afterward, not from an invented bar.

## Known limits

- The fixed node's received-count is a 16-bit field and wraps at 65536. At
  the 100 ms default that's roughly 1.8 hours of continuous successful
  reception before a delta spanning the wrap would read wrong. Restart
  `walk-fixed` if a walk runs that long.
- The waypoints file is plain newline-delimited JSON, appended, never
  rotated or bounded -- there's a real filesystem under this, unlike the
  badge's 64-record NVS limit, so there's nothing to manage.
