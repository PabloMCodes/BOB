"""Conservative image-space recognition of the operator's closed yellow floor-tape convention.

No OCR, floor-plane estimation, hidden-edge reconstruction, or memory of an old boundary.
"""
from __future__ import annotations

from typing import Literal

import cv2
import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

from vision.zones import ZoneRegion


class TapeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    scene_version: Literal[1] = 1
    mode: Literal["yellow_closed_outline"] = "yellow_closed_outline"
    zone_id: str = Field(default="restricted-yellow-1", min_length=1, max_length=80)
    # This is operator-declared meaning/setup, not a fact inferred from the pixels.
    inside_is_restricted: Literal[True]
    boundary_is_on_floor: Literal[True]
    hue_min: int = Field(default=18, ge=0, le=179, strict=True)
    hue_max: int = Field(default=40, ge=0, le=179, strict=True)
    min_saturation: int = Field(default=100, ge=0, le=255, strict=True)
    min_value: int = Field(default=90, ge=0, le=255, strict=True)
    min_area_fraction: float = Field(default=.01, gt=0, lt=1)
    max_area_fraction: float = Field(default=.8, gt=0, lt=1)

    @model_validator(mode="after")
    def ordered(self):
        if self.hue_min > self.hue_max or self.min_area_fraction >= self.max_area_fraction:
            raise ValueError("threshold bounds must be ordered")
        return self


def detect_tape(image: np.ndarray, config: TapeConfig) -> ZoneRegion:
    """Use the enclosed hole in a yellow connected outline, never its convex hull.

    All candidates must be considered before selecting one: two valid outlines are ambiguous.
    We deliberately do not join disconnected strips or project a last-known boundary.
    """
    if image.ndim != 3 or image.shape[2] != 3 or image.dtype != np.uint8:
        raise ValueError("expected upright uint8 BGR image")
    h, w = image.shape[:2]
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (config.hue_min, config.min_saturation, config.min_value),
                       (config.hue_max, 255, 255))
    contours, hierarchy = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    candidates = []
    if hierarchy is not None:
        for i, contour in enumerate(contours):
            parent = hierarchy[0][i][3]
            if parent < 0:
                continue  # yellow blobs without an enclosed region are not boundaries
            area = cv2.contourArea(contour)
            if not config.min_area_fraction * w * h <= area <= config.max_area_fraction * w * h:
                continue
            outer = contours[parent].reshape(-1, 2)
            if np.any(outer[:, 0] <= 1) or np.any(outer[:, 0] >= w-2) or np.any(outer[:, 1] <= 1) or np.any(outer[:, 1] >= h-2):
                continue  # image border is not a visible tape boundary
            polygon = cv2.approxPolyDP(contour, .008 * cv2.arcLength(contour, True), True)
            if len(polygon) < 3 or len(polygon) > 12 or not cv2.isContourConvex(polygon):
                continue
            candidates.append(tuple((float(x), float(y)) for x, y in polygon.reshape(-1, 2)))
    if len(candidates) != 1:
        reason = "multiple_closed_yellow_regions" if candidates else "no_complete_yellow_outline"
        return ZoneRegion(config.zone_id, "unverified", reason, ())
    return ZoneRegion(config.zone_id, "recognized", "operator_declared_yellow_floor_tape", candidates[0])
