# Reviewed footwear specialist v1 — experimental

Trained 2026-10-10. Recognizes the user's **visual boot convention**, which includes work,
hiking, combat and some ordinary/winter boots. This is not evidence of protective certification.
Personal iPhone/worksite evaluation is pending. Keep this model opt-in.

## Artifact and runtime

- File: `models/footwear_yolov8n_v1.pt` (local, gitignored, approximately 6.2 MB).
- SHA-256: `6fc67e15cddd7619d3e92dd8f61c3bc711c699780f03074622e1dbab34ff269a`.
- Native classes: `0: shoes`, `1: safety-boots`. Here `shoes` means other footwear.
- Runtime override: `configs/footwear.yaml`; loading requires the pinned hash.
- Shared `Pipeline` retains SH17 YOLOv8s for the other PPE classes and uses this specialist
  on person feet crops at 320 px. No person/crop or low-confidence footwear means UNVERIFIED.
- Ensemble ID: `sh17_yolov8s+footwear_yolov8n_v1`. Original SH17 IDs are retained except generic
  shoes (14), which is suppressed. Specialist IDs become `17: shoes`, `18: safety-boots`.
  Consumers must interpret IDs using the ensemble's mapping, not the SH17 mapping alone.
- Existing boot rule: confidence >= 0.50, minimum subject size 12 px. Other PPE rules are unchanged.
  `pipeline.mode: single` still performs specialist feet crops when enabled; it omits head crops.

## Data provenance and exclusions

Source: [Roboflow Universe, pe3-kxttv / footwear-w1uf6, version 2](https://universe.roboflow.com/pe3-kxttv/footwear-w1uf6).
Credit the dataset contributors; source data is **CC BY 4.0**.
Original `boots` boxes use the merged local review; human decisions override assisted decisions.
Original flip_flops, loafers, sandals, sneakers and soccer classes map to shoes.
No pseudo-labels, personal photos, or `data/eval/` images were used.

An entire source image was excluded if any boots box was unresolved or marked drop-image:
480 excluded images; 391 contained unresolved boxes, 260 contained dropped boxes, with overlap.
2,278 images remain, with 6,877 shoes and 322 safety-boots boxes.

| Split | Images | Shoes boxes | Safety-boots boxes |
| --- | ---: | ---: | ---: |
| Train | 1,840 | 5,591 | 255 |
| Validation | 217 | 664 | 28 |
| Test | 221 | 622 | 39 |

Splits were rebuilt with seed 42: approximately 80/10/10 by source group, stratified by presence
of safety-boots. All instances of a Roboflow filename family and exact-byte duplicates stay
in one split (769 groups, 155 with safety-boots). Embedded mosaics and unidentified visual
duplicates can still share content across groups; this is not a verified independent worksite test.
No claim of person-disjoint splits is made.

Audit: `data/datasets/footwear-reviewed-v1/{manifest,summary}.json` includes source paths,
image/label hashes, per-image decisions, exclusions, groups and split membership.
Review file hashes at build time:

- `boots_review.json`: `70707020b8c09ba88747b7852c8e6d7eb3ef191908950a3505c5cb56ff5e8618`
- `boots_review_assisted.json`: `62700397ebfc35d01b242039432c42627965667b6794aa937db37550376f7f41`

## Training

Initialized from SH17 YOLOv8n, SHA-256
`5449f62bd7cf30c01c7fd138db2729a38abcb4d5120449773fba475d54f30b62`.
SH17 weights are **CC BY-NC-SA 4.0**; this fine-tune is for non-commercial use under those terms.
Ultralytics software is **AGPL-3.0**. See [SH17 source](https://github.com/ahmadmughees/SH17dataset)
and the existing `models/sh17.md` card.

Recipe: `configs/train_footwear.yaml`. 20 epochs, batch 16, 320 px, frozen backbone (10 layers),
AdamW, seed 42, mosaic 0.5 disabled for the final five epochs. Apple M5/MPS,
Python 3.10.20, torch 2.14.1, ultralytics 8.3.253. Training epochs took 537.7 seconds.
Best checkpoint chosen by validation fitness, not by test performance.

Original run: `runs/detect/runs/footwear/reviewed-v1/` (the installed Ultralytics settings nested
the initial relative project path). The tool now resolves the project path absolutely for future runs.

## Measurements

| Split / class | Precision | Recall | AP50 | AP50–95 |
| --- | ---: | ---: | ---: | ---: |
| Validation / shoes | 0.836 | 0.668 | 0.773 | 0.478 |
| Validation / safety-boots | 0.679 | 0.604 | 0.643 | 0.454 |
| Test / shoes | 0.881 | 0.631 | 0.780 | 0.501 |
| Test / safety-boots | 0.769 | 0.667 | 0.751 | 0.573 |

Precision/recall above use Ultralytics' validation-selected confidence operating point;
they are not measured end-to-end PPE verdict accuracy at the runtime threshold of 0.50.
Test safety-boots support is only 39 boxes across 23 images. The training classes are heavily
imbalanced. About one third of test boot boxes are missed at the reported operating point.
Product photos and mosaics dominate this source; low rover angles, distant feet, occlusion,
lighting, and unseen footwear remain unvalidated.

Test report: `runs/footwear/heldout-test/metrics.json` and its confusion/PR plots.
Eight deterministically selected held-out examples, with labels beside predictions at confidence
0.50: `runs/footwear/preview/comparison.jpg`; raw boxes in `predictions.json`.
The preview includes winter boots labeled safety-boots by the accepted review convention.

Shared-pipeline smoke checks: `runs/footwear/pipeline-preview/`. On bundled `bus.jpg`, all five
rules were active and nine passes ran; two tan footwear boxes were labeled safety-boots and
one shoes box was unverified. `zidane.jpg` produced no footwear verdict. This confirms wiring,
not boot accuracy or certification. Other PPE detections remain provided by SH17.

## Reproduce and use

Validation on the completed checkout: **250 Python tests passed** (one existing Torch
deprecation warning), including schema, specialist isolation, split exclusions, real-model
regressions and server replay. Unsigned iOS device build passed; Swift tests had 15 passed,
2 opt-in tests skipped (live sender and golden-recording export). Python 3.10 syntax and
Jetson import/device checks passed. Schema v2 is unchanged. Logs are in `runs/footwear/`.
Pre-merge G1–G4/G8 are not completed: the checkout includes preserved teammate work, `main`
does not exist, and no commit, PR or merge was requested. G5–G7 checks above passed locally;
physical iPhone and Jetson acceptance remain pending.

```bash
# Build once; refuses to overwrite an existing dataset.
YOLO_AUTOINSTALL=false uv run python -m tools.train_footwear build
YOLO_AUTOINSTALL=false uv run python -m tools.train_footwear train
# Evaluate the trained, hash-pinned specialist (never the seed weights).
YOLO_AUTOINSTALL=false uv run python -m tools.train_footwear test
# Shared PPE + footwear pipeline on the Mac camera:
uv run python -m vision.detect --config configs/footwear.yaml
# In the detection-enabled server, use the same override:
uv run python -m vision.server --detect --config configs/footwear.yaml
```

Training a new checkpoint does not automatically replace the pinned runtime artifact. Evaluate it,
copy the chosen checkpoint to `models/`, and update the hash and this card together.
The existing live server was not restarted during this footwear handoff; another session owns
the server integration. Boxes are rendered on the Mac, not returned to the iPhone preview.
