"""Build a YOLO training set in `training.classes` from an external dataset + boots review.

    uv run python -m tools.build_dataset footwear-w1uf6-v2 [--skip-unreviewed]

  - footwear classes are remapped via training.external.<name>.class_map
    ("review" -> per-box decision from tools/review_boots.py; "drop-image" removes the image)
  - people (training.pseudo_classes: person/head/face/hands) are pseudo-labelled with SH17 at
    training.pseudo_conf, filtered for consistency (see filter_pseudo), so people in these photos
    aren't learned as background. PPE classes are never pseudo-labelled on external data.
  - splits are kept (train / valid -> val / test); writes <out>/data.yaml and <out>/summary.json
"""

from __future__ import annotations

import argparse
import json
import shutil
from collections import Counter
from pathlib import Path
from typing import Any, Optional

import cv2
import yaml

from tools.prelabel import Prelabeler, to_yolo_lines
from tools.review_boots import ASSISTED, DECISIONS, load_json, merged_decisions
from vision.config import REPO_ROOT, load_config
from vision.render import normalize_class_name
from vision.schema import Box

SPLITS = {"train": "train", "valid": "val", "test": "test"}


def _centre_inside(box: Box, outer: Box) -> bool:
    cx, cy = (box.xyxy[0] + box.xyxy[2]) / 2, (box.xyxy[1] + box.xyxy[3]) / 2
    return outer.xyxy[0] <= cx <= outer.xyxy[2] and outer.xyxy[1] <= cy <= outer.xyxy[3]


def filter_pseudo(boxes: list[Box], keep_classes: set[str]) -> list[Box]:
    """Keep only self-consistent pseudo-labels on out-of-domain photos.

    SH17 on close-up shoe product shots invents 'person' on sandals, 'helmet' on footballs and
    'gloves' on laces. So: a person counts only if a head or face lies inside it; head / face /
    hands count only inside such a person; nothing outside `keep_classes` (PPE classes come from
    hand-checked labels only).
    """
    named = [(normalize_class_name(b.cls_name), b) for b in boxes]
    anchors = [b for n, b in named if n in ("head", "face")]
    people = [b for n, b in named if n == "person" and any(_centre_inside(a, b) for a in anchors)]
    kept = list(people)
    for name, box in named:
        if name in keep_classes and name != "person" and any(_centre_inside(box, p) for p in people):
            kept.append(box)
    return kept


def build(
    source: Path,
    out: Path,
    config: dict[str, Any],
    class_map: dict[str, str],
    decisions: dict[str, str],
    labeler: Any = None,
    skip_unreviewed: bool = False,
) -> dict[str, Any]:
    classes = [normalize_class_name(c) for c in config["training"]["classes"]]
    src_names = yaml.safe_load((source / "data.yaml").read_text())["names"]
    unknown = {v for v in class_map.values() if v != "review"} - set(classes)
    if unknown or set(src_names) - set(class_map):
        raise SystemExit(f"class_map mismatch: targets not in training.classes {unknown or '-'}; "
                         f"unmapped source classes {set(src_names) - set(class_map) or '-'}")
    pseudo_classes = {normalize_class_name(c) for c in config["training"]["pseudo_classes"]}

    # Resolve footwear lines first, so an incomplete review fails before any slow work.
    plan, unreviewed, dropped = [], [], 0
    for split in SPLITS:
        for label in sorted((source / split / "labels").glob("*.txt")):
            image = next((source / split / "images").glob(f"{label.stem}.*"), None)
            if image is None:
                continue
            lines, keep = [], True
            for i, line in enumerate(label.read_text().splitlines()):
                if not line.strip():
                    continue
                c, *coords = line.split()
                target = class_map[src_names[int(c)]]
                if target == "review":
                    target = decisions.get(f"{split}/{label.stem}#{i}")
                    if target is None:
                        unreviewed.append(f"{split}/{label.stem}#{i}")
                        keep = False
                        continue
                    if target == "drop-image":
                        keep = False
                        dropped += 1
                        break
                lines.append(f"{classes.index(target)} {' '.join(coords[:4])}")
            if keep:
                plan.append((split, image, lines))
    if unreviewed and not skip_unreviewed:
        raise SystemExit(
            f"{len(unreviewed)} boots boxes not reviewed yet (e.g. {unreviewed[0]}). Run "
            "`uv run python -m tools.review_boots review`, or pass --skip-unreviewed to leave those images out."
        )

    labeler = labeler or Prelabeler(config, use_world=False, conf=config["training"]["pseudo_conf"])
    counts = {SPLITS[s]: Counter() for s in SPLITS}
    for n, (split, image_path, lines) in enumerate(plan, 1):
        image = cv2.imread(str(image_path))
        if image is None:
            raise SystemExit(f"could not read {image_path}")
        pseudo = filter_pseudo(labeler.boxes(image), pseudo_classes)
        lines = lines + to_yolo_lines(pseudo, classes, image.shape[1], image.shape[0])
        dest = SPLITS[split]
        (out / dest / "images").mkdir(parents=True, exist_ok=True)
        (out / dest / "labels").mkdir(parents=True, exist_ok=True)
        shutil.copy2(image_path, out / dest / "images" / image_path.name)
        (out / dest / "labels" / f"{image_path.stem}.txt").write_text("\n".join(lines) + ("\n" if lines else ""))
        counts[dest].update(classes[int(line.split()[0])] for line in lines)
        if n % 200 == 0:
            print(f"built {n}/{len(plan)}", end="\r")

    (out / "data.yaml").write_text(yaml.safe_dump({
        "path": str(out.resolve()), "train": "train/images", "val": "val/images", "test": "test/images",
        "names": dict(enumerate(classes)),
    }, sort_keys=False))
    summary = {
        "source": str(source), "images": {s: sum(1 for p in plan if SPLITS[p[0]] == s) for s in counts},
        "instances": {s: dict(c) for s, c in counts.items()},
        "dropped_images": dropped, "skipped_unreviewed_boxes": len(unreviewed),
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2))
    return summary


def main(argv: Optional[list[str]] = None) -> None:
    config = load_config()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("name", choices=list(config["training"]["external"]))
    parser.add_argument("--out", type=Path, default=None, help="default: data/datasets/<name>")
    parser.add_argument("--skip-unreviewed", action="store_true")
    args = parser.parse_args(argv)
    out = args.out or REPO_ROOT / "data" / "datasets" / args.name
    if out.exists():
        shutil.rmtree(out)  # always rebuild from scratch: stale labels must not survive
    summary = build(
        REPO_ROOT / "data" / "external" / args.name, out, config,
        config["training"]["external"][args.name]["class_map"],
        merged_decisions(load_json(DECISIONS), load_json(ASSISTED)),
        skip_unreviewed=args.skip_unreviewed,
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
