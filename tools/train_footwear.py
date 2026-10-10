"""Build an audited two-class dataset and train the optional footwear specialist.

    uv run python -m tools.train_footwear build
    uv run python -m tools.train_footwear train

No pseudo-labels and no data/eval input. Human review overrides assisted review.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import shutil
from collections import Counter, defaultdict
from pathlib import Path

import yaml

from tools.review_boots import ASSISTED, DATASET, DECISIONS, load_json, merged_decisions
from vision.config import REPO_ROOT, resolve_device
from vision.detector import ensure_weights

OUT = REPO_ROOT / "data/datasets/footwear-reviewed-v1"
RECIPE = REPO_ROOT / "configs/train_footwear.yaml"
NAMES = ["shoes", "safety-boots"]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(source: Path, out: Path, decisions: dict[str, str], seed: int = 42) -> dict:
    """Keep whole eligible images; keep filename families and exact duplicates in one split."""
    if out.exists():
        raise FileExistsError(f"Refusing to overwrite dataset: {out}")
    names = yaml.safe_load((source / "data.yaml").read_text())["names"]
    if set(names) != {"boots", "flip_flops", "loafers", "sandals", "sneakers", "soccer"}:
        raise ValueError("Unexpected source classes")
    rows, excluded = [], []
    parents: dict[str, str] = {}

    def root(key):
        parents.setdefault(key, key)
        if parents[key] != key:
            parents[key] = root(parents[key])
        return parents[key]

    for split in ("train", "valid", "test"):
        for label in sorted((source / split / "labels").glob("*.txt")):
            lines, reasons = [], set()
            for i, line in enumerate(label.read_text().splitlines()):
                if not line.strip():
                    continue
                cls, *coords = line.split()
                if len(coords) != 4 or any(not 0 <= float(v) <= 1 for v in coords):
                    raise ValueError(f"Invalid box: {label}:{i}")
                target = "shoes" if names[int(cls)] != "boots" else decisions.get(f"{split}/{label.stem}#{i}")
                if target is None or target == "drop-image":
                    reasons.add("unreviewed" if target is None else target)
                elif target in NAMES:
                    lines.append(f"{NAMES.index(target)} {' '.join(coords)}")
                else:
                    raise ValueError(f"Unknown review decision: {target}")
            if reasons:
                excluded.append({"source": f"{split}/{label.stem}", "reasons": sorted(reasons)})
                continue
            images = list((source / split / "images").glob(f"{label.stem}.*"))
            if len(images) != 1:
                raise ValueError(f"Expected exactly one image for {label}")
            image = images[0]
            sha = digest(image)
            family = "family:" + label.stem.split(".rf.")[0]
            parents[root("sha:" + sha)] = root(family)
            rows.append({"source": str(image.relative_to(source)), "sha256": sha,
                         "family": family, "labels": lines, "label_sha256": digest(label)})
    groups = defaultdict(list)
    for row in rows:
        row["group"] = root(row["family"])
        groups[row["group"]].append(row)
    rng = random.Random(seed)
    strata = defaultdict(list)
    for key, members in sorted(groups.items()):
        positive = any(line.startswith("1 ") for row in members for line in row["labels"])
        strata[positive].append(key)
    for keys in strata.values():
        rng.shuffle(keys)
        if len(keys) < 10:
            raise ValueError("Too few independent source groups for train/val/test")
        n = max(1, round(len(keys) * .1))
        for i, key in enumerate(keys):
            split = "test" if i < n else "val" if i < 2 * n else "train"
            for row in groups[key]:
                row["split"] = split
    counts, images = defaultdict(Counter), Counter()
    for row in rows:
        split = row["split"]
        original = source / row["source"]
        # Include the original split to prevent basename collisions.
        stem = original.parts[-3] + "_" + original.stem
        dest = out / split / "images" / (stem + original.suffix)
        dest.parent.mkdir(parents=True, exist_ok=True)
        labels = out / split / "labels"
        labels.mkdir(parents=True, exist_ok=True)
        shutil.copy2(original, dest)
        (labels / (stem + ".txt")).write_text("\n".join(row["labels"]) + "\n")
        counts[split].update(NAMES[int(line.split()[0])] for line in row["labels"])
        images[split] += 1
        row["output"] = str(dest.relative_to(out))
    summary = {"source": str(source), "seed": seed, "names": NAMES,
               "images": dict(images), "instances": dict(counts),
               "groups": len(groups), "positive_groups": len(strata[True]),
               "excluded_images": len(excluded),
               "exclusion_reasons": dict(Counter(r for e in excluded for r in e["reasons"])),
               "split_method": "80/10/10 source-filename and exact-byte-hash groups, stratified by safety-boots presence",
               "limitation": "Embedded mosaics and unidentified visual duplicates may share content across groups."}
    (out / "data.yaml").write_text(yaml.safe_dump({"path": str(out.resolve()),
        "train": "train/images", "val": "val/images", "test": "test/images", "names": NAMES}))
    (out / "manifest.json").write_text(json.dumps({"summary": summary, "images": rows, "excluded": excluded}, indent=2))
    (out / "summary.json").write_text(json.dumps(summary, indent=2))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["build", "train", "test"])
    parser.add_argument("--recipe", type=Path, default=RECIPE)
    parser.add_argument("--model-config", type=Path, default=REPO_ROOT / "configs/footwear.yaml")
    parser.add_argument("--device", default=None, help="override training/evaluation device")
    args = parser.parse_args()
    recipe = yaml.safe_load(args.recipe.read_text())
    if args.action == "build":
        summary = build(DATASET, OUT, merged_decisions(load_json(DECISIONS), load_json(ASSISTED)), recipe["seed"])
        summary["review_sha256"] = {p.name: digest(p) for p in (DECISIONS, ASSISTED)}
        (OUT / "summary.json").write_text(json.dumps(summary, indent=2))
        print(json.dumps(summary, indent=2))
        return
    from ultralytics import YOLO
    device = resolve_device(args.device or recipe["device"])
    recipe.pop("device")
    recipe["project"] = str((REPO_ROOT / recipe["project"]).resolve())
    weights_name, weights_hash = recipe.pop("weights"), recipe.pop("weights_sha256")
    if args.action == "test":
        specialist = yaml.safe_load(args.model_config.read_text())["footwear_model"]
        weights_name, weights_hash = specialist["weights"], specialist["weights_sha256"]
    if not weights_hash:
        raise ValueError("A pinned weights_sha256 is required")
    weights = ensure_weights(weights_name, sha256=weights_hash)
    model = YOLO(str(weights))
    if args.action == "train":
        result = model.train(data=str(OUT / "data.yaml"), device=device, **recipe)
    else:
        if list(model.names.values()) != NAMES:
            raise ValueError("Expected trained two-class footwear model")
        result = model.val(data=str(OUT / "data.yaml"), split="test", device=device,
                           imgsz=recipe["imgsz"], batch=recipe["batch"], workers=0,
                           project=recipe["project"], name="heldout-test", plots=True)
        report = {"weights": str(weights), "sha256": weights_hash, "split": "test",
                  "metrics": result.results_dict,
                  "per_class": {NAMES[int(c)]: dict(zip(["precision", "recall", "mAP50", "mAP50-95"],
                                    map(float, result.box.class_result(i))))
                                for i, c in enumerate(result.box.ap_class_index)}}
        (Path(result.save_dir) / "metrics.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(result.results_dict, indent=2))


if __name__ == "__main__":
    main()
