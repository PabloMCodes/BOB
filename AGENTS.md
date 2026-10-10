# AGENTS.md — BOB Computer Vision (`autoCV` branch)

Context and rules for any coding agent working in this repo. Read this fully before changing code.

## What this branch builds

YOLOv8 PPE detection with bounding boxes on frames streamed from an iPhone, with each detection tagged by the ARKit pose captured at the same instant. The **Mac (Python) is a stand-in for the Jetson Orin Nano**; everything in `vision/` will move to the Jetson unchanged except config.

Pipeline: `iPhone ARFrame → WebSocket (JSON header + JPEG) → Python server → YOLOv8 → pose association → OpenCV view + DetectionEvent JSONL`.

## Hard rules

1. **Python owns the logic; Swift stays thin.** The iOS app only captures `ARFrame`, encodes JPEG, attaches pose/tracking/timestamps, and sends. No detection, filtering, or decision logic in Swift.
2. **`vision/` must be Jetson-portable.** Python 3.10 syntax only. No macOS-only imports. Never hard-code `"mps"` — use `vision.config.resolve_device()`.
3. **The schema is a contract.** Once Step 1 freezes `FramePacket` / `DetectionEvent`, any change requires bumping `schema_version` and updating both Python and Swift in the same change.
4. **Associate by timestamp, never by "latest."** A detection gets the pose nearest to its source frame's `iphone_frame_ts_ns`, within `timing.pose_tolerance_ms`, same `session_id`, with `tracking_state == normal`. Otherwise it is emitted with `pose_valid=false` — never silently dropped, never given a guessed pose.
5. **A new `session_id` invalidates everything.** ARKit restart/interruption = new world origin; clear pose buffers.
6. **Latest frame wins.** Never queue frames behind slow inference; drop old frames so latency cannot accumulate.
7. **ARKit is advisory, not safety.** Do not write code that treats pose or detections as collision/obstacle safety. Motor control, safety supervisor, alerts are out of scope for this branch.
8. **No large artifacts in git.** Datasets → `data/`, weights → `models/`, outputs → `runs/` (all gitignored). Record dataset version + metrics in a model card under `models/*.md`.

## Commands

```bash
uv sync                     # install / update env (.venv, Python 3.10)
uv run pytest               # all tests — must pass before any step is marked done
uv run pytest tests/test_x.py -k name   # targeted test
uv add <pkg>                # add a dependency (updates uv.lock)
```

## Layout

| Path | Contents |
| ---- | -------- |
| `vision/` | Importable package: config, schema, detector, render, server, pose buffer, events |
| `tools/` | CLI scripts: train, record, replay client, ONNX export |
| `configs/default.yaml` | Device, model weights, server port, timing thresholds. Override in `configs/local.yaml` |
| `ios/` | Xcode project `BOBCapture` (Step 4+) |
| `tests/` | pytest. Network/phone-dependent tests use the replay client, never a live phone |

## Integration with other branches

Before merging to `main` or changing any interface (schema, config keys, model classes), follow [`integration.md`](integration.md): run its pre-merge gates G1–G8 and update its interface table and branch registry.

## Testing expectations

- Every step has a defined test method in `README.MD` → Progression. A step is done only when its tests pass and the README row is updated with measured results.
- Prefer deterministic tests: fixtures and recorded sessions replayed via `tools/replay_client.py` (Step 5+).
- iOS behavior is verified on a **physical iPhone** (ARKit doesn't run in the Simulator); record what was observed in the README.

## Known gotchas

- `ARFrame.capturedImage` is sensor-oriented (landscape). Handle rotation explicitly or boxes appear on a sideways image.
- `ARFrame.timestamp` is seconds since iPhone boot — unrelated to the Mac clock. Use it only for association; Mac receive time is only for latency metrics.
- iOS needs `NSCameraUsageDescription`, `NSLocalNetworkUsageDescription`, and ATS `NSAllowsLocalNetworking` for `ws://`.
- On the Jetson, torch comes from NVIDIA's JetPack wheels, not PyPI; TensorRT engines must be built on the Jetson.
- Ultralytics is AGPL-3.0.
