"""Hub frontend API (C10): the only service a browser talks to. It reads the hub replicas; it never
contacts the rover on a browser's behalf except to forward inspection start/end (worksites.py).

`?workspace=rover` (default) is the rover's data; `?workspace=sample` is the SAMPLE edge's, held in a
separate database, so sample records can never enter rover counts or be drawn on a real pose.
No route moves, arms, stops or clears faults on anything (route-list test).
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import threading
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response

from bobapp.contracts import APP_VERSION, BlobStatus, BlobStatusValue, Delivery, Hazard, IncidentTransition, SourceMode, is_sha256
from bobapp.edge.api.auth import token_ok

from ..replica import Replica
from . import views
from .frames import frame_router
from .twin import twin_router
from .worksites import worksite_router
from .models import AssessmentPage, InspectionPage, Page, StatusResponse, WorkspaceName

HUB_ROUTES = {
    ("GET", "/v1/status"), ("WEBSOCKET", "/v1/live"), ("GET", "/v1/preview/latest"), ("GET", "/v1/observations"),
    ("GET", "/v1/incidents"), ("GET", "/v1/assessments"), ("GET", "/v1/inspections"), ("GET", "/v1/evidence/{sha256}"),
    ("GET", "/v1/logs"),
    ("GET", "/v1/frames"),
    ("GET", "/v1/worksites"), ("GET", "/v1/worksites/{worksite_id}"), ("PUT", "/v1/worksites/{worksite_id}"),
    ("GET", "/v1/worksites/{worksite_id}/revisions/{revision}"), ("POST", "/v1/inspections"),
    ("POST", "/v1/inspections/{inspection_id}/end"),
    ("GET", "/v1/twin/sessions"), ("GET", "/v1/twin/sessions/{session_id}/track"),
    ("GET", "/v1/twin/sessions/{session_id}/pins"), ("GET", "/v1/twin/sessions/{session_id}/map.svg"),
}
Limit = Query(100, ge=1, le=1000)


def create_hub_app(config: dict[str, Any], token: Optional[str], replica_paths: dict[str, Path],
                   background: Optional[Callable[[asyncio.Event], Any]] = None,
                   edge: Optional[tuple[str, Optional[str]]] = None) -> FastAPI:
    """`edge` = (rover edge API http base, its token) for inspection commands; None = no rover configured."""
    local = threading.local()
    stale_after_s = config["link"]["stale_after_s"]
    api = config["api"]

    def replica(name: str) -> Replica:
        if name not in replica_paths:
            raise HTTPException(404, f"workspace {name!r} is not configured")
        cache = getattr(local, "replicas", None)
        if cache is None:
            cache = local.replicas = {}
        if name not in cache:
            cache[name] = Replica(replica_paths[name])
        return cache[name]

    @contextlib.asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        stop, task = asyncio.Event(), None
        if background is not None:
            task = asyncio.create_task(background(stop))
        yield
        stop.set()
        if task is not None:
            await task

    app = FastAPI(title="BOB hub API (C10)", version=f"bob-app v{APP_VERSION}", lifespan=lifespan,
                  description="Laptop hub for the dashboard and 2D Twin. Read-only views of rover data; "
                              "no motion, arming or fault endpoints. Every item states source_mode and delivery.")
    app.add_middleware(CORSMiddleware, allow_origins=api.get("cors_origins", []), allow_methods=["GET", "POST", "PUT"],
                       allow_headers=["Authorization", "Content-Type"],
                       expose_headers=["X-Sha256", "X-Event-Id", "X-Hub-Received-Wall-Ns"])

    def allowed(authorization: Optional[str], query_token: Optional[str]) -> bool:
        return token_ok(token, authorization) or (query_token is not None and token_ok(token, f"Bearer {query_token}"))

    def auth(authorization: Optional[str] = Header(default=None), token_param: Optional[str] = Query(None, alias="token")) -> None:
        if not allowed(authorization, token_param):
            raise HTTPException(401, "missing or wrong token (Authorization: Bearer … or ?token=)")

    deps = [Depends(auth)]
    app.include_router(worksite_router(lambda: replica("rover"), edge, deps))
    app.include_router(twin_router(replica, stale_after_s, deps))
    app.include_router(frame_router(replica, deps))

    @app.get("/v1/status", response_model=StatusResponse, dependencies=deps)
    def get_status(workspace: WorkspaceName = "rover") -> StatusResponse:
        return views.status(replica(workspace), workspace, stale_after_s)

    @app.get("/v1/preview/latest", dependencies=deps)
    def preview(workspace: WorkspaceName = "rover") -> Response:
        live_json, rx, data, sha = replica(workspace).get_live()
        if data is None:
            return JSONResponse({"preview": None, "reason": "no preview received yet"}, status_code=404)
        event_id = replica(workspace).preview_event(sha)
        return Response(data, media_type="image/jpeg", headers={
            "X-Sha256": sha, "X-Hub-Received-Wall-Ns": str(rx), "Cache-Control": "no-store",
            **({"X-Event-Id": event_id} if event_id else {})})

    @app.get("/v1/observations", response_model=Page, dependencies=deps)
    def observations(workspace: WorkspaceName = "rover", after: int = 0, limit: int = Limit,
                     inspection_id: Optional[str] = None, session_id: Optional[str] = None,
                     source_mode: Optional[SourceMode] = None, delivery: Optional[Delivery] = None,
                     latest: bool = False) -> Page:
        where = {k: v for k, v in (("$.body.assessment.inspection_id", inspection_id),
                                   ("$.body.event.session_id", session_id)) if v}
        return views.page(replica(workspace), workspace, ("observation",), after, limit, where,
                          source_mode.value if source_mode else None, delivery.value if delivery else None, latest)

    @app.get("/v1/incidents", response_model=Page, dependencies=deps)
    def incidents(workspace: WorkspaceName = "rover", after: int = 0, limit: int = Limit,
                  inspection_id: Optional[str] = None, session_id: Optional[str] = None,
                  hazard: Optional[Hazard] = None, transition: Optional[IncidentTransition] = None,
                  delivery: Optional[Delivery] = None, latest: bool = False) -> Page:
        where = {k: v for k, v in (("$.body.key.inspection_id", inspection_id), ("$.body.key.session_id", session_id),
                                   ("$.body.key.hazard", hazard.value if hazard else None),
                                   ("$.body.transition", transition.value if transition else None)) if v}
        return views.page(replica(workspace), workspace, ("incident",), after, limit, where, None,
                          delivery.value if delivery else None, latest)

    @app.get("/v1/logs", response_model=Page, dependencies=deps)
    def logs(workspace: WorkspaceName = "rover", after: int = Query(0, ge=0), limit: int = Limit,
             before: Optional[int] = Query(None, ge=1)) -> Page:
        return views.page(replica(workspace), workspace,
                          ("notice", "incident", "inspection_started", "inspection_ended", "profile_revision", "gap"),
                          after, limit, {}, None, None, latest=True, before=before)

    @app.get("/v1/assessments", response_model=AssessmentPage, dependencies=deps)
    def assessments(workspace: WorkspaceName = "rover", after: int = 0, limit: int = Limit,
                    inspection_id: Optional[str] = None, session_id: Optional[str] = None,
                    delivery: Optional[Delivery] = None) -> AssessmentPage:
        where = {k: v for k, v in (("$.body.assessment.inspection_id", inspection_id),
                                   ("$.body.event.session_id", session_id)) if v}
        return views.assessments(replica(workspace), workspace, after, limit, where, delivery.value if delivery else None)

    @app.get("/v1/inspections", response_model=InspectionPage, dependencies=deps)
    def inspections(workspace: WorkspaceName = "rover") -> InspectionPage:
        return views.inspections(replica(workspace), workspace)

    @app.get("/v1/evidence/{sha256}", dependencies=deps)
    def evidence(sha256: str, workspace: WorkspaceName = "rover") -> Response:
        if not is_sha256(sha256):
            raise HTTPException(422, "not a SHA-256")
        r = replica(workspace)
        status = r.blob_status(sha256) or BlobStatusValue.MISSING
        if status == BlobStatusValue.AVAILABLE:
            return FileResponse(r.blob_file(sha256), media_type="image/jpeg")
        body = BlobStatus(app_version=APP_VERSION, msg_type="blob_status", sha256=sha256, status=status)
        return JSONResponse(body.model_dump(mode="json"), status_code=202 if status == BlobStatusValue.PENDING_SYNC else 404)

    @app.websocket("/v1/live")
    async def live(ws: WebSocket, workspace: WorkspaceName = "rover", token_param: Optional[str] = Query(None, alias="token")) -> None:
        """Snapshot on connect, then the current status every `api.live_interval_s` plus summaries of
        newly replicated records. Latest state only: a slow browser is disconnected, never queued for."""
        if not allowed(ws.headers.get("authorization"), token_param) or workspace not in replica_paths:
            await ws.close(code=4401)
            return
        await ws.accept()

        def snapshot(after: int) -> tuple[dict, list[dict], int]:
            rep = replica(workspace)
            ws_ = rep.active_workspace()
            rows = rep.records(ws_, after_rowid=after, limit=200) if ws_ else []
            records = [{"cursor": rowid, "delivery": delivery, **_summary(text)} for rowid, delivery, text in rows]
            return (views.status(rep, workspace, stale_after_s).model_dump(mode="json"), records,
                    rows[-1][0] if rows else after)

        after = await asyncio.to_thread(lambda: (lambda w: replica(workspace).max_rowid(w) if w else 0)(
            replica(workspace).active_workspace()))
        kind = "snapshot"
        try:
            while True:
                status, records, after = await asyncio.to_thread(snapshot, after)
                message = json.dumps({"type": kind, "workspace": workspace, "status": status, "records": records})
                await asyncio.wait_for(ws.send_text(message), timeout=api["send_timeout_s"])
                kind = "update"
                await asyncio.sleep(api["live_interval_s"])
        except (WebSocketDisconnect, asyncio.TimeoutError, RuntimeError):
            with contextlib.suppress(Exception):
                await ws.close()

    return app


def route_table(app: FastAPI) -> set[tuple[str, str]]:
    """(method, path) of every route, included routers flattened — for the route-list test."""
    table: set[tuple[str, str]] = set()

    def walk(routes: Any) -> None:
        for route in routes:
            if hasattr(route, "original_router"):
                walk(route.original_router.routes)
            elif route.path.startswith("/v1"):
                methods = getattr(route, "methods", None)
                table.update({(m, route.path) for m in methods - {"HEAD"}} if methods else {("WEBSOCKET", route.path)})
    walk(app.routes)
    return table


def _summary(text: str) -> dict[str, Any]:
    head = json.loads(text)
    return {"lane": head["lane"], "seq": head["seq"], "kind": head["body"]["kind"], "source_mode": head["source_mode"]}
