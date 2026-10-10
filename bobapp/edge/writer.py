"""Bounded hand-off from the frame consumer to the edge store (same pattern as vision.scene.SceneWriter).

`submit_*` never blocks and never raises on overload: a full queue drops the item and counts it.
Work items run on the writer thread, so JPEG encoding, hashing and disk I/O never delay inference.
Control items (evidence, notices) have their own queue and go first; observations, track points and
the preview are dropped first when storage is slow. A drop is reported in live status at once and as
a `writer_dropped` notice record as soon as the store keeps up again.

`blocking=True` is for offline replay only (not real-time): submits wait instead of dropping, so a
replayed store is complete and deterministic.
"""
from __future__ import annotations

import queue
import threading
import time
from typing import Any, Callable, Optional

from bobapp.contracts import NoticeBody, SourceMode

from .store import EdgeStore

WorkItem = Callable[[EdgeStore], None]


class EdgeWriter:
    def __init__(self, store: EdgeStore, source_mode: SourceMode, run_id: Optional[str] = None,
                 control_capacity: int = 32, data_capacity: int = 64,
                 retention: Optional[dict[str, Any]] = None, blocking: bool = False) -> None:
        if control_capacity < 1 or data_capacity < 1:
            raise ValueError("writer capacities must be positive")
        self.store, self.source_mode, self.run_id = store, SourceMode(source_mode), run_id
        self.retention, self.blocking = retention, blocking
        self.control: queue.Queue[WorkItem] = queue.Queue(maxsize=control_capacity)
        self.data: queue.Queue[WorkItem] = queue.Queue(maxsize=data_capacity)
        self.closed = threading.Event()
        self.lock = threading.Lock()
        self.written = self.errors = 0
        self.dropped = {"control": 0, "data": 0}
        self._unreported = {"control": 0, "data": 0}
        self.last_error: Optional[str] = None
        self._last_prune = 0.0
        self.thread = threading.Thread(target=self._run, daemon=True, name="edge-writer")
        self.thread.start()

    def submit_control(self, item: WorkItem) -> bool:
        return self._submit(self.control, "control", item)

    def submit_data(self, item: WorkItem) -> bool:
        return self._submit(self.data, "data", item)

    def _submit(self, q: queue.Queue, name: str, item: WorkItem) -> bool:
        if self.closed.is_set():
            raise RuntimeError("edge writer is closed")
        if self.blocking:
            q.put(item)
            return True
        with self.lock:
            if self.closed.is_set():
                raise RuntimeError("edge writer is closed")
            try:
                q.put_nowait(item)
                return True
            except queue.Full:
                self.dropped[name] += 1
                self._unreported[name] += 1
                return False

    def _next(self) -> Optional[WorkItem]:
        try:
            return self.control.get_nowait()
        except queue.Empty:
            pass
        try:
            return self.data.get(timeout=.05)
        except queue.Empty:
            return None

    def _run(self) -> None:
        while not self.closed.is_set() or not (self.control.empty() and self.data.empty()):
            item = self._next()
            if item is not None:
                self._do(item)
            elif not self.closed.is_set():
                self._report_drops()
                self._maybe_prune()
        self._report_drops()

    def _do(self, item: WorkItem) -> None:
        try:
            item(self.store)
            with self.lock:
                self.written += 1
        except Exception as exc:  # full disk, locked db, encoding error: counted, never raised upstream
            with self.lock:
                self.errors += 1
                self.last_error = f"{type(exc).__name__}: {exc}"

    def _report_drops(self) -> None:
        with self.lock:
            dropped, self._unreported = self._unreported, {"control": 0, "data": 0}
        if any(dropped.values()):
            self._do(lambda store: store.append(NoticeBody(
                kind="notice", code="writer_dropped",
                message="Edge storage could not keep up; some records were not stored",
                details={"dropped_since_last_notice": dropped}), self.source_mode, self.run_id))

    def _maybe_prune(self) -> None:
        if not self.retention or time.monotonic() - self._last_prune < self.retention["prune_interval_s"]:
            return
        self._last_prune = time.monotonic()
        r = self.retention
        self._do(lambda store: store.prune(r["acked_max_age_s"], r["max_store_bytes"], r["min_free_disk_bytes"],
                                           source_mode=self.source_mode))

    def stats(self) -> dict[str, Any]:
        with self.lock:
            return {"written": self.written, "dropped": dict(self.dropped), "write_errors": self.errors,
                    "queued": self.control.qsize() + self.data.qsize(), "last_error": self.last_error,
                    "worker_running": self.thread.is_alive()}

    def close(self, timeout: float = 2.) -> dict[str, Any]:
        """Stop accepting work, finish what is queued (bounded by `timeout`) and report what is left."""
        with self.lock:
            self.closed.set()
        self.thread.join(timeout=timeout)
        return self.stats()
