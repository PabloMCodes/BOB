"""The specialist must never reinterpret generic SH17 shoes as a boots violation."""
import copy

import numpy as np
import pytest

from vision.config import load_config
from vision.detector import Detections
from vision.pipeline import Pipeline
from vision.schema import Box, ImageSize


class Stub:
    device = "cpu"

    def __init__(self, names, boxes, model_id):
        self.names, self.boxes, self.model_id = names, boxes, model_id
        self.calls = []

    def warmup(self, imgsz):
        pass

    def __call__(self, image, **kwargs):
        h, w = image.shape[:2]
        self.calls.append((h, w))
        return Detections(self.boxes, ImageSize(width=w, height=h), 1.0)


def box(cls_id, name, xyxy, conf=.9):
    return Box(source="model", cls_id=cls_id, cls_name=name, conf=conf, xyxy=xyxy)


@pytest.mark.parametrize("mode", ["single", "head_crop"])
@pytest.mark.parametrize("target", [None, "shoes", "safety-boots"])
def test_specialist_owns_footwear_and_preserves_other_rules(mode, target):
    config = load_config()
    base = Stub({0: "person", 1: "shoes", 2: "safety-vest"}, [
        box(0, "person", (100., 100., 300., 900.)),
        box(1, "shoes", (110., 810., 190., 880.)),
    ], "sh17-stub")
    classes = {0: "shoes", 1: "safety-boots"}
    shoe_boxes = [] if target is None else [box(list(classes.values()).index(target), target, (10., 100., 90., 150.))]
    footwear = Stub(classes, shoe_boxes, "footwear-stub")
    result = Pipeline(base, config, mode=mode, footwear=footwear)(np.zeros((1000, 600, 3), np.uint8))
    assert footwear.calls == [(200, 200)]
    boot_verdicts = [v for v in result.verdicts if v.rule == "boots"]
    assert len(boot_verdicts) == (target is not None)
    assert any(v.rule == "vest" for v in result.verdicts)
    if target:
        found = next(b for b in result.boxes if b.cls_name == target)
        assert found.cls_id == 3 + list(classes.values()).index(target)
        assert found.xyxy[1] > 600
        assert boot_verdicts[0].verdict.value == ("wearing" if target == "safety-boots" else "not_wearing")
    else:
        assert not any(b.cls_name in {"shoes", "no-safety-boots"} for b in result.boxes)


def test_no_person_no_footwear_verdict():
    base = Stub({0: "person", 1: "shoes"}, [box(1, "shoes", (0., 0., 20., 20.))], "base")
    footwear = Stub({0: "shoes", 1: "safety-boots"}, [], "boots")
    result = Pipeline(base, load_config(), footwear=footwear)(np.zeros((100, 100, 3), np.uint8))
    assert not footwear.calls and not result.verdicts


def test_specialist_requires_pinned_hash():
    config = copy.deepcopy(load_config())
    config["footwear_model"] = {"enabled": True, "weights": "not-loaded.pt"}
    with pytest.raises(ValueError, match="sha256"):
        Pipeline.from_config(config)


def test_direct_pipeline_constructor_honors_specialist_config(monkeypatch):
    """The PPE comparison evaluator constructs Pipeline directly, rather than from_config."""
    config = copy.deepcopy(load_config())
    config["footwear_model"] = {"enabled": True, "weights": "test.pt", "weights_sha256": "a" * 64}
    footwear = Stub({0: "shoes", 1: "safety-boots"}, [], "boots")
    monkeypatch.setattr("vision.pipeline.Detector", lambda *args, **kwargs: footwear)
    base = Stub({0: "person", 1: "shoes"}, [], "base")
    pipeline = Pipeline(base, config)
    assert pipeline.footwear is footwear
    assert "boots" in {r.name for r in pipeline.rules}
    assert pipeline.names == {0: "person", 2: "shoes", 3: "safety-boots"}


def test_crop_config_cannot_reintroduce_generic_sh17_shoes():
    config = copy.deepcopy(load_config())
    config["pipeline"]["feet_crop"]["classes"] = ["safety-boots"]
    base = Stub({0: "person", 1: "shoes"}, [], "base")
    footwear = Stub({0: "shoes", 1: "safety-boots"}, [], "boots")
    with pytest.raises(ValueError, match="feet_crop.classes"):
        Pipeline(base, config, footwear=footwear)
