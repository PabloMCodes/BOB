"""Step 8: Jetson handoff — batched crops == sequential crops, parity matcher, ONNX export pins + parity.

ONNX tests need the `export` dependency group and the exported files:
    YOLO_AUTOINSTALL=false uv run --group export python -m tools.export_onnx
    uv run --group export pytest tests/test_handoff.py
Without them they skip (the Jetson itself has no onnx tooling).
"""

import copy
import shutil

import numpy as np
import pytest

from tools.parity import bundled_images, compare, match_boxes
from vision.config import REPO_ROOT, load_config
from vision.detector import Detector
from vision.pipeline import Pipeline
from vision.schema import Box

CONFIG = load_config()


def _box(name, xyxy, conf=0.8):
    return Box(source="model", cls_id=0, cls_name=name, conf=conf, xyxy=xyxy)


# --- parity matcher ---------------------------------------------------------------------------

def test_match_identical_boxes_passes():
    boxes = [_box("face", (10.0, 10.0, 50.0, 60.0)), _box("glasses", (15.0, 20.0, 45.0, 30.0), 0.5)]
    assert match_boxes(boxes, list(boxes)) == ([], 1.0, 0.0)


@pytest.mark.parametrize("b, why", [
    ([], "no partner"),                                                            # missing box
    ([_box("face", (10.0, 10.0, 50.0, 60.0)), _box("helmet", (0.0, 0.0, 9.0, 9.0))], "extra"),
    ([_box("face", (14.0, 10.0, 54.0, 60.0))], "no partner"),                      # IoU 0.82 < 0.9
    ([_box("face", (10.0, 10.0, 50.0, 60.0), 0.83)], "conf"),                      # |dconf| 0.03 > 0.02
    ([_box("head", (10.0, 10.0, 50.0, 60.0))], "no partner"),                      # other class
])
def test_match_rejects(b, why):
    problems, _, _ = match_boxes([_box("face", (10.0, 10.0, 50.0, 60.0))], b)
    assert problems and any(why in p for p in problems)


# --- batched head crops ----------------------------------------------------------------------

@pytest.fixture(scope="module")
def detector():
    return Detector.from_config(CONFIG)


def test_detect_batch_equals_one_call_per_image(detector):
    crops =[img[:320, :320] for _, img in bundled_images()] + [np.zeros((200, 200, 3), np.uint8)]
    batched = detector.detect_batch(crops, imgsz=320, conf=0.3)
    for crop, b in zip(crops, batched):
        single = detector(crop, imgsz=320, conf=0.3)
        assert match_boxes(single.boxes, b.boxes)[0] == []
        assert b.image_size == single.image_size
    assert detector.detect_batch([]) == []


def test_batched_pipeline_identical_to_sequential(detector, monkeypatch):
    seq_cfg, batch_cfg = copy.deepcopy(CONFIG), copy.deepcopy(CONFIG)
    seq_cfg["pipeline"]["crop"]["batch"], batch_cfg["pipeline"]["crop"]["batch"] = False, True
    calls = []
    real = Detector.detect_batch
    monkeypatch.setattr(Detector, "detect_batch", lambda self, *a, **k: calls.append(len(a[0])) or real(self, *a, **k))
    report = compare(Pipeline(detector, seq_cfg), Pipeline(detector, batch_cfg), bundled_images())
    assert report.passed, report.failures
    assert calls and max(calls) >= 2  # really batched: several crops in one call (bus.jpg)


def test_batch_is_the_default():
    assert CONFIG["pipeline"]["crop"]["batch"] is True


# --- ONNX ------------------------------------------------------------------------------------

def _onnx_ready():
    pytest.importorskip("onnxruntime", reason="needs `uv run --group export`")
    from tools.export_onnx import ONNX_CONFIG
    if not ONNX_CONFIG.exists():
        pytest.skip("configs/onnx.yaml missing — run tools.export_onnx")
    import yaml
    pins = yaml.safe_load(ONNX_CONFIG.read_text())
    from vision.detector import _sha256
    for model in pins.values():
        path = REPO_ROOT / model["weights"]
        if not path.exists() or _sha256(path) != model["weights_sha256"]:
            pytest.skip(f"{model['weights']} missing or not the pinned export — run tools.export_onnx")
    return pins


def test_onnx_config_swaps_models_and_never_enables_footwear():
    pins = _onnx_ready()
    from tools.export_onnx import onnx_config
    config = onnx_config(CONFIG)
    assert config["model"]["weights"].endswith(".onnx")
    assert config["model"]["weights_sha256"] == pins["model"]["weights_sha256"]
    assert config["device"] in ("cpu", "cuda")  # never onnxruntime's CoreML provider
    assert not config.get("footwear_model", {}).get("enabled", False)


def test_tampered_onnx_is_refused(tmp_path):
    pins = _onnx_ready()
    bad = tmp_path / "sh17.onnx"
    shutil.copy(REPO_ROOT / pins["model"]["weights"], bad)
    with open(bad, "ab") as fh:
        fh.write(b"\x00")
    with pytest.raises(ValueError, match="sha256"):
        Detector(bad, "cpu", weights_sha256=pins["model"]["weights_sha256"])


def test_onnx_pipeline_matches_pt_on_bundled_images(detector):
    _onnx_ready()
    from tools.export_onnx import onnx_config
    onnx = Pipeline.from_config(onnx_config(CONFIG))
    assert onnx.detector.weights.suffix == ".onnx"
    report = compare(Pipeline(detector, CONFIG), onnx, bundled_images())
    assert report.passed, report.failures
    assert report.max_dconf <= 1e-3 and report.min_iou >= 0.999  # fp32 export: float noise only
