from collections import deque
import threading
import unittest

from packet_predator.adapters.nrf905 import Nrf905Error
from packet_predator.nrf905_walk import (
    ROLE_CARRIED,
    ROLE_FIXED,
    BurstResult,
    LedPulseWorker,
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

    def __init__(self, clock, fail_transmit_slots=frozenset(), fail_carrier_slots=frozenset()):
        self._clock = clock
        self._pending = deque()
        self.fail_transmit_slots = fail_transmit_slots
        self.fail_carrier_slots = fail_carrier_slots
        self.transmitted = []
        self._carrier_reads = 0
        self.wait_timeouts = []
        self._wait_condition = threading.Condition()

    def queue(self, frame):
        self._pending.append(frame)

    def transmit(self, frame):
        index = len(self.transmitted)
        self.transmitted.append(frame)
        if index in self.fail_transmit_slots:
            raise Nrf905Error("NRF905_TRANSMIT_TIMEOUT", "simulated transmit failure")
        return {"elapsed_ms": 0.0, "frame_hex": frame.hex()}

    def pin_status(self):
        index = self._carrier_reads
        self._carrier_reads += 1
        if index in self.fail_carrier_slots:
            raise Nrf905Error("NRF905_GPIO_READ", "simulated carrier-detect read failure")
        return {"carrier_detect": False}

    def wait_data_ready(self, timeout_s):
        with self._wait_condition:
            self.wait_timeouts.append(timeout_s)
            self._wait_condition.notify_all()
        if self._pending:
            return True
        self._clock.sleep(timeout_s)
        return False

    def wait_for_receive_waits(self, count, timeout=1):
        with self._wait_condition:
            return self._wait_condition.wait_for(
                lambda: len(self.wait_timeouts) >= count,
                timeout=timeout,
            )

    def receive(self):
        return self._pending.popleft() if self._pending else None


class FakeLed:
    def __init__(self, fail_off=False):
        self.blinks = 0
        self.off_count = 0
        self.fail_off = fail_off

    def on(self):
        self.blinks += 1

    def off(self):
        if self.fail_off:
            raise Nrf905Error("LED_WRITE", "simulated LED off failure")
        self.off_count += 1

    def blink(self, seconds=0.05, sleeper=None):
        raise AssertionError("walk feedback must not blink synchronously in the receive slot")


class BlockingSleeper:
    """Block each sleep call until its matching release from the test."""

    def __init__(self):
        self._condition = threading.Condition()
        self.calls = []
        self._released = 0

    def __call__(self, seconds):
        with self._condition:
            call_index = len(self.calls)
            self.calls.append(seconds)
            self._condition.notify_all()
            if not self._condition.wait_for(
                lambda: self._released > call_index,
                timeout=1,
            ):
                raise AssertionError("test did not release blocked LED pulse")

    def wait_for_calls(self, count, timeout=1):
        with self._condition:
            return self._condition.wait_for(
                lambda: len(self.calls) >= count,
                timeout=timeout,
            )

    def release_next(self):
        with self._condition:
            self._released += 1
            self._condition.notify_all()


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

    def test_gap_stats_treats_a_contiguous_wrap_as_four_frames(self):
        self.assertEqual(_distinct_gap_stats({65534, 65535, 0, 1}), (4, 0, 4))

    def test_gap_stats_counts_missing_frames_across_the_wrap(self):
        # 65535 and 1 are missing from an otherwise five-frame window.
        self.assertEqual(_distinct_gap_stats({65534, 0, 2}), (3, 1, 5))

    def test_gap_stats_is_unchanged_by_duplicates_or_arrival_order(self):
        received = [1, 65534, 0, 65534, 2, 0]
        self.assertEqual(_distinct_gap_stats(set(received)), (4, 1, 5))


class BurstResultTests(unittest.TestCase):
    def test_downlink_loss_is_zero_when_nothing_was_measured(self):
        result = BurstResult(
            station=1, slots_run=0, slots_void=0, downlink_received=0, downlink_span=0,
            longest_miss_run=0, uplink_delivered=0, uplink_denominator=0,
            carrier_samples=0, carrier_busy=0, carrier_void=0,
        )
        self.assertEqual(result.downlink_loss_percent, 0)
        self.assertEqual(result.uplink_loss_percent, 0)
        self.assertFalse(result.trustworthy)

    def test_uplink_loss_is_zero_not_100_when_nothing_was_heard_from_fixed(self):
        # Uplink can only be sampled via the fixed node's piggybacked counter,
        # which requires hearing at least one downlink frame. Zero downlink
        # reception with a healthy denominator used to compute a false 100%
        # here -- indistinguishable from "we heard fixed, but it heard none
        # of us" -- when the truth is we have no basis for a number at all.
        result = BurstResult(
            station=1, slots_run=100, slots_void=0, downlink_received=0, downlink_span=0,
            longest_miss_run=0, uplink_delivered=0, uplink_denominator=100,
            carrier_samples=0, carrier_busy=0, carrier_void=0,
        )
        self.assertEqual(result.uplink_loss_percent, 0)

    def test_uplink_delivered_beyond_denominator_is_clamped(self):
        # A stale delta (e.g. a wrapped 16-bit counter) must not report negative loss.
        result = BurstResult(
            station=1, slots_run=10, slots_void=0, downlink_received=0, downlink_span=0,
            longest_miss_run=0, uplink_delivered=999, uplink_denominator=10,
            carrier_samples=0, carrier_busy=0, carrier_void=0,
        )
        self.assertEqual(result.uplink_loss_percent, 0)

    def test_trustworthy_threshold_is_25_percent_void(self):
        # carrier_samples is healthy and identical in both cases, so this
        # isolates the slots_void threshold from the carrier-availability
        # gate covered separately below.
        trustworthy = BurstResult(
            station=1, slots_run=5, slots_void=1, downlink_received=0, downlink_span=0,
            longest_miss_run=0, uplink_delivered=0, uplink_denominator=4,
            carrier_samples=5, carrier_busy=0, carrier_void=0,
        )
        untrustworthy = BurstResult(
            station=1, slots_run=5, slots_void=2, downlink_received=0, downlink_span=0,
            longest_miss_run=0, uplink_delivered=0, uplink_denominator=3,
            carrier_samples=5, carrier_busy=0, carrier_void=0,
        )
        self.assertTrue(trustworthy.trustworthy)
        self.assertFalse(untrustworthy.trustworthy)

    def test_carrier_busy_percent_is_none_not_zero_when_every_sample_failed(self):
        # None is "no reading," distinct from 0, which is "confirmed clear."
        # Collapsing them would let a dead carrier-detect line report a clean
        # channel.
        result = BurstResult(
            station=1, slots_run=5, slots_void=0, downlink_received=0, downlink_span=0,
            longest_miss_run=0, uplink_delivered=0, uplink_denominator=5,
            carrier_samples=0, carrier_busy=0, carrier_void=5,
        )
        self.assertIsNone(result.carrier_busy_percent)
        self.assertFalse(result.trustworthy)

    def test_trustworthy_despite_partial_carrier_sampling_failure(self):
        # A handful of successful reads is still a basis for a percentage,
        # just a noisier one -- only total failure withholds trustworthy.
        result = BurstResult(
            station=1, slots_run=5, slots_void=0, downlink_received=0, downlink_span=0,
            longest_miss_run=0, uplink_delivered=0, uplink_denominator=5,
            carrier_samples=1, carrier_busy=0, carrier_void=4,
        )
        self.assertEqual(result.carrier_busy_percent, 0)
        self.assertTrue(result.trustworthy)


class SysfsLedTests(unittest.TestCase):
    def test_missing_led_device_fails_loudly_rather_than_no_op(self):
        with self.assertRaisesRegex(Nrf905Error, "does not exist") as raised:
            SysfsLed("definitely-not-a-real-led-9c2f1a")
        self.assertEqual(raised.exception.code, "LED_DEVICE_MISSING")


class LedPulseWorkerTests(unittest.TestCase):
    def test_pressure_coalesces_and_close_waits_only_for_the_active_pulse(self):
        led = FakeLed()
        sleeper = BlockingSleeper()
        worker = LedPulseWorker(led, pulse_s=0.05, sleeper=sleeper)

        worker.pulse()
        self.assertTrue(sleeper.wait_for_calls(1))
        for _ in range(1000):
            worker.pulse()

        status = worker.status()
        self.assertTrue(status["active"])
        self.assertTrue(status["pending"])
        self.assertEqual(status["coalesced_count"], 999)

        close_error = []

        def close_worker():
            try:
                worker.close()
            except Exception as exc:  # pragma: no cover - asserted below
                close_error.append(exc)

        closer = threading.Thread(target=close_worker)
        closer.start()
        with worker._condition:
            self.assertTrue(
                worker._condition.wait_for(lambda: worker._closing, timeout=1)
            )

        status = worker.status()
        self.assertTrue(status["active"])
        self.assertFalse(status["pending"])
        self.assertTrue(closer.is_alive())

        sleeper.release_next()
        closer.join(timeout=1)

        self.assertFalse(closer.is_alive())
        self.assertEqual(close_error, [])
        self.assertEqual(sleeper.calls, [0.05])
        self.assertEqual(led.blinks, 1)
        self.assertEqual(led.off_count, 1)

    def test_background_error_discards_pressure_and_remains_explicit(self):
        led = FakeLed(fail_off=True)
        sleeper = BlockingSleeper()
        worker = LedPulseWorker(led, pulse_s=0.05, sleeper=sleeper)

        worker.pulse()
        self.assertTrue(sleeper.wait_for_calls(1))
        for _ in range(1000):
            worker.pulse()

        self.assertTrue(worker.status()["pending"])
        sleeper.release_next()

        with self.assertRaises(Nrf905Error) as raised:
            worker.close()

        self.assertEqual(raised.exception.code, "LED_WRITE")
        self.assertEqual(sleeper.calls, [0.05])
        self.assertFalse(worker.status()["pending"])


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
            led_pulse_s=0, monotonic=clock,
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
        self.assertEqual(len(device.transmitted), 5)
        first_sent = decode_walk_frame(device.transmitted[0])
        self.assertEqual(first_sent.role, ROLE_CARRIED)
        self.assertEqual(first_sent.station, 7)

    def test_uplink_delta_wraps_with_the_fixed_counter(self):
        clock = ManualClock()
        device = FakeWalkDevice(clock)
        device.queue(self._fixed_frame(10, 65535))
        device.queue(self._fixed_frame(11, 1))
        led = FakeLed()

        result = run_carried_burst(
            device, led, station=7, slots=2, interval_s=0.02,
            led_pulse_s=0, monotonic=clock,
        )

        self.assertEqual(result.uplink_delivered, 2)

    def test_a_failed_transmit_is_void_not_lost_and_blinking_is_independent_of_it(self):
        clock = ManualClock()
        device = FakeWalkDevice(clock, fail_transmit_slots={2})
        device.queue(self._fixed_frame(1, 5))
        device.queue(self._fixed_frame(2, 6))
        led = FakeLed()

        result = run_carried_burst(
            device, led, station=1, slots=5, interval_s=0.01,
            led_pulse_s=0, monotonic=clock,
        )

        self.assertEqual(result.slots_run, 5)
        self.assertEqual(result.slots_void, 1)
        self.assertEqual(result.uplink_denominator, 4)
        self.assertTrue(result.trustworthy)

    def test_total_carrier_sampling_failure_is_not_confirmed_zero_busy(self):
        clock = ManualClock()
        device = FakeWalkDevice(clock, fail_carrier_slots={0, 1, 2, 3, 4})
        led = FakeLed()

        result = run_carried_burst(
            device, led, station=1, slots=5, interval_s=0.01,
            led_pulse_s=0, monotonic=clock,
        )

        self.assertEqual(result.slots_run, 5)
        self.assertEqual(result.slots_void, 0)
        self.assertEqual(result.carrier_samples, 0)
        self.assertIsNone(result.carrier_busy_percent)
        self.assertIsNone(result.as_dict()["carrier_busy_percent"])
        # Clean transmit/receive but zero carrier evidence still voids trust
        # in the result -- this is exactly the case that used to serialize
        # as a confirmed 0% busy reading.
        self.assertFalse(result.trustworthy)

    def test_partial_carrier_sampling_failure_still_reports_a_percentage(self):
        clock = ManualClock()
        device = FakeWalkDevice(clock, fail_carrier_slots={0, 1, 2, 3})
        led = FakeLed()

        result = run_carried_burst(
            device, led, station=1, slots=5, interval_s=0.01,
            led_pulse_s=0, monotonic=clock,
        )

        self.assertEqual(result.carrier_samples, 1)
        self.assertEqual(result.carrier_busy_percent, 0)
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
            led_pulse_s=0, monotonic=clock,
        )

        self.assertEqual(result.downlink_received, 0)
        self.assertEqual(result.downlink_span, 0)
        self.assertEqual(result.downlink_loss_percent, 0)
        self.assertEqual(result.uplink_delivered, 0)
        # Not 100: we never sampled the fixed node's counter at all, so there
        # is no basis to claim any uplink loss either -- same "unmeasured
        # reads as 0" convention as downlink, for the same reason.
        self.assertEqual(result.uplink_loss_percent, 0)
        self.assertTrue(result.trustworthy)
        # Nothing arrived, so the LED never lit -- this is the "out of range"
        # signal the walk relies on: it goes dark, not just imprecise.
        self.assertEqual(led.blinks, 0)

    def test_led_pulse_does_not_consume_the_receive_interval(self):
        sleeper = BlockingSleeper()

        class DeviceThatWaitsForThePulse(FakeWalkDevice):
            def wait_data_ready(self, timeout_s):
                with self._wait_condition:
                    self.wait_timeouts.append(timeout_s)
                    wait_count = len(self.wait_timeouts)
                    self._wait_condition.notify_all()
                if wait_count == 2:
                    if not sleeper.wait_for_calls(1):
                        raise AssertionError("LED worker did not start its pulse")
                if self._pending:
                    return True
                self._clock.sleep(timeout_s)
                return False

        clock = ManualClock()
        device = DeviceThatWaitsForThePulse(clock)
        device.queue(self._fixed_frame(1, 1))
        led = FakeLed()
        result = []
        error = []

        def run_burst():
            try:
                result.append(
                    run_carried_burst(
                        device,
                        led,
                        station=1,
                        slots=1,
                        interval_s=0.1,
                        led_pulse_s=0.05,
                        monotonic=clock,
                        led_sleeper=sleeper,
                    )
                )
            except Exception as exc:  # pragma: no cover - asserted below
                error.append(exc)

        runner = threading.Thread(target=run_burst)
        runner.start()

        self.assertTrue(sleeper.wait_for_calls(1))
        self.assertTrue(device.wait_for_receive_waits(2))
        self.assertTrue(runner.is_alive())
        self.assertAlmostEqual(device.wait_timeouts[0], 0.1)
        self.assertAlmostEqual(device.wait_timeouts[1], 0.1)

        sleeper.release_next()
        runner.join(timeout=1)

        self.assertFalse(runner.is_alive())
        self.assertEqual(error, [])
        self.assertEqual(len(result), 1)
        self.assertEqual(sleeper.calls, [0.05])


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
            stop=stop, on_result=on_result, led_pulse_s=0, monotonic=clock,
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
            stop=stop, led_pulse_s=0, monotonic=clock,
        )

        self.assertEqual(results, [])
        self.assertEqual(len(device.transmitted), 0)


class RunFixedLoopTests(unittest.TestCase):
    def test_received_count_wraps_on_the_wire_and_the_loop_continues(self):
        class OneCarriedFramePerInterval(FakeWalkDevice):
            def __init__(self, clock, frame):
                super().__init__(clock)
                self._frame = frame

            def wait_data_ready(self, timeout_s):
                self._clock.sleep(timeout_s)
                return True

            def receive(self):
                return self._frame

        clock = ManualClock()
        carried_frame = WalkFrame(
            role=ROLE_CARRIED, station=4, sequence=1, received_count=0,
        ).encode()
        device = OneCarriedFramePerInterval(clock, carried_frame)

        result = run_fixed_loop(
            device, interval_s=0.01, max_iterations=65538,
            sleeper=clock.sleep, monotonic=clock,
        )

        self.assertEqual(result.received, 65538)
        reported_counts = [
            decode_walk_frame(device.transmitted[index]).received_count
            for index in (65535, 65536, 65537)
        ]
        self.assertEqual(reported_counts, [65535, 0, 1])

    def test_counts_valid_carried_frames_and_reports_running_total_when_sent(self):
        clock = ManualClock()
        device = FakeWalkDevice(clock)
        carried_frame = WalkFrame(role=ROLE_CARRIED, station=4, sequence=1, received_count=0).encode()
        # Available from the very first interval onward.
        device.queue(carried_frame)
        device.queue(carried_frame)

        result = run_fixed_loop(
            device, interval_s=0.01, max_iterations=3,
            sleeper=clock.sleep, monotonic=clock,
        )

        self.assertEqual(result.iterations, 3)
        self.assertEqual(result.received, 2)
        self.assertEqual(result.transmit_void, 0)
        self.assertTrue(result.trustworthy)
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

        result = run_fixed_loop(device, interval_s=0.01, stop=stop, sleeper=clock.sleep, monotonic=clock)

        self.assertEqual(result.iterations, 0)
        self.assertEqual(result.received, 0)
        self.assertEqual(len(device.transmitted), 0)
        self.assertFalse(result.trustworthy)

    def test_a_transmit_failure_does_not_stop_the_loop_but_is_counted_void(self):
        # Whether it's a one-off hardware fault or radio.transmit_enabled set
        # to false (which fails every single call, deterministically), the
        # fixed node must keep listening regardless -- but the failure must
        # not vanish silently.
        clock = ManualClock()
        device = FakeWalkDevice(clock, fail_transmit_slots={0, 1, 2})

        result = run_fixed_loop(
            device, interval_s=0.01, max_iterations=3,
            sleeper=clock.sleep, monotonic=clock,
        )

        self.assertEqual(result.iterations, 3)
        self.assertEqual(result.transmit_void, 3)
        self.assertEqual(len(device.transmitted), 3)
        # Every one of 3 iterations failed to transmit -- well past the 25%
        # void threshold, so the run cannot claim to have beaconed.
        self.assertFalse(result.trustworthy)

    def test_occasional_transmit_failure_stays_trustworthy(self):
        clock = ManualClock()
        device = FakeWalkDevice(clock, fail_transmit_slots={0})

        result = run_fixed_loop(
            device, interval_s=0.01, max_iterations=5,
            sleeper=clock.sleep, monotonic=clock,
        )

        self.assertEqual(result.transmit_void, 1)
        self.assertTrue(result.trustworthy)

    def test_status_callback_receives_the_running_void_count(self):
        clock = ManualClock()
        device = FakeWalkDevice(clock, fail_transmit_slots={0, 1})
        statuses = []

        run_fixed_loop(
            device, interval_s=0.01, max_iterations=3,
            on_status=lambda iterations, received, transmit_void: statuses.append(
                (iterations, received, transmit_void)
            ),
            sleeper=clock.sleep, monotonic=clock,
        )

        self.assertEqual(statuses, [(1, 0, 1), (2, 0, 2), (3, 0, 2)])


if __name__ == "__main__":
    unittest.main()
