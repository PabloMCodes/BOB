"""Live YOLOv8 on the Mac webcam — pipeline check before the iPhone stream exists.

    uv run python -m vision.detect [--camera N] [--config configs/local.yaml]

Without --camera, the first camera delivering a real (non-black) image is used. On macOS an
idle Continuity Camera iPhone can sit at index 0 and stream all-black frames.

Keys: q / Esc quit · s save snapshot to runs/detect/
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Callable, Optional

import cv2
import numpy as np

from vision.config import REPO_ROOT, load_config
from vision.pipeline import Pipeline
from vision.render import draw

SNAPSHOT_DIR = REPO_ROOT / "runs" / "detect"
MAX_CAMERA_INDEX = 4
WARMUP_FRAMES = 15  # cameras often emit a few black frames while starting up

PERMISSION_HINT = (
    "On macOS, grant camera access to VS Code (or your terminal) in System Settings > "
    "Privacy & Security > Camera, then fully restart it."
)


def _first_live_frame(cap: cv2.VideoCapture) -> Optional[np.ndarray]:
    """Read up to WARMUP_FRAMES; return the first frame that isn't pure black."""
    for _ in range(WARMUP_FRAMES):
        ok, frame = cap.read()
        if ok and frame is not None and frame.max() > 0:
            return frame
    return None


def open_camera(
    index: Optional[int], open_fn: Callable[[int], cv2.VideoCapture] = cv2.VideoCapture
) -> tuple[cv2.VideoCapture, int, np.ndarray]:
    """Open the requested camera, or auto-pick the first one producing a real image."""
    candidates = [index] if index is not None else list(range(MAX_CAMERA_INDEX))
    black: list[int] = []
    for i in candidates:
        cap = open_fn(i)
        if not cap.isOpened():
            cap.release()
            continue
        frame = _first_live_frame(cap)
        if frame is not None:
            return cap, i, frame
        black.append(i)
        cap.release()

    if black:
        raise SystemExit(
            f"Camera(s) {black} opened but only sent black frames. If one is an iPhone "
            f"(Continuity Camera), try another index with --camera N. {PERMISSION_HINT}"
        )
    raise SystemExit(f"No camera could be opened (tried {candidates}). {PERMISSION_HINT}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--camera", type=int, default=None, help="OpenCV camera index (default: auto)")
    parser.add_argument("--config", type=Path, default=None, help="override config YAML")
    parser.add_argument("--show-crops", action="store_true", help="outline head_crop regions")
    args = parser.parse_args()

    config = load_config(args.config)
    pipeline = Pipeline.from_config(config)
    detector = pipeline.detector
    categories, hide = config["render"]["categories"], config["render"].get("hide", [])

    cap, camera_index, frame = open_camera(args.camera)
    ok = True

    print(
        f"camera={camera_index} model={detector.model_id} device={detector.device} "
        f"mode={pipeline.mode} — press q to quit, s to snapshot"
    )
    fps = 0.0
    last = time.perf_counter()
    try:
        while ok:
            result = pipeline(frame)
            now = time.perf_counter()
            fps = 0.9 * fps + 0.1 * (1.0 / max(now - last, 1e-6)) if fps else 1.0 / max(now - last, 1e-6)
            last = now
            violations = sum(b.source == "derived" for b in result.boxes)
            status = (
                f"{detector.model_id} | {pipeline.mode} x{result.passes} | {detector.device} | "
                f"{result.inference_ms:.1f} ms | {fps:.1f} FPS | {violations} violations"
            )
            regions = result.crop_regions if args.show_crops else ()
            annotated = draw(frame, result.boxes, categories, status, hide, regions)
            cv2.imshow("BOB vision — webcam", annotated)

            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break
            if key == ord("s"):
                SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
                path = SNAPSHOT_DIR / f"webcam_{time.strftime('%Y%m%d_%H%M%S')}.jpg"
                cv2.imwrite(str(path), annotated)
                print(f"saved {path.relative_to(REPO_ROOT)}")
            ok, frame = cap.read()
    finally:
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
