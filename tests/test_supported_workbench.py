import unittest
from pathlib import Path

from packet_predator.service import WorkbenchService
from packet_predator.wire_adapter import AuthorityError, InspectionError, WireAdapter


REPO_ROOT = Path(__file__).resolve().parents[1]
AUTHORITY_ROOT = REPO_ROOT.parent / "Protocol_Contract"


@unittest.skipUnless(
    (AUTHORITY_ROOT / "registry/v1.json").is_file(),
    "sibling Protocol Contract checkout is required for integration tests",
)
class SupportedWorkbenchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.wire = WireAdapter(AUTHORITY_ROOT)

    def test_all_released_examples_inspect_in_logical_and_fixed_forms(self):
        examples = self.wire.list_examples()["examples"]
        self.assertEqual(len(examples), 38)

        for item in examples:
            with self.subTest(item=item["id"], form="logical"):
                result = self.wire.inspect(item["frame_hex"], "logical")
                self.assertEqual(result["meaning"]["name"], item["name"])
                self.assertEqual(result["padding_bytes"], 0)
            with self.subTest(item=item["id"], form="fixed"):
                result = self.wire.inspect(item["padded_frame_hex"], "fixed")
                self.assertEqual(result["meaning"]["name"], item["name"])
                self.assertEqual(result["received_bytes"], 32)

    def test_plain_language_route_keeps_exact_values(self):
        item = self.wire.list_examples()["examples"][0]
        result = self.wire.inspect(item["frame_hex"])

        self.assertEqual(result["title"], "Node hello")
        self.assertEqual(result["route"]["source_label"], "Node endpoint 1")
        self.assertEqual(result["route"]["destination_label"], "Game Controller")
        self.assertEqual(result["envelope"]["message_type_hex"], "0x01")
        self.assertEqual(result["field_rows"][0]["offset"], 4)
        self.assertEqual(result["field_rows"][0]["value_hex"], "0x04 03 02 01 00 00 00 00")

    def test_invalid_user_hex_has_a_clear_classification(self):
        with self.assertRaisesRegex(InspectionError, "two characters per byte") as raised:
            self.wire.inspect("123")
        self.assertEqual(raised.exception.code, "HEX_ODD_LENGTH")

    def test_invalid_frame_uses_reference_codec_error(self):
        with self.assertRaises(self.wire.codec_error) as raised:
            self.wire.inspect("400100", "auto")
        self.assertEqual(raised.exception.code, "FRAME_TOO_SHORT")

    def test_logical_example_becomes_exact_fixed_adapter_frame(self):
        item = self.wire.list_examples()["examples"][0]
        fixed = self.wire.fixed_frame(item["frame_hex"], "logical")
        self.assertEqual(len(fixed), 32)
        self.assertEqual(fixed.hex(), item["padded_frame_hex"])

    def test_editor_schema_and_compose_are_contract_backed(self):
        schema = self.wire.editor_message("NODE_HELLO")
        message = schema["message"]
        self.assertEqual(message["value"], 1)
        reason = next(
            field
            for field in message["payload"]["fields"]
            if field["name"] == "synchronization_reason"
        )
        self.assertEqual(reason["enum_values"]["ENDPOINT_ASSIGNED"], 5)

        fixture = self.wire.examples_by_id["v1-node-hello"]
        payload = dict(fixture["expected"]["payload"])
        payload["synchronization_reason"] = 5
        result = self.wire.compose(
            "NODE_HELLO",
            source=1,
            destination=0,
            payload=payload,
            representation="fixed",
        )
        self.assertEqual(len(result["fixed_frame_hex"]), 64)
        self.assertEqual(
            result["inspection"]["body"]["synchronization_reason"],
            5,
        )

    def test_all_released_examples_recompose_to_identical_bytes(self):
        for fixture in self.wire.examples:
            with self.subTest(fixture=fixture["id"]):
                result = self.wire.compose(
                    fixture["message_name"],
                    source=fixture["header"]["source"],
                    destination=fixture["header"]["destination"],
                    payload=dict(fixture["expected"]["payload"]),
                    representation="fixed",
                )
                self.assertEqual(result["logical_frame_hex"], fixture["frame_hex"])
                self.assertEqual(
                    result["fixed_frame_hex"],
                    fixture["padded_frame_hex"],
                )
                offsets = [
                    offset
                    for row in result["inspection"]["field_rows"]
                    for offset in range(row["offset"], row["offset"] + row["size"])
                ]
                self.assertEqual(
                    offsets,
                    list(range(4, result["inspection"]["logical_bytes"])),
                )

    def test_decoded_bytes_fields_become_round_trip_editor_hex(self):
        fixture = self.wire.examples_by_id["v1-capability-chunk"]
        inspection = self.wire.inspect(fixture["padded_frame_hex"], "fixed")

        values = self.wire.editor_values(
            inspection["meaning"]["name"],
            inspection["body"],
        )
        result = self.wire.compose(
            inspection["meaning"]["name"],
            source=inspection["route"]["source"],
            destination=inspection["route"]["destination"],
            payload=values,
            representation="fixed",
        )

        self.assertEqual(
            values["canonical_descriptor_bytes"],
            "01000102010504deadbeef40021300",
        )
        self.assertEqual(result["fixed_frame_hex"], fixture["padded_frame_hex"])

    def test_editor_rejects_missing_or_extra_payload_fields(self):
        with self.assertRaises(InspectionError) as raised:
            self.wire.compose(
                "NODE_HELLO",
                source=1,
                destination=0,
                payload={"unexpected": 1},
                representation="fixed",
            )
        self.assertEqual(raised.exception.code, "EDITOR_PAYLOAD_FIELDS")

    def test_editor_preserves_full_u64_values_from_browser_decimal_text(self):
        fixture = self.wire.examples_by_id["v1-node-hello"]
        payload = dict(fixture["expected"]["payload"])
        payload["permanent_device_serial"] = "18446744073709551615"
        result = self.wire.compose(
            "NODE_HELLO",
            source=1,
            destination=0,
            payload=payload,
            representation="fixed",
        )
        self.assertEqual(
            result["inspection"]["body"]["permanent_device_serial"],
            18446744073709551615,
        )

    def test_service_is_truthfully_hardware_free_and_journals_manually(self):
        service = WorkbenchService(self.wire)
        status = service.status()
        self.assertEqual(status["workbench_interface_version"], 1)
        self.assertTrue(status["process_instance_id"].startswith("pp-"))
        self.assertEqual(status["carrier"]["mode"], "inspect-only")
        self.assertFalse(status["carrier"]["can_receive"])
        self.assertFalse(status["carrier"]["can_transmit"])
        self.assertEqual(
            service.model_state()["identity"]["process_instance_id"],
            status["process_instance_id"],
        )

        item = self.wire.list_examples()["examples"][0]
        service.inspect(item["frame_hex"], "auto", "unit example")
        journal = service.journal()
        self.assertEqual(journal["count"], 1)
        self.assertEqual(journal["entries"][0]["origin"], "unit example")

    def test_missing_authority_fails_without_falling_back(self):
        with self.assertRaisesRegex(AuthorityError, "checkout is incomplete"):
            WireAdapter(REPO_ROOT / "does-not-exist")


class BrowserAssetTests(unittest.TestCase):
    def test_browser_surface_contains_human_and_byte_views(self):
        html = (REPO_ROOT / "workbench_web/index.html").read_text(encoding="utf-8")
        for phrase in (
            "Hardware-free inspection",
            "No live carrier",
            "Deterministic recording player",
            "Frames only · no actors",
            "Example frames",
            "Overview",
            "Fields",
            "Bytes",
        ):
            self.assertIn(phrase, html)

    def test_supported_runtime_never_imports_archived_modules(self):
        forbidden = ("web_app", "simulator", "driver", "nodes", "decoder")
        for path in (REPO_ROOT / "packet_predator").glob("*.py"):
            content = path.read_text(encoding="utf-8")
            for name in forbidden:
                self.assertNotIn(f"import {name}", content, f"{path.name} imports {name}")

    def test_recording_player_controls_are_present_in_browser_surface(self):
        html = (REPO_ROOT / "workbench_web/index.html").read_text(encoding="utf-8")
        for identifier in (
            "recordingSelect",
            "replayReset",
            "replayStep",
            "replayPlay",
            "replayPause",
            "replaySpeed",
            "replaySchedule",
            "captureContext",
            "radioCard",
            "transmitConfirm",
            "transmitButton",
        ):
            self.assertIn(f'id="{identifier}"', html)

    def test_structured_draft_controls_and_safety_logic_are_present(self):
        html = (REPO_ROOT / "workbench_web/index.html").read_text(encoding="utf-8")
        source = (REPO_ROOT / "workbench_web/app.js").read_text(encoding="utf-8")
        for identifier in (
            "draftBar",
            "draftSource",
            "draftDestination",
            "draftUndo",
            "draftRedo",
            "draftRevert",
            "draftDiscard",
        ):
            self.assertIn(f'id="{identifier}"', html)
        for phrase in (
            "/api/v1/editor/messages",
            "/api/v1/editor/compose",
            "/api/v1/editor/inspect",
            "EDITOR_DRAFT_INVALID",
            "transmitRequestId",
            "window.confirm",
            "highlightField",
            "highlightByte",
        ):
            self.assertIn(phrase, source)


if __name__ == "__main__":
    unittest.main()
