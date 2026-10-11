"""IncidentRecorder: runs the §8 policy on the rover's writer thread and stores every transition.

Evidence (§8.5, at most `evidence.max_per_incident`): the first positive frame, the confirming frame,
the highest-confidence positive frame, the last positive frame, plus one every `periodic_s` while
confirmed — always the clean upright frame the model saw, with its pixel hash and C2 identity. The
policy names the frames to keep; only those images stay in memory. A frame whose image is gone leaves
the incident without that evidence rather than with a substitute. Open incidents never survive a
restart: at startup they are closed (`source_stopped`) or discarded, never resumed from memory.
"""
from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from bobapp.contracts import (
    EvidenceReason,
    IncidentBody,
    IncidentEndReason,
    IncidentTransition,
    NoticeBody,
    Record,
    SourceMode,
)
from bobapp.edge.store import EdgeStore
from bobapp.incidents import IncidentPolicy, PolicyParams, StepResult, frame_input, incident_body, subject_label

from .evidence import encode_jpeg, evidence_body

OPEN = {IncidentTransition.CANDIDATE, IncidentTransition.CONFIRMED, IncidentTransition.REOPENED}


class IncidentRecorder:
    def __init__(self, store: EdgeStore, params: PolicyParams, source_mode: SourceMode, run_id: str,
                 evidence_quality: int) -> None:
        self.store, self.params, self.source_mode, self.run_id = store, params, source_mode, run_id
        self.quality = evidence_quality
        self.policy = IncidentPolicy(params)
        self.frames: dict[UUID, tuple[Any, str]] = {}          # retained event_id -> (detection, pixel sha)
        self.evidence: dict[UUID, list[str]] = {}               # incident -> evidence shas so far
        self.captured: dict[tuple[UUID, UUID], str] = {}        # (incident, event) -> sha
        self.counts = {"transitions": 0, "incident_evidence": 0, "evidence_unavailable": 0}

    def _append(self, body: Any) -> Record:
        return self.store.append(body, self.source_mode, self.run_id)

    def close_stale(self) -> int:
        """Close incidents a previous run left open (crash or stop without close)."""
        last: dict[UUID, Any] = {}
        for record in self.store.iter_kind("incident"):
            last[record.body.incident_id] = record.body
        closed = 0
        for body in last.values():
            if body.transition not in OPEN:
                continue
            if body.transition == IncidentTransition.CANDIDATE:
                update = {"transition": IncidentTransition.DISCARDED}
            else:
                update = {"transition": IncidentTransition.ENDED, "end_reason": IncidentEndReason.SOURCE_STOPPED}
            self._append(IncidentBody.model_validate({**body.model_dump(), **update, "interruption_ns": None,
                                                      "event_ids": body.event_ids[-1:]}))
            closed += 1
        if closed:
            self._append(NoticeBody(kind="notice", code="incidents_closed_at_startup",
                                    message="Open incidents of a previous run were closed (source_stopped), not resumed",
                                    details={"count": closed, "run_id": self.run_id}))
        return closed

    def observe(self, detection: Any, assessment: Any, scene: Optional[dict], pixels_sha: str) -> None:
        conf = {}
        for v in detection.result.verdicts:
            if v.violation is not None:
                conf[v.rule] = max(conf.get(v.rule, 0.0), v.violation.conf)
        frame = frame_input(detection.event, assessment, scene, conf)
        self.frames[frame.event_id] = (detection, pixels_sha)
        result = self.policy.step(frame)
        self._record(result)
        self.frames = {k: v for k, v in self.frames.items() if k in result.retain}

    def end(self, reason: IncidentEndReason) -> None:
        self._record(self.policy.end_inspection(reason))
        self.frames.clear()

    def _record(self, result: StepResult) -> None:
        for incident_id, ref in result.periodic:
            self._capture(incident_id, ref.event_id, "periodic")
        for t in result.transitions:
            for role, ref in t.evidence:
                self._capture(t.incident_id, ref.event_id, role, label=subject_label(t))
            self._append(incident_body(t, self.params, self.evidence.get(t.incident_id, [])))
            self.counts["transitions"] += 1
        for code, session, rate in result.notices:
            self._append(NoticeBody(kind="notice", code=code, message=(
                "confirmation unavailable: processing rate below min_processing_hz" if code.endswith("rate")
                else "processing rate recovered; confirmation possible again"),
                details={"session_id": str(session), "rate_hz": rate, "min_processing_hz": self.params.min_processing_hz}))

    def _capture(self, incident_id: UUID, event_id: UUID, role: str, label: Optional[str] = None) -> None:
        shas = self.evidence.setdefault(incident_id, [])
        if (incident_id, event_id) in self.captured or len(shas) >= self.params.evidence_max:
            return
        kept = self.frames.get(event_id)
        if kept is None:
            self.counts["evidence_unavailable"] += 1  # never substituted with another frame
            return
        detection, pixels_sha = kept
        data = encode_jpeg(detection.image, self.quality)
        sha = self.store.put_blob(data)
        self._append(evidence_body(detection, sha, len(data), pixels_sha, EvidenceReason.INCIDENT,
                                   [f"incident:{incident_id}", f"role:{role}"] + ([label] if label else [])))
        self.captured[(incident_id, event_id)] = sha
        shas.append(sha)
        self.counts["incident_evidence"] += 1

