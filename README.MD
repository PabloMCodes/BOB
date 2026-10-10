# BOB — Computer Vision Branch (`autoCV`)

> [!NOTE]
> This branch builds the computer vision system for the BOB inspection rover: **YOLOv8 PPE detection with bounding boxes**, tagged with the **ARKit pose** of the iPhone at the moment each frame was captured. The Jetson is not connected yet — a **Mac running Python stands in for the Jetson**, and the same Python code moves to the Jetson later.

## Purpose

The rover patrols a short, controlled route and flags missing PPE — **safety glasses (critical)** and helmets. For this branch, the job is:

1. **See** — detect people, faces, heads, glasses and helmets with SH17 YOLOv8, and draw a box **on the eye area**: green when glasses are worn, red `no-safety-glasses` when they're not (same for helmets on the head).
2. **Locate** — attach each detection to the ARKit pose from the *same moment* the frame was captured (not the latest pose received), and mark it invalid when tracking is degraded or data is stale.

ARKit is treated as an **advisory** localization sensor, never a safety system. Motor control and the safety supervisor are **out of scope** for this branch.

```
iPhone (Xcode / Swift, thin)              Mac (Python → later Jetson)
ARSession → ARFrame                       WebSocket server
  ├─ image → JPEG (res TBD) ──WebSocket──►  ├─ latest-frame-wins slot
  ├─ camera.transform (pose)                ├─ YOLOv8 people → head crops → face/glasses/helmet
  ├─ trackingState                          ├─ PPE rules → derived violation boxes
  │                                         ├─ pose ↔ detection by timestamp
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
| 1 | Message / event schema contract | ✅ Done | pytest on valid/invalid JSON fixtures + wire codec + JSON Schema drift | 74/74 pass · 7 valid / 28 invalid fixtures · 4 message types |
| 2 | Detector wrapper + bounding box render + rotation | ✅ Done (webcam run pending) | Real-model tests on bundled images, render/rotation unit tests, MPS vs CPU benchmark, visual check | 110/110 pass · yolov8n @640: **MPS p50 9.1 ms / p95 11.8 ms (~109 FPS)** · CPU p50 20.9 ms |
| 3 | PPE model + safety-glasses/helmet rules | 🟡 Built — **own-photo eval pending** | Rule unit tests, real-model regressions on bundled images, `tools/eval_ppe.py` on own photos at 3 m+ (recall ≥ 0.9, precision ≥ 0.8) | 157/157 pass · head_crop fixes missed sunglasses that single-pass @640 misses · yolov8s head_crop **53 ms** (5 passes) on 1440×1920 |
| 3a | Hi-vis vest rule | 🟡 Built — **own-photo eval pending** | Rule unit tests, real-model regression on bundled images, `tools/eval_ppe.py --rule vest` | 204/204 pass · `bus.jpg` 4/4 and `zidane.jpg` 2/2 people → `not_wearing` (no vests in either) · positive case unmeasured |
| 3b | Gloves + safety boots + one fine-tune (glasses/gloves/boots) | 🟡 Rules, pre-labeller, foot crop, boots review + dataset builder built — **boots review + own photos pending** | Rule/prelabel unit tests; eval on own photos after fine-tune | 190/190 pass · glasses baseline **4/11** (SH17) · YOLO-World 8/11 · Roboflow footwear: 2,758 imgs, 2,562 boots CLIP-scored |
| 4 | iOS ARKit capture app (Xcode) | 🟡 Built + Simulator-tested — **on-device checklist pending** | Swift unit tests vs shared fixtures, Swift→Python golden recording, on-device recording + `tools/inspect_recording.py` | Swift 11/11 · Python 196/196 · unsigned device build ✅ · golden recording decodes (yaw +90° ✓) |
| 5 | WebSocket transport + record/replay | ⬜ | Replay client in pytest, live FPS/drops/latency, kill test | — |
| 6 | Live inference + bounding boxes | ⬜ | Replay determinism, live PPE on/off test, p50/p95 latency | — |
| 7 | Pose ↔ detection timestamp association | ⬜ | Synthetic timeline unit tests, live occlusion + ARKit reset | — |
| 8 | CV destructive tests + Jetson handoff prep | ⬜ | Scripted failure suite, `.pt` vs `.onnx` parity | — |
| 3c | Scene hazards — *inspection findings only* (backlog, after Step 7) | ⬜ | To define: restricted floor zones, open edges / stairs, blocked walkways / debris | — |

### Step 0 — Environment & repo skeleton ✅

- **Scope:** uv project pinned to Python 3.10 (Jetson parity), locked deps (`uv.lock`), folder layout, `.gitignore` for weights/data/runs, config with device auto-resolution (`cuda → mps → cpu`), `AGENTS.md` / `CLAUDE.md`.
- **Test:** `uv run pytest` — Python version, core imports, config load/validation, MPS availability, tensor op on resolved device.
- **Note:** deviated from plan's Python 3.11 → **3.10**, because JetPack 6 (Ubuntu 22.04) ships 3.10 and NVIDIA's Jetson torch wheels target it.

### Step 1 — Message / event schema contract ✅

- **Scope:** `vision/schema/` package — `common.py` (enums, strict types), `pose.py` (yaw/xyz from ARKit 4×4), `phone.py` (C1: `frame`, `pose`), `events.py` (C2/C3: `detection_event`, `stream_health`), `wire.py` (length-prefixed JSON + JPEG codec). Language-neutral JSON Schema exported to `schema/`.
- **Stack:** pydantic v2 (strict ints, `extra="forbid"`, frozen), stdlib `json` / `struct` / `uuid`, numpy, JSON Schema, pytest fixtures shared with Swift (Step 4).
- **Decisions:** phone sends raw column-major 4×4 only (Python derives pose) · separate image-less `pose` message · unknown fields rejected · `detection_event` carries boxes only (hazard logic belongs to alerts/safety).
- **Test:** `uv run pytest` — every valid fixture parses; every invalid fixture fails with **exactly one** error for its intended reason; wire round-trips; framing/payload errors; pose math (identity, ±90°, 180°, sideways mount roll, straight-down); committed `schema/*.json` must match code.
- **Regenerate after any schema change:** `uv run python -m tools.export_schema`

### Step 2 — Detector wrapper, bounding box render, rotation ✅

- **Scope:**
  - `vision/detector.py` — `Detector(weights, device, imgsz, conf)`: upright BGR → `Detections(boxes: list[schema.Box], image_size, inference_ms)`. Weights-agnostic (Step 3 PPE weights swap in via `model.weights`), boxes clipped and validated by the Step 1 schema, warm-up excluded from timing. Weights auto-download to `models/` (gitignored).
  - `vision/render.py` — safety-semantic colors from `render.categories` in config: **violation red · compliant green · person blue · other grey**. Class names normalized (`NO_Hardhat` = `no-hardhat`). Never mutates the input frame.
  - `vision/orientation.py` — `device_orientation` → upright via `cv2.rotate`; flat/unknown orientations fall back to `camera.mount_orientation`.
  - `vision/detect.py` — live Mac webcam view: `uv run python -m vision.detect` (q quit · s snapshot → `runs/detect/`).
  - `tools/benchmark_detector.py` — p50/p95 latency per available device.
- **Test:** `uv run pytest` — ≥3 people on `bus.jpg`, ≥2 on `zidane.jpg`, blank image → 0 boxes, boxes in bounds (incl. portrait input), non-BGR input rejected, detector output builds a valid `DetectionEvent`; render colors/immutability/label placement; rotation mapping via marker pixel for all 4 orientations + fallback. Visual check of annotated `bus.jpg` ✅. Benchmark: `uv run python -m tools.benchmark_detector`.
- **Pending (needs you):** run `uv run python -m vision.detect` once — macOS will ask for camera permission for VS Code/terminal.
- **Fix — black webcam window:** macOS listed two cameras (MacBook Air Camera + iPhone via Continuity Camera). The idle iPhone feed sat at index 0 sending all-zero frames, and index order changes as the iPhone connects. `vision.detect` now auto-selects the first camera with a non-black image (tolerating ~15 warm-up frames); `--camera N` forces one and fails with a clear message if it's black. Covered by `tests/test_detect_camera.py` (fake captures, no hardware).
- **Findings:** first inference at a *new* input resolution on MPS costs ~70 ms (kernel compile); steady state 9 ms. Live stream has one fixed resolution, so only the first frame pays. Rotation mapping follows Apple's documented sensor orientation — **must be verified on the iPhone in Step 4**.

### Step 3 — PPE model + safety-glasses / helmet rules 🟡 (own-photo eval pending)

- **Model:** pretrained [SH17](https://github.com/ahmadmughees/SH17dataset) YOLOv8 (17 classes incl. `person, face, head, glasses, helmet`). Default `sh17_yolov8s`; n kept for comparison. Auto-downloaded and **SHA-256 verified** (weights are pickles). Details, license (CC BY-NC-SA 4.0, non-commercial) and measurements: [`models/sh17.md`](models/sh17.md). No training was needed so far.
- **Why rules, not a "no-glasses" class:** no dataset reliably labels absence. `vision/ppe.py` pairs subjects with PPE by geometry:
  - **glasses** — face (≥ 24 px, conf ≥ 0.5) with a glasses box centred in its eye band (10–60 % of face height) → **wearing** (green model box on the eyes); otherwise a red **`no-safety-glasses`** box on the eye band.
  - **helmet** — head with a helmet centred in the band from 40 % above to 60 % down the head → wearing; otherwise red **`no-helmet`** on the top of the head.
  - Too small / uncertain → **unverified, no box** ("no violation seen" ≠ "compliant"). Per-frame only; N-frame confirmation belongs to the alerts branch.
- **Schema v2:** `Box.source = model | derived`; `cls_id` is null for derived boxes. Fixtures migrated, 4 new invalid fixtures, JSON Schema regenerated.
- **Two-pass `head_crop` pipeline** (`vision/pipeline.py`, default): pass 1 finds people at 640; pass 2 runs on a square crop of each head region from the **full-resolution** frame at imgsz 320. Required by the mount geometry below.
- **Mount geometry (decided):** iPhone **portrait, tilted up ~15°, ~20 cm off the floor**, inspecting at **3 m+**. Camera looks up ~25° at faces; estimated at 640 px a face is ~22–27 px and glasses ~5–6 px — too small for one pass.
- **Measured on bundled images:** single pass @640 **missed both men's sunglasses on `bus.jpg` → 2 false violations**; head_crop found them (0.70 / 0.67) → wearing ✅. Upscaling crops to 640 made it worse → crop imgsz 320. `zidane.jpg` → both not wearing glasses / helmet ✅, red boxes on the eye bands (visual check ✅).
- **Latency (Mac MPS, 1440×1920 frame):** yolov8n single 9.0 ms · head_crop 31.8 ms (4 passes) — yolov8s single 10.9 ms · head_crop **53.0 ms** (5 passes). Cost grows ~8–10 ms per person.
- **Test:** `uv run pytest` — rule geometry (eye band, outside band, mostly-outside-face, too small, low conf, head-without-face, one glasses box can't serve two faces, two people, helmet above head, name normalization, invalid region), pipeline (crop geometry, NMS, head_crop beats single on `bus.jpg`, expected verdicts, violation box on face, boxes in image), eval tool end-to-end, tampered-weights rejection.
- **Eval tool:** `uv run python -m tools.eval_ppe --rule glasses --save-images` → `runs/eval_ppe/<rule>_<time>/report.md` comparing `single@640/960/1280` vs `head_crop@1280/1920` for n and s, per distance.
- **Webcam:** `uv run python -m vision.detect --show-crops` now runs the full PPE pipeline.
- **Fix — first real photos (11, floor-level, clear safety glasses):** every photo came out `not_wearing`, including ones with obvious clear safety glasses. Two bugs:
  1. head_crop **replaced** pass-1 boxes with pass-2 results. Clear safety glasses on faces of ~130–260 px were found by pass 1 (yolov8s 0.52–0.68) but not by the 320 crop, so good detections were thrown away. → Now **merged** and deduplicated (per-class NMS + containment).
  2. Crops were "top 35 % of the person box", which cut a close-up face in half → two faces for one person. → Crops are now centred on the pass-1 **head box** (2× its size), with the old heuristic only as fallback.
  - After the fix, 4 of the photos are judged wearing (glasses 0.41–0.68); bundled-image regressions unchanged. Accuracy is **not yet measured** — the photos still need ground-truth labels (folders).
  - Finding: SH17 is **much less confident on clear safety glasses** (0.4–0.7, some missed entirely) than on dark sunglasses. If the eval misses the target, fine-tuning on our own clear-safety-glasses photos is the next lever.

#### 📸 Capture protocol for the own-photo eval (needs the team)

1. iPhone **Settings → Camera → Formats → Most Compatible** (JPEG; HEIC is rejected).
2. Phone in the rover mount position: **portrait, ~20 cm off the floor, tilted up ~15°**. Use the main (1×) camera.
3. Horizontal floor distances **3 m, 3.5 m, 4 m** (+ 2 m as a reference). One person per photo, facing the camera ± ~30°.
4. Per distance: **≥ 8 photos wearing safety glasses** and **≥ 8 without**. Add a few with **regular glasses / sunglasses** into `wearing/` (they'll count as compliant — this measures that known limitation). Vary people, lighting, with/without helmet.
5. Save as `data/eval/glasses/{wearing,not_wearing}/{3m,3.5m,4m,2m}/*.jpg` and run the eval tool. For helmets: same under `data/eval/helmet/`.
6. Camera-app photos are sharper than ARKit frames (no HDR/Deep Fusion in ARKit), so results are an upper bound; re-check with recorded ARKit frames in Step 5.

**Done when:** the eval report shows a setting with recall ≥ 0.9 and precision ≥ 0.8 at 3 m — that sets the model (n/s), mode, and the resolution the phone must send in Step 4.

### Step 3a — Hi-vis vest rule 🟡 (own-photo eval pending)

- **Rule `vest`** (pair: `person` ↔ SH17 `safety-vest`): the vest box centre must lie in the person's **torso band** (15–65 % of the person height) and sit ≥ 60 % inside the person box → wearing. Otherwise a red **`no-safety-vest`** box is drawn on the torso band. People under 96 px tall or below conf 0.5 are unverified, with no box. One vest box can't make two people compliant.
- **Limits:** only SH17's `safety-vest` counts, so hi-vis **jackets / coveralls may read as `no-safety-vest`**. "Low visibility" here means *no hi-vis vest*, not a dark scene. SH17's vest accuracy from the low rover camera is **unmeasured**. The 9-class fine-tune has no `safety-vest`, so the rule **switches off** with that model; it is never approximated.
- **Test:** `uv run pytest` — vest on torso, no vest → torso box, vest at the feet doesn't count, one vest per person, small/uncertain person unverified, active with SH17 / inactive with the fine-tune classes. Real model: `bus.jpg` 4/4 and `zidane.jpg` 2/2 people `not_wearing`, never `wearing`.
- **Pending (needs the team):** photos in `data/eval/vest/{wearing,not_wearing}/<distance>/` (same capture protocol as Step 3, incl. a few hi-vis jackets in `not_wearing/` to measure that limitation) → `uv run python -m tools.eval_ppe --rule vest`.

### Step 3c — Scene hazards (backlog, after Step 7)

Restricted floor zones, open edges / stairs, blocked walkways / debris. These are **not** person + PPE pairs: they need floor segmentation or geometry, plus the world position from Step 7's pose association. They also need a schema v3 change (findings that aren't tied to a person). They are **inspection findings for humans only**. The rover must never rely on them to avoid an edge or an obstacle; that is the safety supervisor's job, with its own sensors (AGENTS rule 7). Use Step 5 recording to collect footage of these scenes in the meantime.

### Step 3b — Gloves, safety boots, and one fine-tune for all 🟡 (data collection pending)

- **Eval on the first 11 labelled photos (all wearing clear safety glasses):** best setting (yolov8s `single@640` / `head_crop@1280|1920`) judged **4/11 wearing → 7 false `no-safety-glasses`**. Every model/setting fails. SH17 is unreliable on **clear** safety glasses seen from below. No `not_wearing/` photos yet, so recall is unmeasurable.
- **Alternatives checked:** zero-shot **YOLO-World** (already in ultralytics) found eyewear in **8/11** (conf 0.26–0.72) and nothing on `zidane.jpg`, but called socks "sneakers" (0.63) and saw "gloves" on `bus.jpg` where there are none → good **pre-labeller**, not a runtime footwear check. Roboflow has boots datasets (e.g. `safety_violation`: `safety_boots / no_safety_boots`, listed public domain — unverified, page blocks bots).
- **Decisions:** gloves = **one verdict per visible hand**; boots = **safety-boots vs other shoes**; **one fine-tune** for clear glasses + gloves + boots, using **our photos + a Roboflow boots dataset**; labels **pre-drafted by SH17 + YOLO-World, corrected by hand locally**.
- **Built now:**
  - `gloves` rule (pair: hands ↔ gloves → red `no-gloves` on the bare hand). Active with SH17 today.
  - `boots` rule (new **kind: class** — `safety-boots` = wearing, `shoes` = `no-safety-boots`). **Automatically inactive** while the model lacks a `safety-boots` class: SH17 `shoes` = any footwear and is never used as a stand-in.
  - `tools/prelabel.py` — drafts YOLO-format boxes (`images/`, `labels/`, `classes.txt`) in the 9 training classes `person, head, face, glasses, helmet, hands, gloves, shoes, safety-boots`. YOLO-World needs CLIP, added as an optional **`labeling`** dependency group (never installed on the rover): `uv run --group labeling python -m tools.prelabel data/raw/<batch>`. Weights SHA-256 pinned. Verified by drawing the label files back onto the photos (drafts include expected errors, e.g. `shoes` on bare feet — hence human review).
  - Eval tool: per-image verdict is now "any judged subject not wearing → violation" (one bare hand of two counts); no duplicate `all/ALL` rows; refuses to evaluate an inactive rule.
- **Test:** `uv run pytest` 174 pass (+2 with `--group labeling`): gloves per hand, larger glove box, boots class rule, tiny footwear unverified, boots inactive with SH17 / active with training classes, unknown rule kind, eval single-row + inactive-rule refusal, prelabel YOLO file validity with and without YOLO-World.

#### 📸 Photo plan for the fine-tune (needs the team)

Same mount as before (portrait, ~20 cm, tilted up ~15°), distances 2–4 m. Aim for **~150–300 photos** with **≥ 50 instances each** of: clear safety glasses on / off · work gloves on / off (hands visible!) · **safety boots** · sneakers / other shoes · helmet on / off. Several people, outfits and lighting. Put them in `data/raw/<batch>/` (JPEG, *Most Compatible*).

> ⚠️ Keep `data/eval/` **separate** — never label or train on eval photos, or the eval score is meaningless. Take new eval photos (incl. **not wearing**) for each PPE type.

#### Roboflow footwear dataset — downloaded & inspected ✅

- **Source:** [pe3-kxttv/footwear-w1uf6 v2](https://universe.roboflow.com/pe3-kxttv/footwear-w1uf6), **CC BY 4.0** (attribution required) → `data/external/footwear-w1uf6-v2/` (gitignored). 2,368 train / 240 valid / 150 test images, **stretched to 640×640**.
- **Classes (actual):** `boots 2,562 · flip_flops 2,352 · sneakers 2,259 · soccer 2,189 · loafers 172 · sandals 154` — it *does* have sneakers.
- **Findings:** mostly close-up product / lifestyle shots; many 2×2 mosaics with black cut-outs baked in by the uploader (so near-duplicate crops can sit in different splits → its val score is optimistic); `boots` = *any* boot (UGG, heels, knee-high, rain, hiking, a few real work boots); people appear unlabelled. Shoes cover a median **5–44 %** of the image vs **~0.1 %** at 3 m from the rover — but the low camera sees shoes side-on like these photos.
- **Decisions:** foot-crop pass at runtime + normal training · boots **CLIP-sorted then hand-reviewed** · people **pseudo-labelled with SH17** · footwear collapsed to `shoes` / `safety-boots`.
- **Built:**
  - `pipeline.feet_crop` — square crop around each person's feet from the full-res frame (side = max(width, 0.25 × height)), merged like head crops. **Runs only when the boots rule is active** (never with SH17).
  - `tools/review_boots.py` — `score` (CLIP ViT-B/32, 2,562 boxes in 15 s: 720 suggested safety-boots, 314 ≥ 0.8, 1,402 < 0.2; top/bottom of the ranking visually checked ✅) and `review` (OpenCV, one key per box, saved on every key, resumable).
  - `tools/build_dataset.py` — remaps classes, applies the review (`drop-image` removes the image), refuses to build with unreviewed boots unless `--skip-unreviewed`, pseudo-labels people, writes `data/datasets/<name>/` + `data.yaml` + `summary.json`. Smoke build (boots skipped): 1,917 images in 45 s.
- **Fix — pseudo-label filter:** SH17 on shoe close-ups put `person` on sandals/flip-flops, `helmet` on a football, `gloves` on laces. Now only **person/head/face/hands**, and a person only if a head/face lies inside it → `person` 1,188 → 378 (visually checked: real people only). PPE classes are never pseudo-labelled on external data.


#### Roboflow footwear dataset — original decisions

- **Source:** Universe project `footwear-w1uf6`, version 2. *(Earlier note "no sneakers" was wrong — see above.)*
- **Use:** download the **dataset** (YOLOv8 format) for the local fine-tune only. The hosted cloud model is **not** used — it would break offline operation, add per-frame network latency, and upload images of people.
- **Class mapping:** `flip flops, loafers, sandals, soccer → shoes` (non-compliant). `boots → safety-boots` as a **draft only** — every boots image is hand-reviewed and fashion boots are relabelled `shoes`.
- **Download:** isolated one-off env so `roboflow` (and its `opencv-python-headless`, which conflicts with our `opencv-python`) never enters `uv.lock`:
  `set -a; . ./.env; set +a; uv run --no-project --with roboflow python -c "import os; from roboflow import Roboflow; Roboflow(api_key=os.environ['ROBOFLOW_API_KEY']).workspace('<owner>').project('footwear-w1uf6').version(2).download('yolov8', location='data/external/footwear-w1uf6-v2')"`

#### Roboflow boots data (needs your free Roboflow account)

On the dataset page → **Download Dataset → format "YOLOv8" → download zip** → unzip to `data/external/<dataset-name>/`. Check the license on the page. **Next step after that:** I inspect its real class names, image style and counts, then build `tools/build_dataset.py` (map its classes onto ours, pseudo-label the other classes with SH17 so people/faces aren't learned as background, split train/val by person) and `tools/train.py` (fine-tune SH17 YOLOv8s on the 9 classes). Those are deliberately **not** built yet — the converter depends on what's actually in the download.

#### Training decision + boots review status

- **Train on the MacBook Air, now, without own photos** → a **footwear-only model** (`shoes`, `safety-boots`) from **SH17 yolov8n**, used only inside the foot crop. SH17 keeps everything else — a 9-class model trained without glasses/helmet/gloves labels would *forget* them and make the critical glasses check worse.
- **Boots review:** the assistant reviewed sheets 0–13 (1,120 boxes) with a written standard — *safety-boots* = rugged work-style boot with thick lug/treaded sole covering the ankle (work, logger, combat, hiking, rubber work boots); *shoes* = heels, riding/knee-high, UGG/fur, thin-soled dress/Chelsea/brogue, chukka, fashion ankle, smooth rain boots, high-top sneakers; *drop* = unrecognisable crop. Stored separately in `boots_review_assisted.json`; **human decisions always override** (`merged_decisions`). `review_boots review` now shows only undecided boxes. Remaining sheets are being evaluated by the team.

### Step 4 — iOS ARKit capture app 🟡 (built + Simulator-tested — on-device checklist pending)

- **Decisions:** XcodeGen (`ios/project.yml` is the source of truth; `.xcodeproj` generated, gitignored) · frames **1920×1440 @ 10 Hz** + pose @ 20 Hz, configurable on the debug screen · phone: the team's LiDAR iPhone (the paired "Umo" reports `iPhone17,3` = iPhone 16, no LiDAR — the overlay shows `LiDAR yes/no` to settle it; nothing depends on LiDAR).
- **Built (`ios/BOBCapture`, SwiftUI, thin per AGENTS rule 1):**
  - `Wire/` (Foundation + simd only, unit-testable): `Schema.swift` Codable mirror of schema v2 C1 · `WireCodec.swift` message framing, recording framing, **column-major** `simd_float4x4` → 16 doubles, timestamp → integer ns · `Recorder.swift` → `Documents/recordings/bob_<time>.bobrec` (visible in Files, shareable via AirDrop).
  - `Capture/`: `ARMapping.swift` (ARKit/UIKit → wire enums; unknown future tracking reasons → `not_available`, never guessed) · `FrameEncoder.swift` (`capturedImage` → JPEG, downscaled, no rotation; header size read back from the JPEG) · `CaptureController.swift` (ARSession on a background queue, throttles ~60 fps → 10 Hz frames / 20 Hz poses, one `seq_id` counter, **new `session_id` + seq 0 on every reset/interruption**, screen kept awake, stats).
  - `App/`: camera preview (RealityKit `ARView`) + overlay: tracking (green/orange/red), session, seq, Hz, JPEG KB, encode ms, MB/s, orientation, LiDAR, REC count · Record / Reset session / Settings / Share.
- **Python:** `vision/recording.py` (`.bobrec` read/write — reused by Step 5 replay) · `tools/inspect_recording.py` (per session: rates, seq gaps, out-of-order, tracking/orientation counts, header-vs-JPEG size, **yaw change** (unwrapped), path length, upright sample frames).
- **Test:** Swift (`xcodebuild test`, Simulator) **11/11**: shared fixtures decode → re-encode to identical JSON, framing, integer timestamp, column-major order, recorder file bytes, golden export. **Swift → Python verified:** `tests/fixtures/recordings/swift_golden.bobrec` is written by the Swift encoder and decoded by the strict Python schema (yaw +90° for a +90° left turn, xyz exact). Python **196/196**. Device build (G7, unsigned) ✅.

#### 📱 On-device checklist (needs you — the iPhone + Xcode signing)

1. One-time: create `ios/Signing.local.xcconfig` with `DEVELOPMENT_TEAM = <your team id>` (Xcode → Settings → Accounts) and optionally `BOB_BUNDLE_PREFIX = com.<you>`. Enable **Developer Mode** on the iPhone.
2. `cd ios && xcodegen generate && open BOBCapture.xcodeproj` → select the iPhone → Run.
3. Record ~60 s doing, in order: hold still 5 s · **turn left ~90°** · turn right back · cover the lens 3 s · rotate phone to landscape and back · press **Reset session** · send the app to background and return.
4. Share the `.bobrec` (AirDrop) → `uv run python -m tools.inspect_recording <file>`.
5. **Pass:** 0 decode errors · 0 header/JPEG mismatches · frames ≈ 10 Hz, poses ≈ 10 Hz (+ frames = 20 Hz total) · seq gaps 0 · yaw change **positive** while turning left · cover-lens shows `limited` · Reset + background each start a **new session** · saved frames in `runs/inspect/<file>/` are **upright** for every reported orientation (this is the first real check of the Step 2 rotation mapping).

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
│   ├── pipeline.py    # frame → model boxes (single | head_crop) → PPE rules
│   ├── ppe.py         # face↔glasses, head↔helmet pairing → derived violation boxes
│   └── schema/        # wire contract: common, pose, phone (C1), events (C2/C3), wire
├── schema/            # generated JSON Schema (language-neutral contract)
├── tools/             # training, record/replay, export scripts
├── ios/               # XcodeGen project.yml + BOBCapture (Swift: Wire/, Capture/, App/) + tests
├── tests/             # pytest
└── data/ models/ runs/  # gitignored: datasets, weights, outputs
```

## Out of scope for this branch

Motor control, safety supervisor / P0–P4 state machine, evidence logging & alerting, obstacle detection, TensorRT engine build (must be done on the Jetson itself).
