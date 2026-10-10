"""YOLOv8 wrapper: upright BGR image -> schema Boxes + timing. Weights-agnostic."""

from __future__ import annotations

import hashlib
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import numpy as np

from vision.config import REPO_ROOT, resolve_device
from vision.schema import Box, ImageSize


@dataclass(frozen=True)
class Detections:
    boxes: list[Box]
    image_size: ImageSize
    inference_ms: float  # wall time of predict incl. pre/post-processing and device sync


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_weights(
    weights: str | Path, url: Optional[str] = None, sha256: Optional[str] = None
) -> Path:
    """Resolve weights relative to the repo root, downloading if missing.

    With `url`, downloads from it; otherwise falls back to known Ultralytics assets.
    With `sha256`, the file must match — weights are pickles, so a tampered file runs code.
    """
    path = Path(weights)
    if not path.is_absolute():
        path = REPO_ROOT / path
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        if url:
            tmp = path.with_suffix(".part")
            urllib.request.urlretrieve(url, tmp)
            tmp.rename(path)
        else:
            from ultralytics.utils.downloads import attempt_download_asset

            attempt_download_asset(path)
        if not path.exists():
            raise FileNotFoundError(f"weights not found and could not be downloaded: {path}")
    if sha256 and _sha256(path) != sha256:
        raise ValueError(f"sha256 mismatch for {path}; refusing to load (delete it to re-download)")
    return path


class Detector:
    def __init__(
        self,
        weights: str | Path,
        device: str = "auto",
        imgsz: int = 640,
        conf: float = 0.35,
        weights_url: Optional[str] = None,
        weights_sha256: Optional[str] = None,
    ) -> None:
        from ultralytics import YOLO

        self.weights = ensure_weights(weights, weights_url, weights_sha256)
        self.device = resolve_device(device)
        self.imgsz = imgsz
        self.conf = conf
        self.model = YOLO(str(self.weights))
        self.names: dict[int, str] = dict(self.model.names)
        self.model_id = self.weights.stem
        self.warmup(imgsz)

    def warmup(self, imgsz: int) -> None:
        """First MPS/CUDA call per input shape compiles kernels; keep it out of measured latency."""
        self.model.predict(
            np.zeros((imgsz, imgsz, 3), dtype=np.uint8), device=self.device, imgsz=imgsz, verbose=False
        )

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> Detector:
        model = config["model"]
        return cls(
            model["weights"],
            config["device"],
            model["imgsz"],
            model["conf"],
            model.get("weights_url"),
            model.get("weights_sha256"),
        )

    def __call__(
        self, image_bgr: np.ndarray, imgsz: Optional[int] = None, conf: Optional[float] = None
    ) -> Detections:
        if image_bgr.ndim != 3 or image_bgr.shape[2] != 3 or image_bgr.dtype != np.uint8:
            raise ValueError(f"expected HxWx3 uint8 BGR image, got {image_bgr.shape} {image_bgr.dtype}")
        height, width = image_bgr.shape[:2]

        start = time.perf_counter()
        result = self.model.predict(
            image_bgr,
            device=self.device,
            imgsz=imgsz or self.imgsz,
            conf=self.conf if conf is None else conf,
            verbose=False,
        )[0]
        xyxy = result.boxes.xyxy.cpu().numpy()  # .cpu() forces device sync before timing stops
        cls_ids = result.boxes.cls.cpu().numpy().astype(int)
        confs = result.boxes.conf.cpu().numpy()
        inference_ms = (time.perf_counter() - start) * 1000.0

        boxes = []
        for (x1, y1, x2, y2), cls_id, conf in zip(xyxy, cls_ids, confs):
            x1, x2 = np.clip([x1, x2], 0, width)
            y1, y2 = np.clip([y1, y2], 0, height)
            if x2 <= x1 or y2 <= y1:
                continue  # degenerate after clipping; schema forbids it
            boxes.append(
                Box(
                    source="model",
                    cls_id=int(cls_id),
                    cls_name=self.names[int(cls_id)],
                    conf=float(conf),
                    xyxy=(float(x1), float(y1), float(x2), float(y2)),
                )
            )
        return Detections(boxes, ImageSize(width=width, height=height), inference_ms)
