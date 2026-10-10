"""Track points (plan §7): downsampled valid phone-camera poses from every admitted phone message.

Validity is decided by vision.association.associate(), exactly as for C2: current session, tracking
normal, not stale, yaw defined. An invalid pose ends the segment; the next valid pose starts a new one,
so a path is never drawn across a gap. A new session starts a new map (segment 0).
"""
from __future__ import annotations

import math
from typing import Optional
from uuid import UUID

from bobapp.contracts import TrackPointBody
from vision.association import Association
from vision.schema import FramePacket, PosePacket


class TrackSampler:
    """Emit when moved >= min_move_m, turned >= min_turn_deg or max_interval_s passed (iPhone clock)."""

    def __init__(self, min_move_m: float, min_turn_deg: float, max_interval_s: float) -> None:
        self.min_move_m, self.min_turn_rad = min_move_m, math.radians(min_turn_deg)
        self.max_interval_ns = int(max_interval_s * 1e9)
        self.session: Optional[UUID] = None
        self.segment, self.open, self.last = 0, False, None

    def offer(self, msg: FramePacket | PosePacket, association: Association) -> Optional[TrackPointBody]:
        if msg.session_id != self.session:
            self.session, self.segment, self.open, self.last = msg.session_id, 0, False, None
        if not association.pose_valid:
            if self.open:
                self.segment, self.open, self.last = self.segment + 1, False, None
            return None
        pose, ts = association.pose, msg.iphone_frame_ts_ns
        if self.last is not None:
            last_pose, last_ts = self.last
            moved = math.hypot(pose.x_m - last_pose.x_m, pose.z_m - last_pose.z_m)
            turned = abs((pose.yaw_rad - last_pose.yaw_rad + math.pi) % (2 * math.pi) - math.pi)
            if moved < self.min_move_m and turned < self.min_turn_rad and ts - last_ts < self.max_interval_ns:
                return None
        self.open, self.last = True, (pose, ts)
        return TrackPointBody(kind="track_point", session_id=msg.session_id, segment=self.segment,
                              seq_id=msg.seq_id, iphone_ts_ns=ts,
                              packet="frame" if isinstance(msg, FramePacket) else "pose", pose=pose)
