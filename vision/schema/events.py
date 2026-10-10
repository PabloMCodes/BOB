"""C2/C3 — vision -> consumer messages: `detection_event` and `stream_health`.

Consumed by the safety supervisor and alerts branches; see integration.md §2.
"""

from __future__ import annotations

from typing import Annotated, Literal, Optional
from uuid import UUID

from pydantic import Field, Strict, field_validator, model_validator

from .common import (
    NonNegInt,
    PosInt,
    PoseInvalidReason,
    SchemaVersion,
    TimestampNs,
    TrackingState,
    _Model,
)
from .pose import Pose


class ImageSize(_Model):
    width: PosInt
    height: PosInt


class Box(_Model):
    """One box in pixels of the upright (rotated) image.

    source="model":   a raw YOLO detection; cls_id is the model's class index.
    source="derived": produced by a PPE rule (e.g. "no-safety-glasses" on a face's eye band);
                      cls_id is null and conf is the confidence of the subject it was derived from.
    """

    source: Literal["model", "derived"]
    cls_id: Optional[NonNegInt]
    cls_name: str = Field(min_length=1)
    conf: float = Field(ge=0.0, le=1.0)
    xyxy: tuple[float, float, float, float]

    @model_validator(mode="after")
    def _cls_id_matches_source(self) -> Box:
        if self.source == "model" and self.cls_id is None:
            raise ValueError("source='model' requires a cls_id")
        if self.source == "derived" and self.cls_id is not None:
            raise ValueError("source='derived' requires cls_id=null")
        return self

    @field_validator("xyxy")
    @classmethod
    def _ordered(cls, v: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
        x1, y1, x2, y2 = v
        if min(v) < 0:
            raise ValueError("xyxy coordinates must be >= 0")
        if not (x1 < x2 and y1 < y2):
            raise ValueError("xyxy must satisfy x1 < x2 and y1 < y2")
        return v


class DetectionEvent(_Model):
    """C2 — YOLO result for one source frame, tagged with the pose matched by timestamp.

    Consumers MUST check pose_valid before using pose; an invalid event may still carry the
    nearest pose for debugging. Boxes only: hazard decisions belong to the alerts/safety branch.
    """

    schema_version: SchemaVersion
    msg_type: Literal["detection_event"]
    event_id: UUID
    session_id: UUID
    seq_id: NonNegInt
    iphone_frame_ts_ns: TimestampNs
    jetson_receive_ts_ns: TimestampNs  # receiver clock (Mac today, Jetson later); latency only
    inference_latency_ms: float = Field(ge=0)
    model_id: str = Field(min_length=1)
    image_size: ImageSize
    tracking_state: TrackingState
    boxes: list[Box]
    pose: Optional[Pose] = None
    pose_valid: Annotated[bool, Strict()]
    pose_dt_ms: Optional[float] = Field(default=None, ge=0)
    pose_invalid_reason: Optional[PoseInvalidReason] = None

    @model_validator(mode="after")
    def _consistent(self) -> DetectionEvent:
        for box in self.boxes:
            _, _, x2, y2 = box.xyxy
            if x2 > self.image_size.width or y2 > self.image_size.height:
                raise ValueError(f"box {box.xyxy} lies outside image_size")
        if (self.pose is None) != (self.pose_dt_ms is None):
            raise ValueError("pose_dt_ms must be set exactly when pose is set")
        if self.pose_valid:
            if self.pose is None:
                raise ValueError("pose_valid=true requires a pose")
            if self.pose_invalid_reason is not None:
                raise ValueError("pose_valid=true requires pose_invalid_reason=null")
        elif self.pose_invalid_reason is None:
            raise ValueError("pose_valid=false requires a pose_invalid_reason")
        return self


class StreamHealth(_Model):
    """C3 — iPhone stream health as seen by the vision server. Consumers stop on stale=true."""

    schema_version: SchemaVersion
    msg_type: Literal["stream_health"]
    emitted_ts_ns: TimestampNs  # receiver clock
    session_id: Optional[UUID] = None
    stale: Annotated[bool, Strict()]
    last_seq_id: Optional[NonNegInt] = None
    last_rx_ts_ns: Optional[TimestampNs] = None
    dropped_count: NonNegInt
    tracking_state: Optional[TrackingState] = None

    @model_validator(mode="after")
    def _no_session_is_stale(self) -> StreamHealth:
        if self.session_id is None and not self.stale:
            raise ValueError("stale must be true when no session has been received")
        return self
