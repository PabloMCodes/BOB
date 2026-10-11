"""Run the shared pipeline over supplied stills and keep the boxes as reviewable evidence.

uv run python -m tools.showcase_stills photo.jpg --out runs/showcase/my-set
uv run python -m tools.showcase_stills photo.jpg --mode single --out runs/showcase/single

These are supplied photographs, not rover captures: there is no session, pose or frame
timestamp, so nothing here is a DetectionEvent and no observation is localized. The point is
only to show what this model reports on an image anyone can re-download and re-run.

Each still gets <name>/result.json (source hash, model identity, boxes, per-rule verdicts) and
<name>/annotated.jpg. `--mode` overrides pipeline.mode so one still can be compared across
passes; a half-body framing touching the image edge stays unverified either way.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np

from vision.config import load_config
from vision.pipeline import MODES, Pipeline
from vision.render import draw


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("images", type=Path, nargs="+")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--mode", choices=MODES, help="override pipeline.mode for this run")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--status", help="banner drawn into every annotated image")
    args = parser.parse_args()

    config = load_config(args.config)
    if args.mode:
        config["pipeline"]["mode"] = args.mode
    pipeline = Pipeline.from_config(config)
    args.out.mkdir(parents=True, exist_ok=True)

    for path in args.images:
        raw = path.read_bytes()
        # IMREAD_IGNORE_ORIENTATION: the stored pixels are the coordinate frame, as in inspect_zone.
        image = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR | cv2.IMREAD_IGNORE_ORIENTATION)
        if image is None:
            raise SystemExit(f"{path} cannot be decoded")
        result = pipeline(image)
        out = args.out / path.stem
        out.mkdir(parents=True, exist_ok=True)
        report = {
            "source": path.name,
            "source_sha256": hashlib.sha256(raw).hexdigest(),
            "source_mode": "STILL",
            "model_id": pipeline.model_id,
            "pipeline_mode": config["pipeline"]["mode"],
            "image_size": result.image_size.model_dump(),
            "inference_ms": round(result.inference_ms, 1),
            "passes": result.passes,
            "boxes": [b.model_dump() for b in result.boxes],
            "verdicts": [
                {"rule": v.rule, "verdict": v.verdict.value,
                 "subject": v.subject.model_dump(),
                 "ppe": v.ppe.model_dump() if v.ppe else None,
                 "violation": v.violation.model_dump() if v.violation else None}
                for v in result.verdicts
            ],
        }
        (out / "result.json").write_text(json.dumps(report, indent=2))
        annotated = draw(image, result.boxes, config["render"]["categories"],
                         status=args.status, hide=config["render"].get("hide", ()),
                         regions=result.crop_regions)
        if not cv2.imwrite(str(out / "annotated.jpg"), annotated):
            raise OSError(f"Could not write {out / 'annotated.jpg'}")
        counts: dict[str, int] = {}
        for box in result.boxes:
            counts[box.cls_name] = counts.get(box.cls_name, 0) + 1
        print(f"{path.name}: {result.passes} passes, {result.inference_ms:.0f} ms, "
              f"{len(result.boxes)} boxes {counts}")
        for verdict in result.verdicts:
            print(f"    {verdict.rule:8s} {verdict.verdict.value}")
    print(f"Evidence: {args.out}")


if __name__ == "__main__":
    main()
