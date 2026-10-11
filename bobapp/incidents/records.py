"""Policy transition -> `bob-app` incident record (plan §8.5)."""
from __future__ import annotations

from bobapp.contracts import FrameCounts, IncidentBody, IncidentKey, IncidentLocation
from vision.schema import PoseInvalidReason

from .params import PolicyParams
from .policy import FrameRef, Transition


def location(ref: FrameRef) -> IncidentLocation:
    """Camera pose of that frame ("observed from here"), never the person's position."""
    if ref.pose is not None:
        return IncidentLocation(event_id=ref.event_id, pose=ref.pose)
    return IncidentLocation(event_id=ref.event_id, unlocalized_reason=ref.unlocalized_reason or PoseInvalidReason.NO_POSE)


def incident_body(t: Transition, params: PolicyParams, evidence_sha256: list[str]) -> IncidentBody:
    s = t.subject
    return IncidentBody(
        kind="incident", incident_id=t.incident_id, transition=t.kind, end_reason=t.end_reason,
        key=IncidentKey(inspection_id=t.inspection_id, profile_revision=t.profile_revision, session_id=t.session_id,
                        hazard=s.hazard, rule=s.rule, zone_id=s.zone_id, zone_profile_sha256=s.zone_profile_sha256),
        policy_version=params.policy_version, policy_params_sha256=params.sha256, calibrated=params.calibrated,
        observed_iphone_ts_ns=t.ts_ns, counts=FrameCounts(positive=t.counts[0], negative=t.counts[1], neutral=t.counts[2]),
        event_ids=list(t.event_ids), evidence_sha256=evidence_sha256[:params.evidence_max],
        location=location(t.location) if t.location else None, interruption_ns=t.interruption_ns)


def subject_label(t: Transition) -> str:
    s = t.subject
    return s.rule if s.rule else f"zone:{s.zone_id}" if s.zone_id else s.hazard.value
