"""Draw schema Boxes with safety-semantic colors. Never mutates the input frame."""

from __future__ import annotations

from typing import Iterable, Optional

import cv2
import numpy as np

from vision.schema import Box

# BGR
CATEGORY_COLORS: dict[str, tuple[int, int, int]] = {
    "violation": (0, 0, 230),
    "compliant": (0, 190, 0),
    "person": (230, 120, 0),
    "other": (160, 160, 160),
}


def normalize_class_name(name: str) -> str:
    return name.strip().lower().replace("_", "-").replace(" ", "-")


def categorize(cls_name: str, categories: dict[str, list[str]]) -> str:
    """Map a class name to violation / compliant / person / other via config lists."""
    name = normalize_class_name(cls_name)
    for category, names in categories.items():
        if name in {normalize_class_name(n) for n in names}:
            return category
    return "other"


def draw(
    image: np.ndarray,
    boxes: Iterable[Box],
    categories: dict[str, list[str]],
    status: Optional[str] = None,
    hide: Iterable[str] = (),
    regions: Iterable[tuple[int, int, int, int]] = (),
) -> np.ndarray:
    """Draw boxes (except `hide` classes) and optional thin grey crop `regions`."""
    out = image.copy()
    font, scale, thickness = cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1
    hidden = {normalize_class_name(n) for n in hide}

    for x1, y1, x2, y2 in regions:
        cv2.rectangle(out, (x1, y1), (x2, y2), CATEGORY_COLORS["other"], 1)

    for box in boxes:
        if normalize_class_name(box.cls_name) in hidden:
            continue
        color = CATEGORY_COLORS[categorize(box.cls_name, categories)]
        x1, y1, x2, y2 = (int(round(v)) for v in box.xyxy)
        cv2.rectangle(out, (x1, y1), (x2, y2), color, 2)
        label = f"{box.cls_name} {box.conf:.2f}"
        (tw, th), baseline = cv2.getTextSize(label, font, scale, thickness)
        ty = max(y1, th + baseline)  # keep label on-screen for boxes touching the top edge
        cv2.rectangle(out, (x1, ty - th - baseline), (x1 + tw, ty), color, cv2.FILLED)
        cv2.putText(out, label, (x1, ty - baseline), font, scale, (255, 255, 255), thickness, cv2.LINE_AA)

    if status:
        (tw, th), baseline = cv2.getTextSize(status, font, scale, thickness)
        cv2.rectangle(out, (0, 0), (tw + 10, th + baseline + 10), (0, 0, 0), cv2.FILLED)
        cv2.putText(out, status, (5, th + 5), font, scale, (255, 255, 255), thickness, cv2.LINE_AA)
    return out
