"""GET /v1/assessments: per-frame worksite assessments under the inspection's bound profile revision."""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from pydantic import BaseModel

from bobapp.contracts import Delivery, FrameAssessment, SourceMode
from vision.schema import Pose, PoseInvalidReason

from .common import CLOCK_DOMAINS, WorkspaceName


class AssessmentItem(BaseModel):
    cursor: int
    delivery: Delivery
    source_mode: SourceMode
    event_id: UUID
    session_id: UUID
    seq_id: int
    iphone_frame_ts_ns: int
    pose_valid: bool
    pose: Optional[Pose] = None
    pose_invalid_reason: Optional[PoseInvalidReason] = None
    assessment: FrameAssessment


class AssessmentPage(BaseModel):
    workspace: WorkspaceName
    items: list[AssessmentItem]
    next_after: int
    clock_domains: dict[str, str] = CLOCK_DOMAINS
