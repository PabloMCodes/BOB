"""Store core: opening (epoch, edge identity), transactions, appends and reads.

Every append is one short BEGIN IMMEDIATE transaction, so `seq` is allocated safely across processes
and a crash never leaves a partial record. `lane_head` keeps `seq` monotonic within an epoch even after
a lane has been pruned empty, so a sequence number is never reused.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Iterator, Optional
from uuid import UUID, uuid4

from bobapp.contracts import APP_VERSION, BODY_LANE, Lane, LaneInfo, Record, SourceMode

from .schema import SCHEMA
from .types import RawRecord, StoreError, rover_clock


class StoreCore:
    """One connection per thread/process. `path` is the store directory."""

    def __init__(self, path: Path, edge_id: str, clock_synced: Optional[bool] = None,
                 busy_timeout_ms: int = 5000) -> None:
        self.path, self.edge_id, self.clock_synced = Path(path), edge_id, clock_synced
        self._unlink_after_commit: list[str] = []
        self.blob_dir = self.path / "blobs"
        self.blob_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.path / "store.sqlite"
        self.db = sqlite3.connect(self.db_path, timeout=busy_timeout_ms / 1000, isolation_level=None,
                                  check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=NORMAL")  # WAL: atomic on crash; fsync at checkpoints
        self.db.executescript(SCHEMA)
        with self._tx():
            row = self.db.execute("SELECT value FROM meta WHERE key='store_epoch'").fetchone()
            if row is None:
                self.db.execute("INSERT INTO meta VALUES ('store_epoch', ?), ('edge_id', ?)",
                                (str(uuid4()), edge_id))
            stored_id = self.db.execute("SELECT value FROM meta WHERE key='edge_id'").fetchone()[0]
            if stored_id != edge_id:
                raise StoreError(f"store at {self.path} belongs to edge {stored_id!r}, not {edge_id!r}")
            for lane in Lane:
                self.db.execute("INSERT OR IGNORE INTO lane_head VALUES (?, 0)", (lane.value,))
        self.store_epoch = UUID(self.db.execute("SELECT value FROM meta WHERE key='store_epoch'").fetchone()[0])
        for tmp in self.blob_dir.glob("**/*.tmp"):  # an interrupted blob write is never a blob
            tmp.unlink(missing_ok=True)

    def close(self) -> None:
        self.db.close()

    # --- transactions ---------------------------------------------------------------------------
    class _Tx:
        def __init__(self, store: StoreCore) -> None:
            self.store, self.db = store, store.db

        def __enter__(self) -> sqlite3.Connection:
            self.db.execute("BEGIN IMMEDIATE")
            return self.db

        def __exit__(self, exc_type, *_: Any) -> None:
            self.db.execute("ROLLBACK" if exc_type else "COMMIT")
            pending, self.store._unlink_after_commit = self.store._unlink_after_commit, []
            if not exc_type:  # blob files go only once their rows are gone for good
                for sha in pending:
                    self.store.blob_file(sha).unlink(missing_ok=True)

    def _tx(self) -> _Tx:
        return self._Tx(self)

    # --- appends --------------------------------------------------------------------------------
    def _append(self, body: Any, source_mode: SourceMode, run_id: Optional[str]) -> Record:
        lane = BODY_LANE.get(body.kind, Lane.CONTROL)
        seq = self.db.execute("SELECT head_seq FROM lane_head WHERE lane=?", (lane.value,)).fetchone()[0] + 1
        record = Record(app_version=APP_VERSION, msg_type="record", edge_id=self.edge_id,
                        store_epoch=self.store_epoch, lane=lane, seq=seq, run_id=run_id,
                        source_mode=source_mode, rover=rover_clock(self.clock_synced), body=body)
        text = record.model_dump_json()
        self.db.execute("INSERT INTO records VALUES (?, ?, ?, ?, ?, ?)",
                        (lane.value, seq, body.kind, record.rover.wall_ns, len(text), text))
        self.db.execute("UPDATE lane_head SET head_seq=? WHERE lane=?", (seq, lane.value))
        if body.kind == "evidence":
            self.db.execute("UPDATE blobs SET evidence_seq=? WHERE sha256=?", (seq, body.sha256))
        return record

    def append(self, body: Any, source_mode: SourceMode, run_id: Optional[str] = None) -> Record:
        """Append one record to the lane its body belongs to; returns it with its seq."""
        with self._tx():
            return self._append(body, source_mode, run_id)

    def append_many(self, items: list[tuple[Any, SourceMode, Optional[str]]]) -> list[Record]:
        """All-or-nothing append (e.g. an inspection start with its profile revision)."""
        with self._tx():
            return [self._append(*item) for item in items]

    def transaction(self) -> _Tx:
        """For multi-step command checks (e.g. 'no inspection active' + append) by the edge API."""
        return self._tx()

    def append_in_tx(self, body: Any, source_mode: SourceMode, run_id: Optional[str] = None) -> Record:
        return self._append(body, source_mode, run_id)


    # --- reads ----------------------------------------------------------------------------------
    def lane_info(self) -> dict[Lane, LaneInfo]:
        info = {}
        for lane in Lane:
            head = self.db.execute("SELECT head_seq FROM lane_head WHERE lane=?", (lane.value,)).fetchone()[0]
            oldest = self.db.execute("SELECT MIN(seq) FROM records WHERE lane=?", (lane.value,)).fetchone()[0]
            info[lane] = LaneInfo(oldest_seq=oldest, head_seq=head)
        return info

    def read(self, lane: Lane, after_seq: int, limit: int = 200) -> list[RawRecord]:
        rows = self.db.execute("SELECT seq, kind, json FROM records WHERE lane=? AND seq>? ORDER BY seq LIMIT ?",
                               (lane.value, after_seq, limit)).fetchall()
        return [RawRecord(lane, seq, kind, text) for seq, kind, text in rows]

    def iter_kind(self, kind: str, after_seq: int = 0) -> Iterator[Record]:
        lane = BODY_LANE.get(kind, Lane.CONTROL)
        for (text,) in self.db.execute("SELECT json FROM records WHERE lane=? AND kind=? AND seq>? ORDER BY seq",
                                       (lane.value, kind, after_seq)).fetchall():
            yield Record.model_validate_json(text)

    def blob_file(self, sha256: str) -> Path:  # see BlobsMixin
        raise NotImplementedError
