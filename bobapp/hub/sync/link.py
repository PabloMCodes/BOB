"""Link state shown to the frontend (plan §5.4): CONNECTED · CATCHING_UP · DISCONNECTED · NEW_STORE.

Times are hub (laptop) wall clock. A disconnected rover's state is unknown since the last contact —
never "stopped" or "idle". NEW_STORE lasts for the first catch-up of a new rover store epoch.
"""
from __future__ import annotations

import time
from enum import Enum
from typing import Any, Optional

from bobapp.contracts import Lane, SyncWelcome


class LinkState(str, Enum):
    CONNECTED = "CONNECTED"
    CATCHING_UP = "CATCHING_UP"
    DISCONNECTED = "DISCONNECTED"
    NEW_STORE = "NEW_STORE"


class LinkTracker:
    def __init__(self, replica: Any, persist_interval_s: float = 0.5) -> None:
        self.replica, self.persist_interval_ns = replica, int(persist_interval_s * 1e9)
        previous = replica.get_link() or {}
        self.state: dict[str, Any] = {
            "state": LinkState.DISCONNECTED.value, "edge_id": previous.get("edge_id"),
            "store_epoch": previous.get("store_epoch"), "last_contact_wall_ns": previous.get("last_contact_wall_ns"),
            "connected_since_wall_ns": None, "new_store_at_wall_ns": previous.get("new_store_at_wall_ns"),
            "lanes": previous.get("lanes", {}), "last_error": previous.get("last_error"),
            "rover_state": "unknown since last contact"}
        self._new_store = False
        self._last_persist = 0
        self._persist(force=True)

    def connected(self, welcome: SyncWelcome, cursors: dict[Lane, int], new_store: bool) -> None:
        now = time.time_ns()
        self._new_store = new_store
        self.state.update(edge_id=welcome.edge_id, store_epoch=str(welcome.store_epoch), last_contact_wall_ns=now,
                          connected_since_wall_ns=now, last_error=None, rover_state="live",
                          lanes={lane.value: {"committed": cursors[lane], "head_known": welcome.lanes[lane].head_seq}
                                 for lane in Lane})
        if new_store:
            self.state["new_store_at_wall_ns"] = now
        self._recompute()
        self._persist(force=True)

    def contact(self) -> None:
        self.state["last_contact_wall_ns"] = time.time_ns()
        self._persist()

    def committed(self, lane: Lane, seq: int) -> None:
        entry = self.state["lanes"].setdefault(lane.value, {"committed": 0, "head_known": 0})
        entry["committed"] = seq
        entry["head_known"] = max(entry["head_known"], seq)
        self.contact()
        self._recompute()

    def disconnected(self, error: Optional[BaseException]) -> None:
        if self.state["state"] != LinkState.DISCONNECTED.value or error is not None:
            self.state.update(state=LinkState.DISCONNECTED.value, connected_since_wall_ns=None,
                              rover_state="unknown since last contact",
                              last_error=None if error is None else f"{type(error).__name__}: {error}"[:300])
            self._persist(force=True)

    def _recompute(self) -> None:
        behind = {lane: max(0, e["head_known"] - e["committed"]) for lane, e in self.state["lanes"].items()}
        for lane, n in behind.items():
            self.state["lanes"][lane]["behind"] = n
        previous = self.state["state"]
        if any(behind.values()):
            self.state["state"] = (LinkState.NEW_STORE if self._new_store else LinkState.CATCHING_UP).value
        else:
            self._new_store = False
            self.state["state"] = LinkState.CONNECTED.value
        if self.state["state"] != previous:
            self._persist(force=True)

    def _persist(self, force: bool = False) -> None:
        now = time.monotonic_ns()
        if force or now - self._last_persist >= self.persist_interval_ns:
            self._last_persist = now
            self.replica.set_link(self.state)
