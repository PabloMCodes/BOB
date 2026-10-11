"""Step 3: pipeline geometry + real-model regression on bundled images.

bus.jpg: two men wear sunglasses (SH17 counts these as glasses). zidane.jpg: two men, no glasses.
"""

from pathlib import Path

import copy

import cv2
import numpy as np
import pytest
import ultralytics

from vision.config import load_config
from vision.pipeline import Pipeline, feet_region, head_region, nms_per_class
from vision.ppe import Verdict
from vision.schema import Box

ASSETS = Path(ultralytics.__file__).parent / "assets"
CONFIG = load_config()
# Same pipeline with glasses absence = violation: checks eye-band geometry on real faces.
GLASSES_VIOLATION = copy.deepcopy(CONFIG)
GLASSES_VIOLATION["ppe"]["rules"]["glasses"]["absence"] = "violation"


def test_head_region_is_square_at_top_of_person():
    x0, y0, x1, y1 = head_region((100.0, 200.0, 160.0, 500.0), 1000, 1000, 0.35)
    assert x1 - x0 == y1 - y0 == 105  # 0.35 * 300 px tall person
    assert y0 < 200 < y1 and x0 < 130 < x1


def test_head_region_shifted_inside_image():
    region = head_region((0.0, 0.0, 40.0, 400.0), 300, 200, 0.35)
    assert region[0] >= 0 and region[1] >= 0 and region[2] <= 300 and region[3] <= 200
    assert region[2] - region[0] == region[3] - region[1]


def test_head_region_centred_on_pass1_head():
    head = (400.0, 300.0, 500.0, 420.0)  # 100 x 120 px
    x0, y0, x1, y1 = head_region((300.0, 250.0, 600.0, 1000.0), 2000, 2000, 0.35, head=head, head_scale=2.0)
    assert x1 - x0 == y1 - y0 == 240
    assert x0 < 400 and x1 > 500 and y0 < 300 and y1 > 420  # whole head inside: no half faces


def test_nms_drops_partial_box_inside_full_box():
    full = Box(source="model", cls_id=3, cls_name="face", conf=0.9, xyxy=(0.0, 0.0, 100.0, 100.0))
    partial = Box(source="model", cls_id=3, cls_name="face", conf=0.6, xyxy=(0.0, 0.0, 100.0, 40.0))
    assert nms_per_class([partial, full], 0.5) == [full]


def test_nms_keeps_best_per_class():
    a = Box(source="model", cls_id=8, cls_name="glasses", conf=0.9, xyxy=(0.0, 0.0, 10.0, 10.0))
    b = Box(source="model", cls_id=8, cls_name="glasses", conf=0.6, xyxy=(1.0, 1.0, 10.0, 10.0))
    c = Box(source="model", cls_id=3, cls_name="face", conf=0.5, xyxy=(1.0, 1.0, 10.0, 10.0))
    assert nms_per_class([b, a, c], 0.5) == [a, c]


def test_unknown_mode_rejected():
    with pytest.raises(ValueError, match="pipeline.mode"):
        Pipeline(object(), CONFIG, mode="fast")  # fails before the detector is touched


@pytest.fixture(scope="module")
def detector():
    return Pipeline.from_config(CONFIG).detector


def _run(detector, mode, name, config=CONFIG):
    return Pipeline(detector, config, mode=mode)(cv2.imread(str(ASSETS / name)))


def _verdicts(result, rule):
    return sorted(v.verdict.value for v in result.verdicts if v.rule == rule)


def test_head_crop_finds_sunglasses_single_pass_misses(detector):
    """The reason head_crop exists: small eyewear is missed at 640 on the whole frame."""
    def glasses(r):
        return sum(b.cls_name == "glasses" for b in r.boxes)
    single, crop = _run(detector, "single", "bus.jpg"), _run(detector, "head_crop", "bus.jpg")
    assert glasses(crop) >= 2 and glasses(crop) > glasses(single)


def test_bus_sunglasses_judged_wearing(detector):
    assert _verdicts(_run(detector, "head_crop", "bus.jpg"), "glasses") == ["wearing", "wearing"]


def test_zidane_no_helmet_and_glasses_unverified(detector):
    # SH17 can't see clear safety glasses, so a face without a glasses box is never a violation.
    result = _run(detector, "head_crop", "zidane.jpg")
    assert _verdicts(result, "glasses") == ["unverified", "unverified"]
    assert not any(b.cls_name == "no-safety-glasses" for b in result.boxes)
    assert _verdicts(result, "helmet") == ["not_wearing", "not_wearing"]


def test_zidane_no_glasses_when_absence_is_a_violation(detector):
    result = _run(detector, "head_crop", "zidane.jpg", GLASSES_VIOLATION)
    assert _verdicts(result, "glasses") == ["not_wearing", "not_wearing"]


@pytest.mark.parametrize("name", ["bus.jpg", "zidane.jpg"])
def test_nobody_without_vest_judged_wearing(detector, name):
    verdicts = _verdicts(_run(detector, "head_crop", name), "vest")
    assert "not_wearing" in verdicts and "wearing" not in verdicts


def test_violation_box_lies_on_face(detector):
    result = _run(detector, "head_crop", "zidane.jpg", GLASSES_VIOLATION)
    assert any(v.rule == "glasses" and v.verdict is Verdict.NOT_WEARING for v in result.verdicts)
    for v in result.verdicts:
        if v.rule == "glasses" and v.verdict is Verdict.NOT_WEARING:
            fx1, fy1, fx2, fy2 = v.subject.xyxy
            x1, y1, x2, y2 = v.violation.xyxy
            assert fx1 <= x1 < x2 <= fx2 and fy1 <= y1 < y2 <= fy2
            assert v.violation in result.boxes


def test_head_crop_boxes_stay_in_image(detector):
    result = _run(detector, "head_crop", "bus.jpg")
    w, h = result.image_size.width, result.image_size.height
    assert result.passes == 1 + len(result.crop_regions)
    for b in result.boxes:
        assert 0 <= b.xyxy[0] < b.xyxy[2] <= w and 0 <= b.xyxy[1] < b.xyxy[3] <= h


def test_merge_keeps_pass1_detection_when_crop_misses(detector, monkeypatch):
    """Regression: clear safety glasses found only by pass 1 were discarded by the old 'replace' merge."""
    pipeline = Pipeline(detector, CONFIG, mode="head_crop")
    glasses = Box(source="model", cls_id=8, cls_name="glasses", conf=0.6, xyxy=(110.0, 120.0, 150.0, 135.0))
    first = [
        Box(source="model", cls_id=0, cls_name="person", conf=0.9, xyxy=(50.0, 80.0, 250.0, 600.0)),
        Box(source="model", cls_id=12, cls_name="head", conf=0.9, xyxy=(95.0, 90.0, 165.0, 180.0)),
        glasses,
    ]
    empty = type("R", (), {"boxes": [], "inference_ms": 1.0})()
    monkeypatch.setattr(pipeline, "detector", lambda *a, **k: empty)  # pass 2 finds nothing
    boxes, _, regions = pipeline._head_crops(np.zeros((700, 400, 3), np.uint8), first)
    assert len(regions) == 1 and glasses in boxes


# --- feet crop -----------------------------------------------------------------------------

def test_feet_region_covers_bottom_of_person():
    x0, y0, x1, y1 = feet_region((400.0, 300.0, 700.0, 1500.0), 1440, 1920, 0.25)
    assert x1 - x0 == y1 - y0 == 300  # max(width 300, 0.25 * 1200)
    assert y0 < 1500 < y1 and x0 <= 400 and x1 >= 700  # soles inside, full width


def test_feet_crop_off_with_sh17(detector):
    assert not Pipeline(detector, CONFIG, mode="head_crop").feet_enabled


class FakeFinetuned:
    """Stand-in for a fine-tuned model that has safety-boots; returns canned boxes per call."""

    model_id, device = "fake", "cpu"
    names = dict(enumerate(CONFIG["training"]["classes"]))

    def __init__(self):
        self.calls = []

    def warmup(self, imgsz):
        pass

    def __call__(self, image, imgsz=None, conf=None):
        self.calls.append(image.shape[:2])
        h, w = image.shape[:2]
        if len(self.calls) == 1:  # pass 1: one person, no footwear found at full-frame scale
            boxes = [Box(source="model", cls_id=0, cls_name="person", conf=0.9, xyxy=(100.0, 100.0, 300.0, 900.0))]
        elif w == h and len(self.calls) == 3:  # feet crop: sneakers fill the crop
            boxes = [Box(source="model", cls_id=7, cls_name="shoes", conf=0.8, xyxy=(10.0, 100.0, 90.0, 150.0))]
        else:
            boxes = []
        return type("R", (), {"boxes": boxes, "inference_ms": 1.0, "image_size": None})()


def test_feet_crop_finds_shoes_and_triggers_boots_rule():
    fake = FakeFinetuned()
    pipeline = Pipeline(fake, CONFIG, mode="head_crop")
    assert pipeline.feet_enabled
    result = pipeline(np.zeros((1000, 600, 3), np.uint8))
    assert len(fake.calls) == 3 and result.passes == 3  # full frame + head crop + feet crop
    shoes = [b for b in result.boxes if b.cls_name == "shoes"]
    assert len(shoes) == 1 and shoes[0].xyxy[1] > 600  # shifted back into frame, near the feet
    assert any(b.cls_name == "no-safety-boots" and b.source == "derived" for b in result.boxes)
