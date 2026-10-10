"""Shared base model, strict field types, enums, and errors used by every message."""

from __future__ import annotations

from enum import Enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, Strict

SCHEMA_VERSION = 1

# Strict ints: reject "42" and 42.0 so Swift encoding mistakes surface in tests.
NonNegInt = Annotated[int, Strict(), Field(ge=0)]
PosInt = Annotated[int, Strict(), Field(gt=0)]
TimestampNs = NonNegInt


class WireError(ValueError):
    """Raised for any malformed message: bad framing, invalid header, or payload mismatch."""


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class TrackingState(str, Enum):
    """Mirrors ARCamera.TrackingState."""

    NORMAL = "normal"
    LIMITED = "limited"
    NOT_AVAILABLE = "not_available"


class TrackingReason(str, Enum):
    """Mirrors ARCamera.TrackingState.Reason. Present only when tracking_state == limited."""

    INITIALIZING = "initializing"
    EXCESSIVE_MOTION = "excessive_motion"
    INSUFFICIENT_FEATURES = "insufficient_features"
    RELOCALIZING = "relocalizing"


class DeviceOrientation(str, Enum):
    """Mirrors UIDeviceOrientation. Python decides how to rotate the sensor image upright."""

    UNKNOWN = "unknown"
    PORTRAIT = "portrait"
    PORTRAIT_UPSIDE_DOWN = "portrait_upside_down"
    LANDSCAPE_LEFT = "landscape_left"
    LANDSCAPE_RIGHT = "landscape_right"
    FACE_UP = "face_up"
    FACE_DOWN = "face_down"


class PoseInvalidReason(str, Enum):
    TRACKING_NOT_NORMAL = "tracking_not_normal"
    STALE = "stale"
    SESSION_MISMATCH = "session_mismatch"
    DT_EXCEEDED = "dt_exceeded"
    NO_POSE = "no_pose"
