"""Worksite assessment of one frame under the inspection's bound profile revision (plan §4).

| Requirement | Condition                                   | Status                  |
| unchecked   | any                                         | not_required            |
| checked     | rule inactive / not configured              | assessment_unavailable  |
| checked     | frame verdict wearing / not_wearing         | detected / not_detected |
| checked     | frame verdict unverified (nobody judged)    | not_assessed            |

All unchecked -> `no_requirements_selected` (never an all-clear). Nothing here alters detections,
model thresholds or past records: a new revision only applies to the next explicitly started inspection.
"""
from __future__ import annotations

from typing import Optional

from bobapp.contracts import (
    REQUIREMENT_RULES,
    AssessmentStatus,
    FrameAssessment,
    RequirementAssessment,
    RuleStatus,
    Verdict,
    WorksiteProfile,
)
from bobapp.edge.store import ActiveInspection

NOT_JUDGED = "no judged subject: occluded, absent, too small or uncertain"


def unavailable_reason(requirement: str, rules: list[RuleStatus]) -> Optional[str]:
    """Why a checked requirement cannot be assessed in this run (None if it can)."""
    rule = REQUIREMENT_RULES[requirement]
    status = next((r for r in rules if r.name == rule), None)
    if status is None:
        return f"no rule {rule!r} is configured"
    if not status.active:
        return f"rule {rule!r} inactive: model lacks {status.missing_classes}"
    return None


def unavailable_requirements(profile: WorksiteProfile, rules: list[RuleStatus]) -> dict[str, str]:
    return {req: reason for req, checked in profile.requirements.items() if checked
            for reason in [unavailable_reason(req, rules)] if reason}


def assess(frame_verdicts: dict[str, Verdict], rules: list[RuleStatus], inspection: ActiveInspection) -> FrameAssessment:
    profile, results = inspection.profile, []
    for requirement in REQUIREMENT_RULES:
        if not profile.requirements[requirement]:
            results.append(RequirementAssessment(requirement=requirement, status=AssessmentStatus.NOT_REQUIRED))
            continue
        reason = unavailable_reason(requirement, rules)
        if reason:
            results.append(RequirementAssessment(requirement=requirement, status=AssessmentStatus.ASSESSMENT_UNAVAILABLE,
                                                 reason=reason))
            continue
        verdict = Verdict(frame_verdicts[REQUIREMENT_RULES[requirement]])
        if verdict is Verdict.UNVERIFIED:
            results.append(RequirementAssessment(requirement=requirement, status=AssessmentStatus.NOT_ASSESSED,
                                                 reason=NOT_JUDGED))
        else:
            results.append(RequirementAssessment(requirement=requirement, status=AssessmentStatus.DETECTED
                                                 if verdict is Verdict.WEARING else AssessmentStatus.NOT_DETECTED))
    return FrameAssessment(inspection_id=inspection.inspection_id, worksite_id=inspection.worksite_id,
                           profile_revision=inspection.profile_revision,
                           no_requirements_selected=not any(profile.requirements.values()), requirements=results)
