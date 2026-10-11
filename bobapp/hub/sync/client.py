"""Hub sync client: connect to the rover edge API, resume per lane, commit, then acknowledge.

Every batch is committed before its record acknowledgment. Image retention separately waits for a
verified-JPEG receipt from BlobFetcher. Reconnects back off from `link.reconnect_min_s` to `reconnect_max_s`; a
silent link (no message for `link.stale_after_s`; the rover sends live state every 0.2 s) counts as lost.
"""
from __future__ import annotations

import asyncio
import hashlib
from http.client import HTTPException
from typing import Any, Callable, Optional

from websockets.asyncio.client import connect
from websockets.exceptions import WebSocketException

from bobapp.contracts import (
    APP_VERSION,
    Delivery,
    Lane,
    SyncAck,
    SyncBatch,
    SyncError,
    SyncHello,
    SyncLive,
    SyncWelcome,
    parse_app_message,
)

from .fetcher import BlobFetcher
from .http import HttpStatusError, http_get
from .link import LinkTracker

LINK_ERRORS = (OSError, WebSocketException, asyncio.TimeoutError, ValueError, RuntimeError)


class RoverRefused(RuntimeError):
    pass


class HubSyncClient:
    def __init__(self, replica: Any, config: dict[str, Any], token: Optional[str], edge_url: str, http_base: str,
                 on_event: Optional[Callable[[str, Any], None]] = None) -> None:
        self.replica, self.config, self.token = replica, config, token
        self.edge_url, self.http_base = edge_url.rstrip("/"), http_base
        self.link = LinkTracker(replica)
        self.fetcher = BlobFetcher(replica, http_base, token, config)
        self.on_event = on_event or (lambda kind, data: None)
        self.stale_s = config["link"]["stale_after_s"]
        self.sessions = 0
        self._preview_task: Optional[asyncio.Task] = None

    async def run(self, stop: asyncio.Event) -> None:
        fetcher = asyncio.create_task(self.fetcher.run(stop))
        delay = self.config["link"]["reconnect_min_s"]
        try:
            while not stop.is_set():
                error: Optional[BaseException] = None
                try:
                    await self._session(stop)
                    delay = self.config["link"]["reconnect_min_s"]
                except LINK_ERRORS as exc:
                    error = exc
                self.link.disconnected(error)
                self.on_event("disconnected", error)
                try:
                    await asyncio.wait_for(stop.wait(), timeout=delay)
                except asyncio.TimeoutError:
                    pass
                delay = min(delay * 2, self.config["link"]["reconnect_max_s"])
        finally:
            stop.set()
            await fetcher

    async def _session(self, stop: asyncio.Event) -> None:
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        async with connect(f"{self.edge_url}/v1/sync", additional_headers=headers, open_timeout=5,
                           ping_interval=2, ping_timeout=2, close_timeout=1, max_size=None) as ws:
            active = self.replica.active_workspace()
            await ws.send(SyncHello(app_version=APP_VERSION, msg_type="sync_hello", hub_id=self.config["hub_id"],
                                    store_epoch=active.store_epoch if active else None,
                                    cursors=self.replica.cursors(active)).model_dump_json())
            welcome = parse_app_message(await asyncio.wait_for(ws.recv(), timeout=self.stale_s))
            if isinstance(welcome, SyncError):
                raise RoverRefused(f"{welcome.code}: {welcome.message}")
            if not isinstance(welcome, SyncWelcome):
                raise ValueError(f"expected sync_welcome, got {welcome.msg_type}")
            workspace, changed = self.replica.adopt(welcome.edge_id, welcome.store_epoch)
            self.fetcher.workspace = workspace
            self.replica.db.execute("UPDATE blobs SET attempts=0 WHERE status IN ('pending_sync', 'hash_mismatch')")
            moved = self.replica.reconcile_welcome(workspace, welcome.lanes)
            for lane, seq in moved.items():
                await ws.send(self._ack(workspace, lane, seq))
            self.sessions += 1
            new_store = changed and active is not None  # first contact ever is not a "new store"
            self.link.connected(welcome, self.replica.cursors(workspace), new_store=new_store)
            self.on_event("connected", {"workspace": workspace, "new_store": new_store, "gaps": moved})
            while not stop.is_set():
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=self.stale_s)
                except asyncio.TimeoutError:
                    raise asyncio.TimeoutError(f"no message from the rover for {self.stale_s} s") from None
                await self._handle(ws, workspace, raw)

    async def _handle(self, ws: Any, workspace: Any, raw: str) -> None:
        msg = parse_app_message(raw)
        if isinstance(msg, SyncBatch):
            records = msg.records
            result = self.replica.commit(workspace, msg.lane, list(records),
                                         Delivery.BACKFILLED if msg.backfill else Delivery.REALTIME)
            await ws.send(self._ack(workspace, msg.lane, result.committed_seq))  # only after the commit
            self.link.committed(msg.lane, result.committed_seq)
            self.on_event("batch", (msg, result))
        elif isinstance(msg, SyncLive):
            self.link.contact()
            self.replica.set_live(msg.live.model_dump_json())
            self._maybe_fetch_preview(msg.live.preview.sha256 if msg.live.preview else None)
        elif isinstance(msg, SyncError):
            raise RoverRefused(f"{msg.code}: {msg.message}")

    def _ack(self, workspace: Any, lane: Lane, seq: int) -> str:
        return SyncAck(app_version=APP_VERSION, msg_type="sync_ack", store_epoch=workspace.store_epoch,
                       lane=lane, seq=seq).model_dump_json()

    def _maybe_fetch_preview(self, sha: Optional[str]) -> None:
        if sha is None or (self._preview_task and not self._preview_task.done()):
            return
        if self.replica.get_live()[3] == sha:
            return
        self._preview_task = asyncio.create_task(self._fetch_preview(sha))

    async def _fetch_preview(self, sha: str) -> None:
        try:
            data, headers = await asyncio.to_thread(http_get, f"{self.http_base}/v1/preview/latest", self.token, 5.0)
        except (HttpStatusError, OSError, HTTPException):
            return  # the next live message tries again
        actual = hashlib.sha256(data).hexdigest()
        if headers.get("x-sha256") == actual:  # the preview may have moved on; keep whatever is consistent
            self.replica.set_live_preview(data, actual, headers.get("x-event-id"))

