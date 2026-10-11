"""§8.6 proposed acceptance (agreed at Step 0), evaluated over a labeled recording.

  1. no incident confirmed (or reopened) during any `wearing` segment;
  2. every `not_wearing` segment of >= 10 s in which the model judged the subject is confirmed within
     3 s of its start (or an incident is already confirmed when it starts);
  3. an incident open at the end of a `not_wearing` segment followed by `wearing` ends within
     clear_window_s + 1 s.
Segments are seconds from the first frame of the recording (the replay_detect convention).
"""
from __future__ import annotations

from typing import Any

from bobapp.contracts import IncidentTransition

from .classify import FrameClass, FrameInput
from .params import PolicyParams
from .policy import Transition

CONFIRMING = (IncidentTransition.CONFIRMED, IncidentTransition.REOPENED)


def evaluate(frames: list[FrameInput], transitions: list[Transition], segments: list[tuple[str, float, float]],
             params: PolicyParams) -> dict[str, Any]:
    t0 = frames[0].ts_ns if frames else 0
    sec = lambda ts: (ts - t0) / 1e9  # noqa: E731
    checks = []
    for i, (label, start, end) in enumerate(segments):
        inside = [t for t in transitions if start <= sec(t.ts_ns) < end]
        if label == "wearing":
            bad = [round(sec(t.ts_ns), 2) for t in inside if t.kind in CONFIRMING]
            checks.append({"segment": i, "label": label, "check": "no confirmation while wearing", "passed": not bad,
                           "confirmed_at_s": bad})
            continue
        judged = sum(1 for f in frames if start <= sec(f.ts_ns) < end
                     for c in f.values.values() if c is not FrameClass.NEUTRAL)
        if end - start >= 10 and judged >= params.confirm_min_frames:
            open_at_start = _open_at(transitions, t0 + int(start * 1e9))
            hit = [round(sec(t.ts_ns) - start, 2) for t in inside if t.kind in CONFIRMING and sec(t.ts_ns) <= start + 3]
            checks.append({"segment": i, "label": label, "check": "confirmed within 3 s", "passed": bool(hit or open_at_start),
                           "delay_s": hit[0] if hit else None, "judged_frames": judged})
        if i + 1 < len(segments) and segments[i + 1][0] == "wearing" and _open_at(transitions, t0 + int(end * 1e9)):
            limit = end + params.clear_window_s + 1
            ended = [round(sec(t.ts_ns) - end, 2) for t in transitions
                     if t.kind == IncidentTransition.ENDED and end <= sec(t.ts_ns) <= limit]
            checks.append({"segment": i, "label": label, "check": f"ends within {params.clear_window_s + 1:.0f} s of PPE on",
                           "passed": bool(ended), "end_delay_s": ended[0] if ended else None})
    return {"policy_version": params.policy_version, "policy_params_sha256": params.sha256,
            "checks": checks, "passed": bool(checks) and all(c["passed"] for c in checks)}


def _open_at(transitions: list[Transition], ts_ns: int) -> bool:
    state: dict = {}
    for t in transitions:
        if t.ts_ns > ts_ns:
            break
        state[t.incident_id] = t.kind
    return any(k in CONFIRMING for k in state.values())
