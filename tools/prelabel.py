"""Draft bounding boxes for labelling: SH17 (head_crop pipeline) + optional YOLO-World prompts.

    uv run --group labeling python -m tools.prelabel data/raw/<batch> [--out data/labeling/<batch>]
    uv run python -m tools.prelabel data/raw/<batch> --no-world     # SH17 only, no CLIP needed

Writes YOLO format for Label Studio / CVAT import as *predictions* to correct by hand:
    <out>/images/*.jpg   <out>/labels/*.txt   <out>/classes.txt   (classes = training.classes)

Drafts are deliberately recall-heavy (training.prelabel.conf). Every box must be reviewed:
in particular YOLO-World calls socks "sneakers", and SH17 'shoes' is any footwear — relabel
safety boots as `safety-boots` by hand.
"""

from __future__ import annotations

import argparse
import shutil
from collections import Counter
from pathlib import Path
from typing import Any, Optional

import cv2

from tools.eval_ppe import IMAGE_EXTS
from vision.config import REPO_ROOT, load_config
from vision.detector import Detector, ensure_weights
from vision.pipeline import Pipeline, nms_per_class
from vision.render import normalize_class_name
from vision.schema import Box


class Prelabeler:
    def __init__(self, config: dict[str, Any], use_world: bool = True, conf: Optional[float] = None) -> None:
        self.classes = [normalize_class_name(c) for c in config["training"]["classes"]]
        self.cfg = dict(config["training"]["prelabel"], **({"conf": conf} if conf is not None else {}))
        detector = Detector(
            config["model"]["weights"], config["device"], config["model"]["imgsz"], self.cfg["conf"],
            config["model"].get("weights_url"), config["model"].get("weights_sha256"),
        )
        self.pipeline = Pipeline(detector, config, mode="head_crop")
        self.world, self.prompts = None, list(self.cfg["world_prompts"])
        if use_world:
            from ultralytics import YOLOWorld  # needs the `labeling` group (CLIP text encoder)

            path = ensure_weights(self.cfg["world_weights"], sha256=self.cfg["world_weights_sha256"])
            self.world = YOLOWorld(str(path))
            self.world.set_classes(self.prompts)

    def boxes(self, image) -> list[Box]:
        """Model boxes mapped to training classes, merged across both models."""
        found = [b for b in self.pipeline(image).boxes if b.source == "model"]
        if self.world is not None:
            r = self.world.predict(image, device=self.pipeline.detector.device, conf=self.cfg["conf"], verbose=False)[0]
            height, width = image.shape[:2]
            world = r.boxes
            rows = zip(world.xyxy.tolist(), world.cls.tolist(), world.conf.tolist()) if world is not None else ()
            for (x1, y1, x2, y2), cls, conf in rows:
                x1, x2 = max(0.0, x1), min(float(width), x2)
                y1, y2 = max(0.0, y1), min(float(height), y2)
                if x2 <= x1 or y2 <= y1:
                    continue
                target = self.cfg["world_prompts"][self.prompts[int(cls)]]
                # cls_id is a placeholder: only the training-class *name* is written out.
                found.append(Box(source="model", cls_id=0, cls_name=target, conf=float(conf), xyxy=(x1, y1, x2, y2)))
        kept = [b for b in found if normalize_class_name(b.cls_name) in self.classes]
        return nms_per_class(
            [b.model_copy(update={"cls_name": normalize_class_name(b.cls_name)}) for b in kept], self.cfg["nms_iou"]
        )

    def yolo_lines(self, boxes: list[Box], width: int, height: int) -> list[str]:
        return to_yolo_lines(boxes, self.classes, width, height)


def to_yolo_lines(boxes: list[Box], classes: list[str], width: int, height: int) -> list[str]:
    """Boxes (pixel xyxy, names in `classes`) -> YOLO 'cls cx cy w h' lines, normalized."""
    lines = []
    for b in boxes:
        x1, y1, x2, y2 = b.xyxy
        cx, cy = (x1 + x2) / 2 / width, (y1 + y2) / 2 / height
        w, h = (x2 - x1) / width, (y2 - y1) / height
        lines.append(f"{classes.index(normalize_class_name(b.cls_name))} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}")
    return lines


def prelabel(source: Path, out: Path, config: dict[str, Any], use_world: bool = True) -> Counter:
    images = sorted(p for p in source.rglob("*") if p.suffix.lower() in IMAGE_EXTS)
    if not images:
        raise SystemExit(f"no .jpg/.jpeg/.png images under {source}")
    labeler = Prelabeler(config, use_world)
    (out / "images").mkdir(parents=True, exist_ok=True)
    (out / "labels").mkdir(parents=True, exist_ok=True)
    (out / "classes.txt").write_text("\n".join(labeler.classes) + "\n")

    counts: Counter = Counter()
    for path in images:
        image = cv2.imread(str(path))
        if image is None:
            raise SystemExit(f"could not read {path}")
        # Flatten sub-folders into unique names so images/ and labels/ pair 1:1.
        stem = "__".join(path.relative_to(source).with_suffix("").parts)
        boxes = labeler.boxes(image)
        counts.update(b.cls_name for b in boxes)
        shutil.copy2(path, out / "images" / f"{stem}{path.suffix.lower()}")
        lines = labeler.yolo_lines(boxes, image.shape[1], image.shape[0])
        (out / "labels" / f"{stem}.txt").write_text("\n".join(lines) + ("\n" if lines else ""))
    print(f"{len(images)} images -> {out}  draft boxes: {dict(counts)}")
    return counts


def main(argv: Optional[list[str]] = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", type=Path)
    parser.add_argument("--out", type=Path, default=None, help="default: data/labeling/<source name>")
    parser.add_argument("--no-world", action="store_true", help="SH17 only (no CLIP / YOLO-World)")
    args = parser.parse_args(argv)
    out = args.out or REPO_ROOT / "data" / "labeling" / args.source.name
    prelabel(args.source, out, load_config(), use_world=not args.no_world)


if __name__ == "__main__":
    main()
