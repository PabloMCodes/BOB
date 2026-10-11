"""Build a reviewed one-class eyewear dataset and train the optional eyewear specialist.

    uv run python -m tools.train_eyewear build
    uv run python -m tools.train_eyewear train
    uv run python -m tools.train_eyewear test --weights runs/eyewear/<name>/weights/best.pt

Source: data/external/safety-final-v1 (Roboflow shashank-lwxqs/safety-final-kqmxp v1, CC BY 4.0).
Only its goggles / no-goggles boxes are used, through the per-box review: glasses -> class 0,
no-glasses -> no box (the face stays as background), unclear / drop-image / unreviewed -> the
whole image is excluded. Images without any eyewear box are excluded too: nobody reviewed whether
their people wear eyewear. Human review (eyewear_review.json) overrides the assisted one.
No pseudo-labels and no data/eval input.
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

from vision.config import REPO_ROOT, resolve_device
from vision.detector import ensure_weights

SOURCE = REPO_ROOT / "data/external/safety-final-v1"
OUT = REPO_ROOT / "data/datasets/eyewear-reviewed-v1"
DECISIONS = REPO_ROOT / "data/labeling/eyewear_review.json"
ASSISTED = REPO_ROOT / "data/labeling/eyewear_review_assisted.json"
RECIPE = REPO_ROOT / "configs/train_eyewear.yaml"
NAMES = ["glasses"]
EYEWEAR = {"goggles", "no-goggles"}
KEEP = {"glasses", "no-glasses"}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_decisions(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text())
    return data.get("decisions", data)


def build(source: Path, out: Path, decisions: dict[str, str], seed: int = 42) -> dict:
    """Keep whole fully-reviewed images; keep filename families and exact duplicates in one split."""
    if out.exists():
        raise FileExistsError(f"Refusing to overwrite dataset: {out}")
    names = yaml.safe_load((source / "data.yaml").read_text())["names"]
    if not EYEWEAR <= set(names):
        raise ValueError(f"Source has no {sorted(EYEWEAR)} classes")
    rows, excluded = [], []
    parents: dict[str, str] = {}

    def root(key: str) -> str:
        parents.setdefault(key, key)
        if parents[key] != key:
            parents[key] = root(parents[key])
        return parents[key]

    for split in ("train", "valid", "test"):
        for label in sorted((source / split / "labels").glob("*.txt")):
            lines, reasons, eyewear_boxes = [], set(), 0
            for i, line in enumerate(label.read_text().splitlines()):
                if not line.strip():
                    continue
                cls, *coords = line.split()
                if names[int(cls)] not in EYEWEAR:
                    continue
                if len(coords) != 4 or any(not 0 <= float(v) <= 1 for v in coords):
                    raise ValueError(f"Invalid box: {label}:{i}")
                eyewear_boxes += 1
                decision = decisions.get(f"{split}/{label.stem}#{i}")
                if decision not in KEEP:
                    reasons.add(decision or "unreviewed")
                elif decision == "glasses":
                    lines.append(f"0 {' '.join(coords)}")
            if eyewear_boxes == 0:
                reasons.add("no-eyewear-box")
            if reasons:
                excluded.append({"source": f"{split}/{label.stem}", "reasons": sorted(reasons)})
                continue
            images = list((source / split / "images").glob(f"{label.stem}.*"))
            if len(images) != 1:
                raise ValueError(f"Expected exactly one image for {label}")
            sha = digest(images[0])
            family = "family:" + label.stem.split(".rf.")[0]
            parents[root("sha:" + sha)] = root(family)
            rows.append({"source": str(images[0].relative_to(source)), "sha256": sha,
                         "family": family, "labels": lines})

    groups = defaultdict(list)
    for row in rows:
        row["group"] = root(row["family"])
        groups[row["group"]].append(row)
    rng = random.Random(seed)
    strata = defaultdict(list)
    for key, members in sorted(groups.items()):
        strata[any(row["labels"] for row in members)].append(key)
    for keys in strata.values():
        rng.shuffle(keys)
        if len(keys) < 10:
            raise ValueError("Too few independent source groups for train/val/test")
        n = max(1, round(len(keys) * 0.1))
        for i, key in enumerate(keys):
            for row in groups[key]:
                row["split"] = "test" if i < n else "val" if i < 2 * n else "train"

    instances, images, with_glasses = Counter(), Counter(), Counter()
    for row in rows:
        original = source / row["source"]
        stem = original.parts[-3] + "_" + original.stem  # original split avoids basename collisions
        dest = out / row["split"] / "images" / (stem + original.suffix)
        dest.parent.mkdir(parents=True, exist_ok=True)
        (out / row["split"] / "labels").mkdir(parents=True, exist_ok=True)
        shutil.copy2(original, dest)
        (out / row["split"] / "labels" / (stem + ".txt")).write_text("".join(f"{l}\n" for l in row["labels"]))
        images[row["split"]] += 1
        instances[row["split"]] += len(row["labels"])
        with_glasses[row["split"]] += bool(row["labels"])
        row["output"] = str(dest.relative_to(out))

    summary = {"source": str(source), "seed": seed, "names": NAMES,
               "images": dict(images), "glasses_instances": dict(instances),
               "images_with_glasses": dict(with_glasses), "groups": len(groups),
               "excluded_images": len(excluded),
               "exclusion_reasons": dict(Counter(r for e in excluded for r in e["reasons"])),
               "split_method": "80/10/10 by source-filename and exact-byte-hash groups, stratified by glasses presence",
               "convention": "glasses = any eyewear worn over the eyes; no-glasses faces kept as background"}
    (out / "data.yaml").write_text(yaml.safe_dump({"path": str(out.resolve()), "train": "train/images",
                                                   "val": "val/images", "test": "test/images", "names": NAMES}))
    (out / "manifest.json").write_text(json.dumps({"summary": summary, "images": rows, "excluded": excluded}, indent=2))
    (out / "summary.json").write_text(json.dumps(summary, indent=2))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=["build", "train", "test"])
    parser.add_argument("--recipe", type=Path, default=RECIPE)
    parser.add_argument("--weights", type=Path, help="test: trained weights to evaluate")
    parser.add_argument("--device", default=None)
    args = parser.parse_args()
    recipe = yaml.safe_load(args.recipe.read_text())
    if args.action == "build":
        decisions = {**load_decisions(ASSISTED), **load_decisions(DECISIONS)}  # human wins
        summary = build(SOURCE, OUT, decisions, recipe["seed"])
        summary["review_sha256"] = {p.name: digest(p) for p in (DECISIONS, ASSISTED) if p.exists()}
        (OUT / "summary.json").write_text(json.dumps(summary, indent=2))
        print(json.dumps(summary, indent=2))
        return

    from ultralytics import YOLO

    device = resolve_device(args.device or recipe.pop("device"))
    recipe.pop("device", None)
    recipe["project"] = str((REPO_ROOT / recipe["project"]).resolve())
    if args.action == "train":
        weights = ensure_weights(recipe.pop("weights"), sha256=recipe.pop("weights_sha256"))
        result = YOLO(str(weights)).train(data=str(OUT / "data.yaml"), device=device, **recipe)
        print(json.dumps(result.results_dict, indent=2))
        return
    if args.weights is None:
        raise SystemExit("test needs --weights")
    model = YOLO(str(args.weights))
    if list(model.names.values()) != NAMES:
        raise ValueError("Expected a trained one-class eyewear model")
    result = model.val(data=str(OUT / "data.yaml"), split="test", device=device, imgsz=recipe["imgsz"],
                       batch=recipe["batch"], workers=0, project=recipe["project"], name="heldout-test",
                       plots=True, exist_ok=True)
    report = {"weights": str(args.weights), "sha256": digest(args.weights), "split": "test",
              "metrics": result.results_dict}
    (Path(result.save_dir) / "metrics.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
