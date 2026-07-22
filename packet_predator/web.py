"""Thin FastAPI and static-file layer for the local workbench."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .service import WorkbenchService
from .wire_adapter import AuthorityError, InspectionError


class DecodeRequest(BaseModel):
    frame_hex: str = Field(min_length=1, max_length=512)
    mode: Literal["auto", "logical", "fixed"] = "auto"
    origin: str = Field(default="pasted frame", max_length=120)


@lru_cache(maxsize=1)
def _service() -> WorkbenchService:
    return WorkbenchService()


def _unavailable(exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "error": {
                "code": "AUTHORITY_UNAVAILABLE",
                "message": str(exc),
                "hint": "Keep Protocol_Contract beside Packet_Predator or set PACKET_PREDATOR_CONTRACT_ROOT.",
            }
        },
    )


app = FastAPI(
    title="Packet Predator",
    description="Local, hardware-free packet inspection workbench",
    version="0.1.0",
)


@app.get("/api/status")
async def status():
    try:
        return _service().status()
    except (AuthorityError, OSError) as exc:
        return _unavailable(exc)


@app.get("/api/v1/catalog")
async def catalog():
    try:
        return _service().catalog()
    except (AuthorityError, OSError) as exc:
        return _unavailable(exc)


@app.get("/api/v1/examples")
async def examples():
    try:
        return _service().examples()
    except (AuthorityError, OSError) as exc:
        return _unavailable(exc)


@app.post("/api/v1/inspect")
async def inspect(request: DecodeRequest):
    try:
        service = _service()
    except (AuthorityError, OSError) as exc:
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
    except (AuthorityError, OSError) as exc:
        return _unavailable(exc)


static_root = Path(__file__).resolve().parents[1] / "workbench_web"
app.mount("/assets", StaticFiles(directory=static_root), name="assets")


@app.get("/", include_in_schema=False)
async def index() -> HTMLResponse:
    return HTMLResponse((static_root / "index.html").read_text(encoding="utf-8"))
