"""Shared envelope: workspace name, clock domains, and the paged record item."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from bobapp.contracts import Delivery, Record

WorkspaceName = Literal["rover", "sample"]

CLOCK_DOMAINS = {
    "record.rover.wall_ns, record.rover.mono_ns": "rover computer clock; wall time may be unsynced (rover.clock_synced)",
    "hub_rx_wall_ns, link.*_wall_ns, live_received_wall_ns": "laptop (hub) wall clock",
    "*iphone*_ts_ns": "iPhone clock since boot; comparable only within one ARKit session",
    "live.freshness.*.age_ms": "measured on the rover when that live state was sent",
    "live_received_age_ms": "laptop clock: how long ago the hub received the live state",
    "telemetry rates, window_s, age_ms": "rates measured on the rover monotonic clock; age combines rover measurement age and hub receive age",
}


class Item(BaseModel):
    cursor: int                     # pass as `after` for the next page
    delivery: Delivery              # backfilled records are history, never current conditions
    hub_rx_wall_ns: int
    record: Record


class Page(BaseModel):
    workspace: WorkspaceName
    items: list[Item]
    next_after: int
    clock_domains: dict[str, str] = CLOCK_DOMAINS
