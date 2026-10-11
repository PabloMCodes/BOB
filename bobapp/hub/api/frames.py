"""Saved model frames, including automatic backfill. Never substituted for live preview."""
import json
from typing import Optional, Any

from fastapi import APIRouter, Query
from pydantic import BaseModel

from bobapp.contracts import BlobStatusValue, Delivery
from .models.common import Item, WorkspaceName, CLOCK_DOMAINS
from .views import _item


class FrameItem(Item):
    image_status: BlobStatusValue
    site_photo: Optional[dict[str, Any]] = None


class FramePage(BaseModel):
    workspace: WorkspaceName
    items: list[FrameItem]
    next_after: int
    clock_domains: dict[str, str] = CLOCK_DOMAINS


def frame_router(replica, deps):
    router = APIRouter(dependencies=deps)

    @router.get("/v1/frames", response_model=FramePage)
    def frames(workspace: WorkspaceName = "rover", after: int = Query(0, ge=0),
               before: Optional[int] = Query(None, ge=1), limit: int = Query(12, ge=1, le=100),
               delivery: Optional[Delivery] = None, session_id: Optional[str] = None,
               latest: bool = True, site_only: bool = False):
        r = replica(workspace)
        ws = r.active_workspace()
        if ws is None:
            return FramePage(workspace=workspace, items=[], next_after=after)
        conditions = ["ws_id=?", "kind='observation'", "rowid>?",
                      "json_extract(json, '$.body.evidence_sha256') IS NOT NULL"]
        args = [ws.ws_id, after]
        if before is not None:
            conditions.append("rowid<?")
            args.append(before)
        if delivery:
            conditions.append("delivery=?")
            args.append(delivery.value)
        if session_id:
            conditions.append("json_extract(json, '$.body.event.session_id')=?")
            args.append(session_id)
        selection_query = ("SELECT n.json FROM records n WHERE n.ws_id=records.ws_id AND n.kind='notice' "
                           "AND json_extract(n.json, '$.body.code')='site_photo' "
                           "AND json_extract(n.json, '$.body.details.source_event_id')="
                           "json_extract(records.json, '$.body.event.event_id') "
                           "AND json_extract(n.json, '$.body.details.evidence_sha256')="
                           "json_extract(records.json, '$.body.evidence_sha256')")
        if site_only:
            conditions.append("EXISTS (" + selection_query + ")")
        order = "DESC" if latest else "ASC"
        rows = r.db.execute("SELECT rowid, delivery, hub_rx_wall_ns, json, (" + selection_query + " LIMIT 1) FROM records WHERE " +
                            " AND ".join(conditions) + f" ORDER BY rowid {order} LIMIT ?", (*args, limit)).fetchall()
        if latest:
            rows.reverse()
        items = []
        for row in rows:
            item = _item(row[:4])
            selection = json.loads(row[4])["body"]["details"] if row[4] else None
            items.append(FrameItem(**item.model_dump(), site_photo=selection,
                image_status=r.blob_status(item.record.body.evidence_sha256) or BlobStatusValue.MISSING))
        return FramePage(workspace=workspace, items=items, next_after=rows[-1][0] if rows else after)

    return router


def frame_counts(replica, ws):
    counts = {"total": 0, "available": 0, "pending_sync": 0, "missing": 0,
              "hash_mismatch": 0, "backfilled": 0}
    if ws is None:
        return counts
    rows = replica.db.execute("SELECT COALESCE(b.status, 'missing'), r.delivery, COUNT(*) "
                              "FROM records r LEFT JOIN blobs b "
                              "ON b.sha256=json_extract(r.json, '$.body.evidence_sha256') "
                              "WHERE r.ws_id=? AND r.kind='observation' "
                              "AND json_extract(r.json, '$.body.evidence_sha256') IS NOT NULL "
                              "GROUP BY b.status, r.delivery", (ws.ws_id,)).fetchall()
    for status, delivery, count in rows:
        counts["total"] += count
        counts[status] += count
        if delivery == "backfilled":
            counts["backfilled"] += count
    return counts
