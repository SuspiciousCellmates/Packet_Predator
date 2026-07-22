"""Thin FastAPI and static-file layer for the local workbench."""

from __future__ import annotations

from functools import lru_cache
import os
from pathlib import Path
from typing import Literal

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

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


class TransmitRequest(BaseModel):
    frame_hex: str = Field(min_length=1, max_length=512)
    mode: Literal["auto", "logical", "fixed"] = "auto"
    confirmed: bool = False


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


app = FastAPI(
    title="Packet Predator",
    description="Local packet inspection, deterministic replay, and explicit physical-adapter workbench",
    version="0.2.0",
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


@app.post("/api/carrier/poll")
async def poll_carrier():
    try:
        service = _service()
    except _CONFIGURATION_ERRORS as exc:
        return _unavailable(exc)
    try:
        return service.poll_physical()
    except (TransportError, Nrf905Error) as exc:
        return JSONResponse(status_code=422, content={"error": exc.as_dict()})
    except service.wire.codec_error as exc:
        return JSONResponse(status_code=422, content={"error": exc.as_dict()})


@app.post("/api/carrier/transmit")
async def transmit(request: TransmitRequest):
    try:
        service = _service()
    except _CONFIGURATION_ERRORS as exc:
        return _unavailable(exc)
    try:
        return service.transmit(request.frame_hex, request.mode, request.confirmed)
    except (InspectionError, TransportError, Nrf905Error) as exc:
        return JSONResponse(status_code=422, content={"error": exc.as_dict()})
    except service.wire.codec_error as exc:
        return JSONResponse(status_code=422, content={"error": exc.as_dict()})


static_root = Path(__file__).resolve().parents[1] / "workbench_web"
app.mount("/assets", StaticFiles(directory=static_root), name="assets")


@app.get("/", include_in_schema=False)
async def index() -> HTMLResponse:
    return HTMLResponse((static_root / "index.html").read_text(encoding="utf-8"))
