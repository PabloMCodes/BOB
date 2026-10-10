"""Pre-shared token (D8) and the bind rule that goes with it.

The token comes from the environment or the gitignored `.env`; it is compared in constant time and
never printed. Without a token the API is reachable from this machine only (loopback), with a warning.
"""
from __future__ import annotations

import hmac
import ipaddress
import os
from pathlib import Path
from typing import Optional

from vision.config import REPO_ROOT

LOOPBACK = "127.0.0.1"


def load_token(env_name: str, dotenv: Path = REPO_ROOT / ".env") -> Optional[str]:
    value = os.environ.get(env_name)
    if not value and dotenv.exists():
        for line in dotenv.read_text().splitlines():
            key, sep, rest = line.strip().partition("=")
            if sep and key.strip() == env_name:
                value = rest.strip().strip("'\"")
    return value or None


def is_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def resolve_bind(host: Optional[str], configured: str, token: Optional[str]) -> tuple[str, Optional[str]]:
    """(host to bind, warning). No token: loopback only; an explicit non-loopback host is refused."""
    if token:
        return (configured if host is None else host), None
    if host is not None and not is_loopback(host):
        raise SystemExit(f"refusing to listen on {host} without a token: set the token in .env (see .env.example)")
    return host if host is not None else LOOPBACK, "no token set: listening on loopback only (this machine); set it in .env for the rover network"


def token_ok(expected: Optional[str], authorization: Optional[str]) -> bool:
    if expected is None:
        return True  # loopback-only mode (resolve_bind)
    scheme, _, given = (authorization or "").partition(" ")
    return scheme.lower() == "bearer" and hmac.compare_digest(given.encode(), expected.encode())
