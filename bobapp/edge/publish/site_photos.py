"""Bounded, model-free selection of general site views on the edge writer thread.

Uses only source-frame pixels and pose. This measures view diversity, never hazards,
clearance or complete coverage. Only committed photos advance selection memory.
"""
from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass
import math
from typing import Optional

import cv2
import numpy as np

from vision.schema import DetectionEvent, Pose


@dataclass(frozen=True)
class SitePhotoSettings:
    enabled: bool = True
    min_interval_s: float = 3.0
    min_move_m: float = 0.75
    min_turn_deg: float = 25.0
    max_interval_s: float = 30.0
    similarity_threshold: float = 0.06
    min_sharpness: float = 35.0
    min_brightness: float = 20.0
    max_brightness: float = 235.0
    history_size: int = 128

    def __post_init__(self):
        if type(self.enabled) is not bool:
            raise ValueError("site_photos.enabled must be a boolean")
        if type(self.history_size) is not int or not 1 <= self.history_size <= 1024:
            raise ValueError("site_photos.history_size must be an integer in 1..1024")
        for name in ("min_interval_s", "min_move_m", "min_turn_deg", "max_interval_s",
                     "similarity_threshold", "min_sharpness", "min_brightness", "max_brightness"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ValueError(f"site_photos.{name} must be finite and nonnegative")
        if not 0 < self.min_interval_s <= self.max_interval_s:
            raise ValueError("site_photos intervals must satisfy 0 < min <= max")
        if not 0 < self.min_move_m or not 0 < self.min_turn_deg <= 180:
            raise ValueError("site_photos movement/turn thresholds must be positive (turn <= 180)")
        if not 0 < self.similarity_threshold <= 1:
            raise ValueError("site_photos.similarity_threshold must be in (0, 1]")
        if not 0 <= self.min_brightness < self.max_brightness <= 255:
            raise ValueError("site_photos brightness range must be within 0..255")


@dataclass
class Candidate:
    event: DetectionEvent
    thumbnail: np.ndarray
    details: dict


def nearby(a: Pose, b: Pose, settings: SitePhotoSettings) -> bool:
    distance = math.sqrt((a.x_m-b.x_m)**2 + (a.y_m-b.y_m)**2 + (a.z_m-b.z_m)**2)
    turn = abs(math.atan2(math.sin(a.yaw_rad-b.yaw_rad), math.cos(a.yaw_rad-b.yaw_rad)))
    return distance < settings.min_move_m and math.degrees(turn) < settings.min_turn_deg


class SitePhotoSelector:
    def __init__(self, settings: SitePhotoSettings):
        self.settings = settings
        self.session = None
        self.last_seen_ns = -1
        self.last_check_ns = None
        self.history: deque[Candidate] = deque(maxlen=settings.history_size)
        self.counts: Counter = Counter()

    def offer(self, event: DetectionEvent, image: np.ndarray) -> Optional[Candidate]:
        s = self.settings
        if not s.enabled:
            return None
        if event.session_id != self.session:
            self.session = event.session_id
            self.history.clear()
            self.last_seen_ns = -1
            self.last_check_ns = None
        ts = event.iphone_frame_ts_ns
        if ts <= self.last_seen_ns:
            self.counts['out_of_order'] += 1
            return None
        self.last_seen_ns = ts
        if self.last_check_ns is not None and ts - self.last_check_ns < s.min_interval_s * 1e9:
            return None
        self.last_check_ns = ts
        self.counts['considered'] += 1
        # Fixed analysis resolution makes the heuristic repeatable across phone sizes.
        height, width = image.shape[:2]
        small = cv2.resize(image, (320, max(1, round(height * 320 / width))), interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        brightness = float(gray.mean())
        sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        if not s.min_brightness <= brightness <= s.max_brightness or sharpness < s.min_sharpness:
            self.counts['quality_rejected'] += 1
            return None
        thumb = cv2.resize(small, (32, 24), interpolation=cv2.INTER_AREA).astype(np.float32) / 255
        pose = event.pose if event.pose_valid else None
        last = self.history[-1] if self.history else None
        last_pose = last.event.pose if last and last.event.pose_valid else None
        moved = bool(pose is not None and last_pose is not None and not nearby(pose, last_pose, s))
        elapsed = (ts - last.event.iphone_frame_ts_ns) / 1e9 if last else None
        if last and not moved and elapsed < s.max_interval_s:
            self.counts['interval_rejected'] += 1
            return None
        # Compare nearby views; unknown poses use visual-only matching. Distant but
        # similar rooms are retained. A timeout never forces saving a duplicate.
        comparisons = [old for old in self.history if pose is None or not old.event.pose_valid
                       or nearby(pose, old.event.pose, s)]
        difference = min((float(np.abs(thumb - old.thumbnail).mean()) for old in comparisons), default=None)
        if difference is not None and difference < s.similarity_threshold:
            self.counts['duplicate_rejected'] += 1
            return None
        reason = 'first_view' if last is None else 'new_viewpoint' if moved else 'changed_view'
        return Candidate(event, thumb, {
            'selection_version': 1, 'source_event_id': str(event.event_id),
            'session_id': str(event.session_id), 'seq_id': event.seq_id,
            'reason': reason, 'pose_valid': event.pose_valid,
            'brightness': brightness, 'sharpness': sharpness,
            'nearest_visual_difference': difference,
        })

    def commit(self, candidate: Candidate) -> None:
        self.history.append(candidate)
        self.counts['selected'] += 1
