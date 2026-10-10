"""Benchmark Detector latency per available device on a bundled sample image.

    uv run python -m tools.benchmark_detector [--runs 50]
"""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np
import torch
import ultralytics

from vision.config import load_config
from vision.detector import Detector

SAMPLE = Path(ultralytics.__file__).parent / "assets" / "bus.jpg"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=50)
    args = parser.parse_args()

    config = load_config()
    image = cv2.imread(str(SAMPLE))
    devices = ["cpu"] + (["mps"] if torch.backends.mps.is_available() else [])
    devices += ["cuda"] if torch.cuda.is_available() else []

    print(f"image={SAMPLE.name} {image.shape[1]}x{image.shape[0]} imgsz={config['model']['imgsz']} runs={args.runs}")
    for device in devices:
        detector = Detector(config["model"]["weights"], device, config["model"]["imgsz"], config["model"]["conf"])
        times = np.array([detector(image).inference_ms for _ in range(args.runs)])
        p50, p95 = np.percentile(times, [50, 95])
        print(f"{device:5s} p50={p50:6.1f} ms  p95={p95:6.1f} ms  ~{1000 / p50:5.1f} FPS")


if __name__ == "__main__":
    main()
