# AGENTS.md — BOB Computer Vision (`autoCV` branch)

Context and rules for any coding agent working in this repo. Read this fully before changing code.

## What this branch builds

YOLOv8 PPE detection with bounding boxes on frames streamed from an iPhone, with each detection tagged by the ARKit pose captured at the same instant. The **Mac (Python) is a stand-in for the Jetson Orin Nano**; everything in `vision/` will move to the Jetson unchanged except config.

Pipeline: `iPhone ARFrame → WebSocket (JSON header + JPEG) → Python server → YOLOv8 → pose association → OpenCV view + DetectionEvent JSONL`.

## Hard rules

1. **Python owns the logic; Swift stays thin.** The iOS app only captures `ARFrame`, encodes JPEG, attaches pose/tracking/timestamps, and sends. No detection, filtering, or decision logic in Swift.
2. **`vision/` must be Jetson-portable.** Python 3.10 syntax only. No macOS-only imports. Never hard-code `"mps"` — use `vision.config.resolve_device()`.
3. **The schema is a contract (frozen at v2).** Any change to `vision/schema/` requires: bump `SCHEMA_VERSION` + `SchemaVersion` in `common.py`, update fixtures in `tests/fixtures/`, run `uv run python -m tools.export_schema`, and update the Swift mirror — all in the same change. Each invalid fixture must break exactly one rule.
4. **Associate by timestamp, never by "latest."** A detection gets the pose nearest to its source frame's `iphone_frame_ts_ns`, within `timing.pose_tolerance_ms`, same `session_id`, with `tracking_state == normal`. Otherwise it is emitted with `pose_valid=false` — never silently dropped, never given a guessed pose.
5. **A new `session_id` invalidates everything.** ARKit restart/interruption = new world origin; clear pose buffers.
6. **Latest frame wins.** Never queue frames behind slow inference; drop old frames so latency cannot accumulate.
7. **ARKit is advisory, not safety.** Do not write code that treats pose or detections as collision/obstacle safety. Motor control, safety supervisor, alerts are out of scope for this branch.
8. **No large artifacts in git.** Datasets → `data/`, weights → `models/`, outputs → `runs/` (all gitignored). Record dataset version + metrics in a model card under `models/*.md`.
9. **Third-party weights are code.** `.pt` files are pickles. Only load weights with a pinned `weights_sha256` in config (verified by `ensure_weights`).
10. **"No violation" ≠ "compliant".** PPE rules emit derived boxes (`source="derived"`) only for confident, large-enough subjects; everything else is UNVERIFIED. Never turn an unverified subject into a pass or a violation.

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
| `vision/detector.py`, `render.py`, `orientation.py`, `detect.py` | YOLO wrapper → `schema.Box`, safety-color drawing, sensor→upright rotation, webcam CLI |
| `vision/pipeline.py` | **Single entry point** for frames: `single` or `head_crop` (people → full-res head crops) → PPE rules. Webcam, eval and server must all go through it |
| `vision/ppe.py` | Rules → derived violation boxes + per-subject verdicts. `kind: pair` (face↔glasses, head↔helmet, hands↔gloves, person↔safety-vest) and `kind: class` (safety-boots vs shoes). Rules whose classes the model lacks are inactive (`split_active`) |
| `tools/prelabel.py` | Draft YOLO labels (SH17 + YOLO-World) in `training.classes` for hand correction. Needs `uv run --group labeling` for YOLO-World |
| `tools/review_boots.py` | CLIP-sorted hand review of Roboflow `boots` boxes → `data/labeling/boots_review.json` (`score` needs the labeling group; `review` is an OpenCV window) |
| `tools/build_dataset.py` | External dataset + review decisions + filtered SH17 pseudo-labels → `data/datasets/<name>/` YOLO training set |
| `data/external/` | Downloaded third-party datasets (gitignored). Roboflow downloads run in a throwaway env: `uv run --no-project --with roboflow …` |
| `models/sh17.md` | Model card: source, SHA-256, license, classes, measurements |
| `vision/schema/` | Wire contract: `common` (enums/types), `pose`, `phone` (C1), `events` (C2/C3), `wire` (codec). Import from `vision.schema` |
| `schema/` | Generated JSON Schema — never hand-edit; regenerate with `uv run python -m tools.export_schema` |
| `tests/fixtures/` | `valid/` and `invalid/` message JSON, shared with Swift tests and consumer branches |
| `tools/` | CLI scripts: train, record, replay client, ONNX export |
| `configs/default.yaml` | Device, model weights, server port, timing thresholds. Override in `configs/local.yaml` |
| `ios/project.yml` | XcodeGen spec — **edit this, never the generated `.xcodeproj`**. `cd ios && xcodegen generate` |
| `ios/BOBCapture/Wire/` | Swift wire contract (Foundation + simd only): `Schema.swift` mirrors `vision/schema` C1, `WireCodec.swift`, `Recorder.swift`, `SendGate.swift` + `StreamSender.swift` (WebSocket, 1 frame in flight, reconnect). Unit-tested on the Simulator against `tests/fixtures/` |
| `ios/BOBCapture/Capture/`, `App/` | ARKit/UIKit → wire types, JPEG encoder, throttled capture controller; SwiftUI debug overlay. No decisions |
| `vision/server/` | Step 5 stream server: `slot` (latest-frame-wins), `monitor` (per-session gaps/drops/added latency → StreamHealth), `transport` (websockets `FrameServer` + `ServerThread`), `view`, `__main__` (`python -m vision.server`). Step 6 plugs the pipeline in as the consumer of `server.slot` |
| `vision/server/detection.py` | Step 6 frame path `detect_frame()` (decode upright → pipeline → C2 + per-rule verdicts) and `detection_event()` (frame-bundled pose). Shared by `server --detect` and `tools/replay_detect.py` — don't fork it |
| `tools/replay_detect.py` | Offline replay: every frame of a `.bobrec` → detections + on/off segment scoring; determinism check `box_mismatches` |
| `vision/association.py` | Step 7: `associate()` validity rules (`session_mismatch` > `stale` > `tracking_not_normal` > `no_pose`) + thread-safe `Associator` (newest session, iPhone-clock gaps). Fed only through `FrameServer.admit()` |
| `tools/pose_timeline.py` | Model-free Step 7 check of a recording: sessions + invalid-pose stretches with ARKit reasons |
| `tools/export_onnx.py`, `tools/parity.py`, `configs/onnx.yaml` | Step 8: reproducible ONNX export (pins in `configs/onnx.yaml`, needs `uv run --group export`); parity of two pipeline variants (`batch` / `onnx` / `config --b-config`) = boxes + identical verdicts |
| `tests/test_destructive.py`, `docs/jetson-handoff.md` | Failure suite (invariants I1–I6) and the Jetson team's install / engine build / acceptance J1–J6 |
| `tools/replay_client.py` | `.bobrec` → server at original timing (`--speed`), fresh session per `--loops` pass. Use it (never a live phone) in tests |
| `vision/recording.py`, `tools/inspect_recording.py` | `.bobrec` read/write (Step 5 replay reuses it); on-device recording acceptance report |
| `tests/` | pytest. Network/phone-dependent tests use the replay client, never a live phone |

## Integration with other branches

Before merging to `main` or changing any interface (schema, config keys, model classes), follow [`integration.md`](integration.md): run its pre-merge gates G1–G8 and update its interface table and branch registry.

## Testing expectations

- Every step has a defined test method in `README-CV.md` → Progression. A step is done only when its tests pass and the progression row is updated with measured results. `README.MD` is the overall project overview.
- Prefer deterministic tests: fixtures and recorded sessions replayed via `tools/replay_client.py` (Step 5+).
- iOS behavior is verified on a **physical iPhone** (ARKit doesn't run in the Simulator); record what was observed in the README.

## Known gotchas

- `ARFrame.capturedImage` is sensor-oriented (landscape). Handle rotation explicitly or boxes appear on a sideways image.
- `ARFrame.timestamp` is seconds since iPhone boot — unrelated to the Mac clock. Use it only for association; Mac receive time is only for latency metrics.
- iOS needs `NSCameraUsageDescription`, `NSLocalNetworkUsageDescription`, and ATS `NSAllowsLocalNetworking` for `ws://`.
- On the Jetson, torch comes from NVIDIA's JetPack wheels, not PyPI; TensorRT engines must be built on the Jetson.
- Ultralytics is AGPL-3.0. SH17 data/weights are CC BY-NC-SA 4.0 (non-commercial).
- SH17 `glasses` = any eyewear (sunglasses count as compliant). Its class IDs differ from its README order — always use names from the weights.
- The rover camera sits ~20 cm high looking **up** at faces 3 m+ away: glasses are ~5–6 px at 640. Don't "simplify" `head_crop` back to a single pass without re-running `tools/eval_ppe.py`.
- `head_crop` cost grows ~8–10 ms per person (sequential crops on MPS). Batch crops before porting to the Jetson.
- Never approximate a missing class with a look-alike (e.g. SH17 `shoes` for "not safety boots"): leave the rule inactive.
- `data/eval/` is test data only — never pre-label, label or train on it.
- Any new path that consumes phone messages (live, replay, tools) must go through `FrameServer.admit()` — never re-implement session / gap / drop logic, or live and offline pose validity will drift.
- Any model / backend change (ONNX, TensorRT, batching, new weights) must pass `tools/parity.py` on real recordings: verdicts identical, not just mAP. Batching crops (`pipeline.crop.batch`) is the default — a detector only *needs* `__call__`; `detect_batch` is an optional speed-up.
- On the Mac, ONNX must run on CPU (onnxruntime's CoreML provider crashes on the dynamic crop batch). Exports are reproducible only because `export_onnx` overwrites ultralytics' `date` metadata — don't export by hand.
- Latency across devices is **relative** (`added = offset − min offset` per session): the iPhone clock is unrelated to the Mac's. Don't subtract `iphone_frame_ts_ns` from a Mac timestamp and call it network delay.
- `vision.server` handles SIGTERM/SIGINT once and ignores repeats (`uv run` forwards signals) so `summary.json` and `stream.bobrec` are always complete.
- Never `uv add roboflow`: it pulls `opencv-python-headless`, which clashes with our `opencv-python` (both provide `cv2`).
- Secrets (`ROBOFLOW_API_KEY`) live only in `.env` (gitignored; template `.env.example`). Never print them or write them to files/config.
- SH17 pseudo-labels on out-of-domain photos are unreliable (sandals → "person"). Use `build_dataset.filter_pseudo`; never pseudo-label PPE classes on external data.
- Roboflow footwear data is CC BY 4.0 — credit it in the model card of any model trained on it.
- Boots labels: human decisions (`boots_review.json`) always override assistant ones (`boots_review_assisted.json`); use `merged_decisions`, never edit the human file.
- Swift: only `Wire/` may be compiled into the test target (no ARKit/UIKit there). Map unknown future Apple enum cases to the *conservative* wire value (e.g. tracking `not_available`), never a guess.
- `xcodebuild -destination 'name=…'` can fail to match the Simulator; use `id=<UDID>` from `xcrun simctl list devices available`.
- Signing lives in the gitignored `ios/Signing.local.xcconfig` (`DEVELOPMENT_TEAM`, `BOB_BUNDLE_PREFIX`) — never commit team IDs into `project.yml`.
- CLIP (for YOLO-World) lives in the optional `labeling` dependency group; ultralytics would otherwise auto-install it outside `uv.lock`. Run with `YOLO_AUTOINSTALL=false` when experimenting.

## Team Git workflow

This hackathon moves quickly with multiple teammates. Keep changes small and synchronize frequently to minimize merge conflicts.

- **Before implementing every new feature:** check the current branch and working tree, preserve any existing work, then run `git pull --ff-only` from the branch's upstream before editing. Work on `autoCV` unless instructed otherwise. If local changes or divergent history prevent the pull, reconcile them without discarding teammates' work or rewriting published history before proceeding.
- **After completing every new feature:** run the required tests and review the diff. Commit or push only when the user asks.
- When asked to push and it is rejected because teammates pushed first, fetch and integrate their changes, resolve conflicts, rerun the relevant tests, and retry. Never force-push. Report authentication or other blockers rather than claiming synchronization succeeded.
- Merges into `main` still follow `integration.md` and use a PR; do not push directly to `main`.
