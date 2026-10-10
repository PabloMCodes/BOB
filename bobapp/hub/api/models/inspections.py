"""GET /v1/inspections: each inspection with its start (and end, once synced) records."""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from pydantic import BaseModel

from bobapp.contracts import SourceMode

from .common import CLOCK_DOMAINS, Item, WorkspaceName


class InspectionItem(BaseModel):
    inspection_id: UUID
    worksite_id: str
    profile_revision: int
    profile_sha256: str
    source_mode: SourceMode
    requested_by: Optional[str] = None
    started: Item
    ended: Optional[Item] = None    # null while active (or its end has not synced yet)


class InspectionPage(BaseModel):
    workspace: WorkspaceName
    items: list[InspectionItem]
    clock_domains: dict[str, str] = CLOCK_DOMAINS
