"""Worksite profile authoring on the hub (plan §4): every save creates a new immutable revision.

Works while the rover is offline. A save never touches a running inspection: revisions apply only
when an operator explicitly starts the next inspection. Concurrent editors are caught by the
expected revision (optimistic concurrency -> HTTP 409).
"""
from __future__ import annotations

import time
from typing import Optional

from bobapp.contracts import WorksiteProfile


class RevisionConflict(Exception):
    def __init__(self, current: int) -> None:
        super().__init__(f"the latest revision is {current}; reload before saving")
        self.current = current


class ProfilesMixin:
    def latest_revision(self, worksite_id: str) -> int:
        row = self.db.execute("SELECT MAX(revision) FROM worksite_revisions WHERE worksite_id=?", (worksite_id,)).fetchone()
        return row[0] or 0

    def save_profile(self, worksite_id: str, expected_revision: int, name: str,
                     requirements: dict[str, bool]) -> WorksiteProfile:
        """Save revision expected_revision + 1 (0 creates the worksite)."""
        with self._tx():
            current = self.latest_revision(worksite_id)
            if current != expected_revision:
                raise RevisionConflict(current)
            profile = WorksiteProfile.build(worksite_id, current + 1, name, requirements)
            self.db.execute("INSERT INTO worksite_revisions VALUES (?, ?, ?, ?, ?)", (
                worksite_id, profile.revision, profile.sha256, profile.model_dump_json(), time.time_ns()))
            return profile

    def profile_revision(self, worksite_id: str, revision: Optional[int] = None) -> Optional[WorksiteProfile]:
        revision = revision or self.latest_revision(worksite_id)
        row = self.db.execute("SELECT json FROM worksite_revisions WHERE worksite_id=? AND revision=?",
                              (worksite_id, revision)).fetchone()
        return None if row is None else WorksiteProfile.model_validate_json(row[0])

    def worksite_ids(self) -> list[str]:
        return [r[0] for r in self.db.execute("SELECT DISTINCT worksite_id FROM worksite_revisions ORDER BY worksite_id")]
