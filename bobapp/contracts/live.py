"""Live state: latest wins, never backfilled, never stored as a record."""
from __future__ import annotations

from enum import Enum
from typing import Literal, Optional
from uuid import UUID

from pydantic import Field, model_validator

from vision.schema import ImageSize, Pose, PoseInvalidReason, StreamHealth

from .common import AppVersion, NonNegInt, RoverClock, Sha256, SourceMode, _Model
from .observation import RuleStatus

class PreviewRef(_Model):
    event_id: UUID
    session_id: UUID
    seq_id: NonNegInt
    image_size: ImageSize            # of the preview JPEG
    source_image_size: ImageSize     # boxes are in these (upright model-input) pixels
    sha256: Sha256


class LivePose(_Model):
    session_id: UUID
    seq_id: NonNegInt
    iphone_ts_ns: NonNegInt
    pose: Optional[Pose] = None
    pose_valid: bool
    pose_invalid_reason: Optional[PoseInvalidReason] = None

    @model_validator(mode="after")
    def _pose(self) -> LivePose:
        if self.pose_valid != (self.pose is not None) or self.pose_valid == (self.pose_invalid_reason is not None):
            raise ValueError("pose_valid=true needs a pose and no reason; false needs a reason and no pose")
        return self


class FeedAge(_Model):
    """Rover-clock age of the newest item; null with a reason when there has been none."""
    age_ms: Optional[float] = Field(default=None, ge=0)
    reason: Optional[str] = None

    @model_validator(mode="after")
    def _one(self) -> FeedAge:
        if (self.age_ms is None) == (self.reason is None):
            raise ValueError("feed age is a value or a reason, not both")
        return self


class Freshness(_Model):
    video: FeedAge         # last frame admitted from the phone
    results: FeedAge       # last processed frame (C2)
    pose: FeedAge          # last admitted pose/frame packet
    health: FeedAge        # last C3


class ProducerStatus(str, Enum):
    INTEGRATED = "integrated"
    PROTOTYPE = "prototype"
    NOT_INTEGRATED = "not_integrated"


class Producer(_Model):
    name: str = Field(min_length=1)
    status: ProducerStatus
    note: Optional[str] = None


class Capabilities(_Model):
    model_id: Optional[str] = None
    rules: list[RuleStatus]
    producers: list[Producer]


class EdgeStatus(_Model):
    """Writer fields are null when no vision.server run is publishing (unknown, not zero)."""
    store_bytes: NonNegInt
    disk_free_bytes: Optional[NonNegInt] = None
    writer_queued: Optional[NonNegInt] = None
    writer_dropped: Optional[NonNegInt] = None
    writer_errors: Optional[NonNegInt] = None
    last_error: Optional[str] = None


class LiveState(_Model):
    app_version: AppVersion
    msg_type: Literal["live_state"]
    edge_id: str = Field(min_length=1)
    store_epoch: UUID
    run_id: Optional[str] = None
    source_mode: Optional[SourceMode] = None        # null: no vision.server run is publishing
    rover: RoverClock
    preview: Optional[PreviewRef] = None
    pose: Optional[LivePose] = None
    health: Optional[StreamHealth] = None           # C3 verbatim
    freshness: Freshness
    capabilities: Capabilities
    active_inspection_id: Optional[UUID] = None
    edge: EdgeStatus
