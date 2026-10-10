"""Image-space restricted-zone observations. No world position or movement authority.

This is an independent scene contract (version 1), not an extension of frozen C2.
Foot/footwear boxes provide approximate visible ground-contact evidence, never certification.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

import cv2
import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

from vision.render import normalize_class_name
from vision.schema import Box, ImageSize


class ImageZone(BaseModel):
    """An operator-defined convex polygon, valid only for the exact upright image."""
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    scene_version: Literal[1] = 1
    zone_id: str = Field(min_length=1, max_length=80)
    image_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    width: int = Field(gt=0, strict=True)
    height: int = Field(gt=0, strict=True)
    polygon: tuple[tuple[float, float], ...] = Field(min_length=3, max_length=16)

    @model_validator(mode="after")
    def valid_polygon(self):
        p = np.array(self.polygon, np.float32)
        if np.any(p < 0) or np.any(p > 1):
            raise ValueError("polygon coordinates must be normalized to [0, 1]")
        if not cv2.isContourConvex(p) or abs(cv2.contourArea(p)) < 1e-5:
            raise ValueError("polygon must be nondegenerate, convex and ordered around its boundary")
        return self

    def region(self, image_sha256: str, size: ImageSize) -> ZoneRegion:
        if (image_sha256, size.width, size.height) != (self.image_sha256, self.width, self.height):
            return ZoneRegion(self.zone_id, "unverified", "reference_image_mismatch", ())
        return ZoneRegion(self.zone_id, "recognized", "operator_defined_image_region",
                          tuple((x * self.width, y * self.height) for x, y in self.polygon))


@dataclass(frozen=True)
class ZoneRegion:
    zone_id: str
    status: str
    reason: str
    polygon: tuple[tuple[float, float], ...]


@dataclass(frozen=True)
class PersonFinding:
    person_box_index: int
    status: str
    reason: str
    evidence_box_indices: tuple[int, ...] = ()
    contact_points: tuple[tuple[float, float], ...] = ()


@dataclass(frozen=True)
class ZoneAssessment:
    region: ZoneRegion
    people: tuple[PersonFinding, ...]
    scene_version: int = 1

    def as_dict(self) -> dict:
        return asdict(self)


def assess_zone(region: ZoneRegion, boxes: list[Box], size: ImageSize,
                min_conf: float = .5, boundary_margin_px: float = 6.) -> ZoneAssessment:
    """Report possible presence from visible feet; bbox overlap alone never establishes entry.

    `observed_feet_outside` describes evidence only, never that a person/site is clear.
    No person detection produces an empty people list, not an all-clear result.
    """
    people = [(i, b) for i, b in enumerate(boxes)
              if b.source == "model" and normalize_class_name(b.cls_name) == "person"]
    supports: dict[int, list[tuple[int, Box]]] = {i: [] for i, _ in people}
    for j, foot in enumerate(boxes):
        if foot.source != "model" or normalize_class_name(foot.cls_name) not in {"foot", "shoes", "safety-boots"}:
            continue
        x1, y1, x2, y2 = foot.xyxy
        if foot.conf < min_conf or min(x2 - x1, y2 - y1) < 12:
            continue
        if x1 <= 1 or x2 >= size.width - 1 or y2 >= size.height - 1:
            continue  # cropped evidence cannot establish ground contact
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
        owners = [i for i, p in people if p.xyxy[0] <= cx <= p.xyxy[2]
                  and p.xyxy[1] + .65 * (p.xyxy[3] - p.xyxy[1]) <= cy <= p.xyxy[3]]
        if len(owners) == 1:
            supports[owners[0]].append((j, foot))
    findings = []
    for i, person in people:
        reason = None
        if region.status != "recognized":
            reason = region.reason
        elif person.conf < min_conf or min(person.xyxy[2] - person.xyxy[0], person.xyxy[3] - person.xyxy[1]) < 24:
            reason = "person_small_or_uncertain"
        elif not supports[i]:
            reason = "no_unambiguous_visible_foot_evidence"
        if reason:
            findings.append(PersonFinding(i, "unverified", reason))
            continue
        indices = tuple(j for j, _ in supports[i])
        points = tuple(((b.xyxy[0] + b.xyxy[2]) / 2, b.xyxy[3]) for _, b in supports[i])
        polygon = np.asarray(region.polygon, np.float32)
        distances = [cv2.pointPolygonTest(polygon, p, True) for p in points]
        if any(d > boundary_margin_px for d in distances):
            status, reason = "possible_person_in_zone", "visible_foot_contact_proxy_inside"
        elif any(abs(d) <= boundary_margin_px for d in distances):
            status, reason = "unverified", "foot_near_boundary"
        else:
            status, reason = "observed_feet_outside", "visible_evidence_only_not_person_clearance"
        findings.append(PersonFinding(i, status, reason, indices, points))
    return ZoneAssessment(region, tuple(findings))


def draw_zone(image: np.ndarray, assessment: ZoneAssessment) -> np.ndarray:
    out = image.copy()
    region = assessment.region
    if region.polygon:
        cv2.polylines(out, [np.asarray(region.polygon, np.int32)], True, (0, 210, 255), 2)
    lines = [f"ZONE {region.zone_id}: {region.status} ({region.reason})"]
    for finding in assessment.people:
        color = (0, 0, 255) if finding.status == "possible_person_in_zone" else (0, 210, 255)
        for x, y in finding.contact_points:
            cv2.circle(out, (round(x), round(y)), 5, color, -1)
        lines.append(f"person[{finding.person_box_index}]: {finding.status}")
    if not assessment.people:
        lines.append("No person assessed - not an all-clear result")
    for n, line in enumerate(lines[:10]):
        y = 23 + n * 22
        cv2.putText(out, line, (8, y), cv2.FONT_HERSHEY_SIMPLEX, .48, (0, 0, 0), 3)
        cv2.putText(out, line, (8, y), cv2.FONT_HERSHEY_SIMPLEX, .48, (255, 255, 255), 1)
    return out
