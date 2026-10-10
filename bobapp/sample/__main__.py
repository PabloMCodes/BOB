"""Build (or rebuild) the SAMPLE edge store.

    uv run python -m bobapp.sample [--edge-config configs/sample-edge.yaml]

Rebuilding wipes the old sample store, so the hub sees a new store epoch and archives its old copy.
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from bobapp.edge.config import load_edge_config, store_path
from bobapp.edge.store import EdgeStore
from vision.config import REPO_ROOT

from .builder import build


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--edge-config", type=Path, default=REPO_ROOT / "configs" / "sample-edge.yaml")
    args = parser.parse_args()
    config = load_edge_config(args.edge_config)
    if config["edge_id"] != "sample-edge":
        raise SystemExit("refusing to write SAMPLE data into a store whose edge_id is not sample-edge")
    path = store_path(config)
    shutil.rmtree(path, ignore_errors=True)
    print(json.dumps({"store": str(path), **build(EdgeStore(path, config["edge_id"]))}, indent=2))


if __name__ == "__main__":
    main()
