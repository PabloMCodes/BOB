"""`bob-app` v1 — application envelopes for the rover edge store, the sync link and the hub API.

Separately versioned from the frozen CV wire contract (vision/schema, v2): C2 `DetectionEvent` and
C3 `StreamHealth` are embedded unchanged, never extended. Interfaces C9 (edge sync) and C10 (hub API)
in integration.md. Any change here: bump APP_VERSION + AppVersion, update tests/fixtures/app/ and run
`uv run python -m tools.export_app_schema`.

Meanings kept apart (CLAUDE.md): raw detection (C2 boxes), derived per-subject verdict, worksite
assessment (bound to a profile revision), incident (policy over many frames). Unknown values are
null with a reason, never zero or a default.

Layout:
  common.py       base model, strict types, SourceMode / Lane / Delivery, requirements, RoverClock
  observation.py  observation lane: C2 + verdicts, rule availability, C7 record, frame assessment
  track.py        track lane: phone-camera track points
  profile.py      WorksiteProfile (immutable, hashed revision)
  control.py      control lane: evidence, profile revision, inspection start/end, gap, notice
  incident.py     control lane: incident transitions (plan §8)
  record.py       lane Record envelope + body union
  live.py         LiveState (latest wins, never stored)
  sync.py         sync link messages + blob status
  wire.py         message union, parse_app_message, JSON Schema export
"""

from .common import (
    APP_VERSION,
    LANE_PRIORITY,
    REQUIREMENT_RULES,
    AppVersion,
    Delivery,
    Lane,
    NonNegInt,
    PosInt,
    Requirement,
    RoverClock,
    Sha256,
    SourceMode,
    is_sha256,
)
from .control import (
    EvidenceBody,
    EvidenceReason,
    GapBody,
    GapReason,
    InspectionEndedBody,
    InspectionEndReason,
    InspectionStartedBody,
    NoticeBody,
    ProfileRevisionBody,
)
from .incident import (
    FrameCounts,
    Hazard,
    IncidentBody,
    IncidentEndReason,
    IncidentKey,
    IncidentLocation,
    IncidentTransition,
)
from .live import (
    Capabilities,
    EdgeStatus,
    FeedAge,
    Freshness,
    LivePose,
    LiveState,
    PreviewRef,
    Producer,
    ProducerStatus,
)
from .observation import (
    AssessmentStatus,
    FrameAssessment,
    ObservationBody,
    RequirementAssessment,
    RuleStatus,
    SubjectVerdict,
    Verdict,
)
from .profile import WorksiteProfile
from .record import BODY_LANE, Body, Record
from .sync import (
    BlobStatus,
    BlobStatusValue,
    LaneInfo,
    SyncAck,
    SyncBatch,
    SyncError,
    SyncHello,
    SyncLive,
    SyncWelcome,
)
from .track import TrackPointBody
from .wire import APP_MESSAGE_MODELS, AppMessage, app_json_schemas, parse_app_message

__all__ = [
    "APP_MESSAGE_MODELS", "APP_VERSION", "BODY_LANE", "LANE_PRIORITY", "REQUIREMENT_RULES",
    "AppMessage", "AppVersion", "AssessmentStatus", "BlobStatus", "BlobStatusValue", "Body",
    "Capabilities", "Delivery", "EdgeStatus", "EvidenceBody", "EvidenceReason", "FeedAge",
    "FrameAssessment", "FrameCounts", "Freshness", "Hazard", "GapBody", "GapReason", "IncidentBody",
    "IncidentEndReason", "IncidentKey", "IncidentLocation", "IncidentTransition", "InspectionEndReason",
    "InspectionEndedBody", "InspectionStartedBody", "Lane", "LaneInfo", "LivePose", "LiveState",
    "NonNegInt", "NoticeBody", "ObservationBody", "PosInt", "PreviewRef", "Producer", "ProducerStatus",
    "ProfileRevisionBody", "Record", "Requirement", "RequirementAssessment", "RoverClock", "RuleStatus",
    "Sha256", "SourceMode", "SubjectVerdict", "SyncAck", "SyncBatch", "SyncError", "SyncHello",
    "SyncLive", "SyncWelcome", "TrackPointBody", "Verdict", "WorksiteProfile", "app_json_schemas",
    "is_sha256", "parse_app_message",
]
