"""Step 3: eval tool on a tiny dataset built from bundled images."""

import shutil
from pathlib import Path

import numpy as np
import pytest
import ultralytics

from tools.eval_ppe import Row, evaluate, find_samples, render_report, resize_long_side
from vision.config import load_config

ASSETS = Path(ultralytics.__file__).parent / "assets"


def _dataset(root: Path) -> Path:
    (root / "wearing" / "3m").mkdir(parents=True)
    (root / "not_wearing" / "3m").mkdir(parents=True)
    shutil.copy(ASSETS / "bus.jpg", root / "wearing" / "3m" / "bus.jpg")
    shutil.copy(ASSETS / "zidane.jpg", root / "not_wearing" / "3m" / "zidane.jpg")
    return root


def test_find_samples_reads_labels_and_distance(tmp_path):
    samples = find_samples(_dataset(tmp_path))
    assert {(s.label, s.distance, s.path.name) for s in samples} == {
        ("wearing", "3m", "bus.jpg"),
        ("not_wearing", "3m", "zidane.jpg"),
    }


def test_heic_rejected_with_hint(tmp_path):
    _dataset(tmp_path)
    (tmp_path / "wearing" / "IMG_0001.HEIC").write_bytes(b"")
    with pytest.raises(SystemExit, match="Most Compatible"):
        find_samples(tmp_path)


def test_empty_dataset_rejected(tmp_path):
    with pytest.raises(SystemExit, match="no images"):
        find_samples(tmp_path)


def test_unsorted_images_explained(tmp_path):
    shutil.copy(ASSETS / "bus.jpg", tmp_path / "photo_1.jpg")
    with pytest.raises(SystemExit, match=r"found 1 image.*photo_1\.jpg.*ground-truth label"):
        find_samples(tmp_path)


def test_resize_never_upscales():
    image = np.zeros((100, 200, 3), np.uint8)
    assert resize_long_side(image, 400) is image
    assert resize_long_side(image, 100).shape[:2] == (50, 100)


def test_evaluate_end_to_end(tmp_path):
    config = load_config()
    rows = evaluate(find_samples(_dataset(tmp_path / "data")), "glasses",
                    [config["model"]["weights"]], ["head_crop@1280"], config, tmp_path / "out")
    overall = next(r for r in rows if r.distance == "ALL")
    assert (overall.n, overall.tp, overall.tn, overall.fp, overall.fn) == (2, 1, 1, 0, 0)
    assert overall.passed
    assert any((tmp_path / "out").rglob("zidane.jpg"))  # annotated image saved


def test_unverified_violation_counts_as_miss():
    row = Row("w", "s", "ALL", n=2, tp=1, fn=1, fp=0, tn=0, unverified=1, median_ms=1.0)
    assert row.recall == 0.5 and not row.passed
    assert "❌" in render_report([row], "glasses")


def test_no_distance_folders_gives_single_all_row(tmp_path):
    root = tmp_path / "data"
    (root / "wearing").mkdir(parents=True)
    shutil.copy(ASSETS / "bus.jpg", root / "wearing" / "bus.jpg")
    config = load_config()
    rows = evaluate(find_samples(root), "glasses", [config["model"]["weights"]], ["head_crop@1080"], config)
    assert [r.distance for r in rows] == ["ALL"]


def test_inactive_rule_rejected(tmp_path):
    config = load_config()
    with pytest.raises(SystemExit, match="inactive"):
        evaluate(find_samples(_dataset(tmp_path / "data")), "boots", [config["model"]["weights"]], ["single@640"], config)
