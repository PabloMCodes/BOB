"""Debug view: received frame rotated upright + stream stats overlay (Step 6 adds the boxes)."""

from __future__ import annotations

from typing import Optional

import cv2
import numpy as np

from vision.orientation import to_upright

from .monitor import StreamStats
from .slot import ReceivedFrame


def _fmt(v: Optional[float]) -> str:
    return "-" if v is None else f"{v:.0f}"


def stats_lines(s: StreamStats) -> list[str]:
    session = str(s.session_id)[:8] if s.session_id else "-"
    return [
        f"{'STALE' if s.stale else 'live'}  conn {s.connections}  session {session}  tracking {s.tracking_state or '-'}",
        f"frames {s.frame_hz:.1f} Hz  poses {s.pose_hz:.1f} Hz  ({s.frames} / {s.poses})",
        f"drops: phone {s.seq_gaps}  server {s.slot_drops}  late {s.out_of_order + s.retired_drops}  bad {s.decode_errors}",
        f"added latency p50/p95 {_fmt(s.added_latency_p50_ms)}/{_fmt(s.added_latency_p95_ms)} ms"
        f"  mac {_fmt(s.process_p50_ms)}/{_fmt(s.process_p95_ms)} ms",
    ]


def upright_view(frame: ReceivedFrame, mount: str, lines: list[str]) -> Optional[np.ndarray]:
    """Decode the JPEG, rotate sensor -> upright, draw `lines`. None if the JPEG doesn't decode."""
    image = cv2.imdecode(np.frombuffer(frame.jpeg, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        return None
    image = to_upright(image, frame.packet.image.device_orientation, mount)
    scale = max(image.shape[0] / 1000, 0.6)
    for i, line in enumerate(lines):
        y = int((30 + 32 * i) * scale)
        cv2.putText(image, line, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7 * scale, (0, 0, 0), int(4 * scale))
        cv2.putText(image, line, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7 * scale, (255, 255, 255), int(2 * scale))
    return image
