"""C1 — iPhone -> vision messages: `frame` (pose + JPEG) and `pose` (pose only).

The Swift mirror in ios/ must match these field names and rules exactly.
"""

from __future__ import annotations

from typing import Annotated, Literal, Optional
from uuid import UUID

import numpy as np
from pydantic import Field, Strict, field_validator, model_validator

from .common import (
    NonNegInt,
    PosInt,
    SchemaVersion,
    TimestampNs,
    TrackingReason,
    TrackingState,
    DeviceOrientation,
    _Model,
)
from .pose import Pose, pose_from_transform, transform_matrix

MAX_PAYLOAD_BYTES = 8 * 1024 * 1024


class Intrinsics(_Model):
    """ARCamera.intrinsics, relative to ARCamera.imageResolution (ref_width x ref_height).

    The JPEG is downscaled, so consumers must scale by image.width / ref_width.
    """

    fx: float = Field(gt=0)
    fy: float = Field(gt=0)
    cx: float = Field(ge=0)
    cy: float = Field(ge=0)
    ref_width: PosInt
    ref_height: PosInt

    @model_validator(mode="after")
    def _principal_point_inside(self) -> Intrinsics:
        if self.cx > self.ref_width or self.cy > self.ref_height:
            raise ValueError("principal point cx/cy must lie inside ref_width x ref_height")
        return self


class ImageInfo(_Model):
    """Describes the JPEG payload that follows the header. Pixels are in sensor orientation."""

    width: PosInt
    height: PosInt
    encoding: Literal["jpeg"]
    device_orientation: DeviceOrientation
    byte_length: Annotated[int, Strict(), Field(gt=0, le=MAX_PAYLOAD_BYTES)]


class _PhonePacket(_Model):
    schema_version: SchemaVersion
    session_id: UUID
    seq_id: NonNegInt
    iphone_frame_ts_ns: TimestampNs
    tracking_state: TrackingState
    tracking_reason: Optional[TrackingReason] = None
    camera_transform: Annotated[tuple[float, ...], Field(min_length=16, max_length=16)]

    @field_validator("camera_transform")
    @classmethod
    def _rigid_column_major(cls, v: tuple[float, ...]) -> tuple[float, ...]:
        m = transform_matrix(v)
        if not np.allclose(m[3], [0.0, 0.0, 0.0, 1.0], atol=1e-4):
            raise ValueError(
                "camera_transform bottom row must be [0,0,0,1]; "
                "send simd_float4x4 in column-major order (columns 0..3, translation last)"
            )
        rot = m[:3, :3]
        if not np.allclose(rot @ rot.T, np.eye(3), atol=1e-3):
            raise ValueError("camera_transform rotation part is not orthonormal")
        return v

    @model_validator(mode="after")
    def _reason_matches_state(self) -> _PhonePacket:
        limited = self.tracking_state is TrackingState.LIMITED
        if limited and self.tracking_reason is None:
            raise ValueError("tracking_reason is required when tracking_state is 'limited'")
        if not limited and self.tracking_reason is not None:
            raise ValueError("tracking_reason must be null unless tracking_state is 'limited'")
        return self

    @property
    def pose(self) -> Pose:
        return pose_from_transform(self.camera_transform)


class FramePacket(_PhonePacket):
    """One ARFrame: pose + tracking + a JPEG payload. Sent at ~10-15 Hz."""

    msg_type: Literal["frame"]
    image: ImageInfo
    intrinsics: Optional[Intrinsics] = None


class PosePacket(_PhonePacket):
    """Pose-only ARFrame (no image). Sent at ~20 Hz so pose history survives dropped frames."""

    msg_type: Literal["pose"]
