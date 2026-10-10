"""Step 2: real-model tests on bundled Ultralytics images. Skips (not fails) if weights can't be fetched."""

from pathlib import Path
from uuid import uuid4

import cv2
import numpy as np
import pytest
import ultralytics

from vision.config import load_config
from vision.detector import Detector, ensure_weights
from vision.schema import SCHEMA_VERSION, Box, DetectionEvent, parse_message

ASSETS = Path(ultralytics.__file__).parent / "assets"


@pytest.fixture(scope="session")
def detector():
    config = load_config()
    model = config["model"]
    try:
        ensure_weights(model["weights"], model.get("weights_url"), model.get("weights_sha256"))
    except Exception as e:  # offline with no cached weights
        pytest.skip(f"YOLO weights unavailable: {e}")
    return Detector.from_config(config)


def _load(name: str) -> np.ndarray:
    image = cv2.imread(str(ASSETS / name))
    assert image is not None
    return image


def _persons(result, min_conf: float = 0.5) -> int:
    return sum(b.cls_name == "person" and b.conf >= min_conf for b in result.boxes)


def _assert_in_bounds(result, image):
    h, w = image.shape[:2]
    assert (result.image_size.width, result.image_size.height) == (w, h)
    for box in result.boxes:
        assert isinstance(box, Box)
        x1, y1, x2, y2 = box.xyxy
        assert 0 <= x1 < x2 <= w and 0 <= y1 < y2 <= h


def test_bus_finds_people(detector):
    image = _load("bus.jpg")
    result = detector(image)
    assert _persons(result) >= 3
    assert result.inference_ms > 0
    _assert_in_bounds(result, image)


def test_zidane_finds_people(detector):
    image = _load("zidane.jpg")
    result = detector(image)
    assert _persons(result) >= 2
    _assert_in_bounds(result, image)


def test_blank_image_has_no_detections(detector):
    assert detector(np.zeros((480, 640, 3), dtype=np.uint8)).boxes == []


def test_rotated_portrait_input_stays_in_bounds(detector):
    image = cv2.rotate(_load("zidane.jpg"), cv2.ROTATE_90_CLOCKWISE)
    _assert_in_bounds(detector(image), image)


def test_sh17_classes_present(detector):
    assert {"person", "face", "head", "glasses", "helmet"} <= set(detector.names.values())


def test_tampered_weights_rejected(tmp_path):
    fake = tmp_path / "fake.pt"
    fake.write_bytes(b"not the real weights")
    with pytest.raises(ValueError, match="sha256 mismatch"):
        ensure_weights(fake, sha256="0" * 64)


def test_model_boxes_tagged_model(detector):
    boxes = detector(_load("zidane.jpg")).boxes
    assert boxes and all(b.source == "model" and b.cls_id is not None for b in boxes)


def test_device_is_resolved(detector):
    assert detector.device in ("cuda", "mps", "cpu")


@pytest.mark.parametrize(
    "bad", [np.zeros((10, 10), np.uint8), np.zeros((10, 10, 4), np.uint8), np.zeros((10, 10, 3), np.float32)]
)
def test_rejects_non_bgr_uint8(detector, bad):
    with pytest.raises(ValueError, match="BGR"):
        detector(bad)


def test_detections_feed_detection_event(detector):
    """Step 6 will wrap detector output in a DetectionEvent; prove the types line up."""
    result = detector(_load("bus.jpg"))
    event = DetectionEvent(
        schema_version=SCHEMA_VERSION,
        msg_type="detection_event",
        event_id=uuid4(),
        session_id=uuid4(),
        seq_id=0,
        iphone_frame_ts_ns=0,
        jetson_receive_ts_ns=0,
        inference_latency_ms=result.inference_ms,
        model_id=detector.model_id,
        image_size=result.image_size,
        tracking_state="normal",
        boxes=result.boxes,
        pose_valid=False,
        pose_invalid_reason="no_pose",
    )
    assert parse_message(event.model_dump_json()) == event
