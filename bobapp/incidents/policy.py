"""Incident confirmation state machine (plan §8.3–8.4): a pure, deterministic function of ordered frames.

    (nothing) --first positive--> CANDIDATE --criteria--> CONFIRMED --end condition--> ENDED (reason)
                                      | no positive for window_s                ^            |
                                      v                                         +- REOPENED -+ (within merge_gap_s)
                                  DISCARDED

It confirms a *condition* per (inspection, session, rule | zone) — "someone in view is missing required
eyewear" — not a violation by a specific worker (no worker identity exists). Time is the iPhone clock
of each source frame, so a replay gives the same transitions regardless of processing speed. Frames of
a retired session never open or extend anything; a replayed (duplicate or older) frame is ignored.
"""
from __future__ import annotations

import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Optional
from uuid import UUID

from bobapp.contracts import IncidentEndReason, IncidentTransition
from vision.schema import Pose, PoseInvalidReason

from .classify import FrameClass, FrameInput, Subject
from .params import PolicyParams

NAMESPACE = UUID("8f1b4a52-5d4e-4c8b-9a6e-0b0b0b1c1d1e")
Key = tuple[UUID, UUID, Subject]           # (inspection, session, subject)


@dataclass(frozen=True)
class FrameRef:
    event_id: UUID
    ts_ns: int
    pose: Optional[Pose]
    unlocalized_reason: Optional[PoseInvalidReason]


@dataclass(frozen=True)
class Transition:
    incident_id: UUID
    kind: IncidentTransition
    subject: Subject
    inspection_id: UUID
    profile_revision: int
    session_id: UUID
    ts_ns: int
    counts: tuple[int, int, int]                  # positive, negative, neutral since the incident opened
    event_ids: tuple[UUID, ...]
    location: Optional[FrameRef]
    end_reason: Optional[IncidentEndReason] = None
    interruption_ns: Optional[int] = None
    evidence: tuple[tuple[str, FrameRef], ...] = ()   # (role, frame) to keep as evidence


@dataclass
class StepResult:
    transitions: list[Transition] = field(default_factory=list)
    periodic: list[tuple[UUID, FrameRef]] = field(default_factory=list)   # extra evidence while confirmed
    notices: list[tuple[str, UUID, Optional[float]]] = field(default_factory=list)  # (code, session, rate)
    retain: set[UUID] = field(default_factory=set)  # frames the caller must keep (best / last positive)


@dataclass
class _Entry:
    ts_ns: int
    cls: FrameClass
    ref: FrameRef


@dataclass
class _Episode:
    incident_id: UUID
    subject: Subject
    inspection_id: UUID
    profile_revision: int
    session_id: UUID
    state: IncidentTransition
    first: FrameRef
    best: tuple[float, FrameRef]
    last_positive: FrameRef
    last_judged_ts: int
    counts: list[int] = field(default_factory=lambda: [0, 0, 0])
    ended_ts: Optional[int] = None
    last_evidence_ts: int = 0


class IncidentPolicy:
    def __init__(self, params: PolicyParams) -> None:
        self.p = params
        ns = 1_000_000_000
        self.window_ns, self.clear_ns = int(params.window_s * ns), int(params.clear_window_s * ns)
        self.lost_ns, self.merge_ns = int(params.lost_after_s * ns), int(params.merge_gap_s * ns)
        self.periodic_ns = int(params.evidence_periodic_s * ns)
        self.keep_ns = max(self.window_ns, self.clear_ns)
        self.windows: dict[Key, deque[_Entry]] = {}
        self.episodes: dict[Key, _Episode] = {}
        self.session: Optional[UUID] = None
        self.last_ts: dict[UUID, int] = {}
        self.rate_frames: dict[UUID, deque[int]] = {}
        self.first_ts: dict[UUID, int] = {}
        self.low_rate: dict[UUID, bool] = {}

    # --- public ---------------------------------------------------------------------------------
    def step(self, frame: FrameInput) -> StepResult:
        out = self._step(frame)
        out.retain = self._retain()  # on every path: an ignored frame must not free needed images
        return out

    def _step(self, frame: FrameInput) -> StepResult:
        out = StepResult()
        if frame.retired:
            return out
        last = self.last_ts.get(frame.session_id)
        if last is not None and frame.ts_ns <= last:
            return out                                           # replayed or out of order: never counted twice
        if self.session is not None and frame.session_id != self.session:
            self._end_where(lambda ep: ep.session_id != frame.session_id, IncidentEndReason.SESSION_CHANGED, out)
        self.session = frame.session_id
        self.last_ts[frame.session_id] = frame.ts_ns
        self._end_where(lambda ep: ep.inspection_id != frame.inspection_id, IncidentEndReason.INSPECTION_ENDED, out)
        if frame.inspection_id is None:
            return out
        self._rate(frame, out)
        ref = FrameRef(frame.event_id, frame.ts_ns, frame.pose, frame.unlocalized_reason)
        for subject, cls in frame.values.items():
            self._value((frame.inspection_id, frame.session_id, subject), subject, cls, frame, ref, out)
        for key, ep in list(self.episodes.items()):
            if key[0] == frame.inspection_id and key[1] == frame.session_id:
                self._evaluate(key, ep, frame, ref, out)
        return out

    def _retain(self) -> set[UUID]:
        retain: set[UUID] = set()
        for key, ep in self.episodes.items():
            if ep.state != IncidentTransition.ENDED:
                retain |= {ep.best[1].event_id, ep.last_positive.event_id}
            else:  # a reopen may name the latest positive frame since the end: keep that one image
                latest = next((e for e in reversed(self.windows.get(key, ())) if e.cls is FrameClass.POSITIVE
                               and e.ts_ns > ep.ended_ts), None)
                if latest is not None:
                    retain.add(latest.ref.event_id)
        return retain

    def end_inspection(self, reason: IncidentEndReason = IncidentEndReason.INSPECTION_ENDED) -> StepResult:
        """Close everything (inspection ended without a further frame, run stopped: SOURCE_STOPPED)."""
        out = StepResult()
        self._end_where(lambda ep: True, reason, out)
        return out

    # --- internals ------------------------------------------------------------------------------
    def _transition(self, ep: _Episode, kind: IncidentTransition, ts: int, event_ids: list[UUID],
                    location: Optional[FrameRef], **extra) -> Transition:
        return Transition(ep.incident_id, kind, ep.subject, ep.inspection_id, ep.profile_revision, ep.session_id, ts,
                          tuple(ep.counts), tuple(event_ids[-20:]), location, **extra)

    def _value(self, key: Key, subject: Subject, cls: FrameClass, frame: FrameInput, ref: FrameRef, out: StepResult) -> None:
        window = self.windows.setdefault(key, deque())
        window.append(_Entry(frame.ts_ns, cls, ref))
        while window and window[0].ts_ns <= frame.ts_ns - self.keep_ns:
            window.popleft()
        ep = self.episodes.get(key)
        if ep is not None and ep.state == IncidentTransition.ENDED and frame.ts_ns - ep.ended_ts > self.merge_ns:
            del self.episodes[key]
            ep = None
        if ep is None:
            if cls is FrameClass.POSITIVE:
                ep = _Episode(uuid.uuid5(NAMESPACE, f"{key[0]}:{key[1]}:{subject}:{frame.ts_ns}"), subject, key[0],
                              frame.profile_revision, key[1], IncidentTransition.CANDIDATE, ref,
                              (frame.confidence.get(subject, 0.0), ref), ref, frame.ts_ns, [1, 0, 0])
                ep.last_evidence_ts = frame.ts_ns
                self.episodes[key] = ep
                out.transitions.append(self._transition(ep, IncidentTransition.CANDIDATE, frame.ts_ns, [ref.event_id],
                                                        ref, evidence=(("first", ref),)))
            return
        if ep.state == IncidentTransition.ENDED:
            return  # counted again only if it re-confirms (see _evaluate)
        ep.counts[{FrameClass.POSITIVE: 0, FrameClass.NEGATIVE: 1, FrameClass.NEUTRAL: 2}[cls]] += 1
        if cls is not FrameClass.NEUTRAL:
            ep.last_judged_ts = frame.ts_ns
        if cls is FrameClass.POSITIVE:
            ep.last_positive = ref
            confidence = frame.confidence.get(subject, 0.0)
            if confidence > ep.best[0]:
                ep.best = (confidence, ref)

    def _met(self, key: Key, ts: int, span: int, cls: FrameClass, minimum: int, fraction: float, after: int = -1) -> list[_Entry]:
        entries = [e for e in self.windows.get(key, ()) if e.ts_ns > ts - span and e.ts_ns > after]
        hits = [e for e in entries if e.cls is cls]
        judged = sum(e.cls is not FrameClass.NEUTRAL for e in entries)
        return hits if len(hits) >= minimum and judged and len(hits) / judged >= fraction else []

    def _evaluate(self, key: Key, ep: _Episode, frame: FrameInput, ref: FrameRef, out: StepResult) -> None:
        ts, p = frame.ts_ns, self.p
        positive_now = frame.values.get(ep.subject) is FrameClass.POSITIVE
        if ep.state == IncidentTransition.CANDIDATE:
            hits = self._met(key, ts, self.window_ns, FrameClass.POSITIVE, p.confirm_min_frames, p.confirm_min_fraction)
            if hits:
                ep.state, ep.last_evidence_ts = IncidentTransition.CONFIRMED, ts
                at = ref if positive_now else ep.last_positive
                evidence = (("confirm", at),) + ((("best", ep.best[1]),) if ep.best[1].event_id != at.event_id else ())
                out.transitions.append(self._transition(ep, IncidentTransition.CONFIRMED, ts, [e.ref.event_id for e in hits],
                                                        at, evidence=evidence))
            elif ts - ep.last_positive.ts_ns >= self.window_ns:
                del self.episodes[key]
                out.transitions.append(self._transition(ep, IncidentTransition.DISCARDED, ts, [ref.event_id], ep.first))
        elif ep.state == IncidentTransition.CONFIRMED:
            if self._met(key, ts, self.clear_ns, FrameClass.NEGATIVE, p.clear_min_frames, p.clear_min_fraction):
                self._end(ep, IncidentEndReason.CONDITION_NOT_OBSERVED, ts, ref, out)
            elif ts - ep.last_judged_ts >= self.lost_ns:
                self._end(ep, IncidentEndReason.NOT_ASSESSED, ts, ref, out)
            elif positive_now and ts - ep.last_evidence_ts >= self.periodic_ns:
                ep.last_evidence_ts = ts
                out.periodic.append((ep.incident_id, ref))
        elif ep.state == IncidentTransition.ENDED:
            hits = self._met(key, ts, self.window_ns, FrameClass.POSITIVE, p.confirm_min_frames,
                             p.confirm_min_fraction, after=ep.ended_ts)
            if hits:
                interruption = ts - ep.ended_ts
                ep.state, ep.ended_ts, ep.last_judged_ts, ep.last_evidence_ts = IncidentTransition.CONFIRMED, None, ts, ts
                ep.last_positive = hits[-1].ref
                ep.counts[0] += len(hits)
                out.transitions.append(self._transition(ep, IncidentTransition.REOPENED, ts, [e.ref.event_id for e in hits],
                                                        hits[-1].ref, interruption_ns=interruption,
                                                        evidence=(("confirm", hits[-1].ref),)))

    def _end(self, ep: _Episode, reason: IncidentEndReason, ts: int, ref: FrameRef, out: StepResult) -> None:
        ep.state, ep.ended_ts = IncidentTransition.ENDED, ts
        out.transitions.append(self._transition(ep, IncidentTransition.ENDED, ts, [ref.event_id], ep.last_positive,
                                                end_reason=reason, evidence=(("last", ep.last_positive),)))

    def _end_where(self, condition, reason: IncidentEndReason, out: StepResult) -> None:
        for key, ep in list(self.episodes.items()):
            if not condition(ep):
                continue
            ts = self.last_ts.get(ep.session_id, ep.last_positive.ts_ns)
            if ep.state == IncidentTransition.CANDIDATE:
                out.transitions.append(self._transition(ep, IncidentTransition.DISCARDED, ts, [ep.last_positive.event_id],
                                                        ep.first))
            elif ep.state == IncidentTransition.CONFIRMED:
                self._end(ep, reason, ts, ep.last_positive, out)
            del self.episodes[key]
            self.windows.pop(key, None)

    def _rate(self, frame: FrameInput, out: StepResult) -> None:
        """Below min_processing_hz confirmation is impossible: say so instead of failing silently."""
        session = frame.session_id
        frames = self.rate_frames.setdefault(session, deque())
        self.first_ts.setdefault(session, frame.ts_ns)
        frames.append(frame.ts_ns)
        while frames and frames[0] <= frame.ts_ns - self.window_ns:
            frames.popleft()
        if frame.ts_ns - self.first_ts[session] < self.window_ns:
            return  # not enough history to judge the rate yet
        rate = len(frames) / self.p.window_s
        low = rate < self.p.min_processing_hz
        if low != self.low_rate.get(session, False):
            self.low_rate[session] = low
            out.notices.append(("confirmation_unavailable_rate" if low else "confirmation_rate_recovered", session, rate))
