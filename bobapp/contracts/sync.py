"""Sync link (C9) messages between the rover edge API and the laptop hub, and blob status."""
from __future__ import annotations

from enum import Enum
from typing import Literal, Optional
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from .common import AppVersion, Lane, NonNegInt, PosInt, RoverClock, Sha256, SourceMode, _Model
from .live import LiveState
from .record import Record

class LaneInfo(_Model):
    oldest_seq: Optional[PosInt] = None   # null: lane empty
    head_seq: NonNegInt                   # 0: nothing written yet in this epoch


def _all_lanes(v: dict) -> dict:
    if set(v) != set(Lane):
        raise ValueError("must list every lane exactly once")
    return v


class SyncHello(_Model):
    app_version: AppVersion
    msg_type: Literal["sync_hello"]
    hub_id: str = Field(min_length=1)
    store_epoch: Optional[UUID] = None     # null: first contact
    cursors: dict[Lane, NonNegInt]         # last committed seq per lane (0 = none)

    _lanes = field_validator("cursors")(_all_lanes)


class SyncWelcome(_Model):
    app_version: AppVersion
    msg_type: Literal["sync_welcome"]
    edge_id: str = Field(min_length=1)
    store_epoch: UUID
    lanes: dict[Lane, LaneInfo]
    rover: RoverClock
    run_id: Optional[str] = None
    source_mode: Optional[SourceMode] = None

    _lanes = field_validator("lanes")(_all_lanes)


class SyncBatch(_Model):
    app_version: AppVersion
    msg_type: Literal["sync_batch"]
    lane: Lane
    backfill: bool                         # sent while catching up (records older than the tail)
    records: list[Record] = Field(min_length=1)

    @model_validator(mode="after")
    def _ordered(self) -> SyncBatch:
        seqs = [r.seq for r in self.records]
        if any(r.lane != self.lane for r in self.records) or seqs != sorted(set(seqs)):
            raise ValueError("batch records must be this lane's, in strictly increasing seq")
        return self


class SyncAck(_Model):
    app_version: AppVersion
    msg_type: Literal["sync_ack"]
    store_epoch: UUID
    lane: Lane
    seq: NonNegInt                         # highest contiguous seq committed by the hub


class SyncLive(_Model):
    app_version: AppVersion
    msg_type: Literal["sync_live"]
    live: LiveState


class SyncError(_Model):
    app_version: AppVersion
    msg_type: Literal["sync_error"]
    code: str = Field(min_length=1)
    message: str


class BlobStatusValue(str, Enum):
    AVAILABLE = "available"
    PENDING_SYNC = "pending_sync"
    MISSING = "missing"
    HASH_MISMATCH = "hash_mismatch"


class BlobStatus(_Model):
    app_version: AppVersion
    msg_type: Literal["blob_status"]
    sha256: Sha256
    status: BlobStatusValue
