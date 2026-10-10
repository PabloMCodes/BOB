"""Blocking authenticated GET / JSON POST to the edge API (stdlib only; called from worker threads)."""
from __future__ import annotations

import json
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


def http_post_json(url: str, token: Optional[str], body: dict, timeout: float = 5.0) -> tuple[int, dict]:
    """(status, JSON body) — HTTP error statuses are returned, not raised; network errors raise OSError."""
    headers = {"Content-Type": "application/json", **({"Authorization": f"Bearer {token}"} if token else {})}
    request = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read() or b"{}")
        except ValueError:
            return exc.code, {}
