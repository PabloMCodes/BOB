"""Step 0 smoke tests: environment, config, and device resolution."""

import platform
import sys

import pytest

from vision.config import load_config, resolve_device


def test_python_matches_jetson():
    assert sys.version_info[:2] == (3, 10)


def test_core_imports():
    import cv2
    import numpy
    import pydantic
    import torch
    import ultralytics
    import websockets
    import yaml

    for module in (cv2, numpy, pydantic, torch, ultralytics, websockets, yaml):
        assert module.__version__


def test_default_config_loads():
    config = load_config()
    assert config["device"] in ("auto", "mps", "cuda", "cpu")
    assert config["model"]["imgsz"] == 640
    assert config["timing"]["stale_ms"] == 250


def test_invalid_device_rejected(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("device: tpu\n")
    with pytest.raises(ValueError):
        load_config(bad)


@pytest.mark.skipif(
    not (sys.platform == "darwin" and platform.machine() == "arm64"),
    reason="MPS only exists on Apple Silicon",
)
def test_mps_available_on_apple_silicon():
    import torch

    assert torch.backends.mps.is_available()
    assert resolve_device("auto") == "mps"


def test_tensor_op_on_resolved_device():
    import torch

    device = resolve_device("auto")
    x = torch.ones(2, 2, device=device)
    assert (x @ x).sum().item() == 8.0
