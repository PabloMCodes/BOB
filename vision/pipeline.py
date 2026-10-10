"""Frame -> boxes (model + derived PPE violations). Single entry point for webcam, eval, server.

Modes (config `pipeline.mode`):
  single     one pass over the whole frame.
  head_crop  pass 1 finds people (and heads) on the whole frame; pass 2 re-runs the model on a
             square crop around each person's head, taken from the full-resolution frame, so small
             objects (glasses at 3 m+) get ~3x more pixels. When a footwear rule is active, each
             person's feet get a crop too (shoes are ~0.1 % of the frame at 3 m but 5-44 % of
             the close-up footwear training images). Pass-1 and pass-2 boxes of the crop
             classes are MERGED and deduplicated — a good pass-1 detection is never thrown away
             (clear safety glasses on close-ish faces are often found only by pass 1).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import numpy as np

from vision.detector import Detector
from vision.ppe import SubjectVerdict, apply_rules, rules_from_config, split_active
from vision.render import normalize_class_name
from vision.schema import Box, ImageSize

MODES = ("single", "head_crop")
Region = tuple[int, int, int, int]


@dataclass(frozen=True)
class FrameResult:
    boxes: list[Box]                 # model boxes + derived violation boxes
    verdicts: list[SubjectVerdict]
    image_size: ImageSize
    inference_ms: float              # sum over all model passes
    passes: int
    crop_regions: list[Region]


def head_region(
    person: tuple[float, float, float, float],
    width: int,
    height: int,
    head_fraction: float,
    head: Optional[tuple[float, float, float, float]] = None,
    head_scale: float = 2.0,
) -> Region:
    """Square crop around a person's head, shifted to stay inside the image.

    With a pass-1 `head` box: centred on it, side = head_scale x its longest edge (scales with
    distance, never cuts a close-up face in half). Without one: anchored at the top of the person
    box, side = head_fraction x person height.
    """
    if head is not None:
        hx1, hy1, hx2, hy2 = head
        side = head_scale * max(hx2 - hx1, hy2 - hy1)
        cx, cy = (hx1 + hx2) / 2, (hy1 + hy2) / 2
    else:
        x1, y1, x2, y2 = person
        side = max(head_fraction * (y2 - y1), 0.5 * (x2 - x1))
        cx, cy = (x1 + x2) / 2, y1 - 0.1 * side + side / 2  # headroom for a helmet
    side = int(round(min(side, width, height)))
    left = min(max(int(round(cx - side / 2)), 0), width - side)
    top = min(max(int(round(cy - side / 2)), 0), height - side)
    return left, top, left + side, top + side


def feet_region(
    person: tuple[float, float, float, float], width: int, height: int, fraction: float
) -> Region:
    """Square crop around the bottom of a person box (their feet), shifted inside the image.

    Side = max(person width, fraction x person height). Shoes then fill a few % of the crop,
    close to the close-up footwear training data, instead of ~0.1 % of the full frame.
    """
    x1, y1, x2, y2 = person
    side = max(x2 - x1, fraction * (y2 - y1))
    cx, cy = (x1 + x2) / 2, y2 + 0.1 * side - side / 2  # small margin below the soles
    side = int(round(min(side, width, height)))
    left = min(max(int(round(cx - side / 2)), 0), width - side)
    top = min(max(int(round(cy - side / 2)), 0), height - side)
    return left, top, left + side, top + side


def _area(b: tuple[float, ...]) -> float:
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def _intersection(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    return _area((max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])))


def _iou(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    inter = _intersection(a, b)
    union = _area(a) + _area(b) - inter
    return inter / union if union > 0 else 0.0


def nms_per_class(boxes: list[Box], iou: float, containment: float = 0.8) -> list[Box]:
    """Dedupe same-class boxes found by both passes / overlapping crops.

    A box is a duplicate of a higher-confidence kept box if IoU > `iou`, or if most of the smaller
    box lies inside the other (> `containment`) — e.g. a partial face inside a full face.
    """
    kept: list[Box] = []
    for box in sorted(boxes, key=lambda b: b.conf, reverse=True):
        def duplicate(k: Box) -> bool:
            if k.cls_name != box.cls_name:
                return False
            inter = _intersection(k.xyxy, box.xyxy)
            smaller = min(_area(k.xyxy), _area(box.xyxy))
            return _iou(k.xyxy, box.xyxy) > iou or (smaller > 0 and inter / smaller > containment)
        if not any(duplicate(k) for k in kept):
            kept.append(box)
    return kept


def _inside(box: Box, region: tuple[float, float, float, float]) -> bool:
    """True if the centre of `box` lies within `region`."""
    cx, cy = (box.xyxy[0] + box.xyxy[2]) / 2, (box.xyxy[1] + box.xyxy[3]) / 2
    return region[0] <= cx <= region[2] and region[1] <= cy <= region[3]


class Pipeline:
    def __init__(
        self,
        detector: Detector,
        config: dict[str, Any],
        mode: Optional[str] = None,
        imgsz: Optional[int] = None,
        footwear: Optional[Detector] = None,
    ) -> None:
        self.detector = detector
        self.mode = mode or config["pipeline"]["mode"]
        if self.mode not in MODES:
            raise ValueError(f"pipeline.mode must be one of {MODES}, got {self.mode!r}")
        self.imgsz = imgsz or config["model"]["imgsz"]
        self.crop = config["pipeline"]["crop"]
        self.crop_classes = {normalize_class_name(c) for c in self.crop["classes"]}
        self.feet = config["pipeline"]["feet_crop"]
        self.feet_classes = {normalize_class_name(c) for c in self.feet["classes"]}
        footwear = footwear if footwear is not None else self.footwear_from_config(config)
        self.footwear = footwear
        self.names = dict(detector.names)
        self.model_id = detector.model_id
        self.footwear_offset = max(self.names, default=-1) + 1
        if footwear is not None:
            if self.feet_classes != {"shoes", "safety-boots"}:
                raise ValueError("specialist feet_crop.classes must include exactly shoes and safety-boots")
            if set(footwear.names.values()) != {"shoes", "safety-boots"}:
                raise ValueError("footwear model must have exactly shoes and safety-boots classes")
            # An ensemble has its own class-index map. SH17's generic footwear must never
            # become evidence of missing safety boots.
            self.names = {i: n for i, n in self.names.items() if normalize_class_name(n) not in self.feet_classes}
            self.names.update({self.footwear_offset + i: n for i, n in footwear.names.items()})
            self.model_id += "+" + footwear.model_id
            self.crop_classes -= self.feet_classes
        # Rules needing classes this model lacks (e.g. safety-boots with SH17) are switched off —
        # never approximated with a look-alike class.
        self.rules, self.inactive_rules = split_active(rules_from_config(config), self.names.values())
        for rule in self.inactive_rules:
            missing = sorted(rule.requires - {normalize_class_name(c) for c in self.names.values()})
            print(f"[pipeline] rule {rule.name!r} inactive: model {self.model_id} has no class {missing}")
        # Feet crops only pay off when an active rule judges footwear (never with SH17 alone).
        needed = set().union(*(r.requires for r in self.rules)) if self.rules else set()
        self.feet_enabled = (self.mode == "head_crop" or footwear is not None) and bool(self.feet_classes & needed)
        detector.warmup(self.imgsz)
        if self.mode == "head_crop":
            detector.warmup(self.crop["imgsz"])
        if self.feet_enabled:
            (footwear or detector).warmup(self.feet["imgsz"])

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> Pipeline:
        footwear = cls.footwear_from_config(config)
        return cls(Detector.from_config(config), config, footwear=footwear)

    @staticmethod
    def footwear_from_config(config: dict[str, Any]) -> Optional[Detector]:
        """Also used by direct Pipeline construction (e.g. the PPE comparison evaluator)."""
        settings = config.get("footwear_model", {})
        footwear = None
        if settings.get("enabled", False):
            if not settings.get("weights_sha256"):
                raise ValueError("footwear_model.weights_sha256 is required")
            footwear = Detector(settings["weights"], config["device"],
                                config["pipeline"]["feet_crop"]["imgsz"],
                                config["pipeline"]["feet_crop"]["conf"],
                                weights_sha256=settings["weights_sha256"])
        return footwear

    def __call__(self, image_bgr: np.ndarray) -> FrameResult:
        first = self.detector(image_bgr, imgsz=self.imgsz)
        boxes, total_ms, passes, regions = first.boxes, first.inference_ms, 1, []
        if self.footwear is not None:
            boxes = [b for b in boxes if normalize_class_name(b.cls_name) not in self.feet_classes]

        if self.mode == "head_crop" or self.footwear is not None:
            boxes, crop_ms, regions = self._head_crops(image_bgr, boxes)
            total_ms += crop_ms
            passes += len(regions)

        derived, verdicts = apply_rules(self.rules, boxes)
        return FrameResult(boxes + derived, verdicts, first.image_size, total_ms, passes, regions)

    def _crop_pass(
        self, image: np.ndarray, regions: list[Region], classes: set[str], imgsz: int, conf: float,
        detector: Optional[Detector] = None,
    ) -> tuple[list[Box], float]:
        """Run the model on each region; return boxes of `classes` in full-frame coordinates."""
        boxes, elapsed = [], 0.0
        for x0, y0, x1, y1 in regions:
            result = (detector or self.detector)(image[y0:y1, x0:x1], imgsz=imgsz, conf=conf)
            elapsed += result.inference_ms
            for b in result.boxes:
                if normalize_class_name(b.cls_name) in classes:
                    bx1, by1, bx2, by2 = b.xyxy
                    # Rebuild (not model_copy) so the shifted box is re-validated by the schema.
                    cls_id = b.cls_id + self.footwear_offset if detector is not None else b.cls_id
                    boxes.append(Box(**{**b.model_dump(), "cls_id": cls_id,
                                        "xyxy": (bx1 + x0, by1 + y0, bx2 + x0, by2 + y0)}))
        return boxes, elapsed

    def _head_crops(self, image: np.ndarray, first: list[Box]) -> tuple[list[Box], float, list[Region]]:
        height, width = image.shape[:2]
        people = sorted(
            (b for b in first if normalize_class_name(b.cls_name) == "person" and b.conf >= self.crop["min_person_conf"]),
            key=lambda b: b.conf,
            reverse=True,
        )[: self.crop["max_crops"]]
        heads = sorted(
            (b for b in first if normalize_class_name(b.cls_name) == "head"), key=lambda b: b.conf, reverse=True
        )

        head_regions = []
        for person in people if self.mode == "head_crop" else []:
            head = next((h for h in heads if _inside(h, person.xyxy)), None)
            head_regions.append(head_region(
                person.xyxy, width, height, self.crop["head_fraction"],
                head.xyxy if head else None, self.crop["head_scale"],
            ))
        crop_boxes, elapsed = self._crop_pass(
            image, head_regions, self.crop_classes, self.crop["imgsz"], self.crop["conf"]
        )
        merge_classes, regions = set(self.crop_classes), list(head_regions)

        if self.feet_enabled:
            feet_regions = [feet_region(p.xyxy, width, height, self.feet["fraction"]) for p in people]
            feet_boxes, feet_ms = self._crop_pass(
                image, feet_regions, self.feet_classes, self.feet["imgsz"], self.feet["conf"],
                detector=self.footwear,
            )
            crop_boxes, elapsed = crop_boxes + feet_boxes, elapsed + feet_ms
            merge_classes |= self.feet_classes
            regions += feet_regions

        # Merge, don't replace: pass 1 sometimes finds what pass 2 misses (and vice versa).
        is_crop_class = lambda b: normalize_class_name(b.cls_name) in merge_classes  # noqa: E731
        others = [b for b in first if not is_crop_class(b)]
        candidates = [b for b in first if is_crop_class(b)] + crop_boxes
        return others + nms_per_class(candidates, self.crop["nms_iou"]), elapsed, regions
