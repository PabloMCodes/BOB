"""`WS /v1/sync` (plan §5.4): hello -> welcome -> live first -> backfill by lane priority -> tail.

The hub pulls; the rover never needs its address. Cursors here are what was *sent*; the hub resumes
from what it *committed* (its hello), so delivery is at-least-once and the hub deduplicates on
`(edge_id, store_epoch, lane, seq)`. Records already in the store when the hub connected are sent
with `backfill: true` and throttled to `sync.max_bytes_per_s` (the phone may share the hotspot);
newer records follow as they are written. A hello from another store epoch starts from zero: the
replica must never merge two stores. Pruned ranges are visible to the hub from `welcome.lanes`
(`oldest_seq`) and from stored `gap` records. Nothing is queued per hub on the rover: each batch is
read from the store when the socket can take it.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Awaitable, Callable, Optional

from bobapp.contracts import (
    APP_VERSION,
    LANE_PRIORITY,
    Lane,
    SyncAck,
    SyncError,
    SyncHello,
    SyncLive,
    SyncWelcome,
)
from bobapp.edge.store import EdgeStore, StoreError, rover_clock

from .live import build_live_state

Receive = Callable[[], Awaitable[str]]
Send = Callable[[str], Awaitable[None]]


def batch_json(lane: Lane, backfill: bool, records: list[str]) -> str:
    """A `sync_batch` from stored record JSON without re-encoding (records were validated on write)."""
    return (f'{{"app_version":{APP_VERSION},"msg_type":"sync_batch","lane":"{lane.value}",'
            f'"backfill":{"true" if backfill else "false"},"records":[{",".join(records)}]}}')


class SyncSession:
    def __init__(self, store: Callable[[], EdgeStore], config: dict[str, Any], clock_synced: Optional[bool]) -> None:
        self.store = store                      # thread-local EdgeStore factory
        self.batch_records = config["sync"]["batch_records"]
        self.max_bytes_per_s = config["sync"]["max_bytes_per_s"]
        self.live_interval_s = config["sync"]["live_interval_s"]
        self.clock_synced = clock_synced
        self.sent_bytes = {"backfill": 0, "tail": 0}

    async def _call(self, fn: Callable[..., Any], *args: Any) -> Any:
        return await asyncio.to_thread(lambda: fn(self.store(), *args))

    async def run(self, receive: Receive, send: Send) -> None:
        try:
            hello = SyncHello.model_validate_json(await asyncio.wait_for(receive(), timeout=10))
        except Exception as exc:
            await send(SyncError(app_version=APP_VERSION, msg_type="sync_error", code="bad_hello",
                                 message=str(exc)[:500]).model_dump_json())
            return
        epoch = await self._call(lambda s: s.store_epoch)
        same_store = hello.store_epoch == epoch
        cursors = {lane: (hello.cursors[lane] if same_store else 0) for lane in Lane}
        lanes = await self._call(lambda s: s.lane_info())
        backfill_until = {lane: info.head_seq for lane, info in lanes.items()}
        live, _ = await self._call(build_live_state, self.clock_synced)
        await send(SyncWelcome(app_version=APP_VERSION, msg_type="sync_welcome", edge_id=live.edge_id,
                               store_epoch=epoch, lanes=lanes, rover=rover_clock(self.clock_synced),
                               run_id=live.run_id, source_mode=live.source_mode).model_dump_json())
        acks = asyncio.create_task(self._acks(receive, send, hello.hub_id, epoch))
        try:
            await self._stream(send, cursors, backfill_until, acks)
        finally:
            acks.cancel()

    async def _stream(self, send: Send, cursors: dict[Lane, int], backfill_until: dict[Lane, int],
                      acks: asyncio.Task) -> None:
        next_live = 0.0
        next_batch = 0.0
        while not acks.done():
            if time.monotonic() >= next_live:  # live state first, and between batches
                live, _ = await self._call(build_live_state, self.clock_synced)
                await send(SyncLive(app_version=APP_VERSION, msg_type="sync_live", live=live).model_dump_json())
                next_live = time.monotonic() + self.live_interval_s
            if time.monotonic() < next_batch:
                # A large backfill batch must not delay live-state heartbeats.
                await asyncio.sleep(min(.05, next_batch - time.monotonic()))
                continue
            sent = False
            for lane in LANE_PRIORITY:  # control before track before observations, every round
                raws = await self._call(lambda s, ln=lane: s.read(ln, cursors[ln], self.batch_records))
                if not raws:
                    continue
                old = [r for r in raws if r.seq <= backfill_until[lane]]
                chunk, backfill = (old, True) if old else (raws, False)
                text = batch_json(lane, backfill, [r.json for r in chunk])
                await send(text)
                cursors[lane] = chunk[-1].seq
                self.sent_bytes["backfill" if backfill else "tail"] += len(text)
                if backfill:  # byte-rate cap: leave room for the phone stream on a shared network
                    next_batch = time.monotonic() + len(text) / self.max_bytes_per_s
                sent = True
                break
            if not sent:
                await asyncio.sleep(0.05)
        acks.result()  # surface the receiver's error, if any

    async def _acks(self, receive: Receive, send: Send, hub_id: str, epoch: Any) -> None:
        while True:
            ack = SyncAck.model_validate_json(await receive())
            if ack.store_epoch != epoch:
                continue  # an ack for another store never touches this one
            try:
                await self._call(lambda s: s.ack(hub_id, ack.lane, ack.seq))
            except StoreError as exc:
                await send(SyncError(app_version=APP_VERSION, msg_type="sync_error", code="bad_ack",
                                     message=str(exc)).model_dump_json())

