"""Export real pipeline verdicts for the published website stills as a browser audit fixture.

    uv run python -m tools.export_audit_fixture

The in-browser second-opinion auditor (`web/src/audit/`) needs something to disagree with. On the
deployed site there is no hub and no rover, so it compares itself against this fixture: the actual
`vision.pipeline.Pipeline` output for the stills already shipped in `web/public/media/workers/`.

The fixture is recorded evidence of what the rover's model said, not ground truth. It carries the
model identity, weights hash and which rules were inactive, so the browser can state plainly that a
missing verdict is a missing capability rather than a pass. Re-run this whenever the weights, the
active config or the published stills change.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import cv2

from vision.config import REPO_ROOT, load_config, resolve_device
from vision.pipeline import Pipeline
from vision.render import normalize_class_name
from vision.schema import Box

FIXTURE_VERSION = 1
STILLS_DIR = REPO_ROOT / "web" / "public" / "media" / "workers"
OUTPUT = STILLS_DIR / "audit-fixture.json"
PUBLIC_PREFIX = "/media/workers"
# The annotated copies are renders of these same frames; auditing them would read the rover's
# own boxes back out of the pixels.
ANNOTATED_SUFFIX = "-detections"


def stills(directory: Path) -> list[Path]:
    return sorted(p for p in directory.glob("*.jpg") if not p.stem.endswith(ANNOTATED_SUFFIX))


def box_json(box: Optional[Box]) -> Optional[dict[str, Any]]:
    if box is None:
        return None
    return {
        "source": str(box.source),
        "cls_name": box.cls_name,
        "conf": round(float(box.conf), 4),
        "xyxy": [round(float(v), 2) for v in box.xyxy],
    }


def image_json(path: Path, pipeline: Pipeline) -> dict[str, Any]:
    image = cv2.imread(str(path))
    if image is None:
        raise OSError(f"could not read {path}")
    result = pipeline(image)
    return {
        "src": f"{PUBLIC_PREFIX}/{path.name}",
        "image_size": [int(result.image_size.width), int(result.image_size.height)],
        "inference_ms": round(float(result.inference_ms), 1),
        "passes": int(result.passes),
        "boxes": [box_json(b) for b in result.boxes],
        "verdicts": [
            {
                "rule": v.rule,
                "verdict": v.verdict.value,
                "subject": box_json(v.subject),
                "ppe": box_json(v.ppe),
                "violation": box_json(v.violation),
            }
            for v in result.verdicts
        ],
    }


def fixture(config: dict[str, Any], pipeline: Pipeline, paths: list[Path]) -> dict[str, Any]:
    available = {normalize_class_name(c) for c in pipeline.names.values()}
    return {
        "fixture_version": FIXTURE_VERSION,
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "note": "Real vision.pipeline output for the published stills. Recorded rover-model claims, "
                "not ground truth. Supplied photographs, not rover captures.",
        "model_id": pipeline.model_id,
        "weights_sha256": config["model"].get("weights_sha256"),
        "device": resolve_device(config.get("device", "auto")),
        "mode": pipeline.mode,
        "imgsz": pipeline.imgsz,
        "edge_margin": pipeline.edge_margin,
        "active_rules": sorted(r.name for r in pipeline.rules),
        "inactive_rules": [
            {"name": r.name, "missing_classes": sorted(r.requires - available)}
            for r in sorted(pipeline.inactive_rules, key=lambda r: r.name)
        ],
        "images": [image_json(p, pipeline) for p in paths],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", type=Path, default=None, help="config file (default: configs/default.yaml + local)")
    parser.add_argument("--stills", type=Path, default=STILLS_DIR, help="directory of published stills")
    parser.add_argument("--out", type=Path, default=OUTPUT, help="fixture path to write")
    args = parser.parse_args()

    paths = stills(args.stills)
    if not paths:
        raise SystemExit(f"no stills found in {args.stills}")

    config = load_config(args.config)
    pipeline = Pipeline.from_config(config)
    data = fixture(config, pipeline, paths)

    args.out.write_text(json.dumps(data, indent=2) + "\n")
    judged = sum(1 for i in data["images"] for v in i["verdicts"])
    print(f"[audit-fixture] {len(paths)} stills, {judged} subject verdicts -> {args.out}")
    print(f"[audit-fixture] model {data['model_id']} on {data['device']}, active rules {data['active_rules']}")
    for rule in data["inactive_rules"]:
        print(f"[audit-fixture] rule {rule['name']!r} inactive: model lacks {rule['missing_classes']}")


if __name__ == "__main__":
    main()
