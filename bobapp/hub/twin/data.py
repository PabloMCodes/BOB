"""Twin data from the hub replica (plan §7). Read-only: no motion authority, nothing is inferred.

- Track: the rover's downsampled valid phone-camera poses, per ARKit session, split into segments
  wherever tracking was invalid; backfilled points are labeled so a view draws them as history.
- Pins: incidents (at the confirming frame's pose, else the first positive frame's while a candidate)
  and evidence frames, each at the camera pose of its own frame. No pose -> the unlocalized list with
  the frame's reason; never the latest pose.
- Marker: the phone camera's live pose when the link is current; otherwise the last synced pose with
  "position since then unknown"; for a past session, its last track point — never extrapolated.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Optional
from uuid import UUID

from bobapp.contracts import Delivery, IncidentTransition, Record

from ..api import views
from ..api.models import (
    Marker,
    Pin,
    Pins,
    SessionList,
    SessionSummary,
    Track,
    TrackPoint,
    TrackSegment,
    Unlocalized,
)
from ..api.models.twin import Bounds
from ..replica import Replica
from .projection import DESCRIPTION, east_north


def _records(replica: Replica, kinds: tuple[str, ...]) -> list[tuple[Record, Delivery]]:
    ws = replica.active_workspace()
    rows = replica.query(ws, kinds, limit=1_000_000) if ws else []
    return [(Record.model_validate_json(text), Delivery(delivery)) for _, delivery, _, text in rows]


def _points(replica: Replica) -> dict[UUID, list[tuple[Record, Delivery]]]:
    by_session: dict[UUID, list[tuple[Record, Delivery]]] = defaultdict(list)
    for record, delivery in _records(replica, ("track_point",)):
        by_session[record.body.session_id].append((record, delivery))
    return by_session


def sessions(replica: Replica, workspace: str, stale_after_s: float) -> SessionList:
    status = views.status(replica, workspace, stale_after_s)
    live_session = status.live.pose.session_id if status.live and status.live.pose and status.live_is_current else None
    points = _points(replica)
    order = list(points)
    for record, _ in _records(replica, ("incident", "evidence")):
        sid = record.body.key.session_id if record.body.kind == "incident" else record.body.session_id
        if sid not in points and sid not in order:
            order.append(sid)
    out = []
    for sid in order:
        pts = points.get(sid, [])
        coords = [east_north(r.body.pose) for r, _ in pts]
        out.append(SessionSummary(
            session_id=sid, track_points=len(pts), segments=len({r.body.segment for r, _ in pts}),
            backfilled_points=sum(d == Delivery.BACKFILLED for _, d in pts),
            first_iphone_ts_ns=pts[0][0].body.iphone_ts_ns if pts else None,
            last_iphone_ts_ns=pts[-1][0].body.iphone_ts_ns if pts else None,
            bounds=Bounds(min_east=min(e for e, _ in coords), max_east=max(e for e, _ in coords),
                          min_north=min(n for _, n in coords), max_north=max(n for _, n in coords)) if coords else None,
            source_modes=sorted({r.source_mode for r, _ in pts}, key=lambda m: m.value), current=sid == live_session))
    return SessionList(workspace=workspace, sessions=out, projection=DESCRIPTION)


def track(replica: Replica, workspace: str, session_id: UUID) -> Track:
    segments: dict[int, list[TrackPoint]] = defaultdict(list)
    for record, delivery in _points(replica).get(session_id, []):
        b = record.body
        east, north = east_north(b.pose)
        segments[b.segment].append(TrackPoint(seq_id=b.seq_id, iphone_ts_ns=b.iphone_ts_ns, pose=b.pose,
                                              east_m=east, north_m=north, delivery=delivery))
    out = []
    for segment, pts in sorted(segments.items()):
        kinds = {p.delivery for p in pts}
        out.append(TrackSegment(segment=segment, points=pts,
                                delivery="mixed" if len(kinds) > 1 else next(iter(kinds)).value))
    return Track(workspace=workspace, session_id=session_id, segments=out, projection=DESCRIPTION)


def pins(replica: Replica, workspace: str, session_id: UUID, stale_after_s: float) -> Pins:
    placed: list[Pin] = []
    unlocalized: list[Unlocalized] = []
    incidents: dict[UUID, list[tuple[Record, Delivery]]] = defaultdict(list)
    for record, delivery in _records(replica, ("incident", "evidence")):
        b = record.body
        if b.kind == "incident":
            if b.key.session_id == session_id:
                incidents[b.incident_id].append((record, delivery))
        elif b.session_id == session_id:
            label = f"evidence: {', '.join(r for r in b.rules if not r.startswith(('incident:', 'role:'))) or b.reason.value}"
            if b.pose_valid:
                east, north = east_north(b.pose)
                placed.append(Pin(kind="evidence", id=b.sha256, label=label, event_id=b.event_id, pose=b.pose,
                                  east_m=east, north_m=north, source_mode=record.source_mode, delivery=delivery,
                                  evidence_sha256=[b.sha256]))
            else:
                unlocalized.append(Unlocalized(kind="evidence", id=b.sha256, label=label, event_id=b.event_id,
                                               reason=b.pose_invalid_reason.value, source_mode=record.source_mode,
                                               delivery=delivery))
    for incident_id, history in incidents.items():
        latest, delivery = history[-1]
        confirming = [r for r, _ in history if r.body.transition in (IncidentTransition.CONFIRMED, IncidentTransition.REOPENED)]
        anchor = (confirming[-1] if confirming else history[0][0]).body
        key = latest.body.key
        label = f"{key.hazard.value}: {key.rule or key.zone_id or key.hazard.value}"
        location = anchor.location
        if location is None:
            continue
        if location.pose is not None:
            east, north = east_north(location.pose)
            placed.append(Pin(kind="incident", id=str(incident_id), label=label, hazard=key.hazard.value,
                              state=latest.body.transition.value,
                              end_reason=latest.body.end_reason.value if latest.body.end_reason else None,
                              event_id=location.event_id, pose=location.pose, east_m=east, north_m=north,
                              source_mode=latest.source_mode, delivery=delivery,
                              evidence_sha256=list(latest.body.evidence_sha256)))
        else:
            unlocalized.append(Unlocalized(kind="incident", id=str(incident_id), label=label, event_id=location.event_id,
                                           reason=location.unlocalized_reason.value, source_mode=latest.source_mode,
                                           delivery=delivery))
    return Pins(workspace=workspace, session_id=session_id, pins=placed, unlocalized=unlocalized,
                marker=marker(replica, workspace, session_id, stale_after_s))


def marker(replica: Replica, workspace: str, session_id: UUID, stale_after_s: float) -> Marker:
    status = views.status(replica, workspace, stale_after_s)
    live = status.live
    if live and live.pose and live.pose.session_id == session_id and live.pose.pose_valid:
        rover_age = live.freshness.pose.age_ms or 0.0
        age = rover_age + (status.live_received_age_ms or 0.0)
        if status.live_is_current:
            return Marker(status="current", pose=live.pose.pose, age_ms=age, note="live phone-camera pose")
        return Marker(status="unknown", pose=live.pose.pose, age_ms=age,
                      note=f"last synced {age / 1000:.1f} s ago; position since then unknown (link {status.link['state']})")
    last = _last_point(replica, session_id)
    if last is None:
        return Marker(status="unknown", note="no valid phone-camera pose in this session")
    reason = ("live pose invalid: " + live.pose.pose_invalid_reason.value) if (
        live and live.pose and live.pose.session_id == session_id and live.pose.pose_invalid_reason) else "not the live session"
    return Marker(status="last_known", pose=last.pose, note=f"last known track point ({reason}); not extrapolated")


def _last_point(replica: Replica, session_id: UUID) -> Optional[Record]:
    pts = _points(replica).get(session_id)
    return pts[-1][0].body if pts else None
