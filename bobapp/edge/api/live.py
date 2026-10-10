"""LiveState from the store's live row: rover-monotonic feed times become ages; unknown is null + reason."""
from __future__ import annotations

import time
from typing import Any, Optional

from bobapp.contracts import (
    APP_VERSION,
    Capabilities,
    EdgeStatus,
    FeedAge,
    Freshness,
    LivePose,
    LiveState,
    PreviewRef,
    SourceMode,
)
from bobapp.edge.publish.live import FEEDS, producers
from bobapp.edge.store import EdgeStore, rover_clock
from vision.schema import StreamHealth

NO_RUN = "no vision.server run has published to this store"


def _age(mono_ns: Optional[int], now: int, feed: str) -> FeedAge:
    if mono_ns is None:
        return FeedAge(reason=f"no {feed} in the last run")
    return FeedAge(age_ms=max(0, now - mono_ns) / 1e6)


def build_live_state(store: EdgeStore, clock_synced: Optional[bool] = None) -> tuple[LiveState, Optional[bytes]]:
    snapshot, preview = store.get_live()
    now = time.monotonic_ns()
    active = store.active_inspection()
    edge: dict[str, Any] = {"store_bytes": store.size_bytes(), "disk_free_bytes": store.disk_free_bytes()}
    if snapshot is None:
        state = LiveState(
            app_version=APP_VERSION, msg_type="live_state", edge_id=store.edge_id, store_epoch=store.store_epoch,
            rover=rover_clock(clock_synced), freshness=Freshness(**{f: FeedAge(reason=NO_RUN) for f in FEEDS}),
            capabilities=Capabilities(rules=[], producers=producers(zones_enabled=False)),
            active_inspection_id=active.inspection_id if active else None, edge=EdgeStatus(**edge))
        return state, None
    running = snapshot["running"]
    if running and snapshot["edge"]:
        edge.update({k: snapshot["edge"][k] for k in ("writer_queued", "writer_dropped", "writer_errors", "last_error")})
    state = LiveState(
        app_version=APP_VERSION, msg_type="live_state", edge_id=store.edge_id, store_epoch=store.store_epoch,
        run_id=snapshot["run_id"] if running else None,
        source_mode=SourceMode(snapshot["source_mode"]) if running else None,
        rover=rover_clock(clock_synced),
        preview=PreviewRef(**snapshot["preview"]) if snapshot["preview"] else None,
        pose=LivePose(**snapshot["pose"]) if snapshot["pose"] else None,
        health=StreamHealth.model_validate(snapshot["health"]) if snapshot["health"] else None,
        freshness=Freshness(**{f: _age(snapshot["feeds_mono_ns"][f], now, f) for f in FEEDS}),
        capabilities=Capabilities(**snapshot["capabilities"]),
        active_inspection_id=active.inspection_id if active else None,
        edge=EdgeStatus(**edge))
    return state, preview
