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
| 3b | Gloves + safety boots + fine-tune | 🟡 **Footwear v1 trained and wired into the shared pipeline**; own-photo/worksite eval pending | Grouped held-out footwear test; shared-pipeline regression tests | 20 epochs; test boots precision **76.9%**, recall **66.7%**, AP50 **75.1%** (39 boxes); opt-in `configs/footwear.yaml`; [model card](models/footwear-v1.md) |
| 4 | iOS ARKit capture app (Xcode) | 🟡 Built + Simulator-tested — **on-device checklist pending** | Swift unit tests vs shared fixtures, Swift→Python golden recording, on-device recording + `tools/inspect_recording.py` | Swift 11/11 · Python 196/196 · unsigned device build ✅ · golden recording decodes (yaw +90° ✓) |
| 5 | WebSocket transport + record/replay | 🟡 **Live iPhone stream ✅** — kill tests (a–d) + live latency numbers pending | Replay client in pytest, live FPS/drops/latency, kill test | Python 223/223 · Swift 16/16 (+1 opt-in live) · loopback 1920×1440 @10 Hz (367 KB): **300/300 frames, 0 drops, added latency p50/p95 2.4/2.7 ms**, Mac decode+rotate 17.7/19.1 ms · Swift→Python 30/30 · server SIGKILL mid-stream → sender dropped 16 frames (none queued), reconnected by itself · **live iPhone (IPv6 hotspot): 117.8 s, 1179 frames @ 10.0 Hz, 1920×1440, 259 KB avg (2.66 MB/s), 0 seq gaps, 0 decode errors, tracking normal; upright ✓ for portrait + landscape_left** |
| 6 | Live inference + bounding boxes | 🟡 Built + replay/loopback-tested — **live PPE on/off test pending** | Replay determinism, live PPE on/off test, p50/p95 latency | 248/248 pass · offline replay deterministic + identical to the direct pipeline · `server --detect` 1920×1440 @10 Hz, 0 drops: rx→event **p95 85.6 ms** (2 people, landscape_left) / **117.7 ms** (5–6 people, portrait) ≤ 150 ✅ · inference p95 78 / 99 ms |
| 7 | Pose ↔ detection timestamp association | 🟡 Built + synthetic-tested — **deliberate live occlusion / Reset / background run pending** | Synthetic timeline unit tests, live occlusion + ARKit reset | 21 timeline tests (mutation-checked) · existing live recordings: 3 session switches, each new session invalid only while ARKit `initializing` (1.0–1.3 s), 0 old-session frames after a switch; mid-session re-init (3.9 s) invalid, origin kept (≤ 3 cm, < 1°) |
| 8 | CV destructive tests + Jetson handoff prep | 🟡 Built + Mac-verified — **on-device Jetson checks (J1–J6) pending** | Scripted failure suite, `.pt` vs `.onnx` parity | 20 destructive tests → **3 bugs found + fixed** · `.pt` vs `.onnx` (SH17 and + footwear): 92 images / 606–669 boxes, max \|Δconf\| 1.7e-6, **verdicts identical** · reproducible ONNX SHA · batched crops identical to sequential, live rx→event **p95 65.3 / 75.8 ms** (was 85.6 / 117.7) |
| 3c | Restricted-zone inspection — no movement authority | 🟡 Mac live/replay prototype built; physical tape acceptance pending | Geometry, evidence validity, tape failure cases, correlated scene output | 35 zone/tape/scene tests; full suite 339 pass; 6 synthetic replay frames correlated to C2 |
| 3d | Walkway obstruction (fixed camera) — no movement authority | 🟡 Steps 1–3 of 9 built (definition, settings, reference check + change mask); lane check, CLI and physical tripod test pending | Definition/config validation, synthetic reference-check and change-mask cases | 39 walkway tests pass; full suite 378 pass; synthetic only |
| D | Dashboard / rover-to-laptop sync / 2D Twin backend ([plan](docs/plans/dashboard-twin-integration-plan.md) Steps 1–9) | 🟡 D1 contracts built | Per plan step: fixtures, store/sync link-cut tests, API contract tests, incident timeline tests; physical Twin walk + calibration recordings | D1: `bob-app` v1 — 10 message types, 27 valid / 29 invalid fixtures, 62 contract tests; frozen v2 CV schema untouched |

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
- **Mount geometry (decided):** iPhone **landscape left** (changed from portrait on 2026-10-10, after Step 5), **tilted up ~15°, ~20 cm off the floor**, inspecting at **3 m+**. Landscape keeps the same pixels per degree (so the face/glasses sizes below still hold) but has a narrower vertical view (~51° vs ~65°): about −10° to +40° around the 15° tilt, so a 1.8 m person should still fit head to toe from ~2 m (estimate, to be checked on the rover). Camera looks up ~25° at faces; estimated at 640 px a face is ~22–27 px and glasses ~5–6 px — too small for one pass.
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
2. Phone in the rover mount position: **landscape left, ~20 cm off the floor, tilted up ~15°**. Use the main (1×) camera.
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

### Step 3d — Walkway obstruction inspection 🟡 (steps 1–3 of 9)

"Walkway closed" means **blocked by an obstruction**: no clear lane of a minimum width from the operator-marked entry edge to the exit edge. The walkway is an operator quadrilateral on a declared-empty reference image from a fixed tripod phone (L-shapes out of scope for the demo). Evidence is change vs that reference, so no new model. People are reported separately, not as obstructions. Built so far: `vision/walkway.py` (`WalkwayDefinition`, `WalkwayConfig`, `detect_changes`) and `configs/walkway.yaml`. A moved camera, lighting change, changed background or textureless scene gives `unverified` with no change evidence; the image is never re-aligned to fit. People handling, the lane check, the still-image CLI and the persistence tracker are not built yet. Details and limitations: [walkway guide](docs/walkway-obstruction.md).

### Step 3c — Restricted-zone inspection 🟡 (physical acceptance pending)

**Restricted zones first**, using a fixed-image operator polygon, then the user-confirmed yellow caution-tape convention (closed floor outline, inside restricted), then live/replay integration. Walkway obstruction follows later; open edges/stairs remain deferred. These are inspection findings for humans, with no movement authority. Image-space findings do not establish a hazard world position. The independent scene contract leaves CV schema v2 unchanged; schema v3 is not automatically required.

Feature 1: `tools.inspect_zone` binds a polygon to an exact upright image and runs the shared PPE/person pipeline. A possible person-in-zone finding requires separate visible foot evidence; bounding-box overlap alone is insufficient. Missing or ambiguous evidence remains unverified. Feature 2 recognizes a complete yellow floor-tape outline under an explicit operator convention. Feature 3 adds a separate Mac zone view and frame-linked replay sidecars. Run `uv run python -m vision.server --detect --zones configs/zones-yellow.yaml --record`. Tape color/shape does not prove floor geometry or recognize CAUTION text; physical testing remains pending. Tests, replay commands and limitations: [restricted-zone guide](docs/restricted-zones.md).

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

Same mount as before (landscape left, ~20 cm, tilted up ~15°), distances 2–4 m. Aim for **~150–300 photos** with **≥ 50 instances each** of: clear safety glasses on / off · work gloves on / off (hands visible!) · **safety boots** · sneakers / other shoes · helmet on / off. Several people, outfits and lighting. Put them in `data/raw/<batch>/` (JPEG, *Most Compatible*).

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

**2026-10-10: first footwear training completed.** `tools/train_footwear.py` uses the approved
reviewed labels and original non-boot classes, excluding whole images with unresolved or
`drop-image` boxes. The 2,278 retained images are grouped into 1,840 train / 217 validation /
221 test images; filename families and exact-byte duplicates stay together. Embedded mosaic
overlap remains possible. No `data/eval/` or own photos were used.

`configs/footwear.yaml` enables the hash-pinned two-class specialist in feet crops while SH17
continues the other PPE checks. Use `uv run python -m vision.detect --config configs/footwear.yaml`
for the Mac camera, or pass that config to the detection-enabled server. Generic SH17 `shoes`
boxes never enter the boots rule. The default config keeps the specialist off until explicitly
selected. Model outputs follow the broad reviewed visual convention, not protective certification.

[Model card, reproduction commands and limitations](models/footwear-v1.md).
Preview: `runs/footwear/preview/comparison.jpg`; test metrics: `runs/footwear/heldout-test/metrics.json`.
The 20-epoch run took 537.7 seconds. Other PPE fine-tuning and personal worksite testing remain pending.
Final checkout verification: **250 Python tests passed**; unsigned iOS build passed;
15 Swift tests passed, 2 opt-in tests skipped. No physical-phone acceptance is claimed.

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
3. Record ~60 s doing, in order: hold still 5 s · **turn left ~90°** · turn right back · cover the lens 3 s · rotate phone to landscape and back · press **Reset** · send the app to background and return.
4. Share the `.bobrec` (AirDrop) → `uv run python -m tools.inspect_recording <file>`.
5. **Pass:** 0 decode errors · 0 header/JPEG mismatches · frames ≈ 10 Hz, poses ≈ 10 Hz (+ frames = 20 Hz total) · seq gaps 0 · yaw change **positive** while turning left · cover-lens shows `limited` · Reset + background each start a **new session** · saved frames in `runs/inspect/<file>/` are **upright** for every reported orientation (this is the first real check of the Step 2 rotation mapping).

### Step 5 — WebSocket transport + record/replay 🟡 (live stream ✅ — kill tests + latency numbers pending)

- **Decisions:** Swift client included · latency measured **relative, no schema change** · the Mac shows upright frames + stats only (inference is Step 6).
- **Python — `vision/server/`** (package, one file per area):
  - `slot.py` — one-item **latest-frame-wins** slot between the receiver thread and the consumer. A frame nobody took is replaced and counted, never queued (rule 6).
  - `monitor.py` — per session: frames/poses, **seq gaps** (= frames the phone skipped), out-of-order (dropped), slot drops, rates, **added latency** and Mac processing time p50/p95, staleness → C3 `StreamHealth` (`dropped_count` = seq gaps + slot drops). A **new `session_id` retires the old one**: its counters reset, the slot is cleared, and its late messages are dropped (rule 5).
  - `transport.py` — `FrameServer` (websockets, binary only, no compression, 8 MiB max message, 2 s keepalive ping). Bad framing, text messages and C2/C3 sent the wrong way are counted as `bad`, and the connection stays open. `ServerThread` runs it off the main thread.
  - `view.py` / `__main__.py` — `uv run python -m vision.server [--record] [--no-view]` → OpenCV window (upright frame + stats). Writes `runs/server/<time>/stream_health.jsonl` (10 Hz), `summary.json` on exit, and `stream.bobrec` with `--record`. Clean shutdown on SIGTERM/SIGINT, even when signalled twice (`uv run` forwards signals).
- **`tools/replay_client.py`** — `.bobrec` → server with the original timing (`--speed 1`), faster, or as fast as possible (`--speed 0`). `--loops N` gives every pass a fresh session (like an ARKit restart).
- **Swift:** `Wire/SendGate.swift` (pure flow control: 1 frame in flight, ≤ 4 poses, a frame stalled > 2 s → reconnect) + `Wire/StreamSender.swift` (URLSessionWebSocketTask, reconnect with backoff 0.5 → 2 s, Foundation only so it runs in the test target). The app has a **Stream** button, **Settings → Server…** (URL saved), and overlay lines `ws <state> <url>` / `sent Hz · drop · reconnects`. The `Reset session` button is now `Reset`.
- **Added latency:** the iPhone clock is unrelated to the Mac's, so the absolute network delay is unknown. Per session, `added = (rx − iphone_ts) − min(rx − iphone_ts)`: 0 for the fastest frame, and growing if latency builds up. Clock drift adds a few ms per minute.
- **Test:** `uv run pytest` (19 in `tests/test_server.py`) — slot, gaps/out-of-order, new session retires the old one, stale at exactly `stale_ms`, added-latency math, Swift golden replay, 30 frames with no consumer → 29 drops and the newest survives, **slow 100 ms consumer at 20 Hz → rx→done p95 < 250 ms (no accumulation)**, original timing, bad/oversized messages (1009, server survives), stale ≤ 250 + 100 ms after the client vanishes, abrupt client death, **SIGKILL server mid-stream → client fails in < 1 s**, double SIGTERM still writes the summary + a complete recording, recording == bytes received. Swift: `SendGateTests` (5) + opt-in `StreamSenderLiveTests` against a running server (`TEST_RUNNER_BOB_SERVER_URL=ws://127.0.0.1:<port>`, optional `TEST_RUNNER_BOB_STREAM_SECONDS`, `TEST_RUNNER_BOB_EXPECT_RECONNECT=1`).
- **Live iPhone run (2026-10-10, iPhone personal hotspot):** 117.8 s session, **1179 frames + 1178 poses at 10.0 Hz each**, all 1920×1440, JPEG 259 KB avg (2.66 MB/s), **0 seq gaps, 0 out-of-order, 0 decode errors, 0 header/JPEG mismatches**, tracking `normal` throughout, 1 session. Health log: max `dropped_count` 5 (server slot drops). Sample frames from the recording are **upright for `portrait` and `landscape_left`** — the first real check of the Step 2 rotation mapping on ARKit frames ✅ (`face_up` fell back to the portrait mount, as designed). **Not yet evidenced:** the 4 kill tests (only one session, no Reset in this run) and the live added-latency p50/p95 (written to `summary.json` when the server stops).
- **Finding — IPv6-only hotspot:** on an iPhone personal hotspot from an IPv6-only carrier (T-Mobile here), the Mac gets **no usable IPv4** (only `192.0.0.2`, a CLAT translation address), and the server's default `0.0.0.0` (IPv4 only) can't be reached. **Workaround:** `uv run python -m vision.server --host ::` and, in the app, `ws://<mac-name>.local:8765` (`scutil --get LocalHostName`) or `ws://[<mac IPv6>]:8765` (brackets required). On venue Wi-Fi (`10.15.75.x`) the phone never connected either — probably client isolation; use the hotspot. **To do:** listen on IPv4 + IPv6 by default.
- **Measured:** see the progression row. In the Simulator live test, "added latency" (56/106 ms) is an artifact: the test makes up its timestamps at exactly 100 ms steps while `sleep` drifts. Only the iPhone run counts.

#### 📱 Live checklist (needs you — iPhone + Mac on the same Wi-Fi)

1. Mac: `uv run python -m vision.server --record` (macOS asks to allow incoming connections → Allow). Find the Mac IP: `ipconfig getifaddr en0`. **On a phone hotspot** (often IPv6-only): add `--host ::` and use `ws://<mac-name>.local:8765` in the app instead.
2. iPhone: rebuild (`cd ios && xcodegen generate`, Run). **Settings → Server…** → `ws://<mac-ip>:8765` → **Stream**. First time, iOS asks for **Local Network** access → Allow (if denied: Settings → Privacy → Local Network → BOB Capture).
3. Stream 60 s at 1920 / 10 Hz with the rover mount pose. **Pass:** overlay `ws connected`, Mac window upright, Mac `frames ≈ 10 Hz`, `drops: phone/server` stay ~0, **added latency p95 < 100 ms and not growing** (record p50/p95 and `mac` p50/p95 here).
4. **Kill tests:** (a) Ctrl-C the server, wait 5 s, restart → phone shows `connecting`, then `connected` again within ~2 s, and `reconnects` goes up. (b) Swipe the app away while streaming → Mac shows `STALE` within ~0.35 s (`stream_health.jsonl`). (c) Wi-Fi off on the phone for 5 s → Mac `STALE`; phone reconnects after Wi-Fi returns. (d) Press **Reset** → Mac shows a new session and the counters reset.
5. Replay the recorded session: `uv run python -m tools.replay_client runs/server/<time>/stream.bobrec` into a second server and compare the summaries; also run `tools/inspect_recording` on it (this re-checks the Step 4 rotation on ARKit frames).

### Step 6 — Live inference + bounding boxes 🟡 (live PPE on/off test pending)

- **Decisions:** builds on the existing `--detect` work · on/off test = **glasses + helmet + vest** · target **rx → event p95 ≤ 150 ms at 10 Hz** · determinism tested **offline, every frame**.
- **One frame path:** `vision/server/detection.py` `detect_frame()` = JPEG → upright (`decode_upright`, no overlay text) → `Pipeline` → C2 `DetectionEvent` + one verdict per active rule (`vision.ppe.frame_verdict`, now also used by `tools/eval_ppe.py`). The live server and the offline replay both call it, so they can't drift apart.
- **Pose in C2:** each event takes the pose **from its own frame** (`pose_dt_ms = 0`). `pose_valid=false` (detection still emitted) when the stream is stale, the session changed, tracking isn't `normal`, or yaw is undefined. Standalone pose packets are health inputs only. This already meets rule 4, so Step 7 is left with the synthetic-timeline tests and the live ARKit reset / occlusion checks.
- **Live:** `uv run python -m vision.server --detect [--record] [--config configs/footwear.yaml]` → boxes drawn in the window, overlay `CV <ms> | <n> boxes | pose <valid>` + per-rule verdicts, `detections.jsonl` (C2), `model.json`, and in `summary.json` `detected_frames`, `inference_p50/p95_ms` and `process_p50/p95_ms` (= rx → event written, **the Step 6 latency**).
- **Offline:** `uv run python -m tools.replay_detect <file.bobrec> [--save-images] [--rule glasses --segments "wearing:0-10,not_wearing:12-22"]` → every frame (no drops), `runs/replay_detect/<name>_<time>/{detections.jsonl,summary.json,frames/}`. Pose validity offline: the packet's own session; stale = > `stale_ms` between messages on the iPhone clock.
- **Test:** `uv run pytest` (12 in `tests/test_replay_detect.py`) — every frame processed and poses skipped · **two replays → same boxes / verdicts (≤ 1e-3)** · replay == pipeline on the same decoded image · stream frames in real sensor orientation (`landscape_left` unrotated, `portrait` rotated) → zidane not wearing glasses/helmet, bus sunglasses found only if upright · boots stays inactive · stale gap → `pose_valid=false`, boxes kept · on/off scoring (unverified ignored, any false `wearing` fails, nothing judged ≠ pass, bad segments rejected) · **`server --detect` end to end** (one valid C2 per frame, latency summary).
- **Measured (Mac MPS, SH17 yolov8s head_crop, loopback, JPEG q70 like the phone, 300 frames @ 10 Hz):**

  | Scene | rx → event p50 / p95 | inference p50 / p95 | drops |
  | --- | --- | --- | --- |
  | 2 people, `landscape_left` (rover mount) | 79.8 / **85.6 ms** | 70.0 / 78.2 ms | 0 |
  | 5–6 people (`bus.jpg`), `portrait` | 96.3 / **117.7 ms** | 80.0 / 98.6 ms | 0 |

  Inference is higher than Step 3's 53 ms. Possible reasons: 1920×1440 input and the WebSocket thread competing for the CPU. Each extra person adds a head crop (see AGENTS: batch crops before the Jetson port).
- **Finding — JPEG noise flips borderline glasses:** on `bus.jpg` sent the way the phone does (sensor orientation → JPEG → upright), the 2nd man's sunglasses are found at q98 / 95 / 85 / 80 but **lost at q90 and q70** (conf swings 0.32–0.62), turning one frame into a false `no-safety-glasses`. Not monotonic in quality, so there is no "safe" setting. Per-frame verdicts are noisy near the threshold, which is why the on/off test scores ≥ 80 % over many frames and N-frame confirmation belongs to alerts. The phone stays at JPEG 0.7 until the live test says otherwise.

#### 📱 Live PPE on/off test (needs the team)

1. Mac: `uv run python -m vision.server --detect --record --host ::` (hotspot) · phone in the rover mount (**landscape left**, ~20 cm, tilted up ~15°) → **Stream**.
2. One person at **~3 m**. Per item (glasses, helmet, vest): **10 s wearing → 2 s to change → 10 s not wearing**. Say the times out loud or note them (seconds from the start of the recording).
3. Stop the server (Ctrl-C) → `runs/server/<time>/summary.json`: **pass if `process_p95_ms` ≤ 150** and drops ≈ 0.
4. Score each item offline: `uv run python -m tools.replay_detect runs/server/<time>/stream.bobrec --rule glasses --segments "wearing:0-10,not_wearing:12-22" --save-images` (same for `helmet`, `vest` with their times). **Pass:** every segment `passed` (≥ 80 % of judged frames correct, 0 `wearing` while not wearing). Check `frames/` for what the model saw.

### Step 7 — Pose ↔ detection timestamp association 🟡 (deliberate live run pending)

- **Decisions:** **no pose buffer** — each frame carries the pose of its own ARFrame, so the association is exact (`pose_dt_ms = 0`) · `stale` = **iPhone-clock gap** > `timing.stale_ms` since the session's previous message, same rule live and offline · each frame judged **alone** (no look-ahead, keeps the Step 6 latency budget) · live acceptance = occlusion + Reset + background.
- **Built:**
  - `vision/association.py` — `associate()` (pure rules, first match wins: `session_mismatch` > `stale` > `tracking_not_normal` > `no_pose`; the detection is always emitted, the pose is never guessed) and `Associator` (thread-safe: newest session + iPhone-clock gap per message; `associate` runs at processing time, so a Reset that arrives while the model runs makes that frame `session_mismatch`). `dt_exceeded` stays unused until poses come from a separate source.
  - `FrameServer.admit()` — the **single admission step**: stream monitor (drops late / old-session / duplicate messages) → associator. The WebSocket handler, `tools/replay_detect` and `tools/pose_timeline` all call it, so live and offline association can't drift. `ReceivedFrame.gap_ns` carries the gap from receive time to processing.
  - `tools/pose_timeline.py` — model-free check of any recording: sessions, frames per verdict, every invalid stretch with ARKit's reason (`insufficient_features` = lens covered, `initializing`, `excessive_motion`). Runs in seconds on a 1 GB recording.
- **Test:** `uv run pytest tests/test_association.py` (21) — normal stream valid · the frame's own pose, not a later "latest" pose (yaw 10° kept although a 0° pose arrived after) · `limited` stretch invalid only inside · `not_available` · stale boundary **250 ms valid / 250.001 ms stale** · only the first message after a gap is stale · gap measured on the iPhone clock, arrival time irrelevant · first frame of a new session not stale · Reset then late old-session frame → dropped at admission · frame in flight when a Reset arrives → `session_mismatch` · rule precedence · out-of-order / duplicate seq dropped · timestamps going backwards ≠ stale · camera straight up / down → `no_pose`, still associated · tilted-up rover mount has a valid yaw · timeline tool on a synthetic lens cover + Reset. **Mutation check:** disabling the stale rule fails 5 tests, the session rule 2.
- **Evidence from existing live recordings** (`uv run python -m tools.pose_timeline runs/server/<time>/stream.bobrec`):

  | Recording | What happened | Pose verdicts |
  | --- | --- | --- |
  | `20261010_151221` | 4 sessions (3 Reset / background switches) | each new session invalid only while `initializing` (1.0 / 1.3 / 1.0 s, 11–14 frames), then valid · **0 old-session frames after a switch** |
  | `20261010_125207` | 375 s, one session | 3 single-frame `stale` after network gaps · **3.9 s mid-session `initializing`** (no new session) · 3 short `excessive_motion` stretches |
  | `151645` / `151756` | server restarted twice, same phone session `3bcbbd55` | continuous, valid (a server restart doesn't change the world origin) |

- **Finding — ARKit can re-initialise mid-session:** in `125207` tracking went `limited (initializing)` for 3.9 s **without** a new `session_id`. Those frames are invalid by rule; after recovery the pose was within ~3 cm / 0.6° of before (phone still), i.e. ARKit kept the world origin. If a future recording shows a **jump** after such a stretch, the app should start a new session on it (Swift, `CaptureController`).
- **Not done here:** locating the *person* (needs a distance — LiDAR / box size), phone → rover transform, any safety use (rule 7).

#### 📱 Live checklist (needs you — ~2 min, `--record` is enough, `--detect` optional)

1. `uv run python -m vision.server --record --host ::`, phone streaming in the mount.
2. 10 s still → **cover the lens ~3 s** → 10 s still → press **Reset** → 10 s → **app to background ~5 s** and back → 10 s → Ctrl-C.
3. `uv run python -m tools.pose_timeline runs/server/<time>/stream.bobrec`. **Pass:** one `tracking_not_normal (insufficient_features)` stretch of ~3 s, valid before and after · **3 sessions** (start, Reset, background), each new one invalid only while `initializing` · `frames the server would drop` = 0 or only old-session frames.

### Step 8 — CV destructive tests + Jetson handoff prep 🟡 (on-device checks pending)

- **Decisions:** failure classes **network / transport, bad data, pose / time abuse** (resources / soak and dual-stack server not in scope) · parity = **boxes (IoU ≥ 0.9, \|Δconf\| ≤ 0.02) + identical verdicts** on onnxruntime CPU · **no Jetson available** → prep + handoff doc · fix what the suite breaks · **batch head crops** · **ONNX for the footwear specialist too**.
- **Destructive suite** (`tests/test_destructive.py`, 20 tests, each tagged with invariants I1–I6: server stays up · no fake compliance · nothing disappears silently · latency can't accumulate · trouble reported · pose never guessed):
  - *Network:* half-open connection (peer stops answering pings) · 200 KB frame trickled over 1.5 s while another client streams (server and health loop keep going) · 3000-frame flood (one frame kept, every other counted, health still ticking) · 100-connection reconnect storm · two phones / two sessions (newest wins, old one's messages dropped, never mixed).
  - *Bad data:* corrupt JPEG with a valid header (live server + offline) · header size ≠ JPEG size (boxes fit the real image) · black / white / dark / overexposed / motion-blur / noise / tiny frames on `zidane.jpg` → **never `wearing`** · phone flat (`face_up`) → mount orientation.
  - *Pose / time:* Reset on every message · +1 h clock jump (only that frame stale) · UInt64 max seq / timestamps · pose-only stream (nothing invented).
- **Bugs the suite found — fixed:**

  | Bug | Before | Fix |
  | --- | --- | --- |
  | Corrupt JPEG (valid header) | frame silently vanished: no event, `dropped_count` 0 (violates I3) | counted per session as `undecodable`, included in C3 `dropped_count`, shown as `bad-jpeg`, `summary.json` / `replay_detect` list it |
  | Retired-session memory | grew forever (5,000 Resets → 5,000 ids) | bounded to the newest 10,000 (`MAX_RETIRED_SESSIONS`) |
  | Dead phone connection | lingered **10.5 s** after the ping timeout (library close-handshake default) | `close_timeout` = keepalive → released in ~0.6 s in the test, ~6 s with the 2 s keepalive |

- **Batched head crops:** `Detector.detect_batch` + `pipeline.crop.batch: true` (default) — all crops of a frame in one model call. `tools/parity.py batch` on 92 images (2 bundled + 90 live frames): **identical boxes** (IoU 1.0, Δconf 0), identical verdicts. Pipeline wall time 37.5 → **20.7 ms** (2 people) and 49.7 → **28.4 ms** (5–6 people); live server rx → event p95 **85.6 → 65.3 ms** and **117.7 → 75.8 ms**, 0 drops.
- **ONNX:** `tools/export_onnx.py` (optional `export` dependency group: `onnx`, `onnxruntime`) → `models/*.onnx` (dynamic batch / H / W, opset 17), SHA-256 pinned in tracked **`configs/onnx.yaml`**. Finding: ultralytics stamps the export **date** into the ONNX metadata, so two exports had different hashes with an identical graph → the date is replaced by the source SHA, exports are now **byte-reproducible**. Finding: on the Mac, ultralytics routes ONNX to onnxruntime's **CoreML provider, which crashes on the dynamic crop batch** → ONNX runs on CPU there (`onnx_config`), CUDA on the Jetson.
- **Parity `.pt` (MPS) vs `.onnx` (CPU):** SH17 — 92 images, 606 boxes, **max \|Δconf\| 1.7e-6, min IoU 0.999998**, 0 verdict differences; SH17 + footwear (`--config configs/footwear.yaml`) — 669 boxes, same result. ONNX on the Mac CPU is ~3× slower (114 vs 37 ms); speed is the Jetson's job (TensorRT).
- **Handoff:** [`docs/jetson-handoff.md`](docs/jetson-handoff.md) — install (NVIDIA torch wheels, not PyPI), engine build **on the device** from the pinned `.pt` (FP16, dynamic, batch 8), acceptance J1–J6 (pytest with CUDA, G6 grep, engine parity via `tools.parity config --b-config configs/engine.yaml`, latency ≤ 150 ms, determinism, destructive suite), systemd unit, networking lessons, risks. On-device commands are marked as not yet run.
- **Test:** `uv run pytest` — destructive (20) + `tests/test_handoff.py` (12: parity matcher accepts/rejects, `detect_batch` == single calls, batched == sequential pipeline with a spy proving real batching, batch is default, ONNX config swap never enables footwear / never CoreML, tampered `.onnx` refused, ONNX == `.pt` on bundled images; ONNX tests skip without the `export` group). Mutation check: removing the corrupt-JPEG count fails its test.

### Step D — Dashboard, rover-to-laptop sync and Twin backend 🟡 (plan Steps 1–9 in progress)

Application layer in `bobapp/` (outside `vision/`): rover edge store + sync API, laptop hub + frontend API. Backend only; no frontend is built. Decisions and design: [plan](docs/plans/dashboard-twin-integration-plan.md) (Step 0 decisions recorded there, baseline `bd0d6d7`, 378 tests).

- **D1 — Contracts ✅ (automatically tested).** `bobapp/contracts.py`: separately versioned `bob-app` v1 envelopes — lane `Record` (observation sidecar with per-subject verdicts + active/inactive rules + optional C7 record + frame assessment, track point, evidence metadata, profile revision, inspection start/end, incident transition, gap, notice), `LiveState`, `WorksiteProfile` (content SHA-256), sync messages (`sync_hello` / `welcome` / `batch` / `ack` / `live` / `error`) and `blob_status`. C2/C3 are embedded verbatim; the frozen v2 schema is unchanged (tested). Fixtures in `tests/fixtures/app/`, generated JSON Schema in `schema/app/` (`uv run python -m tools.export_app_schema`). **Test:** `uv run pytest tests/test_app_contracts.py` — every invalid fixture fails for its intended reason; one parser reads LIVE, REPLAY and SAMPLE records without branching on source.

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
│   ├── server/        # WebSocket stream server: slot, monitor, transport, view, CLI
│   └── schema/        # wire contract: common, pose, phone (C1), events (C2/C3), wire
├── schema/            # generated JSON Schema (language-neutral contract)
├── tools/             # training, record/replay, export scripts
├── ios/               # XcodeGen project.yml + BOBCapture (Swift: Wire/, Capture/, App/) + tests
├── tests/             # pytest
└── data/ models/ runs/  # gitignored: datasets, weights, outputs
```

## Out of scope for this branch

Motor control, safety supervisor / P0–P4 state machine, evidence logging & alerting, obstacle detection, TensorRT engine build (must be done on the Jetson itself).

## Standalone hardware bench tests

The user-requested [ESP32 motor and speaker test](hardware/esp32/README.md)
contains the Arduino sketch, Mac BLE terminal client, wiring, and test results.
It is independent of the CV pipeline; production motor control remains outside
the CV work described above.
