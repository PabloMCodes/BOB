"""Edge API (C9) on the rover: serves the store to the hub, accepts inspection and profile commands.

Read-only except: deliver a profile revision, start an inspection, end an inspection. There is no
endpoint that moves, arms, stops or clears faults on the rover (tests/test_edge_api.py checks the
exact route list). It never runs inference: killing or stalling it cannot touch the frame path.
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Optional
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, ConfigDict

from bobapp.contracts import (
    APP_VERSION,
    BlobStatus,
    BlobStatusValue,
    InspectionEndReason,
    LiveState,
    Record,
    SourceMode,
    WorksiteProfile,
    is_sha256,
)
from bobapp.edge.store import CommandRefused, EdgeStore, NotFound

from .auth import token_ok
from .live import build_live_state
from .sync import SyncSession

ROUTES = {
    ("WEBSOCKET", "/v1/sync"), ("GET", "/v1/live"), ("GET", "/v1/preview/latest"), ("GET", "/v1/blobs/{sha256}"),
    ("GET", "/v1/inspections"), ("POST", "/v1/profiles"), ("POST", "/v1/inspections"),
    ("POST", "/v1/inspections/{inspection_id}/end"),
}


class StartInspection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profile: WorksiteProfile                 # full revision; its hash is re-verified here
    inspection_id: Optional[UUID] = None
    requested_by: Optional[str] = None
    source_mode: Optional[SourceMode] = None  # default: the running vision.server's declared mode


class DeliverProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profile: WorksiteProfile
    source_mode: Optional[SourceMode] = None


def create_app(store_path: Path, edge_id: str, config: dict[str, Any], token: Optional[str],
               clock_synced: Optional[bool] = None) -> FastAPI:
    local = threading.local()

    def store() -> EdgeStore:
        if getattr(local, "store", None) is None:
            local.store = EdgeStore(store_path, edge_id, clock_synced)
        return local.store

    store()  # create / open now: a wrong edge_id or unreadable store fails at startup
    app = FastAPI(title="BOB edge API (C9)", version=f"bob-app v{APP_VERSION}",
                  description="Rover-side sync and command API. No motion, arming or fault endpoints.")

    def auth(authorization: Optional[str] = Header(default=None)) -> None:
        if not token_ok(token, authorization):
            raise HTTPException(401, "missing or wrong bearer token")

    def run_mode(requested: Optional[SourceMode]) -> SourceMode:
        if requested is not None:
            return requested
        live, _ = build_live_state(store(), clock_synced)
        if live.source_mode is None:
            raise HTTPException(409, "no vision.server run is publishing; pass source_mode explicitly")
        return live.source_mode

    @app.websocket("/v1/sync")
    async def sync(ws: WebSocket) -> None:
        if not token_ok(token, ws.headers.get("authorization")):
            await ws.close(code=4401)
            return
        await ws.accept()
        try:
            await SyncSession(store, config, clock_synced).run(ws.receive_text, ws.send_text)
        except WebSocketDisconnect:
            pass

    @app.get("/v1/live", response_model=LiveState, dependencies=[Depends(auth)])
    def live() -> LiveState:
        return build_live_state(store(), clock_synced)[0]

    @app.get("/v1/preview/latest", dependencies=[Depends(auth)])
    def preview() -> Response:
        state, data = build_live_state(store(), clock_synced)
        if data is None or state.preview is None:
            return JSONResponse({"preview": None, "reason": "no preview published yet"}, status_code=404)
        return Response(data, media_type="image/jpeg",
                        headers={"X-Event-Id": str(state.preview.event_id), "X-Sha256": state.preview.sha256})

    @app.get("/v1/blobs/{sha256}", dependencies=[Depends(auth)])
    def blob(sha256: str) -> Response:
        if not is_sha256(sha256):
            raise HTTPException(422, "not a SHA-256")
        if not store().has_blob(sha256):
            status = BlobStatus(app_version=APP_VERSION, msg_type="blob_status", sha256=sha256,
                                status=BlobStatusValue.MISSING)
            return JSONResponse(status.model_dump(mode="json"), status_code=404)
        return FileResponse(store().blob_file(sha256), media_type="image/jpeg")

    @app.get("/v1/inspections", dependencies=[Depends(auth)])
    def inspections() -> list[dict]:
        return store().inspections()

    @app.post("/v1/profiles", dependencies=[Depends(auth)])
    def deliver(body: DeliverProfile) -> JSONResponse:
        try:
            record = store().deliver_profile(body.profile, body.source_mode or SourceMode.LIVE)
        except CommandRefused as exc:
            raise HTTPException(409, str(exc))
        return JSONResponse({"stored": record is not None,
                             "record": record.model_dump(mode="json") if record else None},
                            status_code=201 if record else 200)

    @app.post("/v1/inspections", response_model=Record, status_code=201, dependencies=[Depends(auth)])
    def start(body: StartInspection) -> Record:
        try:
            return store().start_inspection(body.profile, run_mode(body.source_mode), body.requested_by,
                                            body.inspection_id)
        except CommandRefused as exc:
            raise HTTPException(409, str(exc))

    @app.post("/v1/inspections/{inspection_id}/end", response_model=Record, dependencies=[Depends(auth)])
    def end(inspection_id: UUID) -> Record:
        try:
            return store().end_inspection(inspection_id, InspectionEndReason.OPERATOR)
        except NotFound as exc:
            raise HTTPException(404, str(exc))
        except CommandRefused as exc:
            raise HTTPException(409, str(exc))

    return app
