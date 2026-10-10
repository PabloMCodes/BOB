"""GET /v1/status: link state, last known live state, lanes, gaps, evidence, workspaces."""
from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel

from bobapp.contracts import LiveState, SourceMode

from .common import CLOCK_DOMAINS, WorkspaceName


class LaneStatus(BaseModel):
    records: int
    committed_seq: int
    behind: Optional[int] = None    # null when not connected (unknown)


class WorkspaceInfo(BaseModel):
    edge_id: str
    store_epoch: UUID
    archived: bool


class StatusResponse(BaseModel):
    workspace: WorkspaceName
    link: dict[str, Any]            # state CONNECTED | CATCHING_UP | DISCONNECTED | NEW_STORE, hub clock times
    live_is_current: bool           # false: `live` is the last known state, not the rover's current one
    live: Optional[LiveState] = None
    live_received_wall_ns: Optional[int] = None
    live_received_age_ms: Optional[float] = None
    source_mode: Optional[SourceMode] = None
    lanes: dict[str, LaneStatus]
    gaps: list[dict[str, Any]]
    evidence: dict[str, int]
    workspaces: list[WorkspaceInfo]
    clock_domains: dict[str, str] = CLOCK_DOMAINS
