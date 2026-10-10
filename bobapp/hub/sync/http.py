"""Blocking authenticated GET to the edge API (stdlib only; called from a worker thread)."""
from __future__ import annotations

import urllib.error
import urllib.request
from typing import Optional


class HttpStatusError(Exception):
    def __init__(self, status: int) -> None:
        super().__init__(f"HTTP {status}")
        self.status = status


def http_get(url: str, token: Optional[str], timeout: float = 10.0) -> tuple[bytes, dict[str, str]]:
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"} if token else {})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read(), {k.lower(): v for k, v in response.headers.items()}
    except urllib.error.HTTPError as exc:
        raise HttpStatusError(exc.code) from None
