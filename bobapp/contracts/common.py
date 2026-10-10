"""Shared base model, strict types, identities and enums of `bob-app` v1."""
from __future__ import annotations

import re
from enum import Enum
from typing import Annotated, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, Strict

APP_VERSION = 1
AppVersion = Literal[1]

NonNegInt = Annotated[int, Strict(), Field(ge=0)]
PosInt = Annotated[int, Strict(), Field(gt=0)]
Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class SourceMode(str, Enum):
    """Declared by the operator at server start: the server cannot tell a replay client from a phone."""
    LIVE = "LIVE"
    REPLAY = "REPLAY"
    SAMPLE = "SAMPLE"


class Lane(str, Enum):
    CONTROL = "control"          # inspections, profiles, incidents, evidence metadata, gaps, notices
    TRACK = "track"              # downsampled valid phone-camera poses
    OBSERVATION = "observation"  # one per processed frame; first pruned under disk pressure


LANE_PRIORITY = (Lane.CONTROL, Lane.TRACK, Lane.OBSERVATION)


class Delivery(str, Enum):
    """Set by the hub on receipt. Backfilled records never update current status."""
    REALTIME = "realtime"
    BACKFILLED = "backfilled"


# Worksite requirement checkbox -> PPE rule name in configs/default.yaml ppe.rules.
REQUIREMENT_RULES: dict[str, str] = {
    "eyewear": "glasses", "helmet": "helmet", "gloves": "gloves", "vest": "vest", "boots": "boots",
}
Requirement = Literal["eyewear", "helmet", "gloves", "vest", "boots"]


class RoverClock(_Model):
    """Rover times of one record. Never subtract them from laptop or iPhone times."""
    wall_ns: NonNegInt
    mono_ns: NonNegInt
    clock_synced: Optional[bool]   # null = unknown (an offline Jetson's wall clock may be wrong)


def is_sha256(value: str) -> bool:
    return bool(_SHA256.match(value))
