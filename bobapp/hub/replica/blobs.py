"""Evidence copies on the laptop: fetched from the rover by hash, verified, written atomically.

Status per hash: pending_sync (metadata arrived, image not yet), available, missing (the rover no
longer has it), hash_mismatch (bytes did not match their address; never stored as evidence).
"""
from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path
from typing import Optional

from bobapp.contracts import BlobStatusValue


class BlobsMixin:
    def blob_file(self, sha256: str) -> Path:
        return self.blob_dir / sha256[:2] / f"{sha256}.jpg"

    def pending_blobs(self, limit: int = 50, retry_after_ns: int = 0) -> list[str]:
        cutoff = time.time_ns() - retry_after_ns
        rows = self.db.execute("SELECT sha256 FROM blobs WHERE status IN ('pending_sync', 'hash_mismatch') AND "
                               "(attempts=0 OR updated_wall_ns<?) ORDER BY rowid LIMIT ?", (cutoff, limit))
        return [r[0] for r in rows.fetchall()]

    def store_blob(self, sha256: str, data: bytes) -> BlobStatusValue:
        """Verify the bytes against their address, then write atomically and mark available."""
        if hashlib.sha256(data).hexdigest() != sha256:
            self.mark_blob(sha256, BlobStatusValue.HASH_MISMATCH, error="content does not match its SHA-256")
            return BlobStatusValue.HASH_MISMATCH
        final = self.blob_file(sha256)
        final.parent.mkdir(exist_ok=True)
        tmp = final.with_suffix(f".{os.getpid()}.tmp")
        with open(tmp, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, final)
        self.mark_blob(sha256, BlobStatusValue.AVAILABLE, size=len(data))
        return BlobStatusValue.AVAILABLE

    def mark_blob(self, sha256: str, status: BlobStatusValue, size: Optional[int] = None,
                  error: Optional[str] = None) -> None:
        with self._tx():
            self.db.execute("UPDATE blobs SET status=?, size=COALESCE(?, size), attempts=attempts+1, last_error=?, "
                            "updated_wall_ns=? WHERE sha256=?",
                            (BlobStatusValue(status).value, size, error, time.time_ns(), sha256))

    def retry_later(self, sha256: str, error: str) -> None:
        with self._tx():
            self.db.execute("UPDATE blobs SET attempts=attempts+1, last_error=?, updated_wall_ns=? WHERE sha256=?",
                            (error, time.time_ns(), sha256))

    def blob_status(self, sha256: str) -> Optional[BlobStatusValue]:
        row = self.db.execute("SELECT status FROM blobs WHERE sha256=?", (sha256,)).fetchone()
        if row is None:
            return None
        if row[0] == BlobStatusValue.AVAILABLE.value and not self.blob_file(sha256).exists():
            return BlobStatusValue.MISSING
        return BlobStatusValue(row[0])

    def blob_counts(self) -> dict[str, int]:
        return dict(self.db.execute("SELECT status, COUNT(*) FROM blobs GROUP BY status").fetchall())

    def pending_receipts(self, ws, limit=20) -> list[str]:
        rows = self.db.execute("SELECT r.sha256 FROM blob_receipts r JOIN blobs b USING(sha256) "
                               "WHERE r.ws_id=? AND r.acknowledged=0 AND b.status='available' LIMIT ?",
                               (ws.ws_id, limit)).fetchall()
        return [sha for (sha,) in rows if self.blob_file(sha).exists()]

    def acknowledge_blob(self, ws, sha):
        with self._tx():
            self.db.execute("UPDATE blob_receipts SET acknowledged=1 WHERE ws_id=? AND sha256=?", (ws.ws_id, sha))
