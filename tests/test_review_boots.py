"""Step 3b: boots review — collection, CLIP-ordered review state, resumable decisions (no GUI)."""

import json
import shutil
from pathlib import Path

import pytest
import ultralytics

from tools.review_boots import Item, Review, collect_boots, crop, save_json, score_all

ASSETS = Path(ultralytics.__file__).parent / "assets"


def make_dataset(root: Path) -> Path:
    """Tiny Roboflow-format dataset: 2 train images; boots = class 0, sneakers = class 4."""
    (root / "data.yaml").parent.mkdir(parents=True, exist_ok=True)
    (root / "data.yaml").write_text("names: [boots, flip_flops, loafers, sandals, sneakers, soccer]\nnc: 6\n")
    for split in ("train", "valid", "test"):
        (root / split / "images").mkdir(parents=True)
        (root / split / "labels").mkdir(parents=True)
    shutil.copy(ASSETS / "bus.jpg", root / "train" / "images" / "a.jpg")
    shutil.copy(ASSETS / "zidane.jpg", root / "train" / "images" / "b.jpg")
    (root / "train" / "labels" / "a.txt").write_text("0 0.2 0.9 0.1 0.08\n4 0.5 0.9 0.1 0.08\n0 0.8 0.9 0.1 0.08\n")
    (root / "train" / "labels" / "b.txt").write_text("4 0.5 0.5 0.2 0.2\n")
    return root


def test_collect_only_boots_with_stable_keys(tmp_path):
    items = collect_boots(make_dataset(tmp_path / "rf"))
    assert [it.key for it in items] == ["train/a#0", "train/a#2"]
    assert crop(items[0]).size > 0


def test_score_all_uses_scorer_in_batches(tmp_path):
    items = collect_boots(make_dataset(tmp_path / "rf"))
    calls = []
    scores = score_all(items, lambda crops: calls.append(len(crops)) or [0.9] * len(crops), batch=1)
    assert scores == {"train/a#0": 0.9, "train/a#2": 0.9} and calls == [1, 1]


def _items():
    return [Item(k, Path("x.jpg"), (0.5, 0.5, 0.1, 0.1)) for k in ("low", "high", "mid")]


SCORES = {"low": 0.1, "high": 0.95, "mid": 0.6}


def test_review_orders_by_score_and_records_keys():
    review = Review(_items(), SCORES, {})
    assert [it.key for it in review.items] == ["high", "mid", "low"]
    review.apply("w")
    review.apply("a")  # mid suggestion = safety-boots (score >= 0.5)
    review.apply("s")
    assert review.done
    assert review.decisions == {"high": "safety-boots", "mid": "safety-boots", "low": "shoes"}


def test_back_allows_changing_a_decision():
    review = Review(_items(), SCORES, {})
    review.apply("w")
    review.apply("b")
    review.apply("x")
    assert review.decisions["high"] == "drop-image"


def test_unknown_keys_ignored_and_resume_skips_decided():
    review = Review(_items(), SCORES, {"high": "shoes"})
    assert review.items[review.index].key == "mid"
    review.apply("z")
    assert review.items[review.index].key == "mid" and len(review.decisions) == 1


def test_missing_scores_rejected():
    with pytest.raises(SystemExit, match="score"):
        Review(_items(), {"high": 0.9}, {})


def test_save_json_is_atomic(tmp_path):
    path = tmp_path / "labeling" / "review.json"
    save_json(path, {"a": "shoes"})
    assert json.loads(path.read_text()) == {"a": "shoes"} and not path.with_suffix(".tmp").exists()


def test_human_decisions_override_assistant():
    from tools.review_boots import merged_decisions

    merged = merged_decisions({"a": "shoes"}, {"a": "safety-boots", "b": "drop-image"})
    assert merged == {"a": "shoes", "b": "drop-image"}
