"""PPE compliance rules.

kind "pair":  pair subjects (face/head/hands) with PPE boxes (glasses/helmet/gloves) by geometry.
kind "class": the class itself decides (safety-boots = compliant, shoes = not), for models that
              separate them. Rules whose classes the model lacks are inactive (see split_active).

No public dataset labels "not wearing safety glasses", so absence is derived:
  a confident, large-enough face with no glasses box in its eye band -> a "no-safety-glasses"
  box (source="derived") drawn on that eye band.
Subjects too small or uncertain get UNVERIFIED and no box: "no violation seen" != "compliant".
These are per-frame observations; confirming a hazard over N frames belongs to the alerts branch.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Optional, Union

from vision.render import normalize_class_name
from vision.schema import Box

XYXY = tuple[float, float, float, float]


class Verdict(str, Enum):
    WEARING = "wearing"
    NOT_WEARING = "not_wearing"
    UNVERIFIED = "unverified"


@dataclass(frozen=True)
class Rule:
    """kind: pair — a subject (face/head/hands) must have a PPE box in a band of it."""

    name: str
    subject: str           # class whose box is judged, e.g. "face"
    ppe: str               # class that must be present, e.g. "glasses"
    violation: str         # derived class name when missing, e.g. "no-safety-glasses"
    region: tuple[float, float]  # band of subject height where PPE centre must lie
    min_subject_px: float
    min_subject_conf: float
    min_overlap: float     # fraction of PPE box area inside the subject box

    @property
    def requires(self) -> set[str]:
        return {self.subject, self.ppe}

    @classmethod
    def from_config(cls, name: str, cfg: dict[str, Any]) -> Rule:
        top, bottom = cfg["region"]
        if not (top < bottom and bottom > 0 and top < 1):
            # The violation box is the region clipped to the subject, so it must overlap it.
            raise ValueError(f"ppe rule {name!r}: region must satisfy top < bottom and overlap [0, 1]")
        return cls(
            name=name,
            subject=normalize_class_name(cfg["subject"]),
            ppe=normalize_class_name(cfg["ppe"]),
            violation=cfg["violation"],
            region=(float(top), float(bottom)),
            min_subject_px=float(cfg["min_subject_px"]),
            min_subject_conf=float(cfg["min_subject_conf"]),
            min_overlap=float(cfg["min_overlap"]),
        )


@dataclass(frozen=True)
class ClassRule:
    """kind: class — the detected class itself is the verdict (e.g. safety-boots vs shoes).

    Only meaningful with a model that separates the two classes; with SH17 'shoes' means any
    footwear, so the rule stays inactive until `requires` are all model classes.
    """

    name: str
    compliant: str         # e.g. "safety-boots"
    noncompliant: str      # e.g. "shoes" (any non-safety footwear in our labelling convention)
    violation: str         # e.g. "no-safety-boots"
    min_subject_px: float
    min_subject_conf: float

    @property
    def requires(self) -> set[str]:
        return {self.compliant, self.noncompliant}

    @classmethod
    def from_config(cls, name: str, cfg: dict[str, Any]) -> ClassRule:
        return cls(
            name=name,
            compliant=normalize_class_name(cfg["compliant"]),
            noncompliant=normalize_class_name(cfg["noncompliant"]),
            violation=cfg["violation"],
            min_subject_px=float(cfg["min_subject_px"]),
            min_subject_conf=float(cfg["min_subject_conf"]),
        )


AnyRule = Union[Rule, ClassRule]


@dataclass(frozen=True)
class SubjectVerdict:
    rule: str
    verdict: Verdict
    subject: Box
    ppe: Optional[Box]           # matched PPE box when WEARING
    violation: Optional[Box]     # derived box when NOT_WEARING


def rules_from_config(config: dict[str, Any]) -> list[AnyRule]:
    kinds = {"pair": Rule, "class": ClassRule}
    rules = []
    for name, cfg in config["ppe"]["rules"].items():
        kind = cfg.get("kind", "pair")
        if kind not in kinds:
            raise ValueError(f"ppe rule {name!r}: kind must be one of {list(kinds)}, got {kind!r}")
        rules.append(kinds[kind].from_config(name, {k: v for k, v in cfg.items() if k != "kind"}))
    return rules


def split_active(rules: Iterable[AnyRule], model_classes: Iterable[str]) -> tuple[list[AnyRule], list[AnyRule]]:
    """(active, inactive): a rule is active only if the model has every class it requires."""
    available = {normalize_class_name(c) for c in model_classes}
    active, inactive = [], []
    for rule in rules:
        (active if rule.requires <= available else inactive).append(rule)
    return active, inactive


def _area(b: XYXY) -> float:
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def _intersection(a: XYXY, b: XYXY) -> float:
    return _area((max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])))


def _region(subject: XYXY, band: tuple[float, float]) -> XYXY:
    x1, y1, x2, y2 = subject
    h = y2 - y1
    return (x1, y1 + band[0] * h, x2, y1 + band[1] * h)


def _matches(rule: Rule, subject: XYXY, ppe: XYXY) -> float:
    """Overlap score if `ppe` sits in the subject's region, else 0."""
    rx1, ry1, rx2, ry2 = _region(subject, rule.region)
    cx, cy = (ppe[0] + ppe[2]) / 2, (ppe[1] + ppe[3]) / 2
    if not (rx1 <= cx <= rx2 and ry1 <= cy <= ry2):
        return 0.0
    overlap = _intersection(ppe, subject) / max(_area(ppe), 1e-9)
    return overlap if overlap >= rule.min_overlap else 0.0


def _too_small_or_uncertain(rule: AnyRule, subject: Box) -> bool:
    height = subject.xyxy[3] - subject.xyxy[1]
    return height < rule.min_subject_px or subject.conf < rule.min_subject_conf


def _apply_class_rule(rule: ClassRule, boxes: list[Box]) -> list[SubjectVerdict]:
    targets = (rule.compliant, rule.noncompliant)
    subjects = sorted(
        (b for b in boxes if normalize_class_name(b.cls_name) in targets), key=lambda b: b.conf, reverse=True
    )
    verdicts = []
    for subject in subjects:
        if _too_small_or_uncertain(rule, subject):
            verdicts.append(SubjectVerdict(rule.name, Verdict.UNVERIFIED, subject, None, None))
        elif normalize_class_name(subject.cls_name) == rule.compliant:
            verdicts.append(SubjectVerdict(rule.name, Verdict.WEARING, subject, subject, None))
        else:
            violation = Box(
                source="derived", cls_id=None, cls_name=rule.violation, conf=subject.conf, xyxy=subject.xyxy
            )
            verdicts.append(SubjectVerdict(rule.name, Verdict.NOT_WEARING, subject, None, violation))
    return verdicts


def apply_rule(rule: AnyRule, boxes: Iterable[Box]) -> list[SubjectVerdict]:
    boxes = list(boxes)
    if isinstance(rule, ClassRule):
        return _apply_class_rule(rule, boxes)
    subjects = sorted(
        (b for b in boxes if normalize_class_name(b.cls_name) == rule.subject),
        key=lambda b: b.conf,
        reverse=True,
    )
    available = [b for b in boxes if normalize_class_name(b.cls_name) == rule.ppe]

    verdicts = []
    for subject in subjects:
        if _too_small_or_uncertain(rule, subject):
            verdicts.append(SubjectVerdict(rule.name, Verdict.UNVERIFIED, subject, None, None))
            continue

        scored = [(_matches(rule, subject.xyxy, p.xyxy), p) for p in available]
        score, best = max(scored, key=lambda s: s[0], default=(0.0, None))
        if best is not None and score > 0:
            available.remove(best)  # one PPE box can't make two people compliant
            verdicts.append(SubjectVerdict(rule.name, Verdict.WEARING, subject, best, None))
            continue

        x1, y1, x2, y2 = subject.xyxy
        _, ry1, _, ry2 = _region(subject.xyxy, rule.region)
        band = (x1, max(y1, ry1), x2, min(y2, ry2))
        violation = Box(
            source="derived", cls_id=None, cls_name=rule.violation, conf=subject.conf, xyxy=band
        )
        verdicts.append(SubjectVerdict(rule.name, Verdict.NOT_WEARING, subject, None, violation))
    return verdicts


def apply_rules(rules: Iterable[AnyRule], boxes: Iterable[Box]) -> tuple[list[Box], list[SubjectVerdict]]:
    """Return (derived violation boxes, all verdicts) across rules."""
    boxes = list(boxes)
    verdicts = [v for rule in rules for v in apply_rule(rule, boxes)]
    return [v.violation for v in verdicts if v.violation is not None], verdicts
