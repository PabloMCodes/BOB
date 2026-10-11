"""Twin routes (plan §6–7): `/v1/twin/sessions`, `/track`, `/pins`, and a debug `map.svg`."""
from __future__ import annotations

from typing import Callable
from uuid import UUID

from fastapi import APIRouter
from fastapi.responses import Response

from ..replica import Replica
from ..twin import data, svg
from . import views
from .models import Pins, SessionList, Track, WorkspaceName


def twin_router(replica: Callable[[str], Replica], stale_after_s: float, dependencies: list) -> APIRouter:
    router = APIRouter(dependencies=dependencies)

    @router.get("/v1/twin/sessions", response_model=SessionList)
    def sessions(workspace: WorkspaceName = "rover") -> SessionList:
        return data.sessions(replica(workspace), workspace, stale_after_s)

    @router.get("/v1/twin/sessions/{session_id}/track", response_model=Track)
    def track(session_id: UUID, workspace: WorkspaceName = "rover") -> Track:
        return data.track(replica(workspace), workspace, session_id)

    @router.get("/v1/twin/sessions/{session_id}/pins", response_model=Pins)
    def pins(session_id: UUID, workspace: WorkspaceName = "rover") -> Pins:
        return data.pins(replica(workspace), workspace, session_id, stale_after_s)

    @router.get("/v1/twin/sessions/{session_id}/map.svg", response_class=Response)
    def map_svg(session_id: UUID, workspace: WorkspaceName = "rover") -> Response:
        r = replica(workspace)
        status = views.status(r, workspace, stale_after_s)
        mode = status.source_mode.value if status.source_mode else (
            "SAMPLE" if workspace == "sample" else "no run publishing")
        body = svg.render(data.track(r, workspace, session_id), data.pins(r, workspace, session_id, stale_after_s),
                          mode, status.link["state"])
        return Response(body, media_type="image/svg+xml")

    return router
