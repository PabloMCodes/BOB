"""Per-frame inputs of the incident policy (plan §8.2).

PPE values come from the frame's worksite assessment, so only requirements that are checked *and*
assessable produce incidents: not_detected = positive, detected = negative, not_assessed = neutral;
not_required / assessment_unavailable produce nothing. A restricted zone (C7) is positive when the
region is recognized and someone is possibly inside it, negative when recognized with nobody found
("not observed", never "zone clear"), neutral when the region is unverified. No inspection, no input.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from bobapp.contracts import AssessmentStatus, FrameAssessment, Hazard
from vision.schema import DetectionEvent, Pose, PoseInvalidReason


class FrameClass(str, Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"


@dataclass(frozen=True)
class Subject:
    """What an episode is about within one inspection and session."""
    hazard: Hazard
    rule: Optional[str] = None
    zone_id: Optional[str] = None
    zone_profile_sha256: Optional[str] = None


@dataclass(frozen=True)
class FrameInput:
    event_id: UUID
    session_id: UUID
    ts_ns: int                                   # iPhone clock of the source frame
    inspection_id: Optional[UUID]
    profile_revision: Optional[int]
    retired: bool                                # a frame of an older ARKit session
    pose: Optional[Pose]
    unlocalized_reason: Optional[PoseInvalidReason]
    values: dict[Subject, FrameClass] = field(default_factory=dict)
    confidence: dict[Subject, float] = field(default_factory=dict)   # of positives, to pick the best frame


PPE_CLASS = {AssessmentStatus.NOT_DETECTED: FrameClass.POSITIVE, AssessmentStatus.DETECTED: FrameClass.NEGATIVE,
             AssessmentStatus.NOT_ASSESSED: FrameClass.NEUTRAL}
RULE_OF = {"eyewear": "glasses", "helmet": "helmet", "gloves": "gloves", "vest": "vest", "boots": "boots"}


def frame_input(event: DetectionEvent, assessment: Optional[FrameAssessment], scene: Optional[dict[str, Any]],
                violation_conf: Optional[dict[str, float]] = None) -> FrameInput:
    values: dict[Subject, FrameClass] = {}
    confidence: dict[Subject, float] = {}
    retired = event.pose_invalid_reason == PoseInvalidReason.SESSION_MISMATCH
    if assessment is not None and not retired:
        for req in assessment.requirements:
            if req.status in PPE_CLASS:
                subject = Subject(Hazard.PPE, rule=RULE_OF[req.requirement])
                values[subject] = PPE_CLASS[req.status]
                confidence[subject] = (violation_conf or {}).get(subject.rule, 0.0)
        if scene is not None:
            region = scene["assessment"]["region"]
            subject = Subject(Hazard.RESTRICTED_ZONE, zone_id=region["zone_id"], zone_profile_sha256=scene["profile_sha256"])
            if region["status"] != "recognized":
                values[subject] = FrameClass.NEUTRAL
            elif any(p["status"] == "possible_person_in_zone" for p in scene["assessment"]["people"]):
                values[subject] = FrameClass.POSITIVE
            else:
                values[subject] = FrameClass.NEGATIVE
    return FrameInput(event_id=event.event_id, session_id=event.session_id, ts_ns=event.iphone_frame_ts_ns,
                      inspection_id=assessment.inspection_id if assessment else None,
                      profile_revision=assessment.profile_revision if assessment else None, retired=retired,
                      pose=event.pose if event.pose_valid else None,
                      unlocalized_reason=None if event.pose_valid else event.pose_invalid_reason,
                      values=values, confidence=confidence)
