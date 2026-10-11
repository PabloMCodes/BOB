"""Edge settings: configs/edge.yaml, overlaid by configs/edge.local.yaml or an explicit file."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import yaml

from vision.config import REPO_ROOT, _deep_merge

EDGE_CONFIG = REPO_ROOT / "configs" / "edge.yaml"
EDGE_LOCAL_CONFIG = REPO_ROOT / "configs" / "edge.local.yaml"


def load_edge_config(path: Optional[Path] = None) -> dict[str, Any]:
    config = yaml.safe_load(EDGE_CONFIG.read_text())
    override = path or (EDGE_LOCAL_CONFIG if EDGE_LOCAL_CONFIG.exists() else None)
    if override is not None:
        config = _deep_merge(config, yaml.safe_load(Path(override).read_text()) or {})
    if not str(config.get("edge_id") or "").strip():
        raise ValueError("edge config: edge_id is required")
    if type(config["archive"]["enabled"]) is not bool:
        raise ValueError("edge config: archive.enabled must be a boolean")
    return config


def store_path(config: dict[str, Any]) -> Path:
    root = Path(config["store_dir"])
    return (root if root.is_absolute() else REPO_ROOT / root) / config["edge_id"]
