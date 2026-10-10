"""Step 8 parity: do two pipeline variants give the same boxes AND the same PPE verdicts?

    uv run python -m tools.parity batch [runs/server/<time>/stream.bobrec ...] [--frames 40]
    uv run python -m tools.parity onnx  [recordings ...] [--frames 40]      (needs tools.export_onnx first)
    python -m tools.parity config --b-config configs/engine.yaml [recordings ...]   (on the Jetson: .pt vs .engine)

batch: sequential head crops vs one batched model call (pipeline.crop.batch).
onnx:  the .pt models vs their exported .onnx (onnxruntime on CPU), same pipeline settings.
config: the base config vs the base merged with --b-config (any model / backend swap, e.g. TensorRT).

Images: the bundled ultralytics images plus `--frames` evenly spaced frames from each recording
(decoded and rotated upright exactly like the live server). Pass (decided in Step 8): every box has a
same-class partner with IoU >= 0.9 and |delta conf| <= 0.02, no extra / missing boxes, and identical
frame verdicts for every active rule.
"""

from __future__ import annotations

import argparse
import copy
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

import numpy as np

from vision.config import load_config
from vision.pipeline import Pipeline
from vision.ppe import frame_verdict
from vision.schema import Box

IOU_MIN = 0.9
CONF_TOL = 0.02


def _iou(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def match_boxes(a: list[Box], b: list[Box], iou_min: float = IOU_MIN,
                conf_tol: float = CONF_TOL) -> tuple[list[str], float, float]:
    """Greedy same-class matching (highest IoU first). Returns (problems, min IoU, max |delta conf|)."""
    problems: list[str] = []
    worst_iou, worst_dconf = 1.0, 0.0
    unmatched = list(b)
    for box in sorted(a, key=lambda x: -x.conf):
        candidates = [(c, _iou(box.xyxy, c.xyxy)) for c in unmatched if c.cls_name == box.cls_name]
        best, iou = max(candidates, key=lambda t: t[1], default=(None, 0.0))
        if best is None or iou < iou_min:
            problems.append(f"{box.cls_name} {box.conf:.2f} at {tuple(round(v) for v in box.xyxy)}: "
                            f"no partner (best IoU {iou:.2f})")
            continue
        unmatched.remove(best)
        dconf = abs(box.conf - best.conf)
        worst_iou, worst_dconf = min(worst_iou, iou), max(worst_dconf, dconf)
        if dconf > conf_tol:
            problems.append(f"{box.cls_name}: conf {box.conf:.3f} vs {best.conf:.3f}")
    problems += [f"extra {c.cls_name} {c.conf:.2f} at {tuple(round(v) for v in c.xyxy)}" for c in unmatched]
    return problems, worst_iou, worst_dconf


@dataclass
class ParityReport:
    images: int = 0
    boxes: int = 0
    failures: dict[str, list[str]] = field(default_factory=dict)
    min_iou: float = 1.0
    max_dconf: float = 0.0
    ms_a: list[float] = field(default_factory=list)
    ms_b: list[float] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.images > 0 and not self.failures

    def summary(self) -> dict[str, Any]:
        return {
            "passed": self.passed, "images": self.images, "boxes": self.boxes,
            "failed_images": len(self.failures), "min_iou": round(self.min_iou, 4),
            "max_dconf": round(self.max_dconf, 4),
            "pipeline_ms_p50_a": float(np.median(self.ms_a)) if self.ms_a else None,
            "pipeline_ms_p50_b": float(np.median(self.ms_b)) if self.ms_b else None,
            "failures": self.failures,
        }


def compare(a: Pipeline, b: Pipeline, images: Iterable[tuple[str, np.ndarray]]) -> ParityReport:
    report = ParityReport()
    for name, image in images:
        ra, rb = a(image), b(image)
        report.images += 1
        report.boxes += len(ra.boxes)
        report.ms_a.append(ra.inference_ms)
        report.ms_b.append(rb.inference_ms)
        problems, iou, dconf = match_boxes(ra.boxes, rb.boxes)
        report.min_iou, report.max_dconf = min(report.min_iou, iou), max(report.max_dconf, dconf)
        for rule in a.rules:
            va, vb = frame_verdict(ra.verdicts, rule.name), frame_verdict(rb.verdicts, rule.name)
            if va is not vb:
                problems.append(f"verdict {rule.name}: {va.value} vs {vb.value}")
        if problems:
            report.failures[name] = problems
    return report


def bundled_images() -> list[tuple[str, np.ndarray]]:
    import cv2
    import ultralytics
    assets = Path(ultralytics.__file__).parent / "assets"
    return [(p.name, cv2.imread(str(p))) for p in sorted(assets.glob("*.jpg"))]


def recording_frames(paths: Iterable[Path], per_recording: int, mount: str) -> list[tuple[str, np.ndarray]]:
    """Evenly spaced frames, decoded + rotated upright exactly like the live server."""
    from tools.replay_client import load
    from vision.schema import FramePacket
    from vision.server.slot import ReceivedFrame
    from vision.server.view import decode_upright

    out = []
    for path in paths:
        frames = [r for r in load(path) if isinstance(r.msg, FramePacket)]
        if not frames:
            continue
        for i in np.linspace(0, len(frames) - 1, min(per_recording, len(frames))).astype(int):
            r = frames[i]
            image = decode_upright(ReceivedFrame(r.msg, r.payload, 0), mount)
            if image is not None:
                out.append((f"{Path(path).parent.name}/seq{r.msg.seq_id}", image))
    return out


def with_overrides(config: dict[str, Any], batch: Optional[bool] = None, onnx: bool = False) -> dict[str, Any]:
    config = copy.deepcopy(config)
    if batch is not None:
        config["pipeline"]["crop"]["batch"] = batch
    if onnx:
        from tools.export_onnx import onnx_config
        config = onnx_config(config)
    return config


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("mode", choices=["batch", "onnx", "config"])
    parser.add_argument("recordings", nargs="*", type=Path)
    parser.add_argument("--frames", type=int, default=40, help="frames sampled per recording")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--b-config", type=Path, help="config mode: override merged into variant B")
    parser.add_argument("--out", type=Path, default=None, help="write the JSON report here")
    args = parser.parse_intermixed_args()  # recordings may come before or after the options

    config = load_config(args.config)
    if args.mode == "batch":
        a = Pipeline.from_config(with_overrides(config, batch=False))
        b = Pipeline(a.detector, with_overrides(config, batch=True), footwear=a.footwear)
    elif args.mode == "onnx":
        a = Pipeline.from_config(config)
        b = Pipeline.from_config(with_overrides(config, onnx=True))
    else:
        if args.b_config is None:
            parser.error("config mode needs --b-config")
        import yaml
        from vision.config import _deep_merge
        a = Pipeline.from_config(config)
        b = Pipeline.from_config(_deep_merge(config, yaml.safe_load(args.b_config.read_text())))
    images = bundled_images() + recording_frames(args.recordings, args.frames, config["camera"]["mount_orientation"])
    report = compare(a, b, images)
    text = json.dumps(report.summary(), indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text)
    print(text)
    raise SystemExit(0 if report.passed else 1)


if __name__ == "__main__":
    main()
