"""Step 3b: draft-label tool writes valid YOLO files with the training class list."""

import shutil
from pathlib import Path

import pytest
import ultralytics

from tools.prelabel import prelabel
from vision.config import load_config

ASSETS = Path(ultralytics.__file__).parent / "assets"


def _source(root: Path) -> Path:
    (root / "batch" / "sub").mkdir(parents=True)
    shutil.copy(ASSETS / "bus.jpg", root / "batch" / "bus.jpg")
    shutil.copy(ASSETS / "zidane.jpg", root / "batch" / "sub" / "zidane.jpg")
    return root / "batch"


def _check_yolo(out: Path, classes: list[str]) -> None:
    assert (out / "classes.txt").read_text().split() == classes
    images = sorted(p.stem for p in (out / "images").iterdir())
    labels = sorted(p.stem for p in (out / "labels").iterdir())
    assert images == labels == ["bus", "sub__zidane"]
    for label in (out / "labels").iterdir():
        for line in label.read_text().splitlines():
            c, *coords = line.split()
            assert 0 <= int(c) < len(classes)
            assert all(0.0 <= float(v) <= 1.0 for v in coords) and len(coords) == 4


def test_prelabel_sh17_only(tmp_path):
    config = load_config()
    counts = prelabel(_source(tmp_path), tmp_path / "out", config, use_world=False)
    _check_yolo(tmp_path / "out", config["training"]["classes"])
    assert counts["person"] >= 4 and counts["glasses"] >= 2  # bus: sunglasses via head_crop


def test_prelabel_with_yolo_world(tmp_path):
    pytest.importorskip("clip", reason="needs: uv run --group labeling")
    config = load_config()
    prelabel(_source(tmp_path), tmp_path / "out", config, use_world=True)
    _check_yolo(tmp_path / "out", config["training"]["classes"])
