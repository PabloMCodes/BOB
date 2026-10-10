"""Hub settings: configs/hub.yaml, overlaid by configs/hub.local.yaml or an explicit file."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import yaml

from vision.config import REPO_ROOT, _deep_merge

HUB_CONFIG = REPO_ROOT / "configs" / "hub.yaml"
HUB_LOCAL_CONFIG = REPO_ROOT / "configs" / "hub.local.yaml"


def load_hub_config(path: Optional[Path] = None) -> dict[str, Any]:
    config = yaml.safe_load(HUB_CONFIG.read_text())
    override = path or (HUB_LOCAL_CONFIG if HUB_LOCAL_CONFIG.exists() else None)
    if override is not None:
        config = _deep_merge(config, yaml.safe_load(Path(override).read_text()) or {})
    if not str(config.get("hub_id") or "").strip():
        raise ValueError("hub config: hub_id is required")
    return config


def replica_path(config: dict[str, Any]) -> Path:
    root = Path(config["replica_dir"])
    return (root if root.is_absolute() else REPO_ROOT / root) / config["hub_id"]


def sample_replica_path(config: dict[str, Any]) -> Path:
    """The SAMPLE edge is replicated into a separate database: it can never enter rover counts."""
    return replica_path(config).with_name(config["hub_id"] + "-sample")


def http_base(edge_url: str) -> str:
    """ws://host:port -> http://host:port (wss -> https)."""
    scheme, sep, rest = edge_url.partition("://")
    return {"ws": "http", "wss": "https"}.get(scheme, scheme) + sep + rest.rstrip("/")
