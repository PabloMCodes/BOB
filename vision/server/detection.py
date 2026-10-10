"""C2 for the exact source ARFrame: its bundled pose has zero timestamp difference.

No latest-pose fallback or cross-session history. A later session or stale stream invalidates
the pose but never suppresses the detection. Standalone PosePackets remain health inputs.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from uuid import UUID, uuid4

import numpy as np

from vision.pipeline import FrameResult, Pipeline
from vision.ppe import Verdict, frame_verdict
from vision.schema import SCHEMA_VERSION, DetectionEvent
from vision.schema.pose import pose_from_transform

from .slot import ReceivedFrame
from .view import decode_upright


@dataclass(frozen=True)
class Detection:
    image: np.ndarray                  # upright, clean (no overlay) — what the model saw
    result: FrameResult
    event: DetectionEvent
    verdicts: dict[str, Verdict]       # one per active rule (vision.ppe.frame_verdict)


def detect_frame(frame: ReceivedFrame, pipeline: Pipeline, mount: str,
                 current_session: UUID | None, stale: bool) -> Optional[Detection]:
    """The one Step 6 frame path, shared by the live server and tools/replay_detect.

    None if the JPEG doesn't decode (nothing to detect on; the frame is not silently given boxes).
    """
    image = decode_upright(frame, mount)
    if image is None:
        return None
    result = pipeline(image)
    event = detection_event(frame, result, pipeline.model_id, current_session, stale)
    verdicts = {rule.name: frame_verdict(result.verdicts, rule.name) for rule in pipeline.rules}
    return Detection(image, result, event, verdicts)


def detection_event(frame: ReceivedFrame, result: FrameResult, model_id: str,
                    current_session: UUID | None, stale: bool) -> DetectionEvent:
    packet = frame.packet
    reason, pose = None, None
    if packet.session_id != current_session:
        reason = "session_mismatch"
    elif stale:
        reason = "stale"
    elif packet.tracking_state != "normal":
        reason = "tracking_not_normal"
    else:
        try:
            pose = pose_from_transform(packet.camera_transform)
        except ValueError:
            reason = "no_pose"  # vertical camera: yaw is undefined
    return DetectionEvent(
        schema_version=SCHEMA_VERSION, msg_type="detection_event", event_id=uuid4(),
        session_id=packet.session_id, seq_id=packet.seq_id,
        iphone_frame_ts_ns=packet.iphone_frame_ts_ns, jetson_receive_ts_ns=frame.rx_ts_ns,
        inference_latency_ms=result.inference_ms, model_id=model_id, image_size=result.image_size,
        tracking_state=packet.tracking_state, boxes=result.boxes, pose=pose,
        pose_valid=pose is not None, pose_dt_ms=0.0 if pose is not None else None,
        pose_invalid_reason=reason,
    )
