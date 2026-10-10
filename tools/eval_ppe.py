"""Evaluate a PPE rule on your own labelled photos across models and pipeline settings.

    uv run python -m tools.eval_ppe --rule glasses [--save-images]

Data layout (one person per image; distance folder optional):
    data/eval/<rule>/wearing/<distance>/*.jpg
    data/eval/<rule>/not_wearing/<distance>/*.jpg

Settings are "<mode>@<N>": the photo is first downscaled so its long side is N — the resolution
the phone would send — then run in that mode. single@N runs one pass at imgsz N; head_crop@N runs
pass 1 at model.imgsz and crops heads from the N-pixel frame.

Positive class = not_wearing. An UNVERIFIED result on a not_wearing person counts as a miss.
"""

from __future__ import annotations

import argparse
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import median

import cv2
import numpy as np

from vision.config import REPO_ROOT, load_config
from vision.detector import Detector
from vision.pipeline import Pipeline
from vision.ppe import Verdict
from vision.render import draw

LABELS = ("wearing", "not_wearing")
IMAGE_EXTS = {".jpg", ".jpeg", ".png"}
DEFAULT_SETTINGS = ["single@640", "single@960", "single@1280", "head_crop@1280", "head_crop@1920"]
TARGET_RECALL, TARGET_PRECISION = 0.90, 0.80


@dataclass(frozen=True)
class Sample:
    path: Path
    label: str
    distance: str


@dataclass(frozen=True)
class Row:
    weights: str
    setting: str
    distance: str
    n: int
    tp: int
    fn: int
    fp: int
    tn: int
    unverified: int
    median_ms: float

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else float("nan")

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else float("nan")

    @property
    def passed(self) -> bool:
        return self.recall >= TARGET_RECALL and self.precision >= TARGET_PRECISION


def find_samples(root: Path) -> list[Sample]:
    heic = sorted(root.rglob("*.heic")) + sorted(root.rglob("*.HEIC"))
    if heic:
        raise SystemExit(
            f"{len(heic)} HEIC file(s) found (e.g. {heic[0].name}); OpenCV can't read HEIC. On the "
            "iPhone set Settings > Camera > Formats > Most Compatible, or export as JPEG."
        )
    samples = []
    for label in LABELS:
        for path in sorted((root / label).rglob("*")):
            if path.suffix.lower() in IMAGE_EXTS:
                rel = path.relative_to(root / label)
                samples.append(Sample(path, label, rel.parts[0] if len(rel.parts) > 1 else "all"))
    if not samples:
        unsorted = [p for p in root.rglob("*") if p.suffix.lower() in IMAGE_EXTS]
        layout = f"{root}/wearing/<distance>/*.jpg and {root}/not_wearing/<distance>/*.jpg"
        if unsorted:
            raise SystemExit(
                f"found {len(unsorted)} image(s) (e.g. {unsorted[0].relative_to(root)}) but none inside "
                f"wearing/ or not_wearing/ — the folder is the ground-truth label. Move them to: {layout}"
            )
        raise SystemExit(f"no images under {root}. Expected: {layout}")
    return samples


def parse_setting(setting: str) -> tuple[str, int]:
    mode, _, size = setting.partition("@")
    return mode, int(size)


def resize_long_side(image: np.ndarray, long_side: int) -> np.ndarray:
    scale = long_side / max(image.shape[:2])
    if scale >= 1:
        return image  # never upscale: that would invent detail the phone doesn't have
    return cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)


def predict(pipeline: Pipeline, image: np.ndarray, rule: str):
    """Image verdict for one person: any judged subject not wearing -> NOT_WEARING (e.g. one bare
    hand of two); else any wearing -> WEARING; else UNVERIFIED."""
    result = pipeline(image)
    verdicts = {v.verdict for v in result.verdicts if v.rule == rule}
    for verdict in (Verdict.NOT_WEARING, Verdict.WEARING):
        if verdict in verdicts:
            return verdict, result
    return Verdict.UNVERIFIED, result


def evaluate(
    samples: list[Sample],
    rule: str,
    weights: list[str],
    settings: list[str],
    config: dict,
    save_dir: Path | None = None,
) -> list[Row]:
    rows = []
    for weight in weights:
        detector = Detector(weight, config["device"], config["model"]["imgsz"], config["model"]["conf"])
        for setting in settings:
            mode, size = parse_setting(setting)
            pipeline = Pipeline(detector, config, mode=mode, imgsz=size if mode == "single" else None)
            if rule not in {r.name for r in pipeline.rules}:
                raise SystemExit(f"rule {rule!r} is inactive for {detector.model_id} (model lacks its classes)")
            stats: dict[str, dict] = defaultdict(lambda: {"c": defaultdict(int), "ms": []})
            for sample in samples:
                image = cv2.imread(str(sample.path))
                if image is None:
                    raise SystemExit(f"could not read {sample.path}")
                image = resize_long_side(image, size)
                verdict, result = predict(pipeline, image, rule)
                for key in (sample.distance, "ALL"):
                    s = stats[key]
                    s["ms"].append(result.inference_ms)
                    positive = sample.label == "not_wearing"
                    if verdict is Verdict.UNVERIFIED:
                        s["c"]["unverified"] += 1
                        s["c"]["fn" if positive else "tn"] += 1  # missed violation / no false alarm
                    elif verdict is Verdict.NOT_WEARING:
                        s["c"]["tp" if positive else "fp"] += 1
                    else:
                        s["c"]["fn" if positive else "tn"] += 1
                if save_dir is not None:
                    out = save_dir / Path(weight).stem / setting / sample.label / sample.distance
                    out.mkdir(parents=True, exist_ok=True)
                    annotated = draw(
                        image, result.boxes, config["render"]["categories"],
                        f"{setting} truth={sample.label} pred={verdict.value}",
                        config["render"].get("hide", []), result.crop_regions,
                    )
                    cv2.imwrite(str(out / sample.path.name), annotated)
            if set(stats) == {"all", "ALL"}:
                del stats["all"]  # no distance folders: the per-distance row would duplicate ALL
            for distance, s in sorted(stats.items(), key=lambda kv: (kv[0] == "ALL", kv[0])):
                c = s["c"]
                rows.append(Row(
                    Path(weight).stem, setting, distance, len(s["ms"]),
                    c["tp"], c["fn"], c["fp"], c["tn"], c["unverified"], median(s["ms"]),
                ))
    return rows


def render_report(rows: list[Row], rule: str) -> str:
    lines = [
        f"# PPE eval — rule `{rule}` (positive = not_wearing)",
        "",
        f"Pass: recall >= {TARGET_RECALL} and precision >= {TARGET_PRECISION}. Unverified on a not_wearing person counts as a miss.",
        "",
        "| weights | setting | distance | n | recall | precision | unverified | TP | FN | FP | TN | median ms | pass |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in rows:
        lines.append(
            f"| {r.weights} | {r.setting} | {r.distance} | {r.n} | {r.recall:.2f} | {r.precision:.2f} | "
            f"{r.unverified} | {r.tp} | {r.fn} | {r.fp} | {r.tn} | {r.median_ms:.1f} | {'✅' if r.passed else '❌'} |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    config = load_config()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--rule", default="glasses", choices=list(config["ppe"]["rules"]))
    parser.add_argument("--data", type=Path, default=None, help="default: data/eval/<rule>")
    parser.add_argument("--weights", nargs="+", default=["models/sh17_yolov8n.pt", "models/sh17_yolov8s.pt"])
    parser.add_argument("--settings", nargs="+", default=DEFAULT_SETTINGS)
    parser.add_argument("--save-images", action="store_true")
    args = parser.parse_args()

    samples = find_samples(args.data or REPO_ROOT / "data" / "eval" / args.rule)
    run_dir = REPO_ROOT / "runs" / "eval_ppe" / f"{args.rule}_{time.strftime('%Y%m%d_%H%M%S')}"
    run_dir.mkdir(parents=True)
    rows = evaluate(samples, args.rule, args.weights, args.settings, config, run_dir if args.save_images else None)
    report = render_report(rows, args.rule)
    (run_dir / "report.md").write_text(report)
    print(report)
    print(f"saved {run_dir.relative_to(REPO_ROOT)}/report.md")


if __name__ == "__main__":
    main()
