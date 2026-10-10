"""Track lane: downsampled valid phone-camera poses (plan §7)."""
from __future__ import annotations

from typing import Literal
from uuid import UUID

from vision.schema import Pose

from .common import NonNegInt, _Model

class TrackPointBody(_Model):
    """Valid phone-camera pose (never the rover's or a person's position). A new `segment` starts
    after any invalid pose; segments are never joined across a gap."""
    kind: Literal["track_point"]
    session_id: UUID
    segment: NonNegInt
    seq_id: NonNegInt
    iphone_ts_ns: NonNegInt
    packet: Literal["frame", "pose"]
    pose: Pose
