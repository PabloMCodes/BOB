"""Twin (plan §7): session-local phone-camera track, pins "observed from here", unlocalized items.

Pins sit at the camera pose of their own frame — never the person's or hazard's position, never a
later pose. A new ARKit session is a new map; sessions are never merged or drawn on each other.
"""
from __future__ import annotations

from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel

from bobapp.contracts import Delivery, SourceMode
from vision.schema import Pose

from .common import CLOCK_DOMAINS, WorkspaceName

PIN_MEANING = "observed from here: the phone camera's position for that frame, not the person's or hazard's"


class TrackPoint(BaseModel):
    seq_id: int
    iphone_ts_ns: int
    pose: Pose
    east_m: float
    north_m: float
    delivery: Delivery


class TrackSegment(BaseModel):
    segment: int                                   # a gap in valid tracking starts a new segment
    delivery: Literal["realtime", "backfilled", "mixed"]   # backfilled = history synced later, draw distinctly
    points: list[TrackPoint]


class Bounds(BaseModel):
    min_east: float
    max_east: float
    min_north: float
    max_north: float


class SessionSummary(BaseModel):
    session_id: UUID
    track_points: int
    segments: int
    backfilled_points: int
    first_iphone_ts_ns: Optional[int] = None
    last_iphone_ts_ns: Optional[int] = None
    bounds: Optional[Bounds] = None
    source_modes: list[SourceMode]
    current: bool                                  # the session the rover reports live right now


class SessionList(BaseModel):
    workspace: WorkspaceName
    sessions: list[SessionSummary]
    projection: dict[str, Any]
    clock_domains: dict[str, str] = CLOCK_DOMAINS


class Track(BaseModel):
    workspace: WorkspaceName
    session_id: UUID
    segments: list[TrackSegment]
    projection: dict[str, Any]


class Pin(BaseModel):
    kind: Literal["incident", "evidence"]
    id: str                                        # incident id or evidence sha256
    label: str
    hazard: Optional[str] = None
    state: Optional[str] = None                    # latest incident transition
    end_reason: Optional[str] = None
    event_id: UUID
    pose: Pose
    east_m: float
    north_m: float
    source_mode: SourceMode
    delivery: Delivery
    evidence_sha256: list[str] = []
    meaning: str = PIN_MEANING


class Unlocalized(BaseModel):
    kind: Literal["incident", "evidence"]
    id: str
    label: str
    event_id: UUID
    reason: str                                    # why it has no position (pose invalid for that frame)
    source_mode: SourceMode
    delivery: Delivery


class Marker(BaseModel):
    label: str = "Phone camera"                    # not the rover: no phone-to-rover transform exists
    status: Literal["current", "last_known", "unknown"]
    pose: Optional[Pose] = None
    age_ms: Optional[float] = None
    note: str


class Pins(BaseModel):
    workspace: WorkspaceName
    session_id: UUID
    pins: list[Pin]
    unlocalized: list[Unlocalized]
    marker: Marker
    clock_domains: dict[str, str] = CLOCK_DOMAINS
