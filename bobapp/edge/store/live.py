"""Live snapshot: one row, latest wins, never backfilled or kept as a lane record (plan §5.3).

The snapshot carries rover-monotonic times of the newest frame, result, pose and health; readers turn
them into ages, so a crashed producer shows growing ages instead of a frozen "fresh" state.
"""
from __future__ import annotations

import json
from typing import Any, Optional


class LiveMixin:
    def put_live(self, snapshot: dict[str, Any], preview: Optional[bytes] = None,
                 preview_sha256: Optional[str] = None) -> None:
        """Replace the snapshot; the stored preview is kept unless a new one is given."""
        text = json.dumps(snapshot)
        with self._tx():
            if preview is None:
                self.db.execute("INSERT INTO live (id, json) VALUES (1, ?) "
                                "ON CONFLICT(id) DO UPDATE SET json=excluded.json", (text,))
            else:
                self.db.execute("INSERT INTO live VALUES (1, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET "
                                "json=excluded.json, preview=excluded.preview, preview_sha256=excluded.preview_sha256",
                                (text, preview, preview_sha256))

    def get_live(self) -> tuple[Optional[dict[str, Any]], Optional[bytes]]:
        row = self.db.execute("SELECT json, preview FROM live WHERE id=1").fetchone()
        return (None, None) if row is None else (json.loads(row[0]), row[1])
