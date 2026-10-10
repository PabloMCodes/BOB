# Jetson Orin Nano handoff — BOB computer vision (`autoCV`)

For the team deploying `vision/` on the Jetson. Everything here was verified on the Mac stand-in
(Apple Silicon, MPS) unless marked **⚠️ not run on a Jetson yet** — those commands are the expected
path and must be confirmed on the device.

## 1. What you get

| Item | Where | Notes |
| --- | --- | --- |
| Python package `vision` | repo, branch `autoCV` | Python 3.10 only, no macOS imports, device from `vision.config.resolve_device()` (`cuda → mps → cpu`) |
| PPE model SH17 YOLOv8s | `models/sh17_yolov8s.pt` (auto-download, SHA-256 pinned in `configs/default.yaml`) | Non-commercial license (CC BY-NC-SA 4.0); see `models/sh17.md` |
| Footwear specialist (optional, experimental) | `models/footwear_yolov8n_v1.pt`, pinned in `configs/footwear.yaml` | Off by default; see `models/footwear-v1.md` |
| ONNX exports of both | `models/*.onnx` — **not in git**, hand over as files | SHA-256 pinned in `configs/onnx.yaml`; reproducible: `tools.export_onnx` re-creates the same bytes from the same `.pt` |
| Wire / event contract | `vision/schema/`, `schema/*.json`, `integration.md` C1–C6 | Unchanged by the move |

**Verified on the Mac (Step 8):** `.pt` vs `.onnx` (onnxruntime CPU) on 92 images incl. 90 live rover
frames — every box matched (max |Δconf| 1.7e-6, min IoU 0.999998), every PPE verdict identical, for
SH17 and for SH17 + footwear.

## 2. Install on the Jetson ⚠️ not run on a Jetson yet

1. JetPack 6.x (Ubuntu 22.04, Python 3.10 — the reason the repo is pinned to 3.10).
2. **torch / torchvision from NVIDIA's Jetson wheels for your JetPack version** (NVIDIA's "PyTorch for
   Jetson" install guide), **not PyPI** — PyPI aarch64 wheels have no CUDA. Install them first, into the
   environment you'll run from.
3. The remaining dependencies at the versions in `uv.lock` (`ultralytics 8.3.x`, `opencv-python`,
   `numpy`, `websockets`, `pydantic`, `pyyaml`). If you use `uv`, make sure it does **not** replace
   NVIDIA's torch with the PyPI one (e.g. a venv with `--system-site-packages` and torch excluded).
   Never let ultralytics auto-install packages: run with `YOLO_AUTOINSTALL=false`.
4. Copy `models/` from the Mac (or let the `.pt` auto-download) and check every file:
   `sha256sum models/*.pt models/*.onnx` must equal the pins in `configs/default.yaml`,
   `configs/footwear.yaml`, `configs/onnx.yaml`. The loader refuses mismatches anyway (rule 9).
5. `configs/local.yaml` (gitignored): `device: cuda`.

## 3. Build the TensorRT engine — on the Jetson only ⚠️ not run on a Jetson yet

Engines are specific to the GPU + TensorRT version, so they can't be built on the Mac. Recommended:
let ultralytics build it **from the SHA-verified `.pt`**, so the engine carries the class-name metadata
the pipeline needs (a bare `trtexec` engine has no class names):

```bash
YOLO_AUTOINSTALL=false yolo export model=models/sh17_yolov8s.pt format=engine \
    half=True dynamic=True batch=8 imgsz=640 device=0
```

- `dynamic=True` + `batch=8`: one engine serves pass 1 (640, batch 1) **and** the batched head / feet
  crops (320, up to `pipeline.crop.max_crops` = 8). Batching crops is on by default since Step 8.
- Pin it like every other model in a new `configs/engine.yaml`:

```yaml
model:
  weights: models/sh17_yolov8s.engine
  weights_url: null
  weights_sha256: <sha256sum of the engine>
```

The `.onnx` files are the verified intermediate: use them with `trtexec` or onnxruntime-gpu if the
ultralytics path fails, and as the reference when debugging a difference.

## 4. Acceptance on the Jetson (gate G6 + parity) ⚠️ not run on a Jetson yet

| # | Check | Command | Pass |
| --- | --- | --- | --- |
| J1 | Test suite with CUDA | `pytest` (device `cuda` from `configs/local.yaml`) | all pass (ONNX tests skip without onnxruntime — fine) |
| J2 | Portability gate | `grep -rn '"mps"' vision/ \| grep -v config.py` | prints nothing |
| J3 | Engine parity vs `.pt` | `python -m tools.parity config --b-config configs/engine.yaml <recordings.bobrec>` | `"passed": true` — boxes IoU ≥ 0.9, \|Δconf\| ≤ 0.02, **verdicts identical** (FP16 is expected to move conf by ~1e-3, not more) |
| J4 | Latency | `python -m vision.server --detect --no-view --config configs/engine.yaml` + `tools.replay_client <recording> --speed 1` | `summary.json` `process_p95_ms` ≤ **150** at 10 Hz (Mac: 85.6 ms with 2 people, 117.7 ms with 5–6) |
| J5 | Offline determinism | `python -m tools.replay_detect <recording>` twice | identical boxes |
| J6 | Destructive suite | `pytest tests/test_destructive.py` | all pass |

Ask the CV branch for recordings (`runs/server/<time>/stream.bobrec`, 0.1–1 GB) — they contain people
and private screens, so share them directly, never in git.

## 5. Run as a service ⚠️ not run on a Jetson yet

```ini
# /etc/systemd/system/bob-vision.service
[Unit]
Description=BOB vision server
After=network-online.target

[Service]
WorkingDirectory=/opt/bob
Environment=YOLO_AUTOINSTALL=false
ExecStart=/opt/bob/.venv/bin/python -m vision.server --detect --no-view --config configs/engine.yaml
KillSignal=SIGTERM
TimeoutStopSec=15
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

`vision.server` handles SIGTERM once and finishes `summary.json` / recordings even if signalled twice.
Outputs go to `runs/server/<time>/` (`stream_health.jsonl` = C3, `detections.jsonl` = C2).

## 6. Networking lessons from the Mac runs

- The phone connects to `ws://<jetson>:8765`. The server listens on **one** address family:
  default `0.0.0.0` (IPv4). On an **IPv6-only phone hotspot** start it with `--host ::` and point the app at
  `ws://<jetson-hostname>.local:8765` (Bonjour/mDNS) or `ws://[<IPv6>]:8765`.
- Venue Wi-Fi often isolates clients (the phone never connected on `10.15.75.x`): use a hotspot or a
  network you control.
- A vanished phone is reported `stale` within ~0.35 s; its connection is closed after ~6 s
  (2 s keepalive ping + 2 s timeout + 2 s close handshake).

## 7. Known risks

| Risk | Mitigation |
| --- | --- |
| FP16 engine shifts borderline detections (glasses conf 0.3–0.6 are already JPEG-sensitive) | J3 parity on real rover recordings, not just bundled images |
| Orin Nano slower than the Mac for the 5-pass head-crop pipeline | Batched crops (Step 8: −45 % on the Mac); measure J4 before tuning `max_crops` / model size |
| ultralytics / torch versions differ from the Mac | Keep ultralytics at 8.3.x; any upgrade re-runs J1–J6 |
| Licenses | Ultralytics AGPL-3.0, SH17 CC BY-NC-SA 4.0 (non-commercial), footwear data CC BY 4.0 |
| Pose is advisory (AGENTS rule 7) | Never feed `DetectionEvent` pose or boxes into motor / safety decisions |
