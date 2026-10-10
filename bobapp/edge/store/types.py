"""Store error, raw record and rover clock."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

from bobapp.contracts import Lane, RoverClock


class StoreError(RuntimeError):
    pass


@dataclass(frozen=True)
class RawRecord:
    """A stored record as JSON text: sync forwards it without re-encoding."""
    lane: Lane
    seq: int
    kind: str
    json: str


def rover_clock(clock_synced: Optional[bool] = None) -> RoverClock:
    return RoverClock(wall_ns=time.time_ns(), mono_ns=time.monotonic_ns(), clock_synced=clock_synced)
