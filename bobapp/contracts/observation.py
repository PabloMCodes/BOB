"""Observation lane: one record per processed frame — C2 verbatim plus the per-subject verdicts,
rule availability, optional C7 record and the frame's worksite assessment."""
from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import Field, model_validator

from vision.ppe import Verdict
from vision.schema import Box, DetectionEvent

from .common import REQUIREMENT_RULES, PosInt, Requirement, Sha256, _Model

class RuleStatus(_Model):
    name: str = Field(min_length=1)
    active: bool
    missing_classes: list[str] = []   # why an inactive rule is inactive

    @model_validator(mode="after")
    def _reason(self) -> RuleStatus:
        if self.active == bool(self.missing_classes):
            raise ValueError("inactive rules need missing_classes; active rules must have none")
        return self


class SubjectVerdict(_Model):
    rule: str = Field(min_length=1)
    verdict: Verdict
    subject: Box
    ppe: Optional[Box] = None
    violation: Optional[Box] = None

    @model_validator(mode="after")
    def _boxes(self) -> SubjectVerdict:
        if (self.verdict == Verdict.NOT_WEARING) != (self.violation is not None):
            raise ValueError("a violation box is present exactly when verdict is not_wearing")
        return self


class AssessmentStatus(str, Enum):
    NOT_REQUIRED = "not_required"                    # unchecked: never 'detected' or 'compliant'
    DETECTED = "detected"                            # required PPE seen on a judged subject
    NOT_DETECTED = "not_detected"                    # judged subject without it (per frame, not an incident)
    NOT_ASSESSED = "not_assessed"                    # no judged subject: occluded, absent, small, uncertain
    ASSESSMENT_UNAVAILABLE = "assessment_unavailable"  # required, but the rule/model is missing


class RequirementAssessment(_Model):
    requirement: Requirement
    status: AssessmentStatus
    reason: Optional[str] = None

    @model_validator(mode="after")
    def _reason(self) -> RequirementAssessment:
        needs = {AssessmentStatus.NOT_ASSESSED, AssessmentStatus.ASSESSMENT_UNAVAILABLE}
        if (self.status in needs) != bool(self.reason):
            raise ValueError("reason is required exactly for not_assessed / assessment_unavailable")
        return self


class FrameAssessment(_Model):
    """One frame under the inspection's bound profile revision (§4)."""
    inspection_id: UUID
    worksite_id: str = Field(min_length=1)
    profile_revision: PosInt
    no_requirements_selected: bool                  # all unchecked: not an all-clear
    requirements: list[RequirementAssessment]

    @model_validator(mode="after")
    def _all(self) -> FrameAssessment:
        names = [r.requirement for r in self.requirements]
        if sorted(names) != sorted(REQUIREMENT_RULES):
            raise ValueError("assessment must list every requirement exactly once")
        required = any(r.status != AssessmentStatus.NOT_REQUIRED for r in self.requirements)
        if self.no_requirements_selected == required:
            raise ValueError("no_requirements_selected must be true exactly when nothing is required")
        return self


class ObservationBody(_Model):
    kind: Literal["observation"]
    event: DetectionEvent                            # C2 verbatim
    rules: list[RuleStatus]
    verdicts: list[SubjectVerdict]
    frame_verdicts: dict[str, Verdict]               # vision.ppe.frame_verdict per active rule
    image_pixels_sha256: Sha256                      # clean upright frame the model saw
    evidence_sha256: Optional[Sha256] = None         # set when this frame was kept as evidence
    scene: Optional[dict[str, Any]] = None           # C7 record (scene_version 1) for this frame
    assessment: Optional[FrameAssessment] = None     # null when no inspection is running

    @model_validator(mode="after")
    def _consistent(self) -> ObservationBody:
        active = {r.name for r in self.rules if r.active}
        if set(self.frame_verdicts) != active:
            raise ValueError("frame_verdicts must cover exactly the active rules")
        if any(v.rule not in active for v in self.verdicts):
            raise ValueError("subject verdicts must belong to active rules")
        if self.scene is not None:
            if self.scene.get("scene_version") != 1:
                raise ValueError("scene must be a scene_version 1 (C7) record")
            if self.scene.get("source_event_id") != str(self.event.event_id):
                raise ValueError("scene record must reference this observation's event_id")
        return self
