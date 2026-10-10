"""Offline Step 6 replay: every frame of a .bobrec -> PPE pipeline -> C2 DetectionEvents (+ on/off score).

    uv run python -m tools.replay_detect runs/server/<time>/stream.bobrec [--config configs/x.yaml]
        [--rule glasses --segments "wearing:0-10,not_wearing:12-22"] [--save-images]

Unlike the live server nothing is dropped, so two runs over the same file must give the same boxes
(Step 6 determinism). It runs the same frame path as `vision.server --detect` (detect_frame).

Messages go through the server's own admission step (FrameServer.admit: stream monitor + Step 7
associator), so pose validity offline is exactly what the live server decides for the same messages.

--segments: seconds from the first frame of the recording, label wearing | not_wearing. Per segment,
only judged frames count (unverified = no verdict, never a pass). Pass: >= --min-accuracy correct and,
in not_wearing segments, no frame judged wearing.
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional

import numpy as np

from tools.replay_client import Record, load
from vision.config import REPO_ROOT, load_config
from vision.pipeline import Pipeline
from vision.ppe import Verdict
from vision.schema import DetectionEvent
from vision.server.detection import detect_frame
from vision.server.transport import FrameServer


@dataclass(frozen=True)
class FrameOutcome:
    t_s: float                      # seconds since the first frame (iPhone clock)
    event: DetectionEvent
    verdicts: dict[str, Verdict]


@dataclass(frozen=True)
class SegmentScore:
    label: Verdict
    start_s: float
    end_s: float
    frames: int
    judged: int
    correct: int
    false_wearing: int              # judged wearing during a not_wearing segment

    @property
    def accuracy(self) -> Optional[float]:
        return self.correct / self.judged if self.judged else None

    def passed(self, min_accuracy: float) -> bool:
        accuracy = self.accuracy
        return accuracy is not None and accuracy >= min_accuracy and self.false_wearing == 0


def run(records: Iterable[Record], pipeline: Pipeline, config: dict[str, Any],
        on_frame=None, on_undecodable=None) -> list[FrameOutcome]:
    mount = config["camera"]["mount_orientation"]
    server = FrameServer(config, clock=time.time_ns)  # admission + association only, no network
    outcomes: list[FrameOutcome] = []
    first_ts: Optional[int] = None
    for record in records:
        frame = server.admit(record.msg, record.payload, time.time_ns())
        if frame is None:
            continue  # a pose, or a message the live server would drop (late / old session)
        detection = detect_frame(frame, pipeline, mount, server.associator)
        if detection is None:
            if on_undecodable is not None:
                on_undecodable(frame)  # corrupt JPEG: counted, never silently skipped
            continue
        ts = frame.packet.iphone_frame_ts_ns
        first_ts = ts if first_ts is None else first_ts
        outcome = FrameOutcome((ts - first_ts) / 1e9, detection.event, detection.verdicts)
        outcomes.append(outcome)
        if on_frame is not None:
            on_frame(outcome, detection)
    return outcomes


def box_mismatches(a: list[FrameOutcome], b: list[FrameOutcome], tol: float = 1e-3) -> list[str]:
    """Differences between two runs (event ids / receive times / latency are expected to differ)."""
    if len(a) != len(b):
        return [f"frame count {len(a)} != {len(b)}"]
    problems = []
    for x, y in zip(a, b):
        ex, ey = x.event, y.event
        where = f"seq {ex.seq_id}"
        if ex.seq_id != ey.seq_id or ex.pose_valid != ey.pose_valid or x.verdicts != y.verdicts:
            problems.append(f"{where}: seq/pose/verdict differ")
            continue
        bx = sorted(ex.boxes, key=lambda bb: (bb.cls_name, bb.xyxy))
        by = sorted(ey.boxes, key=lambda bb: (bb.cls_name, bb.xyxy))
        if [bb.cls_name for bb in bx] != [bb.cls_name for bb in by]:
            problems.append(f"{where}: classes {[bb.cls_name for bb in bx]} != {[bb.cls_name for bb in by]}")
            continue
        for p, q in zip(bx, by):
            if abs(p.conf - q.conf) > tol or max(abs(u - v) for u, v in zip(p.xyxy, q.xyxy)) > tol:
                problems.append(f"{where}: {p.cls_name} {p.xyxy}/{p.conf} vs {q.xyxy}/{q.conf}")
    return problems


def parse_segments(text: str) -> list[tuple[Verdict, float, float]]:
    segments = []
    for part in text.split(","):
        label, _, span = part.strip().partition(":")
        start, _, end = span.partition("-")
        verdict = Verdict(label.strip())
        if verdict is Verdict.UNVERIFIED:
            raise ValueError("segment label must be wearing or not_wearing")
        start_s, end_s = float(start), float(end)
        if not start_s < end_s:
            raise ValueError(f"segment {part!r}: start must be < end")
        segments.append((verdict, start_s, end_s))
    return segments


def score(outcomes: list[FrameOutcome], rule: str, segments: list[tuple[Verdict, float, float]]) -> list[SegmentScore]:
    scores = []
    for label, start, end in segments:
        inside = [o.verdicts.get(rule, Verdict.UNVERIFIED) for o in outcomes if start <= o.t_s < end]
        judged = [v for v in inside if v is not Verdict.UNVERIFIED]
        false_wearing = sum(v is Verdict.WEARING for v in judged) if label is Verdict.NOT_WEARING else 0
        scores.append(SegmentScore(label, start, end, len(inside), len(judged),
                                   sum(v is label for v in judged), false_wearing))
    return scores


def summarize(outcomes: list[FrameOutcome]) -> dict[str, Any]:
    latency = [o.event.inference_latency_ms for o in outcomes]
    rules = sorted({r for o in outcomes for r in o.verdicts})
    return {
        "frames": len(outcomes),
        "pose_valid": sum(o.event.pose_valid for o in outcomes),
        "inference_p50_ms": float(np.percentile(latency, 50)) if latency else None,
        "inference_p95_ms": float(np.percentile(latency, 95)) if latency else None,
        "verdicts": {r: {v.value: sum(o.verdicts.get(r) is v for o in outcomes) for v in Verdict} for r in rules},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("recording", type=Path)
    parser.add_argument("--config", type=Path, help="runtime override, e.g. configs/footwear.yaml")
    parser.add_argument("--out", type=Path, default=None, help="default: runs/replay_detect/<name>_<time>")
    parser.add_argument("--rule", default="glasses")
    parser.add_argument("--segments", default=None, help='e.g. "wearing:0-10,not_wearing:12-22"')
    parser.add_argument("--min-accuracy", type=float, default=0.8)
    parser.add_argument("--save-images", action="store_true", help="annotated frames -> <out>/frames/")
    args = parser.parse_args()

    config = load_config(args.config)
    segments = parse_segments(args.segments) if args.segments else None
    out = args.out or REPO_ROOT / "runs" / "replay_detect" / f"{args.recording.stem}_{time.strftime('%Y%m%d_%H%M%S')}"
    out.mkdir(parents=True, exist_ok=True)
    pipeline = Pipeline.from_config(config)
    if segments and args.rule not in {r.name for r in pipeline.rules}:
        raise SystemExit(f"rule {args.rule!r} is inactive for {pipeline.model_id}")

    save_frame = None
    if args.save_images:
        import cv2

        from vision.render import draw
        (out / "frames").mkdir(exist_ok=True)

        def save_frame(outcome: FrameOutcome, detection) -> None:
            image = draw(detection.image, detection.result.boxes, config["render"]["categories"],
                         status=" ".join(f"{k}:{v.value}" for k, v in outcome.verdicts.items()),
                         hide=config["render"]["hide"])
            cv2.imwrite(str(out / "frames" / f"{outcome.t_s:08.2f}s_seq{outcome.event.seq_id}.jpg"), image)

    undecodable: list[int] = []
    outcomes = run(load(args.recording), pipeline, config, on_frame=save_frame,
                   on_undecodable=lambda f: undecodable.append(f.packet.seq_id))
    with open(out / "detections.jsonl", "w") as fh:
        for o in outcomes:
            fh.write(o.event.model_dump_json() + "\n")
    summary = {"recording": str(args.recording), "model_id": pipeline.model_id, **summarize(outcomes),
               "undecodable_seq_ids": undecodable}
    if segments:
        scores = score(outcomes, args.rule, segments)
        summary["rule"] = args.rule
        summary["segments"] = [
            {**s.__dict__, "label": s.label.value, "accuracy": s.accuracy, "passed": s.passed(args.min_accuracy)}
            for s in scores
        ]
        summary["passed"] = all(s.passed(args.min_accuracy) for s in scores)
    (out / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    print(f"-> {out}")


if __name__ == "__main__":
    main()
