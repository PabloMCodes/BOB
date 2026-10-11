"""Policy parameters (configs/incidents.yaml) and their hash, recorded with every incident."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

import yaml

from vision.config import REPO_ROOT

INCIDENTS_CONFIG = REPO_ROOT / "configs" / "incidents.yaml"


@dataclass(frozen=True)
class PolicyParams:
    policy_version: int
    calibrated: bool
    window_s: float
    confirm_min_frames: int
    confirm_min_fraction: float
    clear_window_s: float
    clear_min_frames: int
    clear_min_fraction: float
    lost_after_s: float
    merge_gap_s: float
    min_processing_hz: float
    evidence_max: int
    evidence_periodic_s: float

    @property
    def sha256(self) -> str:
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True).encode()).hexdigest()

    @classmethod
    def load(cls, path: Optional[Path] = None) -> PolicyParams:
        raw = yaml.safe_load((path or INCIDENTS_CONFIG).read_text())
        evidence = raw.pop("evidence")
        params = cls(**raw, evidence_max=evidence["max_per_incident"], evidence_periodic_s=evidence["periodic_s"])
        if not 1 <= params.evidence_max <= 10:
            raise ValueError("evidence.max_per_incident must be 1..10 (bob-app v1 limit)")
        return params
