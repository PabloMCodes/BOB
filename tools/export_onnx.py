"""Step 8: export the PPE models to ONNX for the Jetson (TensorRT engines are built ON the Jetson).

    YOLO_AUTOINSTALL=false uv run --group export python -m tools.export_onnx

Exports the SHA-verified SH17 model (configs/default.yaml `model`) and the footwear specialist
(configs/footwear.yaml) with dynamic batch / height / width — one file serves pass 1 at 640, the batched
320 head and feet crops. Writes models/<stem>.onnx (gitignored) and pins every SHA-256 in
configs/onnx.yaml (tracked): the loader refuses an .onnx that doesn't match (AGENTS rule 9).

Use the ONNX models: `--config configs/onnx.yaml` (SH17) or merge it after configs/footwear.yaml (see
tools/parity.py). Verify with `uv run --group export python -m tools.parity onnx`.
"""

from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path
from typing import Any

import yaml

from vision.config import REPO_ROOT, _deep_merge, load_config
from vision.detector import _sha256, ensure_weights

ONNX_CONFIG = REPO_ROOT / "configs" / "onnx.yaml"
FOOTWEAR_CONFIG = REPO_ROOT / "configs" / "footwear.yaml"
OPSET = 17  # TensorRT 8.6 / 10 (JetPack 6) parse opset 17


def export(weights: str, sha256: str, url: str | None = None) -> tuple[Path, str]:
    """Verified .pt -> models/<stem>.onnx. Returns (path, sha256)."""
    os.environ.setdefault("YOLO_AUTOINSTALL", "false")  # never pip-install outside uv.lock
    from ultralytics import YOLO

    pt = ensure_weights(weights, url, sha256)
    exported = Path(YOLO(str(pt)).export(format="onnx", dynamic=True, simplify=False, opset=OPSET,
                                         imgsz=640, device="cpu", verbose=False))
    target = pt.with_suffix(".onnx")
    if exported.resolve() != target.resolve():
        shutil.move(str(exported), target)
    _make_reproducible(target, sha256)
    return target, _sha256(target)


def _make_reproducible(path: Path, source_sha256: str) -> None:
    """Ultralytics stamps the export time into the `date` metadata — the only byte that differs between
    two exports of the same .pt (graph identical, checked in Step 8). Replace it so the SHA pin is stable."""
    import onnx

    model = onnx.load(str(path))
    for prop in model.metadata_props:
        if prop.key == "date":
            prop.value = f"source-sha256:{source_sha256}"
    onnx.save(model, str(path))


def onnx_config(config: dict[str, Any]) -> dict[str, Any]:
    """`config` with every model it uses swapped for its pinned ONNX export (configs/onnx.yaml)."""
    if not ONNX_CONFIG.exists():
        raise FileNotFoundError(f"{ONNX_CONFIG} missing — run tools.export_onnx first")
    override = yaml.safe_load(ONNX_CONFIG.read_text())
    if not config.get("footwear_model", {}).get("enabled", False):
        override.pop("footwear_model", None)  # never switch the specialist on as a side effect
    merged = _deep_merge(config, override)
    # On a Mac, ultralytics would hand ONNX to onnxruntime's CoreML provider, which fails on the dynamic
    # batch of crops (Step 8). Parity is defined on onnxruntime CPU; on the Jetson, cuda -> CUDA provider.
    from vision.config import resolve_device
    if resolve_device(merged["device"]) not in ("cuda", "cpu"):
        merged["device"] = "cpu"
    return merged


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--no-footwear", action="store_true", help="export SH17 only")
    args = parser.parse_args()

    config = load_config(None)
    model = config["model"]
    sh17, sh17_sha = export(model["weights"], model["weights_sha256"], model.get("weights_url"))
    pins: dict[str, Any] = {"model": {"weights": str(sh17.relative_to(REPO_ROOT)), "weights_url": None,
                                      "weights_sha256": sh17_sha}}
    print(f"{sh17.relative_to(REPO_ROOT)}  sha256 {sh17_sha}")
    if not args.no_footwear:
        foot = load_config(FOOTWEAR_CONFIG)["footwear_model"]
        path, sha = export(foot["weights"], foot["weights_sha256"])
        pins["footwear_model"] = {"weights": str(path.relative_to(REPO_ROOT)), "weights_sha256": sha}
        print(f"{path.relative_to(REPO_ROOT)}  sha256 {sha}")
    header = ("# ONNX exports of the PPE models (Step 8), written by tools/export_onnx.py — do not hand-edit.\n"
              f"# Dynamic batch/height/width, opset {OPSET}. The .onnx files are not in git (models/ is ignored):\n"
              "# hand them to the Jetson team as files; the loader refuses any whose SHA-256 differs.\n")
    ONNX_CONFIG.write_text(header + yaml.safe_dump(pins, sort_keys=False))
    print(f"pins -> {ONNX_CONFIG.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
