"""Profile revisions and the inspection lifecycle on the rover (plan §4, D3).

State tables mirror the append-only control records so the active inspection survives retention
pruning of its start record. Every command is one transaction: checks and appends commit together.
At most one inspection is active (also enforced by a unique index).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from uuid import UUID, uuid4

from bobapp.contracts import (
    InspectionEndedBody,
    InspectionEndReason,
    InspectionStartedBody,
    ProfileRevisionBody,
    Record,
    SourceMode,
    WorksiteProfile,
)


class CommandRefused(Exception):
    """A command that conflicts with the store's state (HTTP 409)."""


class NotFound(Exception):
    """HTTP 404."""


@dataclass(frozen=True)
class ActiveInspection:
    inspection_id: UUID
    worksite_id: str
    profile_revision: int
    profile_sha256: str
    source_mode: SourceMode
    profile: WorksiteProfile


class InspectionsMixin:
    def _deliver_profile(self, profile: WorksiteProfile, source_mode: SourceMode) -> Optional[Record]:
        row = self.db.execute("SELECT sha256 FROM profiles WHERE worksite_id=? AND revision=?",
                              (profile.worksite_id, profile.revision)).fetchone()
        if row is not None:
            if row[0] != profile.sha256:
                raise CommandRefused(f"{profile.worksite_id} revision {profile.revision} already exists "
                                     "with different content; revisions are immutable")
            return None  # idempotent re-delivery
        self.db.execute("INSERT INTO profiles VALUES (?, ?, ?, ?)", (profile.worksite_id, profile.revision,
                                                                    profile.sha256, profile.model_dump_json()))
        return self._append(ProfileRevisionBody(kind="profile_revision", profile=profile), source_mode, None)

    def deliver_profile(self, profile: WorksiteProfile, source_mode: SourceMode) -> Optional[Record]:
        """Store an immutable revision (None if this exact revision is already stored)."""
        with self._tx():
            return self._deliver_profile(profile, source_mode)

    def profile(self, worksite_id: str, revision: int) -> Optional[WorksiteProfile]:
        row = self.db.execute("SELECT json FROM profiles WHERE worksite_id=? AND revision=?",
                              (worksite_id, revision)).fetchone()
        return None if row is None else WorksiteProfile.model_validate_json(row[0])

    def start_inspection(self, profile: WorksiteProfile, source_mode: SourceMode,
                         requested_by: Optional[str] = None, inspection_id: Optional[UUID] = None) -> Record:
        """Bind a new inspection to exactly this profile revision. Refused while another is active."""
        inspection_id = inspection_id or uuid4()
        with self._tx():
            active = self.db.execute("SELECT inspection_id FROM inspections WHERE ended_seq IS NULL").fetchone()
            if active is not None:
                raise CommandRefused(f"inspection {active[0]} is still active; end it first")
            if self.db.execute("SELECT 1 FROM inspections WHERE inspection_id=?", (str(inspection_id),)).fetchone():
                raise CommandRefused(f"inspection {inspection_id} already exists")
            self._deliver_profile(profile, source_mode)
            record = self._append(InspectionStartedBody(
                kind="inspection_started", inspection_id=inspection_id, worksite_id=profile.worksite_id,
                profile_revision=profile.revision, profile_sha256=profile.sha256, requested_by=requested_by),
                source_mode, None)
            self.db.execute("INSERT INTO inspections VALUES (?, ?, ?, ?, ?, ?, NULL, NULL)",
                            (str(inspection_id), profile.worksite_id, profile.revision, profile.sha256,
                             SourceMode(source_mode).value, record.seq))
            return record

    def end_inspection(self, inspection_id: UUID, reason: InspectionEndReason) -> Record:
        with self._tx():
            row = self.db.execute("SELECT ended_seq, source_mode FROM inspections WHERE inspection_id=?",
                                  (str(inspection_id),)).fetchone()
            if row is None:
                raise NotFound(f"no inspection {inspection_id}")
            if row[0] is not None:
                raise CommandRefused(f"inspection {inspection_id} has already ended")
            record = self._append(InspectionEndedBody(kind="inspection_ended", inspection_id=inspection_id,
                                                      reason=reason), SourceMode(row[1]), None)
            self.db.execute("UPDATE inspections SET ended_seq=?, end_reason=? WHERE inspection_id=?",
                            (record.seq, InspectionEndReason(reason).value, str(inspection_id)))
            return record

    def active_inspection(self) -> Optional[ActiveInspection]:
        row = self.db.execute("SELECT i.inspection_id, i.worksite_id, i.profile_revision, i.profile_sha256, "
                              "i.source_mode, p.json FROM inspections i JOIN profiles p ON "
                              "p.worksite_id=i.worksite_id AND p.revision=i.profile_revision "
                              "WHERE i.ended_seq IS NULL").fetchone()
        if row is None:
            return None
        return ActiveInspection(UUID(row[0]), row[1], row[2], row[3], SourceMode(row[4]),
                                WorksiteProfile.model_validate_json(row[5]))

    def inspections(self) -> list[dict]:
        rows = self.db.execute("SELECT inspection_id, worksite_id, profile_revision, profile_sha256, source_mode, "
                               "started_seq, ended_seq, end_reason FROM inspections ORDER BY started_seq").fetchall()
        keys = ("inspection_id", "worksite_id", "profile_revision", "profile_sha256", "source_mode",
                "started_seq", "ended_seq", "end_reason")
        return [dict(zip(keys, r)) for r in rows]
