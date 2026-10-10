import json

import pytest
import yaml

from tools.train_footwear import build


def test_exclusions_and_source_groups_never_cross_splits(tmp_path):
    source, out = tmp_path / "source", tmp_path / "built"
    (source / "train/images").mkdir(parents=True)
    (source / "train/labels").mkdir()
    (source / "data.yaml").write_text(yaml.safe_dump({"names": ["boots", "flip_flops", "loafers", "sandals", "sneakers", "soccer"]}))
    decisions = {}

    def add(stem, labels, content=None):
        (source / "train/images" / (stem + ".jpg")).write_bytes(content or stem.encode())
        (source / "train/labels" / (stem + ".txt")).write_text(labels)

    for i in range(30):
        add(f"boot{i}.rf.a", "0 .5 .5 .2 .2\n")
        decisions[f"train/boot{i}.rf.a#0"] = "safety-boots"
        add(f"shoe{i}.rf.a", "4 .5 .5 .2 .2\n")
    add("boot0.rf.b", "0 .5 .5 .2 .2\n")
    decisions["train/boot0.rf.b#0"] = "shoes"  # grouping does not depend on class
    add("exact-copy", "4 .5 .5 .2 .2\n", b"shoe0.rf.a")
    add("unresolved", "4 .5 .5 .2 .2\n0 .5 .5 .2 .2\n")
    add("drop", "0 .5 .5 .2 .2\n")
    decisions["train/drop#0"] = "drop-image"
    result = build(source, out, decisions)
    assert result["excluded_images"] == 2 and sum(result["images"].values()) == 62
    rows = json.loads((out / "manifest.json").read_text())["images"]
    for field in ("family", "sha256", "group"):
        for value in {r[field] for r in rows}:
            assert len({r["split"] for r in rows if r[field] == value}) == 1
    assert all(result["instances"][s]["safety-boots"] > 0 for s in ("train", "val", "test"))
    with pytest.raises(FileExistsError):
        build(source, out, decisions)
