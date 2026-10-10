"""Image-space walkway obstruction evidence for a fixed camera. No metric or world geometry.

Independent walkway contract (`walkway_version: 1`), not an extension of frozen C2 or scene v1.
The walkway is an operator-drawn quadrilateral on a declared-empty reference image; occupancy
evidence is change against that reference. A changed pixel is evidence for human review, never
a verified object footprint: tall objects also hide floor behind them in the image.
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import cv2
import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator


class WalkwayConfig(BaseModel):
    """Prototype evidence filters — demo defaults, not validated worksite accuracy thresholds."""
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    walkway_version: Literal[1] = 1
    blur_kernel_px: int = Field(default=5, ge=1, le=31, strict=True)
    morph_kernel_px: int = Field(default=5, ge=1, le=31, strict=True)
    change_threshold: float = Field(default=28., gt=0, le=255)  # OpenCV 8-bit LAB distance
    min_change_area_px: int = Field(default=150, ge=1, strict=True)
    edge_margin_px: int = Field(default=4, ge=0, le=50, strict=True)
    min_clear_width_fraction: float = Field(default=.3, gt=0, le=1)  # lane check (later step)
    check_max_side_px: int = Field(default=480, ge=64, strict=True)
    min_background_fraction: float = Field(default=.1, gt=0, lt=1)
    max_camera_shift_px: float = Field(default=4., gt=0)
    max_brightness_change: float = Field(default=20., gt=0, le=255)
    max_background_change_fraction: float = Field(default=.2, gt=0, lt=1)

    @model_validator(mode="after")
    def odd_kernels(self):
        if self.blur_kernel_px % 2 == 0 or self.morph_kernel_px % 2 == 0:
            raise ValueError("kernel sizes must be odd")
        return self


class WalkwayDefinition(BaseModel):
    """Operator quadrilateral bound to the exact declared-empty reference file.

    Edge i runs from polygon[i] to polygon[(i + 1) % 4]. Entry and exit are opposite edges.
    The declarations are operator setup, not facts inferred from the pixels.
    """
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    walkway_version: Literal[1] = 1
    walkway_id: str = Field(min_length=1, max_length=80)
    reference_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    width: int = Field(gt=0, strict=True)
    height: int = Field(gt=0, strict=True)
    polygon: tuple[tuple[float, float], tuple[float, float], tuple[float, float], tuple[float, float]]
    entry_edge: int = Field(ge=0, le=3, strict=True)
    exit_edge: int = Field(ge=0, le=3, strict=True)
    reference_declared_empty: Literal[True]
    camera_declared_fixed: Literal[True]
    walkway_declared_floor_rectangle: Literal[True]

    @model_validator(mode="after")
    def valid_geometry(self):
        p = np.array(self.polygon, np.float32)
        if np.any(p < 0) or np.any(p > 1):
            raise ValueError("polygon coordinates must be normalized to [0, 1]")
        if not cv2.isContourConvex(p) or abs(cv2.contourArea(p)) < 1e-5:
            raise ValueError("polygon must be nondegenerate, convex and ordered around its boundary")
        if self.exit_edge != (self.entry_edge + 2) % 4:
            raise ValueError("entry and exit must be opposite edges of the walkway")
        return self

    def polygon_px(self) -> np.ndarray:
        return np.array([(x * self.width, y * self.height) for x, y in self.polygon], np.float32)

    def mask(self, margin_px: int = 0) -> np.ndarray:
        """Walkway pixels (255); a positive margin shrinks it away from the drawn edges."""
        mask = np.zeros((self.height, self.width), np.uint8)
        cv2.fillConvexPoly(mask, np.round(self.polygon_px()).astype(np.int32), 255)
        return cv2.erode(mask, _disk(margin_px)) if margin_px else mask


def load_reference(definition: WalkwayDefinition, path: Path) -> np.ndarray:
    """Decode the pinned reference; any other file — even a similar picture — is rejected."""
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != definition.reference_sha256:
        raise ValueError("reference image does not match the walkway definition")
    image = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR | cv2.IMREAD_IGNORE_ORIENTATION)
    if image is None or image.shape[:2] != (definition.height, definition.width):
        raise ValueError("reference image cannot be decoded at the defined size")
    return image


@dataclass(frozen=True)
class ReferenceCheck:
    status: str  # "valid" | "unverified"
    reason: str
    camera_shift_px: float | None = None
    brightness_change: float | None = None
    background_change_fraction: float | None = None


@dataclass(frozen=True)
class ChangeObservation:
    """`changed` is None whenever the reference check fails: no occupancy evidence at all."""
    check: ReferenceCheck
    interior: np.ndarray            # assessed walkway pixels (255), edge margin removed
    changed: np.ndarray | None      # changed walkway pixels (255), zero outside `interior`
    changed_fraction: float | None


def detect_changes(reference: np.ndarray, image: np.ndarray, definition: WalkwayDefinition,
                   config: WalkwayConfig) -> ChangeObservation:
    """Reference validity first; only then a cleaned change mask inside the walkway.

    The image is never warped or relit to fit the reference: a moved camera or changed lighting
    makes the frame unverified rather than producing compensated evidence.
    """
    for name, im in (("reference", reference), ("image", image)):
        if im.ndim != 3 or im.shape[2] != 3 or im.dtype != np.uint8:
            raise ValueError(f"expected upright uint8 BGR {name}")
    interior = definition.mask(config.edge_margin_px)
    size = (definition.height, definition.width)
    if reference.shape[:2] != size or image.shape[:2] != size:
        return ChangeObservation(ReferenceCheck("unverified", "image_size_mismatch"), interior, None, None)
    check = _check_reference(reference, image, definition, config)
    if check.status != "valid":
        return ChangeObservation(check, interior, None, None)
    if not interior.any():
        return ChangeObservation(ReferenceCheck("unverified", "walkway_too_small"), interior, None, None)
    distance = _lab_distance(reference, image, config.blur_kernel_px)
    changed = np.where((distance > config.change_threshold) & (interior > 0), 255, 0).astype(np.uint8)
    kernel = _disk(config.morph_kernel_px // 2)
    changed = cv2.morphologyEx(cv2.morphologyEx(changed, cv2.MORPH_OPEN, kernel), cv2.MORPH_CLOSE, kernel)
    changed &= interior
    n, labels, stats, _ = cv2.connectedComponentsWithStats(changed, connectivity=8)
    keep = stats[:, cv2.CC_STAT_AREA] >= config.min_change_area_px
    keep[0] = False  # background label
    changed = np.where(keep[labels], 255, 0).astype(np.uint8)
    fraction = float(np.count_nonzero(changed)) / float(np.count_nonzero(interior))
    return ChangeObservation(check, interior, changed, fraction)


def _check_reference(reference: np.ndarray, image: np.ndarray, definition: WalkwayDefinition,
                     config: WalkwayConfig) -> ReferenceCheck:
    """Camera movement, lighting and background change, measured outside the walkway only."""
    background = cv2.bitwise_not(cv2.dilate(definition.mask(), _disk(config.edge_margin_px)))
    if np.count_nonzero(background) < config.min_background_fraction * background.size:
        return ReferenceCheck("unverified", "insufficient_background_for_camera_check")
    scale = min(1., config.check_max_side_px / max(definition.width, definition.height))
    gray = [cv2.cvtColor(im, cv2.COLOR_BGR2GRAY) for im in (reference, image)]
    small_bg = background
    if scale < 1:
        gray = [cv2.resize(g, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) for g in gray]
        small_bg = cv2.resize(background, gray[0].shape[::-1], interpolation=cv2.INTER_NEAREST)
    try:
        _, warp = cv2.findTransformECC(gray[0], gray[1], np.eye(2, 3, dtype=np.float32),
                                       cv2.MOTION_TRANSLATION,
                                       (cv2.TERM_CRITERIA_COUNT | cv2.TERM_CRITERIA_EPS, 100, 1e-5),
                                       small_bg, 5)
    except cv2.error:
        return ReferenceCheck("unverified", "camera_check_failed")  # e.g. textureless background
    shift = math.hypot(float(warp[0, 2]), float(warp[1, 2])) / scale
    if not math.isfinite(shift):
        return ReferenceCheck("unverified", "camera_check_failed")
    if shift > config.max_camera_shift_px:
        return ReferenceCheck("unverified", "camera_moved", shift)
    bg = background > 0
    lab = [cv2.cvtColor(im, cv2.COLOR_BGR2LAB) for im in (reference, image)]
    brightness = abs(float(lab[1][..., 0][bg].mean()) - float(lab[0][..., 0][bg].mean()))
    if brightness > config.max_brightness_change:
        return ReferenceCheck("unverified", "lighting_changed", shift, brightness)
    changed = float(np.mean(_lab_distance(reference, image, config.blur_kernel_px)[bg] > config.change_threshold))
    if changed > config.max_background_change_fraction:
        return ReferenceCheck("unverified", "background_changed", shift, brightness, changed)
    return ReferenceCheck("valid", "reference_consistent", shift, brightness, changed)


def _lab_distance(reference: np.ndarray, image: np.ndarray, blur_px: int) -> np.ndarray:
    a, b = (cv2.cvtColor(cv2.GaussianBlur(im, (blur_px, blur_px), 0), cv2.COLOR_BGR2LAB).astype(np.float32)
            for im in (reference, image))
    return np.linalg.norm(b - a, axis=2)


def _disk(radius: int) -> np.ndarray:
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * radius + 1, 2 * radius + 1))
