"""Observation lane body: C2 verbatim plus what C2 omits — per-subject verdicts and rule availability."""
from __future__ import annotations

from typing import Any, Optional

from bobapp.contracts import FrameAssessment, ObservationBody, RuleStatus, SubjectVerdict
from vision.render import normalize_class_name


def rule_statuses(pipeline: Any) -> list[RuleStatus]:
    """Active rules, then inactive ones with the model classes they lack (never a look-alike)."""
    classes = {normalize_class_name(c) for c in pipeline.names.values()}
    return ([RuleStatus(name=r.name, active=True) for r in pipeline.rules]
            + [RuleStatus(name=r.name, active=False, missing_classes=sorted(r.requires - classes))
               for r in pipeline.inactive_rules])


def observation_body(detection: Any, rules: list[RuleStatus], pixels_sha256: str,
                     evidence_sha256: Optional[str], scene: Optional[dict],
                     assessment: Optional[FrameAssessment] = None) -> ObservationBody:
    verdicts = [SubjectVerdict(rule=v.rule, verdict=v.verdict, subject=v.subject, ppe=v.ppe, violation=v.violation)
                for v in detection.result.verdicts]
    return ObservationBody(kind="observation", event=detection.event, rules=rules, verdicts=verdicts,
                           frame_verdicts=detection.verdicts, image_pixels_sha256=pixels_sha256,
                           evidence_sha256=evidence_sha256, scene=scene, assessment=assessment)
