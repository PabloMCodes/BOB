"""Inspect an upright still image with an operator-defined restricted polygon.

uv run python -m tools.inspect_zone image.jpg --polygon '0.1,0.6;0.8,0.6;0.8,0.95;0.1,0.95'
Coordinates are normalized to the full upright image; no automatic EXIF/sensor rotation.
Outputs: pinned zone.json, findings.json, annotated.jpg. This is not a live-camera registration.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from uuid import uuid4

import cv2
import numpy as np
import yaml

from vision.config import load_config
from vision.pipeline import Pipeline
from vision.schema import ImageSize
from vision.zones import ImageZone, assess_zone, draw_zone


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--polygon", help="ordered normalized x,y pairs separated by semicolons")
    choice.add_argument("--zone", type=Path, help="existing image-bound zone.json")
    choice.add_argument("--tape-config", type=Path, help="operator-declared closed yellow floor-tape convention")
    parser.add_argument("--zone-id", default="restricted-1")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    raw = args.image.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    # IMREAD_IGNORE_ORIENTATION makes the supplied pixel-coordinate convention explicit.
    image = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR | cv2.IMREAD_IGNORE_ORIENTATION)
    if image is None:
        raise SystemExit("Image cannot be decoded")
    h, w = image.shape[:2]
    zone = None
    if args.tape_config:
        from vision.tape import TapeConfig, detect_tape
        tape = TapeConfig.model_validate(yaml.safe_load(args.tape_config.read_text()))
        region = detect_tape(image, tape)
    elif args.zone:
        zone = ImageZone.model_validate_json(args.zone.read_text())
    else:
        zone = ImageZone(zone_id=args.zone_id, image_sha256=sha, width=w, height=h,
                         polygon=tuple(tuple(map(float, p.split(','))) for p in args.polygon.split(';')))
    if zone is not None:
        region = zone.region(sha, ImageSize(width=w, height=h))
    pipeline = Pipeline.from_config(load_config(args.config))
    result = pipeline(image)
    assessment = assess_zone(region, result.boxes, result.image_size)
    out = args.out or Path("runs/zones") / time.strftime("%Y%m%d_%H%M%S")
    out.mkdir(parents=True, exist_ok=False)
    (out / "zone.json").write_text((zone or tape).model_dump_json(indent=2))
    report = {"observation_id": str(uuid4()), "source_mode": "STILL", "source_image": args.image.name,
              "image_sha256": sha, "model_id": pipeline.model_id, "model_classes": pipeline.names,
              "image_size": result.image_size.model_dump(), "boxes": [b.model_dump() for b in result.boxes],
              "assessment": assessment.as_dict()}
    (out / "findings.json").write_text(json.dumps(report, indent=2))
    if not cv2.imwrite(str(out / "annotated.jpg"), draw_zone(image, assessment)):
        raise OSError("Could not write annotated evidence")
    print(json.dumps(assessment.as_dict(), indent=2))
    print(f"Evidence and pinned zone: {out}")


if __name__ == "__main__":
    main()
