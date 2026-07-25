import threading
import time
import unittest

from packet_predator.model import WorkbenchModel


def observation(identifier, direction=None, invalid=False):
    capture = None
    if direction is not None:
        capture = {
            "transport": "nrf905",
            "direction": direction,
        }
    return {
        "id": identifier,
        "observed_at": "2026-07-25T00:00:00+00:00",
        "origin": "unit test",
        "title": f"Observation {identifier}",
        "summary": "Deterministic model test",
        "received_frame_hex": "00" * 32,
        "family": {"id": "test", "label": "Test"},
        "capture": capture,
        "inspection_error": (
            {"code": "TEST_INVALID", "message": "Invalid test frame"} if invalid else None
        ),
    }


class WorkbenchModelTests(unittest.TestCase):
    def test_publish_orders_entries_and_returns_immutable_copies(self):
        model = WorkbenchModel(retention=2)
        source = observation("one", "received")
        stored = model.publish(source)
        source["title"] = "mutated source"
        stored["title"] = "mutated return"
        model.publish(observation("two", "sent"))
        model.publish(observation("three", "received"))

        journal = model.journal()
        self.assertEqual([item["id"] for item in journal["entries"]], ["three", "two"])
        self.assertEqual(model.inspection("two")["title"], "Observation two")
        self.assertIsNone(model.inspection("one"))
        self.assertEqual(model.snapshot()["receiver"]["received_count"], 2)
        self.assertEqual(model.snapshot()["receiver"]["sent_count"], 1)

    def test_invalid_observation_and_receiver_fault_are_visible(self):
        model = WorkbenchModel()
        model.publish(observation("bad", "received", invalid=True))
        model.set_receiver_state(
            "faulted",
            {"code": "GPIO_FAILED", "message": "GPIO unavailable"},
        )

        snapshot = model.snapshot()
        self.assertEqual(snapshot["receiver"]["invalid_count"], 1)
        self.assertEqual(snapshot["receiver"]["state"], "faulted")
        self.assertEqual(snapshot["receiver"]["last_error"]["code"], "GPIO_FAILED")
        self.assertEqual(snapshot["latest"]["inspection_error"]["code"], "TEST_INVALID")

    def test_waiter_wakes_for_change_without_blocking_publish(self):
        model = WorkbenchModel()
        result = {}

        def wait():
            result.update(model.wait_for_changes(0, 1.0))

        thread = threading.Thread(target=wait)
        thread.start()
        time.sleep(0.01)
        model.publish(observation("wake"))
        thread.join(1.0)

        self.assertFalse(thread.is_alive())
        self.assertFalse(result["resync"])
        self.assertEqual(result["changes"][0]["observation_id"], "wake")

    def test_old_revision_requires_resynchronization(self):
        model = WorkbenchModel(change_retention=2)
        model.publish(observation("one"))
        model.publish(observation("two"))
        model.publish(observation("three"))

        result = model.changes_since(0)
        self.assertTrue(result["resync"])
        self.assertEqual(result["revision"], 3)
        self.assertEqual(result["changes"], [])


if __name__ == "__main__":
    unittest.main()
