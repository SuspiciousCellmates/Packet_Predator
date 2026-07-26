"""Thin FastAPI and static-file layer for the local workbench."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from functools import lru_cache
import json
import os
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, StrictInt

from . import __version__
from .service import WorkbenchService
from .adapters.nrf905 import Nrf905Error
from .nrf905_profile import Nrf905ProfileError, load_nrf905_profile
from .nrf905_transport import open_nrf905_transport
from .replay import RecordingError
from .transport import TransportError
from .wire_adapter import AuthorityError, InspectionError


_CONFIGURATION_ERRORS = (AuthorityError, RecordingError, Nrf905Error, Nrf905ProfileError, OSError)


class DecodeRequest(BaseModel):
    frame_hex: str = Field(min_length=1, max_length=512)
    mode: Literal["auto", "logical", "fixed"] = "auto"
    origin: str = Field(default="pasted frame", max_length=120)


class ReplaySelectRequest(BaseModel):
    recording_id: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class ReplayControlRequest(BaseModel):
    action: Literal["play", "pause", "step", "reset", "speed"]
    speed: Literal[0.25, 0.5, 1.0, 2.0, 4.0] | None = None


DraftFieldName = Annotated[
    str,
    Field(min_length=1, max_length=80, pattern=r"^(?:source|destination|[a-z][a-z0-9_]*)$"),
]
DraftByteOffset = Annotated[StrictInt, Field(ge=0, le=31)]


class TransmitProvenance(BaseModel):
    draft_id: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
    )
    base_identity: str = Field(min_length=1, max_length=240)
    changed_fields: list[DraftFieldName] = Field(default_factory=list, max_length=128)
    changed_bytes: list[DraftByteOffset] = Field(default_factory=list, max_length=32)
    console_run_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
    )


class TransmitRequest(BaseModel):
    frame_hex: str = Field(min_length=1, max_length=512)
    mode: Literal["auto", "logical", "fixed"] = "auto"
    confirmed: bool = False
    request_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
    )
    provenance: TransmitProvenance | None = None


class ComposeRequest(BaseModel):
    definition: str = Field(
        min_length=1,
        max_length=80,
        pattern=r"^[A-Z][A-Z0-9_]*$",
    )
    source: StrictInt = Field(ge=0, le=255)
    destination: StrictInt = Field(ge=0, le=255)
    values: dict[str, object]
    representation: Literal["logical", "fixed"] = "fixed"


@lru_cache(maxsize=1)
def _service() -> WorkbenchService:
    configured = os.environ.get("PACKET_PREDATOR_ADAPTER_PROFILE")
    if not configured:
        return WorkbenchService()
    profile = load_nrf905_profile(Path(configured))
    return WorkbenchService(carrier=open_nrf905_transport(profile))


def _unavailable(exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "error": {
                "code": "WORKBENCH_CONFIGURATION_UNAVAILABLE",
                "message": str(exc),
                "hint": "Check the sibling Protocol_Contract and recordings, then run ./scripts/check.",
            }
        },
    )


@asynccontextmanager
async def _lifespan(application: FastAPI):
    service = None
    try:
        service = _service()
        service.start()
        application.state.startup_error = None
    except _CONFIGURATION_ERRORS as exc:
        application.state.startup_error = exc
    try:
        yield
    finally:
        if service is not None:
            service.close()
        _service.cache_clear()


app = FastAPI(
    title="Packet Predator",
    description="Local packet inspection, deterministic replay, and explicit physical-adapter workbench",
    version=__version__,
    lifespan=_lifespan,
)


@app.get("/api/status")
async def status():
    try:
        return _service().status()
    except _CONFIGURATION_ERRORS as exc:
        return _unavailable(exc)


@app.get("/api/v1/catalog")
async def catalog():
    try:
        return _service().catalog()
    except _CONFIGURATION_ERRORS as exc:
        return _unavailable(exc)


@app.get("/api/v1/examples")
async def examples():
    try:
        return _service().examples()
    except _CONFIGURATION_ERRORS as exc:
        return _unavailable(exc)


@app.get("/api/v1/editor/messages")
async def editor_messages():
    try:
        return _service().editor_messages()
    except _CONFIGURATION_ERRORS as exc:
        return _unavailable(exc)


@app.get("/api/v1/editor/messages/{message_name}")
async def editor_message(message_name: str):
    try:
        return _service().editor_message(message_name)
    except InspectionError as exc:
        return JSONResponse(status_code=404, content={"error": exc.as_dict()})
    except _CONFIGURATION_ERRORS as exc:
        return _unavailable(exc)


@app.post("/api/v1/editor/compose")
async def compose(request: ComposeRequest):
    try:
        service = _service()
    except _CONFIGURATION_ERRORS as exc:
        return _unavailable(exc)
    try:
        return service.compose(
            request.definition,
            request.source,
            request.destination,
            request.values,
            request.representation,
        )
    except InspectionError as exc:
        return JSONResponse(status_code=422, content={"error": exc.as_dict()})
    except service.wire.codec_error as exc:
        return JSONResponse(status_code=422, content={"error": exc.as_dict()})


@app.post("/api/v1/editor/inspect")
async def inspect_editor_draft(request: DecodeRequest):
    try:
        service = _service()
    except _CONFIGURATION_ERRORS as exc:
        return _unavailable(exc)
    try:
        return service.inspect_draft(request.frame_hex, request.mode)
    except InspectionError as exc:
        return JSONResponse(status_code=422, content={"error": exc.as_dict()})
    except service.wire.codec_error as exc:
        return JSONResponse(status_code=422, content={"error": exc.as_dict()})


@app.post("/api/v1/inspect")
async def inspect(request: DecodeRequest):
    try:
        service = _service()
    except _CONFIGURATION_ERRORS as exc:
        return _unavailable(exc)
    try:
        return service.inspect(request.frame_hex, request.mode, request.origin)
    except InspectionError as exc:
        return JSONResponse(status_code=422, content={"error": exc.as_dict()})
    except service.wire.codec_error as exc:
        return JSONResponse(status_code=422, content={"error": exc.as_dict()})


@app.get("/api/inspections")
async def journal():
    try:
        return _service().journal()
    except _CONFIGURATION_ERRORS as exc:
        return _unavailable(exc)


@app.get("/api/inspections/{identifier}")
async def inspection(identifier: str):
    try:
        item = _service().inspection(identifier)
    except _CONFIGURATION_ERRORS as exc:
        return _unavailable(exc)
    if item is None:
        return JSONResponse(
            status_code=404,
            content={"error": {"code": "INSPECTION_NOT_FOUND", "message": "That inspection is no longer in the local journal."}},
        )
    return item


@app.get("/api/workbench/state")
async def workbench_state():
    try:
        return _service().model_state()
    except _CONFIGURATION_ERRORS as exc:
        return _unavailable(exc)


@app.get("/api/workbench/events")
async def workbench_events(request: Request, after: int = 0):
    try:
        service = _service()
    except _CONFIGURATION_ERRORS as exc:
        return _unavailable(exc)

    header_revision = request.headers.get("last-event-id")
    if header_revision and header_revision.isdecimal():
        after = max(after, int(header_revision))
    after = max(0, after)

    async def stream():
        revision = after
        loop = asyncio.get_running_loop()
        changed = asyncio.Event()
        unsubscribe = service.subscribe_to_model(
            lambda _: loop.call_soon_threadsafe(changed.set)
        )
        try:
            yield "retry: 1000\n\n"
            while True:
                if await request.is_disconnected():
                    return
                changed.clear()
                result = service.model_changes(revision)
                if result["resync"]:
                    revision = result["revision"]
                    payload = json.dumps({"revision": revision}, separators=(",", ":"))
                    yield f"id: {revision}\nevent: resync\ndata: {payload}\n\n"
                    continue
                if result["changes"]:
                    for change in result["changes"]:
                        revision = change["revision"]
                        payload = json.dumps(change, separators=(",", ":"))
                        yield f"id: {revision}\nevent: model\ndata: {payload}\n\n"
                    continue
                try:
                    await asyncio.wait_for(changed.wait(), timeout=15.0)
                except TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            unsubscribe()

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/replays")
async def replays():
    try:
        return _service().replay_catalog()
    except _CONFIGURATION_ERRORS as exc:
        return _unavailable(exc)


@app.post("/api/replays/select")
async def select_replay(request: ReplaySelectRequest):
    try:
        return _service().select_replay(request.recording_id)
    except (RecordingError, TransportError) as exc:
        return JSONResponse(status_code=422, content={"error": exc.as_dict()})
    except _CONFIGURATION_ERRORS as exc:
        return _unavailable(exc)


@app.post("/api/replays/control")
async def control_replay(request: ReplayControlRequest):
    try:
        return _service().control_replay(request.action, request.speed)
    except (RecordingError, TransportError) as exc:
        return JSONResponse(status_code=422, content={"error": exc.as_dict()})
    except _CONFIGURATION_ERRORS as exc:
        return _unavailable(exc)


@app.get("/api/replays/state")
async def replay_state():
    try:
        return _service().replay_state()
    except (RecordingError, TransportError) as exc:
        return JSONResponse(status_code=422, content={"error": exc.as_dict()})
    except _CONFIGURATION_ERRORS as exc:
        return _unavailable(exc)


@app.post("/api/carrier/transmit")
async def transmit(request: TransmitRequest):
    try:
        service = _service()
    except _CONFIGURATION_ERRORS as exc:
        return _unavailable(exc)
    try:
        return service.transmit(
            request.frame_hex,
            request.mode,
            request.confirmed,
            request.request_id,
            None if request.provenance is None else request.provenance.model_dump(),
        )
    except (InspectionError, TransportError, Nrf905Error) as exc:
        return JSONResponse(status_code=422, content={"error": exc.as_dict()})
    except service.wire.codec_error as exc:
        return JSONResponse(status_code=422, content={"error": exc.as_dict()})


static_root = Path(__file__).resolve().parents[1] / "workbench_web"
app.mount("/assets", StaticFiles(directory=static_root), name="assets")


@app.get("/", include_in_schema=False)
async def index() -> HTMLResponse:
    return HTMLResponse((static_root / "index.html").read_text(encoding="utf-8"))
