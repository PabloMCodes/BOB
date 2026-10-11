"""Replica -> response models. Pure reads; called from worker threads with thread-local replicas."""
from __future__ import annotations

import time
from typing import Any, Optional

from bobapp.contracts import Lane, LiveState, Record

from ..replica import Replica
from .models import (
    AssessmentItem,
    AssessmentPage,
    InspectionItem,
    InspectionPage,
    Item,
    LaneStatus,
    Page,
    StatusResponse,
    WorkspaceInfo,
)
from .models.status import StreamTelemetry

CURRENT_STATES = {"CONNECTED", "CATCHING_UP", "NEW_STORE"}


def status(replica: Replica, name: str, stale_after_s: float) -> StatusResponse:
    link = replica.get_link() or {"state": "DISCONNECTED", "lanes": {}, "rover_state": "unknown since last contact"}
    ws = replica.active_workspace()
    live_json, rx, _, _ = replica.get_live()
    live = LiveState.model_validate_json(live_json) if live_json else None
    age_ms = (time.time_ns() - rx) / 1e6 if rx else None
    connected = link["state"] in CURRENT_STATES
    lanes: dict[str, LaneStatus] = {}
    if ws is not None:
        counts, cursors = replica.counts(ws), replica.cursors(ws)
        for lane in Lane:
            behind = link.get("lanes", {}).get(lane.value, {}).get("behind") if connected else None
            lanes[lane.value] = LaneStatus(records=counts.get(lane.value, 0), committed_seq=cursors[lane], behind=behind)
    response = StatusResponse(
        workspace=name, link=link,
        live_is_current=bool(connected and age_ms is not None and age_ms < stale_after_s * 1000),
        live=live, live_received_wall_ns=rx, live_received_age_ms=age_ms,
        source_mode=live.source_mode if live else None, lanes=lanes,
        gaps=replica.gaps(ws) if ws else [], evidence=replica.blob_counts(),
        workspaces=[WorkspaceInfo(edge_id=w.edge_id, store_epoch=w.store_epoch, archived=w.archived)
                    for w in replica.workspaces()])
    response.telemetry_reason = "No measured stream telemetry from this producer"
    if ws is not None and live is not None and live.run_id and live.pose is not None:
        row = replica.db.execute(
            "SELECT delivery, json FROM records WHERE ws_id=? AND kind='notice' "
            "AND json_extract(json, '$.body.code')='stream_metrics' "
            "AND json_extract(json, '$.run_id')=? "
            "AND json_extract(json, '$.body.details.session_id')=? ORDER BY rowid DESC LIMIT 1",
            (ws.ws_id, live.run_id, str(live.pose.session_id))).fetchone()
        if row:
            try:
                details = Record.model_validate_json(row[1]).body.details
                measured = details["measured_mono_ns"]
                if not isinstance(measured, int) or isinstance(measured, bool) or measured < 0:
                    raise ValueError("Invalid rover measurement timestamp")
                metric_age = max(0, live.rover.mono_ns - measured) / 1e6 + (age_ms or 0)
                response.telemetry = StreamTelemetry(
                    **{k: v for k, v in details.items() if k != "measured_mono_ns"}, run_id=live.run_id,
                    age_ms=metric_age,
                    current=bool(response.live_is_current and row[0] == "realtime" and metric_age < 3000))
                response.telemetry_reason = None
            except (KeyError, TypeError, ValueError):
                # Generic notices are an extensible v1 envelope. A malformed optional metric
                # must not take down status or hide the independent link/capability information.
                response.telemetry_reason = "Producer telemetry is invalid; measured rates are unavailable"
    return response


def _item(row: tuple[int, str, int, str]) -> Item:
    rowid, delivery, rx, text = row
    return Item(cursor=rowid, delivery=delivery, hub_rx_wall_ns=rx, record=Record.model_validate_json(text))


def page(replica: Replica, name: str, kinds: tuple[str, ...], after: int, limit: int,
         where: dict[str, str], source_mode: Optional[str], delivery: Optional[str], latest: bool = False,
         before: Optional[int] = None) -> Page:
    ws = replica.active_workspace()
    rows = replica.query(ws, kinds, after, limit, where, source_mode, delivery, newest=latest,
                         before_rowid=before) if ws else []
    return Page(workspace=name, items=[_item(r) for r in rows], next_after=rows[-1][0] if rows else after)


def inspections(replica: Replica, name: str) -> InspectionPage:
    ws = replica.active_workspace()
    rows = replica.query(ws, ("inspection_started", "inspection_ended"), limit=100_000) if ws else []
    started: dict[Any, InspectionItem] = {}
    for row in rows:
        item = _item(row)
        body = item.record.body
        if body.kind == "inspection_started":
            started[body.inspection_id] = InspectionItem(
                inspection_id=body.inspection_id, worksite_id=body.worksite_id, profile_revision=body.profile_revision,
                profile_sha256=body.profile_sha256, source_mode=item.record.source_mode,
                requested_by=body.requested_by, started=item)
        elif body.inspection_id in started:
            started[body.inspection_id] = started[body.inspection_id].model_copy(update={"ended": item})
    return InspectionPage(workspace=name, items=list(started.values()))


def assessments(replica: Replica, name: str, after: int, limit: int, where: dict[str, str],
                delivery: Optional[str]) -> AssessmentPage:
    ws = replica.active_workspace()
    rows = replica.query(ws, ("observation",), after, limit, where, None, delivery) if ws else []
    items = []
    for row in rows:
        item = _item(row)
        body = item.record.body
        if body.assessment is None:
            continue  # no inspection was running for this frame: an observation, not an assessment
        e = body.event
        items.append(AssessmentItem(
            cursor=item.cursor, delivery=item.delivery, source_mode=item.record.source_mode, event_id=e.event_id,
            session_id=e.session_id, seq_id=e.seq_id, iphone_frame_ts_ns=e.iphone_frame_ts_ns,
            pose_valid=e.pose_valid, pose=e.pose if e.pose_valid else None, pose_invalid_reason=e.pose_invalid_reason,
            assessment=body.assessment))
    return AssessmentPage(workspace=name, items=items, next_after=rows[-1][0] if rows else after)
