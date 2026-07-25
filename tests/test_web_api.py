import asyncio
import json
import unittest
from pathlib import Path

from packet_predator import web
from packet_predator.web import app


REPO_ROOT = Path(__file__).resolve().parents[1]
AUTHORITY_ROOT = REPO_ROOT.parent / "Protocol_Contract"


async def asgi_request(method: str, path: str, body: dict | None = None):
    raw_body = json.dumps(body).encode("utf-8") if body is not None else b""
    request_sent = False
    events = []

    async def receive():
        nonlocal request_sent
        if not request_sent:
            request_sent = True
            return {"type": "http.request", "body": raw_body, "more_body": False}
        return {"type": "http.disconnect"}

    async def send(event):
        events.append(event)

    headers = [(b"host", b"testserver")]
    if body is not None:
        headers.append((b"content-type", b"application/json"))
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.4"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "root_path": "",
        "headers": headers,
        "client": ("127.0.0.1", 12345),
        "server": ("127.0.0.1", 8000),
    }
    await app(scope, receive, send)
    started = next(event for event in events if event["type"] == "http.response.start")
    content = b"".join(
        event.get("body", b"") for event in events if event["type"] == "http.response.body"
    )
    return started["status"], dict(started["headers"]), content


@unittest.skipUnless(
    (AUTHORITY_ROOT / "registry/v1.json").is_file(),
    "sibling Protocol Contract checkout is required for API integration tests",
)
class WebApiTests(unittest.TestCase):
    def setUp(self):
        web._service.cache_clear()

    def test_browser_index_is_served(self):
        status, headers, body = asyncio.run(asgi_request("GET", "/"))
        self.assertEqual(status, 200)
        self.assertIn(b"text/html", headers[b"content-type"])
        self.assertIn(b"Hardware-free inspection", body)
        self.assertIn(b'id="textSizePreference"', body)
        self.assertIn(b'id="fontPreference"', body)
        self.assertIn(b"/assets/style.css?v=20260725-2", body)
        self.assertIn(b"/assets/app.js?v=20260725-2", body)
        self.assertLess(body.index(b'id="inputHeading"'), body.index(b'id="radioCard"'))
        self.assertLess(body.index(b'id="radioCard"'), body.index(b'id="replayHeading"'))
        self.assertLess(body.index(b'id="replayHeading"'), body.index(b'id="resultPanel"'))

        app_source = (REPO_ROOT / "workbench_web/app.js").read_text(encoding="utf-8")
        self.assertIn("elements.resultTitle.textContent = item.meaning.name;", app_source)

    def test_status_is_explicitly_inspect_only(self):
        status, _, body = asyncio.run(asgi_request("GET", "/api/status"))
        result = json.loads(body)
        self.assertEqual(status, 200)
        self.assertEqual(result["carrier"]["mode"], "inspect-only")
        self.assertFalse(result["carrier"]["can_transmit"])
        self.assertEqual(result["authority"]["authority_version"], "1.0.1")

    def test_examples_and_inspection_use_the_released_authority(self):
        status, _, body = asyncio.run(asgi_request("GET", "/api/v1/examples"))
        examples = json.loads(body)["examples"]
        self.assertEqual(status, 200)
        self.assertEqual(len(examples), 38)

        status, _, body = asyncio.run(
            asgi_request(
                "POST",
                "/api/v1/inspect",
                {"frame_hex": examples[0]["frame_hex"], "mode": "auto", "origin": "API test"},
            )
        )
        result = json.loads(body)
        self.assertEqual(status, 200)
        self.assertEqual(result["meaning"]["name"], "NODE_HELLO")
        self.assertEqual(result["title"], "Node hello")

    def test_malformed_frame_is_a_visible_client_error(self):
        status, _, body = asyncio.run(
            asgi_request(
                "POST",
                "/api/v1/inspect",
                {"frame_hex": "400100", "mode": "auto", "origin": "API test"},
            )
        )
        result = json.loads(body)
        self.assertEqual(status, 422)
        self.assertEqual(result["error"]["code"], "FRAME_TOO_SHORT")

    def test_recording_selection_and_step_deliver_one_inspectable_frame(self):
        status, _, body = asyncio.run(asgi_request("GET", "/api/replays"))
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["count"], 3)

        status, _, body = asyncio.run(
            asgi_request("POST", "/api/replays/select", {"recording_id": "task-session-success"})
        )
        selected = json.loads(body)
        self.assertEqual(status, 200)
        self.assertEqual(selected["carrier"]["state"], "ready")
        self.assertFalse(selected["carrier"]["can_transmit"])

        status, _, body = asyncio.run(
            asgi_request("POST", "/api/replays/control", {"action": "step"})
        )
        stepped = json.loads(body)
        self.assertEqual(status, 200)
        self.assertEqual(len(stepped["delivered"]), 1)
        self.assertEqual(stepped["delivered"][0]["meaning"]["name"], "SCAN_OBSERVATION")
        self.assertEqual(stepped["delivered"][0]["capture"]["scheduled_at_ms"], 0)

        identifier = stepped["delivered"][0]["id"]
        status, _, body = asyncio.run(asgi_request("GET", f"/api/inspections/{identifier}"))
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["id"], identifier)

    def test_recording_play_is_explicit_and_never_transmits(self):
        asyncio.run(
            asgi_request("POST", "/api/replays/select", {"recording_id": "node-onboarding"})
        )
        status, _, body = asyncio.run(
            asgi_request(
                "POST",
                "/api/replays/control",
                {"action": "play", "speed": 4.0},
            )
        )
        result = json.loads(body)
        self.assertEqual(status, 200)
        self.assertEqual(result["carrier"]["state"], "playing")
        self.assertFalse(result["carrier"]["can_transmit"])
        self.assertEqual([item["capture"]["sequence"] for item in result["delivered"]], [0])

    def test_physical_routes_fail_clearly_in_default_inspect_only_mode(self):
        status, _, body = asyncio.run(asgi_request("POST", "/api/carrier/poll"))
        self.assertEqual(status, 422)
        self.assertEqual(json.loads(body)["error"]["code"], "PHYSICAL_ADAPTER_UNAVAILABLE")

        status, _, body = asyncio.run(
            asgi_request(
                "POST",
                "/api/carrier/transmit",
                {"frame_hex": "40010100", "mode": "auto", "confirmed": False},
            )
        )
        self.assertEqual(status, 422)
        self.assertEqual(json.loads(body)["error"]["code"], "TRANSMIT_CONFIRMATION_REQUIRED")


if __name__ == "__main__":
    unittest.main()
