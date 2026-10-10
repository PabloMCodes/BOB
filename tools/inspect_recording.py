"""Inspect a .bobrec recording from the iPhone app — the Step 4 on-device acceptance check.

    uv run python -m tools.inspect_recording path/to/bob_YYYYMMDD_HHMMSS.bobrec [--frames 8]

Reports, per AR session: message rates, seq_id gaps, tracking states, orientations, JPEG sizes and
header/payload agreement, yaw over time (turn LEFT => yaw must INCREASE: verifies the column-major
matrix end to end) — and saves sample frames rotated upright with vision.orientation so the
rotation mapping can be checked by eye (Step 2 risk).
"""

from __future__ import annotations

import argparse
import math
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import cv2
import numpy as np

from vision.config import REPO_ROOT, load_config
from vision.orientation import resolve_orientation, to_upright
from vision.recording import RecordingError, iter_records
from vision.schema import FramePacket, WireError, decode


@dataclass
class SessionStats:
    session_id: str
    frames: int = 0
    poses: int = 0
    first_ts_ns: Optional[int] = None
    last_ts_ns: Optional[int] = None
    seqs: list[int] = field(default_factory=list)
    tracking: Counter = field(default_factory=Counter)
    orientations: Counter = field(default_factory=Counter)
    sizes: Counter = field(default_factory=Counter)
    payload_bytes: int = 0
    dim_mismatches: int = 0
    undecodable_jpegs: int = 0
    yaw_track: list[tuple[float, float]] = field(default_factory=list)  # (seconds, yaw deg)
    path_m: float = 0.0
    _last_xyz: Optional[tuple[float, float, float]] = None

    @property
    def duration_s(self) -> float:
        if self.first_ts_ns is None or self.last_ts_ns is None:
            return 0.0
        return (self.last_ts_ns - self.first_ts_ns) / 1e9

    @property
    def seq_gaps(self) -> int:
        ordered = sorted(set(self.seqs))
        return (ordered[-1] - ordered[0] + 1 - len(ordered)) if ordered else 0

    @property
    def out_of_order(self) -> int:
        return sum(1 for a, b in zip(self.seqs, self.seqs[1:]) if b <= a)

    @property
    def yaw_change_deg(self) -> float:
        """Net yaw change, unwrapped (so 170 -> -170 counts as +20, not -340)."""
        if len(self.yaw_track) < 2:
            return 0.0
        unwrapped = np.degrees(np.unwrap(np.radians([y for _, y in self.yaw_track])))
        return float(unwrapped[-1] - unwrapped[0])


def inspect(path: Path, out: Optional[Path] = None, sample_frames: int = 0,
            config: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    config = config or load_config()
    mount = config["camera"]["mount_orientation"]
    sessions: dict[str, SessionStats] = {}
    errors: list[str] = []
    records = 0
    frames_to_save: list[tuple[FramePacket, bytes]] = []

    try:
        for raw in iter_records(path):
            records += 1
            try:
                msg, payload = decode(raw)
            except WireError as e:
                errors.append(str(e).splitlines()[0])
                continue
            sid = str(msg.session_id)
            s = sessions.setdefault(sid, SessionStats(sid))
            ts = msg.iphone_frame_ts_ns
            s.first_ts_ns = ts if s.first_ts_ns is None else min(s.first_ts_ns, ts)
            s.last_ts_ns = ts if s.last_ts_ns is None else max(s.last_ts_ns, ts)
            s.seqs.append(msg.seq_id)
            s.tracking[msg.tracking_state.value] += 1
            try:
                pose = msg.pose
            except ValueError:
                pose = None  # camera pointing straight up/down: yaw undefined
            if pose is not None:
                t = (ts - s.first_ts_ns) / 1e9
                if not s.yaw_track or t - s.yaw_track[-1][0] >= 0.5:
                    s.yaw_track.append((t, math.degrees(pose.yaw_rad)))
                xyz = (pose.x_m, pose.y_m, pose.z_m)
                if s._last_xyz is not None:
                    s.path_m += math.dist(xyz, s._last_xyz)
                s._last_xyz = xyz
            if isinstance(msg, FramePacket):
                s.frames += 1
                s.payload_bytes += len(payload)
                s.orientations[msg.image.device_orientation.value] += 1
                s.sizes[f"{msg.image.width}x{msg.image.height}"] += 1
                image = cv2.imdecode(np.frombuffer(payload, np.uint8), cv2.IMREAD_COLOR)
                if image is None:
                    s.undecodable_jpegs += 1
                elif (image.shape[1], image.shape[0]) != (msg.image.width, msg.image.height):
                    s.dim_mismatches += 1
                frames_to_save.append((msg, payload))
            else:
                s.poses += 1
    except RecordingError as e:
        errors.append(f"recording: {e}")

    saved = []
    if out is not None and sample_frames and frames_to_save:
        out.mkdir(parents=True, exist_ok=True)
        picks = np.linspace(0, len(frames_to_save) - 1, min(sample_frames, len(frames_to_save))).astype(int)
        for i in sorted(set(picks.tolist())):
            msg, payload = frames_to_save[i]
            image = cv2.imdecode(np.frombuffer(payload, np.uint8), cv2.IMREAD_COLOR)
            if image is None:
                continue
            reported = msg.image.device_orientation
            upright = to_upright(image, reported, mount)
            label = f"seq {msg.seq_id} reported={reported.value} rotated_as={resolve_orientation(reported, mount).value}"
            cv2.putText(upright, label, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2, cv2.LINE_AA)
            dest = out / f"frame_{msg.seq_id:06d}.jpg"
            cv2.imwrite(str(dest), upright)
            saved.append(dest)

    return {"records": records, "errors": errors, "sessions": list(sessions.values()), "saved": saved}


def render(summary: dict[str, Any]) -> str:
    lines = [f"records: {summary['records']}   decode errors: {len(summary['errors'])}"]
    lines += [f"  ! {e}" for e in summary["errors"][:3]]
    for n, s in enumerate(summary["sessions"]):
        d = max(s.duration_s, 1e-9)
        mb = s.payload_bytes / d / 1e6
        lines += [
            f"\nsession {n} {s.session_id[:8]}  {s.duration_s:.1f} s",
            f"  frames {s.frames} ({s.frames / d:.1f} Hz)   poses {s.poses} ({s.poses / d:.1f} Hz)   "
            f"jpeg {s.payload_bytes / max(s.frames, 1) / 1024:.0f} KB avg, {mb:.2f} MB/s",
            f"  seq gaps {s.seq_gaps}   out-of-order {s.out_of_order}   "
            f"header/JPEG size mismatches {s.dim_mismatches}   undecodable JPEGs {s.undecodable_jpegs}",
            f"  tracking {dict(s.tracking)}",
            f"  orientation {dict(s.orientations)}   sizes {dict(s.sizes)}",
            f"  yaw change {s.yaw_change_deg:+.0f} deg (turn LEFT => positive)   path {s.path_m:.2f} m",
            "  yaw @0.5 s: " + " ".join(f"{y:+.0f}" for _, y in s.yaw_track[:24]),
        ]
    if summary["saved"]:
        lines.append(f"\nsaved {len(summary['saved'])} upright sample frames -> {summary['saved'][0].parent}")
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("recording", type=Path)
    parser.add_argument("--frames", type=int, default=8, help="sample frames to save upright (0 = none)")
    parser.add_argument("--out", type=Path, default=None, help="default: runs/inspect/<recording name>")
    args = parser.parse_args(argv)
    out = args.out or REPO_ROOT / "runs" / "inspect" / args.recording.stem
    print(render(inspect(args.recording, out, args.frames)))


if __name__ == "__main__":
    main()
