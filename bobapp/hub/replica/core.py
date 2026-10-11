"""Replica core: workspaces (one per rover store epoch), idempotent commits, contiguous cursors, gaps.

A batch is committed in one transaction before it is acknowledged. Replayed records are ignored by the
`(workspace, lane, seq)` key, so delivery is at-least-once without inflating anything. A seq range the
hub can never receive (pruned on the rover first) becomes an explicit gap row; the cursor moves past it
so acknowledgment continues, and the UI shows the hole instead of closing it silently.
"""
from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional
from uuid import UUID

from bobapp.contracts import Delivery, Lane, LaneInfo, Record

from .schema import SCHEMA

PRUNED_BEFORE_SYNC = "pruned_before_sync"


@dataclass(frozen=True)
class Workspace:
    ws_id: int
    edge_id: str
    store_epoch: UUID
    archived: bool = False


@dataclass(frozen=True)
class CommitResult:
    committed_seq: int     # highest contiguous seq (gaps accounted) — what the hub acknowledges
    inserted: int          # new records (replays are 0)
    gaps: list[tuple[int, int]]


class ReplicaCore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.blob_dir = self.path / "blobs"
        self.blob_dir.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path / "replica.sqlite", timeout=5, isolation_level=None,
                                  check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=NORMAL")
        self.db.executescript(SCHEMA)
        with self._tx():
            if self.db.execute("SELECT 1 FROM replica_meta WHERE key='blob_receipts_v1'").fetchone() is None:
                self.db.execute("INSERT OR IGNORE INTO blob_receipts (ws_id, sha256) SELECT ws_id, "
                                "CASE kind WHEN 'evidence' THEN json_extract(json, '$.body.sha256') "
                                "ELSE json_extract(json, '$.body.evidence_sha256') END FROM records "
                                "WHERE kind IN ('evidence', 'observation') AND COALESCE("
                                "json_extract(json, '$.body.sha256'), json_extract(json, '$.body.evidence_sha256')) IS NOT NULL")
                self.db.execute("INSERT OR IGNORE INTO blobs (sha256, status, updated_wall_ns) "
                                "SELECT DISTINCT sha256, 'pending_sync', ? FROM blob_receipts", (time.time_ns(),))
                self.db.execute("INSERT INTO replica_meta VALUES ('blob_receipts_v1', '1')")

    def close(self) -> None:
        self.db.close()

    class _Tx:
        def __init__(self, db: sqlite3.Connection) -> None:
            self.db = db

        def __enter__(self) -> sqlite3.Connection:
            self.db.execute("BEGIN IMMEDIATE")
            return self.db

        def __exit__(self, exc_type, *_: Any) -> None:
            self.db.execute("ROLLBACK" if exc_type else "COMMIT")

    def _tx(self) -> _Tx:
        return self._Tx(self.db)

    # --- workspaces -----------------------------------------------------------------------------
    def _ws(self, row: tuple) -> Workspace:
        return Workspace(row[0], row[1], UUID(row[2]), row[3] is not None)

    def active_workspace(self) -> Optional[Workspace]:
        row = self.db.execute("SELECT ws_id, edge_id, store_epoch, archived_wall_ns FROM workspaces "
                              "WHERE archived_wall_ns IS NULL ORDER BY ws_id DESC LIMIT 1").fetchone()
        return None if row is None else self._ws(row)

    def workspaces(self) -> list[Workspace]:
        rows = self.db.execute("SELECT ws_id, edge_id, store_epoch, archived_wall_ns FROM workspaces ORDER BY ws_id")
        return [self._ws(r) for r in rows.fetchall()]

    def adopt(self, edge_id: str, store_epoch: UUID) -> tuple[Workspace, bool]:
        """Make (edge_id, store_epoch) the active workspace. Returns (workspace, changed). Any other
        active workspace is archived (kept read-only), never merged into this one."""
        with self._tx():
            active = self.active_workspace()
            if active is not None and (active.edge_id, active.store_epoch) == (edge_id, store_epoch):
                return active, False
            now = time.time_ns()
            self.db.execute("UPDATE workspaces SET archived_wall_ns=? WHERE archived_wall_ns IS NULL", (now,))
            self.db.execute("INSERT INTO workspaces (edge_id, store_epoch, created_wall_ns) VALUES (?, ?, ?) "
                            "ON CONFLICT(edge_id, store_epoch) DO UPDATE SET archived_wall_ns=NULL",
                            (edge_id, str(store_epoch), now))
            row = self.db.execute("SELECT ws_id, edge_id, store_epoch, archived_wall_ns FROM workspaces "
                                  "WHERE edge_id=? AND store_epoch=?", (edge_id, str(store_epoch))).fetchone()
            return self._ws(row), True

    # --- cursors, commits, gaps -----------------------------------------------------------------
    def cursors(self, ws: Optional[Workspace]) -> dict[Lane, int]:
        found = {} if ws is None else dict(self.db.execute(
            "SELECT lane, committed_seq FROM cursors WHERE ws_id=?", (ws.ws_id,)).fetchall())
        return {lane: found.get(lane.value, 0) for lane in Lane}

    def _cursor(self, ws: Workspace, lane: Lane) -> int:
        row = self.db.execute("SELECT committed_seq FROM cursors WHERE ws_id=? AND lane=?", (ws.ws_id, lane.value)).fetchone()
        return row[0] if row else 0

    def _set_cursor(self, ws: Workspace, lane: Lane, seq: int) -> None:
        self.db.execute("INSERT INTO cursors VALUES (?, ?, ?) ON CONFLICT(ws_id, lane) DO UPDATE SET "
                        "committed_seq=MAX(committed_seq, excluded.committed_seq)", (ws.ws_id, lane.value, seq))

    def _gap(self, ws: Workspace, lane: Lane, first: int, last: int) -> None:
        self.db.execute("INSERT OR IGNORE INTO gaps VALUES (?, ?, ?, ?, ?, ?)",
                        (ws.ws_id, lane.value, first, last, PRUNED_BEFORE_SYNC, time.time_ns()))

    def reconcile_welcome(self, ws: Workspace, lanes: dict[Lane, LaneInfo]) -> dict[Lane, int]:
        """Ranges older than the rover's oldest retained record can never arrive: record them as gaps
        now (also when a lane was pruned empty). Returns cursors that moved, to acknowledge."""
        moved = {}
        with self._tx():
            for lane, info in lanes.items():
                cursor = self._cursor(ws, lane)
                end = (info.oldest_seq - 1) if info.oldest_seq is not None else info.head_seq
                if end > cursor:
                    self._gap(ws, lane, cursor + 1, end)
                    self._set_cursor(ws, lane, end)
                    moved[lane] = end
        return moved

    def commit(self, ws: Workspace, lane: Lane, records: list[Record], delivery: Delivery,
               raw: Optional[list[str]] = None) -> CommitResult:
        rx = time.time_ns()
        inserted, gaps = 0, []
        with self._tx():
            cursor = self._cursor(ws, lane)
            for i, record in enumerate(records):
                if (record.edge_id, record.store_epoch) != (ws.edge_id, ws.store_epoch):
                    raise ValueError("record from another store: never merged")
                text = raw[i] if raw else record.model_dump_json()
                inserted += self.db.execute("INSERT OR IGNORE INTO records VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                                            (ws.ws_id, lane.value, record.seq, record.body.kind,
                                             record.source_mode.value, Delivery(delivery).value, rx, text)).rowcount
                sha = (record.body.sha256 if record.body.kind == "evidence" else
                       record.body.evidence_sha256 if record.body.kind == "observation" else None)
                if sha:
                    self.db.execute("INSERT OR IGNORE INTO blobs (sha256, status, updated_wall_ns) "
                                    "VALUES (?, 'pending_sync', ?)", (sha, rx))
                    self.db.execute("INSERT OR IGNORE INTO blob_receipts (ws_id, sha256) VALUES (?, ?)",
                                    (ws.ws_id, sha))
                if record.seq <= cursor:
                    continue  # a replay of something already committed
                if record.seq > cursor + 1:
                    self._gap(ws, lane, cursor + 1, record.seq - 1)
                    gaps.append((cursor + 1, record.seq - 1))
                cursor = record.seq
            self._set_cursor(ws, lane, cursor)
        return CommitResult(cursor, inserted, gaps)

    # --- reads ----------------------------------------------------------------------------------
    def records(self, ws: Workspace, lane: Optional[Lane] = None, kind: Optional[str] = None,
                after_rowid: int = 0, limit: int = 1000) -> list[tuple[int, str, str]]:
        """(rowid, delivery, record json) in arrival order."""
        sql, args = "SELECT rowid, delivery, json FROM records WHERE ws_id=? AND rowid>?", [ws.ws_id, after_rowid]
        if lane is not None:
            sql, args = sql + " AND lane=?", args + [lane.value]
        if kind is not None:
            sql, args = sql + " AND kind=?", args + [kind]
        return self.db.execute(sql + " ORDER BY rowid LIMIT ?", (*args, limit)).fetchall()

    def counts(self, ws: Workspace) -> dict[str, int]:
        return dict(self.db.execute("SELECT lane, COUNT(*) FROM records WHERE ws_id=? GROUP BY lane",
                                    (ws.ws_id,)).fetchall())

    def gaps(self, ws: Workspace) -> list[dict[str, Any]]:
        rows = self.db.execute("SELECT lane, first_seq, last_seq, reason, detected_wall_ns FROM gaps WHERE ws_id=? "
                               "ORDER BY lane, first_seq", (ws.ws_id,)).fetchall()
        return [dict(zip(("lane", "first_seq", "last_seq", "reason", "detected_wall_ns"), r)) for r in rows]

    def query(self, ws: Workspace, kinds: tuple[str, ...], after_rowid: int = 0, limit: int = 100,
              where: Optional[dict[str, str]] = None, source_mode: Optional[str] = None,
              delivery: Optional[str] = None, newest: bool = False,
              before_rowid: Optional[int] = None) -> list[tuple[int, str, int, str]]:
        """Paged history: (rowid, delivery, hub_rx_wall_ns, json) in arrival order. `where` maps a fixed
        JSON path (from code, never from the request) to the value it must equal."""
        sql = (f"SELECT rowid, delivery, hub_rx_wall_ns, json FROM records WHERE ws_id=? AND rowid>? "
               f"AND kind IN ({','.join('?' * len(kinds))})")
        args: list[Any] = [ws.ws_id, after_rowid, *kinds]
        for path, value in (where or {}).items():
            sql, args = sql + " AND json_extract(json, ?) = ?", args + [path, value]
        if source_mode is not None:
            sql, args = sql + " AND source_mode=?", args + [source_mode]
        if delivery is not None:
            sql, args = sql + " AND delivery=?", args + [delivery]
        if before_rowid is not None:
            sql, args = sql + " AND rowid<?", args + [before_rowid]
        rows = self.db.execute(sql + (" ORDER BY rowid DESC LIMIT ?" if newest else " ORDER BY rowid LIMIT ?"),
                               (*args, limit)).fetchall()
        return list(reversed(rows)) if newest else rows

    def max_rowid(self, ws: Workspace) -> int:
        return self.db.execute("SELECT COALESCE(MAX(rowid), 0) FROM records WHERE ws_id=?", (ws.ws_id,)).fetchone()[0]
