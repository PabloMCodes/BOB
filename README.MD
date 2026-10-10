# BOB — Computer Vision Branch (`autoCV`)

> [!NOTE]
> This branch builds the computer vision system for the BOB inspection rover: **YOLOv8 PPE detection with bounding boxes**, tagged with the **ARKit pose** of the iPhone at the moment each frame was captured. The Jetson is not connected yet — a **Mac running Python stands in for the Jetson**, and the same Python code moves to the Jetson later.

## Purpose

The rover patrols a short, controlled route and flags missing PPE (hard hat, vest). For this branch, the job is:

1. **See** — detect `person / hardhat / no-hardhat / vest / no-vest` with a fine-tuned YOLOv8n and draw bounding boxes.
2. **Locate** — attach each detection to the ARKit pose from the *same moment* the frame was captured (not the latest pose received), and mark it invalid when tracking is degraded or data is stale.

ARKit is treated as an **advisory** localization sensor, never a safety system. Motor control and the safety supervisor are **out of scope** for this branch.

```
iPhone (Xcode / Swift, thin)              Mac (Python → later Jetson)
ARSession → ARFrame                       WebSocket server
  ├─ image → JPEG 640px   ──WebSocket──►    ├─ latest-frame-wins slot
  ├─ camera.transform (pose)                ├─ YOLOv8 PPE → bounding boxes
  ├─ trackingState                          ├─ pose ↔ detection by timestamp
  └─ timestamp, seq_id, session_id          └─ OpenCV view + DetectionEvent JSONL
```

## Quick start

Requires Apple Silicon Mac, [uv](https://docs.astral.sh/uv/), Xcode (for the iOS app, Step 4+), and a physical iPhone (ARKit does not run in the Simulator).

```bash
uv sync            # creates .venv with Python 3.10 (matches Jetson JetPack 6)
uv run pytest      # runs the test suite
```

Per-machine settings: copy `configs/default.yaml` → `configs/local.yaml` (gitignored).

## Progression

| Step | Name | Status | Test method | Result |
| ---- | ---- | ------ | ----------- | ------ |
| 0 | Environment & repo skeleton | ✅ Done | `uv run pytest` smoke tests | 6/6 pass · Python 3.10.20 · torch 2.14.1 (MPS ✅) · ultralytics 8.3.253 |
| 1 | Message / event schema contract | ⏳ Next | pytest on valid/invalid JSON fixtures | — |
| 2 | Detector wrapper + bounding box render (offline) | ⬜ | Unit tests on sample images, visual check, MPS FPS | — |
| 3 | PPE dataset + YOLOv8n fine-tune | ⬜ | `yolo val` mAP50 / per-class AP + own photo set | — |
| 4 | iOS ARKit capture app (Xcode) | ⬜ | On-device debug overlay, cover-lens tracking test | — |
| 5 | WebSocket transport + record/replay | ⬜ | Replay client in pytest, live FPS/drops/latency, kill test | — |
| 6 | Live inference + bounding boxes | ⬜ | Replay determinism, live PPE on/off test, p50/p95 latency | — |
| 7 | Pose ↔ detection timestamp association | ⬜ | Synthetic timeline unit tests, live occlusion + ARKit reset | — |
| 8 | CV destructive tests + Jetson handoff prep | ⬜ | Scripted failure suite, `.pt` vs `.onnx` parity | — |

### Step 0 — Environment & repo skeleton ✅

- **Scope:** uv project pinned to Python 3.10 (Jetson parity), locked deps (`uv.lock`), folder layout, `.gitignore` for weights/data/runs, config with device auto-resolution (`cuda → mps → cpu`), `AGENTS.md` / `CLAUDE.md`.
- **Test:** `uv run pytest` — Python version, core imports, config load/validation, MPS availability, tensor op on resolved device.
- **Note:** deviated from plan's Python 3.11 → **3.10**, because JetPack 6 (Ubuntu 22.04) ships 3.10 and NVIDIA's Jetson torch wheels target it.

## Repository layout

```
BOB/
├── README.MD          # this file — branch purpose + progression log
├── AGENTS.md          # rules and context for coding agents
├── CLAUDE.md          # Claude Code entry point (imports AGENTS.md)
├── integration.md     # interfaces to other parts + pre-merge gates for main
├── pyproject.toml     # deps; exact versions locked in uv.lock
├── configs/           # default.yaml (+ local.yaml override, gitignored)
├── vision/            # Python package — must stay Jetson-portable
├── tools/             # training, record/replay, export scripts
├── ios/               # Xcode project (Step 4)
├── tests/             # pytest
└── data/ models/ runs/  # gitignored: datasets, weights, outputs
```

## Out of scope for this branch

Motor control, safety supervisor / P0–P4 state machine, evidence logging & alerting, obstacle detection, TensorRT engine build (must be done on the Jetson itself).
