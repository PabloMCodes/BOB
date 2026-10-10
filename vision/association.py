"""Step 7 — pose <-> detection association (AGENTS rules 4 and 5).

Each frame message carries the camera_transform of the same ARFrame as its image, so the pose of a
detection is exact (pose_dt_ms = 0): no buffer, no interpolation, never "the latest pose". What this
module decides is whether that pose may be trusted. Every input is from the phone stream itself (iPhone
clock), so the live server and the offline replay reach the same verdict for the same messages.

Rules, first match wins (the detection itself is always emitted):
  session_mismatch     the frame's session is not the newest one seen (new world origin, rule 5)
  stale                > timing.stale_ms since the previous message of the session, on the iPhone
                       clock (the stream broke right before this frame)
  tracking_not_normal  ARKit tracking is limited / not_available for this frame
  no_pose              yaw undefined (camera pointing straight up or down)

Each frame is judged alone: no look-ahead (that would delay every event past the Step 6 budget).
`dt_exceeded` is unused until poses come from a separate source (see README Step 7).
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Optional, Union
from uuid import UUID

from vision.schema import FramePacket, PoseInvalidReason, PosePacket, TrackingState
from vision.schema.pose import Pose, pose_from_transform

PhonePacket = Union[FramePacket, PosePacket]


@dataclass(frozen=True)
class Association:
    pose: Optional[Pose]
    pose_valid: bool
    pose_dt_ms: Optional[float]           # 0.0 when valid: the frame's own pose
    reason: Optional[PoseInvalidReason]


def associate(packet: FramePacket, gap_ns: Optional[int], current_session: Optional[UUID],
              stale_ns: int) -> Association:
    """Pure rule evaluation. gap_ns: iPhone-clock time since the session's previous message (None for
    the first message of a session)."""
    reason: Optional[PoseInvalidReason] = None
    pose: Optional[Pose] = None
    if packet.session_id != current_session:
        reason = PoseInvalidReason.SESSION_MISMATCH
    elif gap_ns is not None and gap_ns > stale_ns:
        reason = PoseInvalidReason.STALE
    elif packet.tracking_state != TrackingState.NORMAL:  # str enum: also matches a plain "normal"
        reason = PoseInvalidReason.TRACKING_NOT_NORMAL
    else:
        try:
            pose = pose_from_transform(packet.camera_transform)
        except ValueError:
            reason = PoseInvalidReason.NO_POSE
    if pose is None:
        return Association(None, False, None, reason)
    return Association(pose, True, 0.0, None)


class Associator:
    """Follows the phone stream on the iPhone clock. Thread-safe: `observe` runs where messages arrive,
    `associate` where frames are processed (possibly after a newer session has started).

    Feed it only messages the stream monitor kept (in order, not from a retired session).
    """

    def __init__(self, stale_ms: float) -> None:
        self.stale_ns = int(stale_ms * 1_000_000)
        self._lock = threading.Lock()
        self._session: Optional[UUID] = None
        self._last_ts: Optional[int] = None

    @property
    def current_session(self) -> Optional[UUID]:
        with self._lock:
            return self._session

    def observe(self, msg: PhonePacket) -> Optional[int]:
        """Record a message; returns the iPhone-clock gap since the session's previous message."""
        with self._lock:
            if msg.session_id != self._session:
                self._session, self._last_ts = msg.session_id, None
            gap = None if self._last_ts is None else msg.iphone_frame_ts_ns - self._last_ts
            self._last_ts = msg.iphone_frame_ts_ns
            return gap

    def associate(self, packet: FramePacket, gap_ns: Optional[int]) -> Association:
        return associate(packet, gap_ns, self.current_session, self.stale_ns)
