"""Saved model frames, including automatic backfill. Never substituted for live preview."""
from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from bobapp.contracts import BlobStatusValue, Delivery
from .models.common import Item, WorkspaceName, CLOCK_DOMAINS
from .views import _item


class FrameItem(Item):
    image_status: BlobStatusValue


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
               latest: bool = True):
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
        order = "DESC" if latest else "ASC"
        rows = r.db.execute("SELECT rowid, delivery, hub_rx_wall_ns, json FROM records WHERE " +
                            " AND ".join(conditions) + f" ORDER BY rowid {order} LIMIT ?", (*args, limit)).fetchall()
        if latest:
            rows.reverse()
        items = []
        for row in rows:
            item = _item(row)
            items.append(FrameItem(**item.model_dump(),
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
