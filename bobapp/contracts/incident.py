"""Incident transitions (plan §8): append-only, one record per state change."""
from __future__ import annotations

from enum import Enum
from typing import Literal, Optional
from uuid import UUID

from pydantic import Field, model_validator

from vision.schema import Pose, PoseInvalidReason

from .common import NonNegInt, PosInt, Sha256, _Model


class Hazard(str, Enum):
    """The three hazard categories (+ walkway). person_in_path and walkway have no producer yet:
    their incidents exist only as SAMPLE data until a producer and its own policy exist."""
    PPE = "ppe"
    RESTRICTED_ZONE = "restricted_zone"
    PERSON_IN_PATH = "person_in_path"
    WALKWAY = "walkway"


class IncidentTransition(str, Enum):
    CANDIDATE = "candidate"
    CONFIRMED = "confirmed"
    DISCARDED = "discarded"
    ENDED = "ended"
    REOPENED = "reopened"


class IncidentEndReason(str, Enum):
    CONDITION_NOT_OBSERVED = "condition_not_observed"   # "no longer observed", never "resolved"
    NOT_ASSESSED = "not_assessed"
    SESSION_CHANGED = "session_changed"
    INSPECTION_ENDED = "inspection_ended"
    SOURCE_STOPPED = "source_stopped"


class IncidentKey(_Model):
    inspection_id: UUID
    profile_revision: PosInt
    session_id: UUID
    hazard: Hazard
    rule: Optional[str] = None                 # ppe: the PPE rule
    zone_id: Optional[str] = None              # restricted_zone: C7 zone; walkway: walkway id
    zone_profile_sha256: Optional[Sha256] = None

    @model_validator(mode="after")
    def _shape(self) -> IncidentKey:
        has_rule, has_zone, has_hash = self.rule is not None, self.zone_id is not None, self.zone_profile_sha256 is not None
        expected = {Hazard.PPE: (True, False, False), Hazard.RESTRICTED_ZONE: (False, True, True),
                    Hazard.PERSON_IN_PATH: (False, False, False), Hazard.WALKWAY: (False, True, has_hash)}[self.hazard]
        if (has_rule, has_zone, has_hash) != expected:
            raise ValueError("incident key shape: ppe needs only rule; restricted_zone needs zone_id + "
                             "zone_profile_sha256; person_in_path neither; walkway needs zone_id")
        return self


class FrameCounts(_Model):
    positive: NonNegInt
    negative: NonNegInt
    neutral: NonNegInt


class IncidentLocation(_Model):
    """Camera pose of the frame ("observed from here"), never the person's position."""
    event_id: UUID
    pose: Optional[Pose] = None
    unlocalized_reason: Optional[PoseInvalidReason] = None

    @model_validator(mode="after")
    def _one(self) -> IncidentLocation:
        if (self.pose is None) == (self.unlocalized_reason is None):
            raise ValueError("location has a pose or an unlocalized_reason, not both")
        return self


class IncidentBody(_Model):
    """One append-only state transition (§8.3). Records are never edited."""
    kind: Literal["incident"]
    incident_id: UUID
    transition: IncidentTransition
    end_reason: Optional[IncidentEndReason] = None
    key: IncidentKey
    policy_version: PosInt
    policy_params_sha256: Sha256
    calibrated: bool                           # false: "policy uncalibrated"
    observed_iphone_ts_ns: NonNegInt           # phone clock of the frame that caused the transition
    counts: FrameCounts                        # since the incident opened
    event_ids: list[UUID]                      # frames that caused this transition
    evidence_sha256: list[Sha256] = Field(default=[], max_length=10)
    location: Optional[IncidentLocation] = None
    interruption_ns: Optional[NonNegInt] = None   # reopened: phone-clock time it was not confirmed

    @model_validator(mode="after")
    def _end(self) -> IncidentBody:
        if (self.transition == IncidentTransition.ENDED) != (self.end_reason is not None):
            raise ValueError("end_reason is required exactly for the ended transition")
        if (self.transition == IncidentTransition.REOPENED) != (self.interruption_ns is not None):
            raise ValueError("interruption_ns is required exactly for the reopened transition")
        return self
