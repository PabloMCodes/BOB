"""C2 for the exact source ARFrame: its bundled pose, judged by vision.association (Step 7).

No latest-pose fallback or cross-session history. A newer session, a stream gap or degraded
tracking invalidates the pose but never suppresses the detection.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from uuid import uuid4

import numpy as np

from vision.association import Association, Associator
from vision.pipeline import FrameResult, Pipeline
from vision.ppe import Verdict, frame_verdict
from vision.schema import SCHEMA_VERSION, DetectionEvent

from .slot import ReceivedFrame
from .view import decode_upright


@dataclass(frozen=True)
class Detection:
    image: np.ndarray                  # upright, clean (no overlay) — what the model saw
    result: FrameResult
    event: DetectionEvent
    verdicts: dict[str, Verdict]       # one per active rule (vision.ppe.frame_verdict)


def detect_frame(frame: ReceivedFrame, pipeline: Pipeline, mount: str,
                 associator: Associator) -> Optional[Detection]:
    """The one Step 6 frame path, shared by the live server and tools/replay_detect.

    None if the JPEG doesn't decode (nothing to detect on; the frame is not silently given boxes).
    """
    image = decode_upright(frame, mount)
    if image is None:
        return None
    result = pipeline(image)
    association = associator.associate(frame.packet, frame.gap_ns)  # at processing time: sees a newer session
    event = detection_event(frame, result, pipeline.model_id, association)
    verdicts = {rule.name: frame_verdict(result.verdicts, rule.name) for rule in pipeline.rules}
    return Detection(image, result, event, verdicts)


def detection_event(frame: ReceivedFrame, result: FrameResult, model_id: str,
                    association: Association) -> DetectionEvent:
    packet = frame.packet
    return DetectionEvent(
        schema_version=SCHEMA_VERSION, msg_type="detection_event", event_id=uuid4(),
        session_id=packet.session_id, seq_id=packet.seq_id,
        iphone_frame_ts_ns=packet.iphone_frame_ts_ns, jetson_receive_ts_ns=frame.rx_ts_ns,
        inference_latency_ms=result.inference_ms, model_id=model_id, image_size=result.image_size,
        tracking_state=packet.tracking_state, boxes=result.boxes, pose=association.pose,
        pose_valid=association.pose_valid, pose_dt_ms=association.pose_dt_ms,
        pose_invalid_reason=association.reason,
    )
