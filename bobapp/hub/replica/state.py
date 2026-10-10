"""Link state and the latest live state (with its preview) as the hub last received them.

Both are single rows: latest wins. The live row keeps the hub receive time, so a reader can tell how
old the newest rover state is on the laptop clock without subtracting rover and laptop clocks.
"""
from __future__ import annotations

import json
import time
from typing import Any, Optional


class StateMixin:
    def set_link(self, state: dict[str, Any]) -> None:
        with self._tx():
            self.db.execute("INSERT INTO link VALUES (1, ?) ON CONFLICT(id) DO UPDATE SET json=excluded.json",
                            (json.dumps(state),))

    def get_link(self) -> Optional[dict[str, Any]]:
        row = self.db.execute("SELECT json FROM link WHERE id=1").fetchone()
        return None if row is None else json.loads(row[0])

    def set_live(self, live_json: str) -> None:
        with self._tx():
            self.db.execute("INSERT INTO live (id, json, hub_rx_wall_ns) VALUES (1, ?, ?) ON CONFLICT(id) "
                            "DO UPDATE SET json=excluded.json, hub_rx_wall_ns=excluded.hub_rx_wall_ns",
                            (live_json, time.time_ns()))

    def set_live_preview(self, preview: bytes, sha256: str) -> None:
        with self._tx():
            self.db.execute("UPDATE live SET preview=?, preview_sha256=? WHERE id=1", (preview, sha256))

    def get_live(self) -> tuple[Optional[str], Optional[int], Optional[bytes], Optional[str]]:
        """(live json, hub receive wall ns, preview bytes, preview sha256)."""
        row = self.db.execute("SELECT json, hub_rx_wall_ns, preview, preview_sha256 FROM live WHERE id=1").fetchone()
        return (None, None, None, None) if row is None else row
