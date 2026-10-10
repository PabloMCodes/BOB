"""Acknowledgments, retention and disk-pressure pruning with explicit gap records (plan §5.4, D4)."""
from __future__ import annotations

import shutil
import time
from typing import Optional

from bobapp.contracts import GapBody, GapReason, Lane, SourceMode

from .types import StoreError


class RetentionMixin:
    def ack(self, hub_id: str, lane: Lane, seq: int) -> None:
        """Acknowledgments only move forward (a replayed, older ack never un-acknowledges)."""
        with self._tx():
            head = self.db.execute("SELECT head_seq FROM lane_head WHERE lane=?", (lane.value,)).fetchone()[0]
            if seq > head:
                raise StoreError(f"ack {lane.value}:{seq} beyond head {head}")
            self.db.execute("INSERT INTO acks VALUES (?, ?, ?) ON CONFLICT(hub_id, lane) DO UPDATE "
                            "SET seq=MAX(seq, excluded.seq)", (hub_id, lane.value, seq))

    def acked_seq(self, lane: Lane) -> int:
        """Lowest acknowledgment over the hubs that have ever acknowledged (0 = none)."""
        row = self.db.execute("SELECT MIN(seq) FROM acks WHERE lane=?", (lane.value,)).fetchone()
        return row[0] or 0

    def size_bytes(self) -> int:
        files = [self.db_path, self.db_path.with_name("store.sqlite-wal")]
        db = sum(f.stat().st_size for f in files if f.exists())
        return db + (self.db.execute("SELECT COALESCE(SUM(size), 0) FROM blobs").fetchone()[0])

    def disk_free_bytes(self) -> int:
        return shutil.disk_usage(self.path).free

    def prune(self, acked_max_age_s: float, max_store_bytes: int, min_free_disk_bytes: int,
              now_wall_ns: Optional[int] = None, source_mode: SourceMode = SourceMode.LIVE) -> dict[str, int]:
        """Retention: delete acknowledged records older than the age limit. Disk pressure: delete the
        oldest observation records (then track points), acknowledged or not, writing a gap record for
        any unacknowledged range. Control records (incidents, evidence) are never pruned unacknowledged."""
        now = time.time_ns() if now_wall_ns is None else now_wall_ns
        cutoff = now - int(acked_max_age_s * 1e9)
        removed = {"retention": 0, "pressure": 0}
        with self._tx():
            for lane in Lane:
                acked = self.acked_seq(lane)
                removed["retention"] += self._delete(lane, "seq<=? AND wall_ns<?", (acked, cutoff))
        for lane in (Lane.OBSERVATION, Lane.TRACK):
            while self._under_pressure(max_store_bytes, min_free_disk_bytes):
                n = self._prune_oldest(lane, 500, source_mode)
                if not n:
                    break
                removed["pressure"] += n
        if removed["retention"] or removed["pressure"]:
            self.db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        return removed

    def _under_pressure(self, max_store_bytes: int, min_free_disk_bytes: int) -> bool:
        return self.size_bytes() > max_store_bytes or self.disk_free_bytes() < min_free_disk_bytes

    def _delete(self, lane: Lane, where: str, args: tuple) -> int:
        if lane == Lane.CONTROL:
            seqs = [s for (s,) in self.db.execute(f"SELECT seq FROM records WHERE lane=? AND kind='evidence' AND {where}",
                                                   (lane.value, *args))]
            for (sha,) in self.db.execute(f"SELECT sha256 FROM blobs WHERE evidence_seq IN ({','.join('?' * len(seqs))})",
                                          seqs).fetchall() if seqs else []:
                self.db.execute("DELETE FROM blobs WHERE sha256=?", (sha,))
                self._unlink_after_commit.append(sha)
        return self.db.execute(f"DELETE FROM records WHERE lane=? AND {where}", (lane.value, *args)).rowcount

    def _prune_oldest(self, lane: Lane, count: int, source_mode: SourceMode) -> int:
        with self._tx():
            rows = self.db.execute("SELECT seq FROM records WHERE lane=? ORDER BY seq LIMIT ?",
                                   (lane.value, count)).fetchall()
            if not rows:
                return 0
            first, last = rows[0][0], rows[-1][0]
            acked = self.acked_seq(lane)
            if last > acked:  # someone has not received part of this range: say so explicitly
                self._append(GapBody(kind="gap", lane=lane, first_seq=max(first, acked + 1), last_seq=last,
                                     reason=GapReason.PRUNED_DISK_PRESSURE), source_mode, None)
            return self._delete(lane, "seq BETWEEN ? AND ?", (first, last))
