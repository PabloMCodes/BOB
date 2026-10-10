"""Pose model and derivation from ARKit's camera.transform."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from pydantic import Field

from .common import _Model


class Pose(_Model):
    """Camera position in the ARKit world frame (right-handed, +Y up, origin = session start).

    yaw_rad: rotation about world +Y; 0 = facing the session's initial -Z, positive = turning left.
    """

    x_m: float
    y_m: float
    z_m: float
    yaw_rad: float = Field(ge=-math.pi, le=math.pi)


def transform_matrix(values: Any) -> np.ndarray:
    """16 column-major floats (ARKit simd_float4x4 order) -> 4x4 row-major numpy matrix."""
    return np.asarray(values, dtype=np.float64).reshape(4, 4).T


def pose_from_transform(values: Any) -> Pose:
    """Derive position + yaw from ARKit's camera.transform.

    The camera looks along its own -Z axis, so forward = -(third column). Yaw is undefined
    when the camera points straight up or down; that raises ValueError.
    Note: this is the *phone camera* pose. T_rover_from_phone is applied later (out of scope).
    """
    m = transform_matrix(values)
    forward = -m[:3, 2]
    if math.hypot(forward[0], forward[2]) < 1e-2:
        raise ValueError("camera is pointing straight up/down; yaw is undefined")
    yaw = math.atan2(-forward[0], -forward[2])
    return Pose(x_m=float(m[0, 3]), y_m=float(m[1, 3]), z_m=float(m[2, 3]), yaw_rad=yaw)
