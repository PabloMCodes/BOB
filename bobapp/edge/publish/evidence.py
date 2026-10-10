"""Evidence capture policy (D6): the clean full-resolution upright frame of a frame with a derived box
or a restricted-zone finding, at most one per `min_interval_s` per rule (or zone) per session.

The decision is cheap and runs on the frame consumer; encoding and storage run on the writer thread.
Rate limiting uses the iPhone clock of the source frame, so a replay keeps the same evidence frames.
"""
from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

import cv2

from bobapp.contracts import EvidenceBody, EvidenceReason


def evidence_triggers(detection: Any, scene: Optional[dict]) -> tuple[Optional[EvidenceReason], list[str]]:
    """(reason, keys): rule names with a derived box, `zone:<id>` with a possible person in the zone."""
    keys = sorted({v.rule for v in detection.result.verdicts if v.violation is not None})
    reason = EvidenceReason.DERIVED_BOX if keys else None
    if scene is not None:
        assessment = scene["assessment"]
        if any(p["status"] == "possible_person_in_zone" for p in assessment["people"]):
            keys.append(f"zone:{assessment['region']['zone_id']}")
            reason = reason or EvidenceReason.SCENE_FINDING
    return reason, keys


class EvidenceGate:
    """Per (session, key) rate limit on the source frame's iPhone clock. Single-threaded use."""

    def __init__(self, min_interval_s: float) -> None:
        self.min_interval_ns = int(min_interval_s * 1e9)
        self.last: dict[tuple[UUID, str], int] = {}

    def admit(self, session_id: UUID, keys: list[str], ts_ns: int) -> list[str]:
        passed = [k for k in keys if ts_ns - self.last.get((session_id, k), -self.min_interval_ns) >= self.min_interval_ns]
        for k in passed:
            self.last[(session_id, k)] = ts_ns
        return passed


def encode_jpeg(image: Any, quality: int) -> bytes:
    ok, buf = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, int(quality)])
    if not ok:
        raise OSError("could not encode JPEG")
    return buf.tobytes()


def evidence_body(detection: Any, sha256: str, size: int, pixels_sha256: str, reason: EvidenceReason,
                  keys: list[str]) -> EvidenceBody:
    event = detection.event
    return EvidenceBody(kind="evidence", sha256=sha256, size_bytes=size, media_type="image/jpeg",
                        image_pixels_sha256=pixels_sha256, event_id=event.event_id, session_id=event.session_id,
                        seq_id=event.seq_id, iphone_frame_ts_ns=event.iphone_frame_ts_ns, model_id=event.model_id,
                        image_size=event.image_size, reason=reason, rules=keys,
                        pose=event.pose if event.pose_valid else None, pose_valid=event.pose_valid,
                        pose_invalid_reason=event.pose_invalid_reason)
