"""Step 2: box rendering and safety-semantic categorization (no model needed)."""

import numpy as np
import pytest

from vision.config import load_config
from vision.render import CATEGORY_COLORS, categorize, draw
from vision.schema import Box

CATEGORIES = load_config()["render"]["categories"]


@pytest.mark.parametrize(
    "name, expected",
    [
        ("no-hardhat", "violation"),
        ("NO-Hardhat", "violation"),
        ("no_hardhat", "violation"),
        ("NO-Safety Vest", "violation"),
        ("Hardhat", "compliant"),
        ("safety vest", "compliant"),
        ("person", "person"),
        ("no-safety-glasses", "violation"),
        ("glasses", "compliant"),
        ("helmet", "compliant"),
        ("tie", "other"),
        ("bus", "other"),
    ],
)
def test_categorize(name, expected):
    assert categorize(name, CATEGORIES) == expected


def _box(name, xyxy=(20.0, 30.0, 80.0, 90.0)):
    return Box(source="model", cls_id=0, cls_name=name, conf=0.9, xyxy=xyxy)


def test_draw_does_not_mutate_input():
    image = np.zeros((120, 160, 3), dtype=np.uint8)
    out = draw(image, [_box("person")], CATEGORIES, status="status")
    assert image.sum() == 0
    assert out.shape == image.shape and out.dtype == image.dtype


@pytest.mark.parametrize("name, category", [("no-hardhat", "violation"), ("hardhat", "compliant"), ("tie", "other")])
def test_box_edge_uses_category_color(name, category):
    image = np.zeros((120, 160, 3), dtype=np.uint8)
    out = draw(image, [_box(name)], CATEGORIES)
    # Bottom edge midpoint of the rectangle — away from the label.
    assert tuple(int(c) for c in out[90, 50]) == CATEGORY_COLORS[category]


def test_status_bar_drawn_top_left():
    image = np.zeros((120, 160, 3), dtype=np.uint8)
    assert draw(image, [], CATEGORIES, status="mps | 18 ms")[:20, :40].any()
    assert not draw(image, [], CATEGORIES)[:20, :40].any()


def test_box_at_top_edge_keeps_label_on_screen():
    image = np.zeros((120, 160, 3), dtype=np.uint8)
    out = draw(image, [_box("person", (10.0, 0.0, 100.0, 60.0))], CATEGORIES)
    assert out[:15, 10:60].any()


def test_hidden_classes_not_drawn():
    image = np.zeros((120, 160, 3), dtype=np.uint8)
    assert not draw(image, [_box("face")], CATEGORIES, hide=["Face"]).any()
    assert draw(image, [_box("face")], CATEGORIES).any()


def test_crop_regions_drawn_grey():
    image = np.zeros((120, 160, 3), dtype=np.uint8)
    out = draw(image, [], CATEGORIES, regions=[(10, 10, 60, 60)])
    assert tuple(int(c) for c in out[10, 30]) == CATEGORY_COLORS["other"]
