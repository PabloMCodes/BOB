"""Config loading and inference-device resolution."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = REPO_ROOT / "configs" / "default.yaml"
LOCAL_CONFIG = REPO_ROOT / "configs" / "local.yaml"

VALID_DEVICES = ("auto", "mps", "cuda", "cpu")


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(path: Path | None = None) -> dict[str, Any]:
    """Load default.yaml, overlaid by local.yaml (if present) or an explicit path."""
    config = yaml.safe_load(DEFAULT_CONFIG.read_text())
    override_path = path or (LOCAL_CONFIG if LOCAL_CONFIG.exists() else None)
    if override_path is not None:
        config = _deep_merge(config, yaml.safe_load(Path(override_path).read_text()) or {})
    if config["device"] not in VALID_DEVICES:
        raise ValueError(f"device must be one of {VALID_DEVICES}, got {config['device']!r}")
    return config


def resolve_device(requested: str = "auto") -> str:
    """Map a requested device to one that is actually available on this machine."""
    import torch

    if requested not in VALID_DEVICES:
        raise ValueError(f"device must be one of {VALID_DEVICES}, got {requested!r}")
    if requested == "auto":
        if torch.cuda.is_available():
            return "cuda"
        if torch.backends.mps.is_available():
            return "mps"
        return "cpu"
    if requested == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("device 'cuda' requested but CUDA is not available")
    if requested == "mps" and not torch.backends.mps.is_available():
        raise RuntimeError("device 'mps' requested but MPS is not available")
    return requested
