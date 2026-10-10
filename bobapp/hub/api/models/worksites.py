"""Worksite profiles and inspection commands (plan §4): requirements are inspection policy, not
visual filters; saved revisions apply only at the next explicitly started inspection."""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from bobapp.contracts import Requirement, SourceMode, WorksiteProfile


class SaveProfileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=0)    # the revision the editor started from (0 = new worksite)
    name: str = Field(min_length=1, max_length=200)
    requirements: dict[Requirement, bool]   # all five; unchecked = "not required", never "compliant"


class WorksiteView(BaseModel):
    worksite_id: str
    latest: WorksiteProfile
    active_inspection_id: Optional[UUID] = None    # as last synced from the rover
    active_revision: Optional[int] = None
    pending: bool        # latest saved revision is not the one the active inspection is bound to
    note: str = "saved revisions apply at the next explicitly started inspection"


class WorksiteList(BaseModel):
    items: list[WorksiteView]


class StartInspectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    worksite_id: str
    revision: Optional[int] = None          # default: latest saved revision
    source_mode: Optional[SourceMode] = None  # default: the running vision.server's declared mode
    requested_by: Optional[str] = None
    inspection_id: Optional[UUID] = None
