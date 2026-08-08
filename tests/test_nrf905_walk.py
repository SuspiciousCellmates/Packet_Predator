from collections import deque
import threading
import unittest

from packet_predator.adapters.nrf905 import Nrf905Error
from packet_predator.nrf905_walk import (
    ROLE_CARRIED,
    ROLE_FIXED,
    BurstResult,
    SysfsLed,
    WalkFrame,
    WalkFrameError,
    _distinct_gap_stats,
    decode_walk_frame,
    percent_of,
    run_carried_burst,
    run_carried_loop,
    run_fixed_loop,
)


class ManualClock:
    """A fake monotonic clock: time only ever advances when told to."""

    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class FakeWalkDevice:
    """A double for run_carried_burst/run_fixed_loop with no hardware and no real time.

    wait_data_ready never actually blocks: it drains a scripted queue instantly, and
    only when the queue is empty does it advance the shared fake clock by the full
    requested timeout before reporting nothing arrived -- exactly what a real block-
    until-timeout wait would cost, without spending any wall-clock time on it.
    """

    def __init__(self, clock, fail_transmit_slots=frozenset()):
        self._clock = clock
        self._pending = deque()
        self.fail_transmit_slots = fail_transmit_slots
        self.transmitted = []

    def queue(self, frame):
        self._pending.append(frame)

    def transmit(self, frame):
        index = len(self.transmitted)
        self.transmitted.append(frame)
        if index in self.fail_transmit_slots:
            raise Nrf905Error("NRF905_TRANSMIT_TIMEOUT", "simulated transmit failure")
        return {"elapsed_ms": 0.0, "frame_hex": frame.hex()}

    def pin_status(self):
        return {"carrier_detect": False}

    def wait_data_ready(self, timeout_s):
        if self._pending:
            return True
        self._clock.sleep(timeout_s)
        return False

    def receive(self):
        return self._pending.popleft() if self._pending else None


class FakeLed:
    def __init__(self):
        self.blinks = 0

    def blink(self, seconds=0.05, sleeper=None):
        self.blinks += 1


class WalkFrameEncodingTests(unittest.TestCase):
    def test_encode_matches_the_literal_wire_layout(self):
        # Hardcoded expected bytes, not a round trip through this module's own
        # decoder -- a round trip would pass even if encode and decode agreed
        # on a layout that does not match walk_frame.hpp.
        expected = bytes([0x52, 0x46, 0x57, 0x4B, 0x01, 0x00, 0x04, 0x00, 0x07, 0x00, 0x0C]) + bytes(21)
        frame = WalkFrame(role=ROLE_CARRIED, station=4, sequence=7, received_count=12)
        self.assertEqual(frame.encode(), expected)
        self.assertEqual(len(frame.encode()), 32)

    def test_fixed_role_and_zero_fields_encode_to_all_zero_tail(self):
        expected = bytes([0x52, 0x46, 0x57, 0x4B, 0x00]) + bytes(27)
        self.assertEqual(WalkFrame(role=ROLE_FIXED, station=0, sequence=0, received_count=0).encode(), expected)

    def test_field_out_of_16_bit_range_is_rejected(self):
        with self.assertRaises(WalkFrameError):
            WalkFrame(role=ROLE_CARRIED, station=0x10000, sequence=0, received_count=0)

    def test_unknown_role_is_rejected(self):
        with self.assertRaises(WalkFrameError):
            WalkFrame(role=2, station=0, sequence=0, received_count=0)

    def test_decode_round_trips_a_valid_frame(self):
        original = WalkFrame(role=ROLE_FIXED, station=3, sequence=9001, received_count=42)
        self.assertEqual(decode_walk_frame(original.encode()), original)

    def test_decode_rejects_wrong_magic(self):
        frame = bytearray(WalkFrame(role=ROLE_CARRIED, station=1, sequence=1, received_count=1).encode())
        frame[0] ^= 0xFF
        self.assertIsNone(decode_walk_frame(bytes(frame)))

    def test_decode_rejects_an_unrelated_frame_of_the_right_length(self):
        # A badge game frame can physically arrive at a walk-test node on the
        # same address/channel; it must not be mistaken for a beacon.
        self.assertIsNone(decode_walk_frame(bytes(range(32))))

    def test_decode_rejects_wrong_length(self):
        self.assertIsNone(decode_walk_frame(WalkFrame(role=ROLE_FIXED, station=0, sequence=0, received_count=0).encode()[:31]))

    def test_decode_rejects_out_of_range_role_byte(self):
        frame = bytearray(WalkFrame(role=ROLE_CARRIED, station=1, sequence=1, received_count=1).encode())
        frame[4] = 2
        self.assertIsNone(decode_walk_frame(bytes(frame)))


class PercentAndGapTests(unittest.TestCase):
    def test_percent_of_zero_whole_is_zero(self):
        self.assertEqual(percent_of(5, 0), 0)

    def test_percent_of_rounds_to_nearest(self):
        self.assertEqual(percent_of(1, 3), 33)
        self.assertEqual(percent_of(2, 3), 67)
        self.assertEqual(percent_of(1, 8), 13)

    def test_percent_of_caps_at_100(self):
        self.assertEqual(percent_of(150, 100), 100)

    def test_gap_stats_on_empty_set(self):
        self.assertEqual(_distinct_gap_stats(set()), (0, 0, 0))

    def test_gap_stats_on_contiguous_run(self):
        self.assertEqual(_distinct_gap_stats({0, 1, 2, 3, 4}), (5, 0, 5))

    def test_gap_stats_finds_the_longest_gap(self):
        # Missing 1, then missing 4,5,6 -- the longer gap should win.
        received, longest, span = _distinct_gap_stats({0, 2, 3, 7})
        self.assertEqual(received, 4)
        self.assertEqual(span, 8)
        self.assertEqual(longest, 3)


class BurstResultTests(unittest.TestCase):
    def test_downlink_loss_is_zero_when_nothing_was_measured(self):
        result = BurstResult(
            station=1, slots_run=0, slots_void=0, downlink_received=0, downlink_span=0,
            longest_miss_run=0, uplink_delivered=0, uplink_denominator=0,
            carrier_samples=0, carrier_busy=0,
        )
        self.assertEqual(result.downlink_loss_percent, 0)
        self.assertEqual(result.uplink_loss_percent, 0)
        self.assertFalse(result.trustworthy)

    def test_uplink_delivered_beyond_denominator_is_clamped(self):
        # A stale delta (e.g. a wrapped 16-bit counter) must not report negative loss.
        result = BurstResult(
            station=1, slots_run=10, slots_void=0, downlink_received=0, downlink_span=0,
            longest_miss_run=0, uplink_delivered=999, uplink_denominator=10,
            carrier_samples=0, carrier_busy=0,
        )
        self.assertEqual(result.uplink_loss_percent, 0)

    def test_trustworthy_threshold_is_25_percent_void(self):
        trustworthy = BurstResult(
            station=1, slots_run=5, slots_void=1, downlink_received=0, downlink_span=0,
            longest_miss_run=0, uplink_delivered=0, uplink_denominator=4,
            carrier_samples=0, carrier_busy=0,
        )
        untrustworthy = BurstResult(
            station=1, slots_run=5, slots_void=2, downlink_received=0, downlink_span=0,
            longest_miss_run=0, uplink_delivered=0, uplink_denominator=3,
            carrier_samples=0, carrier_busy=0,
        )
        self.assertTrue(trustworthy.trustworthy)
        self.assertFalse(untrustworthy.trustworthy)


class SysfsLedTests(unittest.TestCase):
    def test_missing_led_device_fails_loudly_rather_than_no_op(self):
        with self.assertRaisesRegex(Nrf905Error, "does not exist") as raised:
            SysfsLed("definitely-not-a-real-led-9c2f1a")
        self.assertEqual(raised.exception.code, "LED_DEVICE_MISSING")


class RunCarriedBurstTests(unittest.TestCase):
    def _fixed_frame(self, sequence, received_count):
        return WalkFrame(role=ROLE_FIXED, station=0, sequence=sequence, received_count=received_count).encode()

    def test_burst_measures_downlink_gap_and_uplink_delta(self):
        clock = ManualClock()
        device = FakeWalkDevice(clock)
        # Sequence 12 is deliberately absent: a one-frame gap in the middle.
        for sequence, received_count in ((10, 100), (11, 101), (13, 102), (14, 103)):
            device.queue(self._fixed_frame(sequence, received_count))
        led = FakeLed()

        result = run_carried_burst(
            device, led, station=7, slots=5, interval_s=0.02,
            sleeper=clock.sleep, monotonic=clock,
        )

        self.assertEqual(result.slots_run, 5)
        self.assertEqual(result.slots_void, 0)
        self.assertEqual(result.downlink_received, 4)
        self.assertEqual(result.downlink_span, 5)
        self.assertEqual(result.longest_miss_run, 1)
        self.assertEqual(result.downlink_loss_percent, 20)
        self.assertEqual(result.uplink_delivered, 3)
        self.assertEqual(result.uplink_denominator, 5)
        self.assertEqual(result.uplink_loss_percent, 40)
        self.assertTrue(result.trustworthy)
        # The LED tracks received downlink frames, not our own transmits --
        # 4 distinct sequences arrived, so 4 blinks, not 5 (our slot count).
        self.assertEqual(led.blinks, 4)
        self.assertEqual(len(device.transmitted), 5)
        first_sent = decode_walk_frame(device.transmitted[0])
        self.assertEqual(first_sent.role, ROLE_CARRIED)
        self.assertEqual(first_sent.station, 7)

    def test_a_failed_transmit_is_void_not_lost_and_blinking_is_independent_of_it(self):
        clock = ManualClock()
        device = FakeWalkDevice(clock, fail_transmit_slots={2})
        device.queue(self._fixed_frame(1, 5))
        device.queue(self._fixed_frame(2, 6))
        led = FakeLed()

        result = run_carried_burst(
            device, led, station=1, slots=5, interval_s=0.01,
            sleeper=clock.sleep, monotonic=clock,
        )

        self.assertEqual(result.slots_run, 5)
        self.assertEqual(result.slots_void, 1)
        self.assertEqual(result.uplink_denominator, 4)
        # Reception, not our own transmit success, drives the blink -- these
        # two receptions blink regardless of the unrelated transmit failure.
        self.assertEqual(led.blinks, 2)
        self.assertTrue(result.trustworthy)

    def test_no_reception_yields_zero_span_not_100_percent_loss(self):
        # With nothing received there is no denominator (we never learned how
        # many beacons the fixed node even sent), so this reads as 0% loss on
        # a 0-length span rather than 100% -- span/trustworthy is how a reader
        # tells "nothing arrived" apart from "everything arrived".
        clock = ManualClock()
        device = FakeWalkDevice(clock)
        led = FakeLed()

        result = run_carried_burst(
            device, led, station=1, slots=3, interval_s=0.01,
            sleeper=clock.sleep, monotonic=clock,
        )

        self.assertEqual(result.downlink_received, 0)
        self.assertEqual(result.downlink_span, 0)
        self.assertEqual(result.downlink_loss_percent, 0)
        self.assertEqual(result.uplink_delivered, 0)
        self.assertTrue(result.trustworthy)
        # Nothing arrived, so the LED never lit -- this is the "out of range"
        # signal the walk relies on: it goes dark, not just imprecise.
        self.assertEqual(led.blinks, 0)


class RunCarriedLoopTests(unittest.TestCase):
    def test_auto_increments_station_and_stops_on_request(self):
        clock = ManualClock()
        device = FakeWalkDevice(clock)
        led = FakeLed()
        stop = threading.Event()
        seen_stations = []

        def on_result(result):
            seen_stations.append(result.station)
            if len(seen_stations) == 3:
                stop.set()

        results = run_carried_loop(
            device, led, start_station=5, slots=2, interval_s=0.01,
            stop=stop, on_result=on_result, sleeper=clock.sleep, monotonic=clock,
        )

        self.assertEqual([result.station for result in results], [5, 6, 7])
        self.assertEqual(seen_stations, [5, 6, 7])

    def test_an_already_set_stop_runs_nothing(self):
        clock = ManualClock()
        device = FakeWalkDevice(clock)
        led = FakeLed()
        stop = threading.Event()
        stop.set()

        results = run_carried_loop(
            device, led, start_station=1, slots=2, interval_s=0.01,
            stop=stop, sleeper=clock.sleep, monotonic=clock,
        )

        self.assertEqual(results, [])
        self.assertEqual(len(device.transmitted), 0)


class RunFixedLoopTests(unittest.TestCase):
    def test_counts_valid_carried_frames_and_reports_running_total_when_sent(self):
        clock = ManualClock()
        device = FakeWalkDevice(clock)
        carried_frame = WalkFrame(role=ROLE_CARRIED, station=4, sequence=1, received_count=0).encode()
        # Available from the very first interval onward.
        device.queue(carried_frame)
        device.queue(carried_frame)

        received = run_fixed_loop(
            device, interval_s=0.01, max_iterations=3,
            sleeper=clock.sleep, monotonic=clock,
        )

        self.assertEqual(received, 2)
        self.assertEqual(len(device.transmitted), 3)
        reported_counts = [decode_walk_frame(frame).received_count for frame in device.transmitted]
        # The count reported in each outgoing beacon reflects what had been
        # received *before* that beacon was sent -- what a carried burst
        # samples to compute its own uplink delta.
        self.assertEqual(reported_counts, [0, 2, 2])

    def test_stop_event_ends_the_loop_between_iterations(self):
        clock = ManualClock()
        device = FakeWalkDevice(clock)
        stop = threading.Event()
        stop.set()

        received = run_fixed_loop(device, interval_s=0.01, stop=stop, sleeper=clock.sleep, monotonic=clock)

        self.assertEqual(received, 0)
        self.assertEqual(len(device.transmitted), 0)


if __name__ == "__main__":
    unittest.main()
