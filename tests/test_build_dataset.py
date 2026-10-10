"""Step 3b: dataset builder — class remap, boots review decisions, pseudo-labels, data.yaml."""

import json

import pytest
import yaml

from tests.test_review_boots import make_dataset
from tools.build_dataset import build, filter_pseudo
from vision.config import load_config
from vision.schema import Box

CONFIG = load_config()
CLASSES = CONFIG["training"]["classes"]
CLASS_MAP = CONFIG["training"]["external"]["footwear-w1uf6-v2"]["class_map"]


def _b(name, xyxy, conf=0.9):
    return Box(source="model", cls_id=0, cls_name=name, conf=conf, xyxy=xyxy)


PERSON, HEAD = (10.0, 10.0, 100.0, 300.0), (30.0, 15.0, 70.0, 60.0)


class FakeLabeler:
    """Pseudo-labels: a consistent person + head, plus 'shoes' and 'helmet' that must be ignored."""

    def boxes(self, image):
        return [_b("person", PERSON), _b("head", HEAD), _b("shoes", (10.0, 280.0, 60.0, 300.0)),
                _b("helmet", (30.0, 10.0, 70.0, 40.0))]


def test_filter_drops_person_without_head_and_ppe_classes():
    sandal_person = _b("person", (200.0, 200.0, 300.0, 300.0))   # no head/face inside
    stray_hand = _b("hands", (400.0, 400.0, 420.0, 420.0))       # outside any person
    hand = _b("hands", (40.0, 150.0, 60.0, 170.0))
    kept = filter_pseudo([_b("person", PERSON), _b("face", HEAD), hand, sandal_person, stray_hand,
                          _b("gloves", (40.0, 150.0, 60.0, 170.0))], {"person", "head", "face", "hands"})
    assert sorted(b.cls_name for b in kept) == ["face", "hands", "person"]
    assert sandal_person not in kept and stray_hand not in kept


def _labels(out, split, stem):
    return [line.split() for line in (out / split / "labels" / f"{stem}.txt").read_text().splitlines()]


def test_build_maps_classes_and_applies_review(tmp_path):
    src = make_dataset(tmp_path / "rf")
    decisions = {"train/a#0": "safety-boots", "train/a#2": "shoes"}
    summary = build(src, tmp_path / "out", CONFIG, CLASS_MAP, decisions, labeler=FakeLabeler())

    a = _labels(tmp_path / "out", "train", "a")
    names = [CLASSES[int(row[0])] for row in a]
    # boots#0 -> safety-boots, sneakers -> shoes, boots#2 -> shoes (review), + pseudo person + head
    assert names == ["safety-boots", "shoes", "shoes", "person", "head"]
    assert a[0][1:] == ["0.2", "0.9", "0.1", "0.08"]  # footwear coordinates copied untouched
    assert summary["images"]["train"] == 2 and summary["dropped_images"] == 0

    data = yaml.safe_load((tmp_path / "out" / "data.yaml").read_text())
    assert list(data["names"].values()) == CLASSES and data["val"] == "val/images"
    assert json.loads((tmp_path / "out" / "summary.json").read_text())["instances"]["train"]["person"] == 2


def test_drop_image_decision_removes_image(tmp_path):
    src = make_dataset(tmp_path / "rf")
    summary = build(src, tmp_path / "out", CONFIG, CLASS_MAP,
                    {"train/a#0": "drop-image", "train/a#2": "shoes"}, labeler=FakeLabeler())
    assert summary["images"]["train"] == 1 and summary["dropped_images"] == 1
    assert not (tmp_path / "out" / "train" / "labels" / "a.txt").exists()


def test_unreviewed_boots_stop_the_build(tmp_path):
    src = make_dataset(tmp_path / "rf")
    with pytest.raises(SystemExit, match="not reviewed"):
        build(src, tmp_path / "out", CONFIG, CLASS_MAP, {"train/a#0": "shoes"}, labeler=FakeLabeler())
    assert not (tmp_path / "out").exists()  # failed before writing anything


def test_skip_unreviewed_leaves_those_images_out(tmp_path):
    src = make_dataset(tmp_path / "rf")
    summary = build(src, tmp_path / "out", CONFIG, CLASS_MAP, {}, labeler=FakeLabeler(), skip_unreviewed=True)
    assert summary["images"]["train"] == 1 and summary["skipped_unreviewed_boxes"] == 2


def test_class_map_must_cover_source_classes(tmp_path):
    src = make_dataset(tmp_path / "rf")
    with pytest.raises(SystemExit, match="unmapped"):
        build(src, tmp_path / "out", CONFIG, {"boots": "review"}, {}, labeler=FakeLabeler())
