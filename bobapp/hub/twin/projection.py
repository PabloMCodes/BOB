"""Session-local 2D projection (plan §7).

ARKit world: right-handed, +Y up, origin and initial facing at session start; yaw 0 faces the session's
initial -Z, positive yaw turns left. Map: east = x_m, north = -z_m, so map "up" is the direction the
phone faced at session start — not compass north. Height (y_m) is ignored. SVG (y down): svg_x = x_m,
svg_y = z_m (times a scale); the heading arrow is (-sin yaw, -cos yaw) in SVG axes.
"""
from __future__ import annotations

import math

from vision.schema import Pose

DESCRIPTION = {
    "frame": "session-local; origin and 'up' = where the phone camera was and faced at session start",
    "east_m": "x_m", "north_m": "-z_m", "svg": "svg_x = x_m * scale, svg_y = z_m * scale (y down)",
    "heading": "unit vector (-sin yaw, -cos yaw) in SVG axes; yaw 0 = up, positive yaw = turned left",
    "not_compass_north": True, "height_ignored": True,
}


def east_north(pose: Pose) -> tuple[float, float]:
    return pose.x_m, -pose.z_m


def svg_point(pose: Pose) -> tuple[float, float]:
    return pose.x_m, pose.z_m


def svg_heading(yaw_rad: float) -> tuple[float, float]:
    return -math.sin(yaw_rad), -math.cos(yaw_rad)
