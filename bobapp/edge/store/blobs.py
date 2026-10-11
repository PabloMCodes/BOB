"""Evidence blobs: content-addressed by SHA-256, written atomically (temp file, fsync, rename)."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from uuid import UUID

from .types import StoreError


class BlobsMixin:
    def blob_file(self, sha256: str) -> Path:
        return self.blob_dir / sha256[:2] / f"{sha256}.jpg"

    def put_blob(self, data: bytes, media_type: str = "image/jpeg") -> str:
        """Atomic: written to a temp file, fsynced, renamed. Returns the SHA-256 address."""
        sha = hashlib.sha256(data).hexdigest()
        final = self.blob_file(sha)
        if not final.exists():
            final.parent.mkdir(exist_ok=True)
            tmp = final.with_suffix(f".{os.getpid()}.tmp")
            with open(tmp, "wb") as fh:
                fh.write(data)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, final)
        with self._tx():
            self.db.execute("INSERT OR IGNORE INTO blobs VALUES (?, ?, ?, NULL)", (sha, len(data), media_type))
        return sha

    def has_blob(self, sha256: str) -> bool:
        return self.db.execute("SELECT 1 FROM blobs WHERE sha256=?", (sha256,)).fetchone() is not None \
            and self.blob_file(sha256).exists()

    def ack_blob(self, hub_id: str, epoch: UUID, sha256: str) -> None:
        """Authenticated hub reports a hash-verified, durable copy, not just metadata."""
        if epoch != self.store_epoch:
            raise StoreError("blob receipt belongs to another store epoch")
        with self._tx():
            # Idempotent even when a retry arrives after acknowledged retention.
            if self.has_blob(sha256):
                self.db.execute("INSERT OR IGNORE INTO blob_acks VALUES (?, ?)", (hub_id, sha256))
