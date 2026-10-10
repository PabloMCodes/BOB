"""Worksite profile authoring and inspection start/end, forwarded to the rover (plan §4, Step 7).

Profiles are edited on the hub, also while the rover is offline. Starting an inspection sends the full
revision to the rover, which re-verifies its hash and binds it atomically; it fails honestly (503) when
the rover cannot be reached and passes the rover's 409 through when another inspection is active.
Reconnecting a browser, the phone or the rover link never starts an inspection. Starting one is an
application action: it does not arm or move anything.
"""
from __future__ import annotations

from typing import Any, Callable, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from bobapp.contracts import Record, WorksiteProfile

from ..replica import Replica, RevisionConflict
from ..sync.http import http_post_json
from . import views
from .models import SaveProfileRequest, StartInspectionRequest, WorksiteList, WorksiteView


def worksite_router(replica: Callable[[], Replica], edge: Optional[tuple[str, Optional[str]]],
                    dependencies: list) -> APIRouter:
    router = APIRouter(dependencies=dependencies)

    def view(r: Replica, worksite_id: str) -> WorksiteView:
        latest = r.profile_revision(worksite_id)
        if latest is None:
            raise HTTPException(404, f"no worksite {worksite_id!r}")
        active = next((i for i in views.inspections(r, "rover").items
                       if i.ended is None and i.worksite_id == worksite_id), None)
        return WorksiteView(worksite_id=worksite_id, latest=latest,
                            active_inspection_id=active.inspection_id if active else None,
                            active_revision=active.profile_revision if active else None,
                            pending=active is not None and active.profile_revision != latest.revision)

    @router.get("/v1/worksites", response_model=WorksiteList)
    def list_worksites() -> WorksiteList:
        r = replica()
        return WorksiteList(items=[view(r, w) for w in r.worksite_ids()])

    @router.get("/v1/worksites/{worksite_id}", response_model=WorksiteView)
    def get_worksite(worksite_id: str) -> WorksiteView:
        return view(replica(), worksite_id)

    @router.put("/v1/worksites/{worksite_id}", response_model=WorksiteView)
    def save_worksite(worksite_id: str, body: SaveProfileRequest) -> Any:
        r = replica()
        try:
            r.save_profile(worksite_id, body.expected_revision, body.name, dict(body.requirements))
        except RevisionConflict as exc:
            return JSONResponse({"detail": str(exc), "current_revision": exc.current}, status_code=409)
        except ValueError as exc:
            raise HTTPException(422, str(exc))
        return view(r, worksite_id)

    @router.get("/v1/worksites/{worksite_id}/revisions/{revision}", response_model=WorksiteProfile)
    def get_revision(worksite_id: str, revision: int) -> WorksiteProfile:
        profile = replica().profile_revision(worksite_id, revision)
        if profile is None:
            raise HTTPException(404, f"no revision {revision} of {worksite_id!r}")
        return profile

    def forward(path: str, body: dict) -> Any:
        if edge is None:
            raise HTTPException(503, "no rover edge configured")
        try:
            status, payload = http_post_json(edge[0] + path, edge[1], body)
        except OSError as exc:
            raise HTTPException(503, f"rover unreachable ({type(exc).__name__}); nothing was started or ended")
        if status >= 400:
            raise HTTPException(status, payload.get("detail", payload))
        return payload

    @router.post("/v1/inspections", response_model=Record, status_code=201)
    def start_inspection(body: StartInspectionRequest) -> Any:
        profile = replica().profile_revision(body.worksite_id, body.revision)
        if profile is None:
            raise HTTPException(404, f"no saved revision {body.revision or 'latest'} of {body.worksite_id!r}")
        payload = {"profile": profile.model_dump(mode="json"), "requested_by": body.requested_by,
                   "source_mode": body.source_mode.value if body.source_mode else None,
                   "inspection_id": str(body.inspection_id) if body.inspection_id else None}
        return forward("/v1/inspections", payload)

    @router.post("/v1/inspections/{inspection_id}/end", response_model=Record)
    def end_inspection(inspection_id: UUID) -> Any:
        return forward(f"/v1/inspections/{inspection_id}/end", {})

    return router
