"""Evidence prefetch: every image whose metadata has committed is fetched by hash, verified and kept,
under a byte-rate cap so catch-up cannot starve the phone stream on a shared hotspot. A 404 from the
rover is final (`missing`); network errors and mismatched hashes retry after `blobs.retry_s`.
Only verified saved JPEGs generate image receipts, retried until acknowledged by the edge."""
from __future__ import annotations

import asyncio
from http.client import HTTPException
from typing import Any, Optional

from bobapp.contracts import BlobStatusValue

from .http import HttpStatusError, http_get, http_post_json


class BlobFetcher:
    def __init__(self, replica: Any, base_url: str, token: Optional[str], config: dict[str, Any]) -> None:
        self.replica, self.base_url, self.token = replica, base_url, token
        self.max_bytes_per_s = config["blobs"]["max_bytes_per_s"]
        self.retry_ns = int(config["blobs"]["retry_s"] * 1e9)
        self.fetched_bytes = 0
        self.hub_id = config["hub_id"]
        self.workspace = None

    async def run(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            if self.workspace is not None:
                for sha in self.replica.pending_receipts(self.workspace):
                    if not await self.receipt(sha):
                        break
            pending = self.replica.pending_blobs(limit=20, retry_after_ns=self.retry_ns)
            if not pending:
                await asyncio.sleep(0.5)
                continue
            for sha in pending:
                if stop.is_set():
                    return
                await self.fetch(sha)

    async def fetch(self, sha: str) -> BlobStatusValue:
        try:
            data, _ = await asyncio.to_thread(http_get, f"{self.base_url}/v1/blobs/{sha}", self.token)
        except HttpStatusError as exc:
            if exc.status == 404:
                self.replica.mark_blob(sha, BlobStatusValue.MISSING, error="not on the rover")
                return BlobStatusValue.MISSING
            self.replica.retry_later(sha, str(exc))
            return BlobStatusValue.PENDING_SYNC
        except (OSError, HTTPException) as exc:  # includes a cut in the middle of an HTTP body
            self.replica.retry_later(sha, f"{type(exc).__name__}: {exc}")
            await asyncio.sleep(0.5)
            return BlobStatusValue.PENDING_SYNC
        try:
            status = self.replica.store_blob(sha, data)
        except OSError as exc:
            self.replica.retry_later(sha, f"Image could not be saved: {exc}")
            return BlobStatusValue.PENDING_SYNC
        self.fetched_bytes += len(data)
        await asyncio.sleep(len(data) / self.max_bytes_per_s)
        return status

    async def receipt(self, sha: str) -> bool:
        ws = self.workspace
        if ws is None:
            return False
        try:
            status, _ = await asyncio.to_thread(http_post_json,
                f"{self.base_url}/v1/blobs/{sha}/ack", self.token,
                {"hub_id": self.hub_id, "store_epoch": str(ws.store_epoch)}, 2.)
        except (OSError, HTTPException, ValueError):
            return False
        if status != 200:
            return False
        self.replica.acknowledge_blob(ws, sha)
        return True
