"""Pose-association timeline of a recording — the Step 7 live acceptance check (no model needed).

    uv run python -m tools.pose_timeline runs/server/<time>/stream.bobrec

Plays the messages through the live server's admission step (FrameServer.admit) and the Step 7
associator, exactly as `vision.server --detect` would, and prints per session: frames by pose verdict
and every stretch of invalid poses (start-end seconds from the recording start, reason, frames).

Live tests (README Step 7): cover the lens ~3 s -> one tracking_not_normal stretch of ~3 s, valid
before and after · Reset / app to background -> a new session each time, no frame of an old session
after it, the new session's first frames may be tracking_not_normal (ARKit initialising).
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional
from uuid import UUID

from tools.replay_client import Record, load
from vision.config import load_config
from vision.schema import FramePacket
from vision.server.transport import FrameServer


@dataclass
class Stretch:
    reason: str
    start_s: float
    end_s: float
    frames: int = 1


@dataclass
class SessionTimeline:
    session_id: UUID
    start_s: float
    end_s: float = 0.0
    verdicts: Counter = field(default_factory=Counter)
    invalid: list[Stretch] = field(default_factory=list)
    _open: Optional[Stretch] = None  # invalid stretch still running (closed by any valid frame)

    def add(self, t: float, verdict: str) -> None:
        self.end_s = t
        self.verdicts[verdict] += 1
        if verdict == "valid":
            self._open = None
        elif self._open is not None and self._open.reason == verdict:
            self._open.end_s, self._open.frames = t, self._open.frames + 1
        else:
            self._open = Stretch(verdict, t, t)
            self.invalid.append(self._open)


@dataclass
class Timeline:
    sessions: list[SessionTimeline]
    dropped: int  # frames the live server would drop (late / old session / duplicate)


def build(records: Iterable[Record], config: dict[str, Any]) -> Timeline:
    server = FrameServer(config)
    sessions: list[SessionTimeline] = []
    first_ts: Optional[int] = None
    dropped = 0
    for record in records:
        msg = record.msg
        first_ts = msg.iphone_frame_ts_ns if first_ts is None else first_ts
        frame = server.admit(msg, record.payload, 0)
        if frame is None:
            dropped += isinstance(msg, FramePacket)  # poses never become frames; a dropped frame does count
            continue
        t = (msg.iphone_frame_ts_ns - first_ts) / 1e9
        if not sessions or sessions[-1].session_id != msg.session_id:
            sessions.append(SessionTimeline(msg.session_id, t))
        a = server.associator.associate(frame.packet, frame.gap_ns)
        verdict = "valid" if a.pose_valid else a.reason.value
        if verdict == "tracking_not_normal":  # say why: lens covered vs initialising vs fast motion
            verdict += f" ({msg.tracking_reason.value if msg.tracking_reason else msg.tracking_state.value})"
        sessions[-1].add(t, verdict)
    return Timeline(sessions, dropped)


def render(timeline: Timeline) -> str:
    lines = [f"sessions {len(timeline.sessions)}   frames the server would drop {timeline.dropped}"]
    for i, s in enumerate(timeline.sessions):
        total = sum(s.verdicts.values())
        lines.append(f"\nsession {i} {str(s.session_id)[:8]}  {s.start_s:.1f}-{s.end_s:.1f} s  frames {total}  "
                     + "  ".join(f"{k} {v}" for k, v in s.verdicts.most_common()))
        for st in s.invalid:
            lines.append(f"  invalid {st.start_s:7.2f}-{st.end_s:7.2f} s  ({st.end_s - st.start_s:4.1f} s, "
                         f"{st.frames:3d} frames)  {st.reason}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("recording", type=Path)
    parser.add_argument("--config", type=Path)
    args = parser.parse_args()
    print(render(build(load(args.recording), load_config(args.config))))


if __name__ == "__main__":
    main()
