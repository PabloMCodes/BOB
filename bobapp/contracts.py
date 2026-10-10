"""`bob-app` v1 — application envelopes for the rover edge store, the sync link and the hub API.

Separately versioned from the frozen CV wire contract (vision/schema, v2): C2 `DetectionEvent` and
C3 `StreamHealth` are embedded unchanged, never extended. Interfaces C9 (edge sync) and C10 (hub API)
in integration.md. Any change here: bump APP_VERSION + AppVersion, update tests/fixtures/app/ and run
`uv run python -m tools.export_app_schema`.

Meanings kept apart (CLAUDE.md): raw detection (C2 boxes), derived per-subject verdict, worksite
assessment (bound to a profile revision), incident (policy over many frames). Unknown values are
null with a reason, never zero or a default.
"""
from __future__ import annotations

import hashlib
import json
import re
from enum import Enum
from typing import Annotated, Any, Literal, Optional, Union
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, Strict, TypeAdapter, field_validator, model_validator

from vision.ppe import Verdict
from vision.schema import Box, DetectionEvent, ImageSize, Pose, PoseInvalidReason, StreamHealth

APP_VERSION = 1
AppVersion = Literal[1]

NonNegInt = Annotated[int, Strict(), Field(ge=0)]
PosInt = Annotated[int, Strict(), Field(gt=0)]
Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class SourceMode(str, Enum):
    """Declared by the operator at server start: the server cannot tell a replay client from a phone."""
    LIVE = "LIVE"
    REPLAY = "REPLAY"
    SAMPLE = "SAMPLE"


class Lane(str, Enum):
    CONTROL = "control"          # inspections, profiles, incidents, evidence metadata, gaps, notices
    TRACK = "track"              # downsampled valid phone-camera poses
    OBSERVATION = "observation"  # one per processed frame; first pruned under disk pressure


LANE_PRIORITY = (Lane.CONTROL, Lane.TRACK, Lane.OBSERVATION)


class Delivery(str, Enum):
    """Set by the hub on receipt. Backfilled records never update current status."""
    REALTIME = "realtime"
    BACKFILLED = "backfilled"


# Worksite requirement checkbox -> PPE rule name in configs/default.yaml ppe.rules.
REQUIREMENT_RULES: dict[str, str] = {
    "eyewear": "glasses", "helmet": "helmet", "gloves": "gloves", "vest": "vest", "boots": "boots",
}
Requirement = Literal["eyewear", "helmet", "gloves", "vest", "boots"]


class RoverClock(_Model):
    """Rover times of one record. Never subtract them from laptop or iPhone times."""
    wall_ns: NonNegInt
    mono_ns: NonNegInt
    clock_synced: Optional[bool]   # null = unknown (an offline Jetson's wall clock may be wrong)


# --- observation lane ---------------------------------------------------------------------------

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


# --- track lane ---------------------------------------------------------------------------------

class TrackPointBody(_Model):
    """Valid phone-camera pose (never the rover's or a person's position). A new `segment` starts
    after any invalid pose; segments are never joined across a gap."""
    kind: Literal["track_point"]
    session_id: UUID
    segment: NonNegInt
    seq_id: NonNegInt
    iphone_ts_ns: NonNegInt
    packet: Literal["frame", "pose"]
    pose: Pose


# --- control lane -------------------------------------------------------------------------------

class EvidenceReason(str, Enum):
    DERIVED_BOX = "derived_box"
    SCENE_FINDING = "scene_finding"
    INCIDENT = "incident"


class EvidenceBody(_Model):
    """Metadata of one clean upright full-resolution JPEG blob, tied to its exact source frame."""
    kind: Literal["evidence"]
    sha256: Sha256                                   # of the JPEG bytes (blob address)
    size_bytes: PosInt
    media_type: Literal["image/jpeg"]
    image_pixels_sha256: Sha256                      # of the decoded upright pixels (= observation's)
    event_id: UUID
    session_id: UUID
    seq_id: NonNegInt
    iphone_frame_ts_ns: NonNegInt
    model_id: str = Field(min_length=1)
    image_size: ImageSize
    reason: EvidenceReason
    rules: list[str]                                 # rules / zones that triggered the capture
    pose: Optional[Pose] = None
    pose_valid: bool
    pose_invalid_reason: Optional[PoseInvalidReason] = None

    @model_validator(mode="after")
    def _pose(self) -> EvidenceBody:
        if self.pose_valid != (self.pose is not None) or self.pose_valid == (self.pose_invalid_reason is not None):
            raise ValueError("pose_valid=true needs a pose and no reason; false needs a reason and no pose")
        return self


class WorksiteProfile(_Model):
    """Immutable revision of a worksite's PPE requirements. `sha256` covers every other field."""
    app_version: AppVersion
    msg_type: Literal["worksite_profile"]
    worksite_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    revision: PosInt
    name: str = Field(min_length=1, max_length=200)
    requirements: dict[Requirement, bool]
    sha256: Sha256

    @staticmethod
    def content_sha256(worksite_id: str, revision: int, name: str, requirements: dict[str, bool]) -> str:
        canonical = json.dumps({"worksite_id": worksite_id, "revision": revision, "name": name,
                                "requirements": requirements}, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()

    @classmethod
    def build(cls, worksite_id: str, revision: int, name: str, requirements: dict[str, bool]) -> WorksiteProfile:
        return cls(app_version=APP_VERSION, msg_type="worksite_profile", worksite_id=worksite_id,
                   revision=revision, name=name, requirements=requirements,
                   sha256=cls.content_sha256(worksite_id, revision, name, requirements))

    @model_validator(mode="after")
    def _hash(self) -> WorksiteProfile:
        if sorted(self.requirements) != sorted(REQUIREMENT_RULES):
            raise ValueError("requirements must list every requirement exactly once")
        if self.sha256 != self.content_sha256(self.worksite_id, self.revision, self.name, dict(self.requirements)):
            raise ValueError("sha256 does not match the profile content")
        return self


class ProfileRevisionBody(_Model):
    kind: Literal["profile_revision"]
    profile: WorksiteProfile


class InspectionStartedBody(_Model):
    kind: Literal["inspection_started"]
    inspection_id: UUID
    worksite_id: str = Field(min_length=1)
    profile_revision: PosInt
    profile_sha256: Sha256
    requested_by: Optional[str] = None


class InspectionEndReason(str, Enum):
    OPERATOR = "operator"
    SOURCE_STOPPED = "source_stopped"     # the edge restarted: never resumed from memory


class InspectionEndedBody(_Model):
    kind: Literal["inspection_ended"]
    inspection_id: UUID
    reason: InspectionEndReason


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
    rule: Optional[str] = None                 # PPE rule, or
    zone_id: Optional[str] = None              # restricted zone (C7)
    zone_profile_sha256: Optional[Sha256] = None

    @model_validator(mode="after")
    def _one(self) -> IncidentKey:
        if (self.rule is None) == (self.zone_id is None):
            raise ValueError("an incident key has exactly one of rule or zone_id")
        if (self.zone_id is None) != (self.zone_profile_sha256 is None):
            raise ValueError("zone incidents need zone_profile_sha256 (and only they)")
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


class GapReason(str, Enum):
    PRUNED_RETENTION = "pruned_retention"
    PRUNED_DISK_PRESSURE = "pruned_disk_pressure"


class GapBody(_Model):
    """Records first_seq..last_seq of `lane` were removed on the rover before the hub had them."""
    kind: Literal["gap"]
    lane: Lane
    first_seq: PosInt
    last_seq: PosInt
    reason: GapReason

    @model_validator(mode="after")
    def _order(self) -> GapBody:
        if self.first_seq > self.last_seq:
            raise ValueError("gap first_seq must be <= last_seq")
        return self


class NoticeBody(_Model):
    """Capability / health notices: 'Required — assessment unavailable', writer drops, low rate..."""
    kind: Literal["notice"]
    code: str = Field(min_length=1, pattern=r"^[a-z_]+$")
    message: str = Field(min_length=1)
    details: dict[str, Any] = {}


Body = Annotated[
    Union[ObservationBody, TrackPointBody, EvidenceBody, ProfileRevisionBody, InspectionStartedBody,
          InspectionEndedBody, IncidentBody, GapBody, NoticeBody],
    Field(discriminator="kind"),
]
BODY_LANE = {"observation": Lane.OBSERVATION, "track_point": Lane.TRACK}  # every other kind: control


class Record(_Model):
    """One durable lane record. `(edge_id, store_epoch, lane, seq)` is the deduplication key; order by
    `seq`, never by time."""
    app_version: AppVersion
    msg_type: Literal["record"]
    edge_id: str = Field(min_length=1)
    store_epoch: UUID
    lane: Lane
    seq: PosInt
    run_id: Optional[str] = None
    source_mode: SourceMode
    rover: RoverClock
    body: Body

    @model_validator(mode="after")
    def _lane(self) -> Record:
        if self.lane != BODY_LANE.get(self.body.kind, Lane.CONTROL):
            raise ValueError(f"a {self.body.kind} record does not belong in the {self.lane.value} lane")
        return self


# --- live state (latest wins, never backfilled, never stored as a record) -------------------------

class PreviewRef(_Model):
    event_id: UUID
    session_id: UUID
    seq_id: NonNegInt
    image_size: ImageSize            # of the preview JPEG
    source_image_size: ImageSize     # boxes are in these (upright model-input) pixels
    sha256: Sha256


class LivePose(_Model):
    session_id: UUID
    seq_id: NonNegInt
    iphone_ts_ns: NonNegInt
    pose: Optional[Pose] = None
    pose_valid: bool
    pose_invalid_reason: Optional[PoseInvalidReason] = None

    @model_validator(mode="after")
    def _pose(self) -> LivePose:
        if self.pose_valid != (self.pose is not None) or self.pose_valid == (self.pose_invalid_reason is not None):
            raise ValueError("pose_valid=true needs a pose and no reason; false needs a reason and no pose")
        return self


class FeedAge(_Model):
    """Rover-clock age of the newest item; null with a reason when there has been none."""
    age_ms: Optional[float] = Field(default=None, ge=0)
    reason: Optional[str] = None

    @model_validator(mode="after")
    def _one(self) -> FeedAge:
        if (self.age_ms is None) == (self.reason is None):
            raise ValueError("feed age is a value or a reason, not both")
        return self


class Freshness(_Model):
    video: FeedAge         # last frame admitted from the phone
    results: FeedAge       # last processed frame (C2)
    pose: FeedAge          # last admitted pose/frame packet
    health: FeedAge        # last C3


class ProducerStatus(str, Enum):
    INTEGRATED = "integrated"
    PROTOTYPE = "prototype"
    NOT_INTEGRATED = "not_integrated"


class Producer(_Model):
    name: str = Field(min_length=1)
    status: ProducerStatus
    note: Optional[str] = None


class Capabilities(_Model):
    model_id: Optional[str] = None
    rules: list[RuleStatus]
    producers: list[Producer]


class EdgeStatus(_Model):
    store_bytes: NonNegInt
    disk_free_bytes: Optional[NonNegInt] = None
    writer_queued: NonNegInt
    writer_dropped: NonNegInt
    writer_errors: NonNegInt
    last_error: Optional[str] = None


class LiveState(_Model):
    app_version: AppVersion
    msg_type: Literal["live_state"]
    edge_id: str = Field(min_length=1)
    store_epoch: UUID
    run_id: Optional[str] = None
    source_mode: Optional[SourceMode] = None        # null: no vision.server run is publishing
    rover: RoverClock
    preview: Optional[PreviewRef] = None
    pose: Optional[LivePose] = None
    health: Optional[StreamHealth] = None           # C3 verbatim
    freshness: Freshness
    capabilities: Capabilities
    active_inspection_id: Optional[UUID] = None
    edge: EdgeStatus


# --- sync link (C9) -----------------------------------------------------------------------------

class LaneInfo(_Model):
    oldest_seq: Optional[PosInt] = None   # null: lane empty
    head_seq: NonNegInt                   # 0: nothing written yet in this epoch


def _all_lanes(v: dict) -> dict:
    if set(v) != set(Lane):
        raise ValueError("must list every lane exactly once")
    return v


class SyncHello(_Model):
    app_version: AppVersion
    msg_type: Literal["sync_hello"]
    hub_id: str = Field(min_length=1)
    store_epoch: Optional[UUID] = None     # null: first contact
    cursors: dict[Lane, NonNegInt]         # last committed seq per lane (0 = none)

    _lanes = field_validator("cursors")(_all_lanes)


class SyncWelcome(_Model):
    app_version: AppVersion
    msg_type: Literal["sync_welcome"]
    edge_id: str = Field(min_length=1)
    store_epoch: UUID
    lanes: dict[Lane, LaneInfo]
    rover: RoverClock
    run_id: Optional[str] = None
    source_mode: Optional[SourceMode] = None

    _lanes = field_validator("lanes")(_all_lanes)


class SyncBatch(_Model):
    app_version: AppVersion
    msg_type: Literal["sync_batch"]
    lane: Lane
    backfill: bool                         # sent while catching up (records older than the tail)
    records: list[Record] = Field(min_length=1)

    @model_validator(mode="after")
    def _ordered(self) -> SyncBatch:
        seqs = [r.seq for r in self.records]
        if any(r.lane != self.lane for r in self.records) or seqs != sorted(set(seqs)):
            raise ValueError("batch records must be this lane's, in strictly increasing seq")
        return self


class SyncAck(_Model):
    app_version: AppVersion
    msg_type: Literal["sync_ack"]
    store_epoch: UUID
    lane: Lane
    seq: NonNegInt                         # highest contiguous seq committed by the hub


class SyncLive(_Model):
    app_version: AppVersion
    msg_type: Literal["sync_live"]
    live: LiveState


class SyncError(_Model):
    app_version: AppVersion
    msg_type: Literal["sync_error"]
    code: str = Field(min_length=1)
    message: str


class BlobStatusValue(str, Enum):
    AVAILABLE = "available"
    PENDING_SYNC = "pending_sync"
    MISSING = "missing"
    HASH_MISMATCH = "hash_mismatch"


class BlobStatus(_Model):
    app_version: AppVersion
    msg_type: Literal["blob_status"]
    sha256: Sha256
    status: BlobStatusValue


AppMessage = Annotated[
    Union[Record, LiveState, WorksiteProfile, SyncHello, SyncWelcome, SyncBatch, SyncAck, SyncLive,
          SyncError, BlobStatus],
    Field(discriminator="msg_type"),
]
APP_MESSAGE_MODELS = {m.model_fields["msg_type"].annotation.__args__[0]: m for m in
                      (Record, LiveState, WorksiteProfile, SyncHello, SyncWelcome, SyncBatch, SyncAck,
                       SyncLive, SyncError, BlobStatus)}
_ADAPTER: TypeAdapter = TypeAdapter(AppMessage)


def parse_app_message(data: Union[str, bytes, dict]) -> BaseModel:
    """The single parser for every `bob-app` envelope, whatever its source_mode."""
    if isinstance(data, dict):
        return _ADAPTER.validate_python(data)
    return _ADAPTER.validate_json(data)


def is_sha256(value: str) -> bool:
    return bool(_SHA256.match(value))


def app_json_schemas() -> dict[str, dict]:
    return {f"{name}.schema.json": model.model_json_schema() for name, model in APP_MESSAGE_MODELS.items()}
