"""Control lane bodies: evidence metadata, profile revisions, inspection lifecycle, gaps, notices.
Incident transitions live in `incident`."""
from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import Field, model_validator

from vision.schema import ImageSize, Pose, PoseInvalidReason

from .common import Lane, NonNegInt, PosInt, Sha256, _Model
from .profile import WorksiteProfile

class EvidenceReason(str, Enum):
    DERIVED_BOX = "derived_box"
    SCENE_FINDING = "scene_finding"
    INCIDENT = "incident"


class EvidenceBody(_Model):
    """Metadata of one clean upright full-resolution JPEG blob, tied to its exact source frame."""
    kind: Literal["evidence"]
    sha256: Sha256                                   # of the JPEG bytes (blob address)
    size_bytes: PosInt
    media_type: Literal["image/jpeg"]
    image_pixels_sha256: Sha256                      # of the decoded upright pixels (= observation's)
    event_id: UUID
    session_id: UUID
    seq_id: NonNegInt
    iphone_frame_ts_ns: NonNegInt
    model_id: str = Field(min_length=1)
    image_size: ImageSize
    reason: EvidenceReason
    rules: list[str]                                 # rules / zones that triggered the capture
    pose: Optional[Pose] = None
    pose_valid: bool
    pose_invalid_reason: Optional[PoseInvalidReason] = None

    @model_validator(mode="after")
    def _pose(self) -> EvidenceBody:
        if self.pose_valid != (self.pose is not None) or self.pose_valid == (self.pose_invalid_reason is not None):
            raise ValueError("pose_valid=true needs a pose and no reason; false needs a reason and no pose")
        return self


class ProfileRevisionBody(_Model):
    kind: Literal["profile_revision"]
    profile: WorksiteProfile


class InspectionStartedBody(_Model):
    kind: Literal["inspection_started"]
    inspection_id: UUID
    worksite_id: str = Field(min_length=1)
    profile_revision: PosInt
    profile_sha256: Sha256
    requested_by: Optional[str] = None


class InspectionEndReason(str, Enum):
    OPERATOR = "operator"
    SOURCE_STOPPED = "source_stopped"     # the edge restarted: never resumed from memory


class InspectionEndedBody(_Model):
    kind: Literal["inspection_ended"]
    inspection_id: UUID
    reason: InspectionEndReason


class GapReason(str, Enum):
    PRUNED_RETENTION = "pruned_retention"
    PRUNED_DISK_PRESSURE = "pruned_disk_pressure"


class GapBody(_Model):
    """Records first_seq..last_seq of `lane` were removed on the rover before the hub had them."""
    kind: Literal["gap"]
    lane: Lane
    first_seq: PosInt
    last_seq: PosInt
    reason: GapReason

    @model_validator(mode="after")
    def _order(self) -> GapBody:
        if self.first_seq > self.last_seq:
            raise ValueError("gap first_seq must be <= last_seq")
        return self


class NoticeBody(_Model):
    """Capability / health notices: 'Required — assessment unavailable', writer drops, low rate..."""
    kind: Literal["notice"]
    code: str = Field(min_length=1, pattern=r"^[a-z_]+$")
    message: str = Field(min_length=1)
    details: dict[str, Any] = {}
