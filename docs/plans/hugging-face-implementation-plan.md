# BOB Hugging Face implementation plan

Planning date: October 10, 2026.

Status: **Proposed implementation sequence. This document does not implement software, publish artifacts, or establish new measured results.** The user requested this plan after selecting the Hugging Face competition pathway. Work through the gates below; do not mark an implementation step complete from documentation alone.

## 1. Outcome and competition story

Build a reproducible construction-inspection demonstration around BOB's existing vision pipeline:

> BOB helps reviewers inspect selected PPE conditions from a rover-height camera. It preserves the source frame, camera observation pose, and uncertainty. Our Hugging Face release lets others reproduce the model results and see where the system fails.

The minimum submission consists of:

1. A Hub model repository for the existing experimental footwear specialist, with provenance, exact artifacts and honest evaluation.
2. A small, manually labeled rover-view evaluation dataset with permitted staged examples and documented limitations.
3. A Hugging Face Space comparing single-pass and head-crop PPE inference through the shared Python pipeline.
4. A local offline demonstration using the same pinned artifacts, plus a short backup recording.

An optional SmolVLM evidence-description experiment follows the working minimum submission. Autonomous motion, new hazard detectors, a new foundation-model training run, and Jetson deployment are not prerequisites for this submission.

The supplied challenge description names creativity, technical execution, and meaningful Hugging Face ecosystem use. This plan addresses those criteria; it does not promise a prize or assume additional eligibility rules.

## 2. Current baseline and boundaries

| Area | Documented baseline | Consequence |
| --- | --- | --- |
| Phone input | Live iPhone-to-Mac JPEG/pose transport; recording and replay available | Reuse existing capture and recordings |
| PPE | SH17, shared `Pipeline`, head crops, batching, per-subject verdicts | Compare configurations without implementing another detector path |
| Footwear | Reviewed specialist trained; boots precision 76.9%, recall 66.7%, 39 held-out boxes | Publish as experimental visual footwear classification |
| Performance | Mac receive-to-event p95 65.3/75.8 ms on documented recordings | These are Mac results, not Jetson or Space measurements |
| Zones | Yellow-tape inspection implemented; physical acceptance pending | Optional contextual example after physical validation |
| Walkway | Reference validation/change mask only; lane check and CLI pending | Exclude from the minimum submission |
| Hardware | Standalone ESP32 motor bench test | No integrated hazard stopping claim |
| Deployment | Jetson J1–J6 pending; application backend/dashboard planned | Demonstrate the Mac baseline first |
| Hugging Face | No project integration identified in the review | Every release and hosting step below remains to be built |

Baseline sources: [CV progression](../../README-CV.md#progression), [SH17 card](../../models/sh17.md), [footwear card](../../models/footwear-v1.md), [integration contracts](../../integration.md), [Jetson handoff](../jetson-handoff.md), and [ESP32 status](../../hardware/esp32/README.md).

Architecture constraints:

- Python owns inference and assessment. Swift stays thin; no new phone payload is needed.
- Reuse `vision.pipeline.Pipeline`. Phone-message ingestion must go through `FrameServer.admit()`; recorded detection must reuse the existing replay/detection path.
- Preserve C1/C2/C3 schema v2. Application reports and release manifests are separate versioned artifacts. C2 alone does not publish all per-subject verdicts or rule availability; obtain them from the shared pipeline or the future backend's documented observation contract.
- Keep latest-frame-wins behavior. Space requests, evidence descriptions, downloads and publishing must not block local capture/inference.
- Pose means the source frame's camera observation pose, not a worker's or zone's world location. Preserve session and pose-validity semantics.
- Never infer compliance from missing boxes. Show detected, not detected, unverified, unavailable and not required distinctly where applicable.
- The [dashboard/backend plan](dashboard-twin-integration-plan.md) retains its local-only rover-to-laptop architecture. The Space is a separate showcase using curated release assets; it does not subscribe to the rover, upload live footage, or replace the backend plan.
- This planning request does not publish anything. Prepare an exact release inventory before any later authorized publication. Do not treat raw recordings as approved public assets.

## 3. Step-by-step implementation

### Step 0 — Establish a reproducible starting point

**Work**

1. Before feature implementation, inspect branch and working tree, preserve teammate changes, and follow the repository's `git pull --ff-only` workflow. Do not reset, force-push or silently stash others' work.
2. Record the source commit and any relevant uncommitted changes. Select a reproducible baseline for the eventual release.
3. Run `uv run pytest` and retain its result. Review the existing model cards and real-recording parity evidence.
4. Identify available staged recordings and model files without copying private content into tracked directories.
5. Record the intended HF account/organization, sponsor eligibility interpretation, available hosting resources, and the event credit's eligible services. These are implementation inputs, not assumptions that the accounts or credits already exist.

**Deliverable:** baseline record under `runs/huggingface/` and a release checklist in documentation.

**Gate:** source, model hashes, environment and test outcome are recorded; existing failures or uncommitted dependencies are explicit. No public artifacts are created.

### Step 1 — Freeze the showcase question and labels

**Work**

1. Use this primary question: **How does head cropping change PPE inspection quality and processing cost from a low rover camera?**
2. Compare SH17 single-pass and head-crop configurations with the same checkpoint and otherwise controlled settings.
3. Keep the footwear specialist as a separate experimental demonstration. Do not attribute its benefit to head cropping; feet crops are a separate mechanism.
4. Define labels for each selected PPE item: visible/present, visibly absent, and unobservable/ambiguous. Keep human ground truth separate from model verdicts.
5. Display eyewear as visual eyewear presence, not verified protective eyewear. Display the specialist's boot convention as visual footwear appearance, not certified safety boots. Preserve native class mappings in machine-readable results.
6. Select one or two staged PPE checks for the main demonstration after measuring them. Do not advertise all five rules as validated.

**Deliverable:** short evaluation protocol and public-facing terminology.

**Gate:** the comparison, labels, success criteria and exclusions are written before evaluating the final held-out set. Existing README quality targets remain targets, not achieved results.

### Step 2 — Prepare a small rover-view evaluation dataset

**Work**

1. Collect staged, consented examples from approximately the actual mount height. Record camera height/angle, approximate distance, lighting, session and subject pseudonym.
2. Aim initially for 60–100 manually labeled frames across several sessions, covering present, absent and ambiguous cases. This is a proposed feasibility target, not a statistical validation claim. Prefer diverse independent scenes over adjacent frames.
3. Include clear glasses, ordinary eyewear, helmets, occluded/tiny subjects and negative examples. Include footwear only with its visual label convention documented.
4. Define capture-session/person groups. Keep related frames in one partition and separate development examples from the held-out evaluation set. Document any unavoidable overlap.
5. Never train or pre-label `data/eval/`. Any future fine-tuning needs a separate approved training collection and new held-out evaluation.
6. Manually check annotations, including ambiguous cases. Log disagreements and exclusions rather than forcing labels.
7. Build a public subset that excludes private screens, bystanders, identifying metadata and unapproved recordings. If images are transformed for release, assign new hashes and evaluate the exact released images.

**Deliverable:** images, annotations, split manifest, hashes, collection notes and a draft dataset card. Keep large local artifacts in gitignored data directories.

**Gate:** every public candidate has sharing permission and a defined license; labels and group splits are audited; support counts are reported. Small sample sizes and sampling limitations are visible.

### Step 3 — Produce the comparison report

**Work**

1. Reuse `tools/eval_ppe.py` where its existing inputs and metrics fit. Extend a reporting adapter only where necessary; do not duplicate inference or PPE rules.
2. Run both frozen configurations on the same evaluation images. Record checkpoint hash, effective configuration, source revision and environment.
3. Report per-rule precision, recall, false findings, missed findings and unverified rate with denominators. Separate evaluable subjects from ambiguous ground truth; report incorrect definitive claims on ambiguous examples explicitly.
4. Report sample/group counts. Do not present neighboring video frames as independent trials or treat detector confidence as calibrated correctness probability.
5. Measure warm-run processing p50/p95 on the named host and record startup separately. Use same-host clocks; do not subtract iPhone timestamps from host timestamps.
6. Select successful, failed and ambiguous examples for the Space. Publish the complete aggregate results, not only selected successes.
7. If a new backend/export is introduced, run required parity checks on real recordings. The intentional single-pass/head-crop experiment may produce different verdicts; deployment parity compares the same configuration across implementations.

**Deliverable:** machine-readable results, a readable report, annotated comparisons and a reproducibility manifest under `runs/huggingface/`.

**Gate:** another local run reproduces the recorded findings within documented numerical tolerances. Timing variability is reported separately. No improvement is claimed unless measurements support it.

### Step 4 — Package the model release

**Work**

1. Start with the trained footwear v1 specialist, not a fresh training run. Package the verified checkpoint and existing reproducible ONNX export if redistribution terms permit.
2. Preserve its native two-class mapping and document the different ensemble mapping used by BOB.
3. Adapt the existing model card with training provenance, reviewed-label convention, split limitations, supported use, failures and exact evaluation operating points.
4. Carry forward the documented SH17-derived non-commercial restrictions and source attribution. Do not label the entire stack Apache/MIT or equate Hub hosting with an open-source license.
5. For the Space's SH17 dependency, record its permitted source and checksum; do not assume the footwear repository contains the full PPE model.
6. Build a release manifest listing each file, SHA-256, intended license, origin and purpose. Exclude tokens, private recordings, local signing settings and unrelated artifacts.

**Deliverable:** locally prepared model repository contents and an exact publication inventory.

**Gate:** each artifact's provenance and redistribution basis are established. Resolve uncertain terms before distributing that artifact; confirm sponsor eligibility separately. Existing limited test results are not relabeled as worksite accuracy.

### Step 5 — Add pinned Hub retrieval and offline loading

**Work**

1. Once publishing the reviewed package is authorized, create the model/dataset repositories and record their immutable revisions. Before then, test against the prepared local release directory.
2. Add an explicit setup/download path using `huggingface_hub`; isolate showcase dependencies from the core runtime where practical.
3. Pin the full Hub commit revision and expected file hashes. Continue using `ensure_weights` for `.pt` verification; never load an arbitrary user-supplied checkpoint.
4. Download before the demonstration, verify artifacts and populate local caches. The running rover does not fetch models or upload evidence.
5. On a cold offline start, report a missing artifact clearly. On a warm offline start, load only the pinned local artifacts.

**Deliverable:** reproducible setup instructions, pinned artifact manifest and offline-ready cache.

**Gate:** missing file, wrong hash and unavailable network cases behave predictably; the cached path works without upstream internet. Frozen CV schemas remain unchanged.

### Step 6 — Build the comparison Space locally

**Work**

1. Build a small showcase adapter, proposed under `showcase/huggingface/`, that imports the shared Python pipeline. A Docker Space is a candidate for keeping the runtime compatible with Python 3.10; verify the supported environment before choosing it.
2. Begin with curated examples only. Provide an example selector, paired annotated views, per-subject verdicts, uncertainty reasons and measured processing times.
3. Show model revision, configuration identity, source mode and host. Distinguish **fresh inference**, **cached replay** and **sample data**.
4. Offer the matching observation/report for download. Preserve image dimensions and hashes so boxes cannot be paired with another frame.
5. Use one shared model instance per worker, bounded request concurrency and input-size limits. A slow visitor must not create an unbounded inference queue.
6. Start with the real comparison pipeline on CPU and measure usability. If too slow, show clearly labeled cached comparisons plus an optional bounded fresh-inference action; do not present cached latency as current host performance.
7. Keep the existing local inspection dashboard/backend a separate workstream. Do not implement motion controls, operational incident confirmation or a second live rover service in this Space.

**Deliverable:** locally working showcase using the same pinned models and comparison outputs.

**Gate:** boxes align correctly; ambiguous cases stay unverified; repeated requests remain bounded; model failures are visible; no arbitrary weights or raw rover feed are accepted.

### Step 7 — Publish and verify the public demonstration

**Work**

1. Review the exact model, dataset and Space release inventories and publish only the authorized curated package.
2. Cross-link the model card, dataset card, evaluation report, Space and project source. Include applicable licenses and attributions.
3. Test a clean build from the pinned sources. Ensure the Space does not depend on local untracked files or private model paths.
4. Verify the public visitor flow, cold start, error reporting and download links. Confirm that source is available where required by applicable licensing.
5. Track actual hosting spend. Treat the advertised $20 event credit as unverified until redemption and service eligibility are confirmed; do not assume unlimited GPU availability.
6. Prepare a local fallback with cached models and curated evidence. Disconnect upstream internet while keeping the phone-to-host LAN intact and rehearse it.

**Deliverable:** verified public URLs, source/release identifiers and an offline backup.

**Gate:** a clean environment reproduces the demo; published files match the reviewed inventory; cold-start/hosting limitations are disclosed; the local fallback succeeds.

### Step 8 — Optional SmolVLM evidence descriptions

**Dependency:** Steps 0–7 work. Skip this step if the remaining time is needed for evaluation, reliability or rehearsal.

**Work**

1. Evaluate `HuggingFaceTB/SmolVLM2-500M-Video-Instruct` on the curated evidence set. Pin its revision and dependencies; the model card identifies an Apache-2.0 image/video-to-text model, not a validated construction inspector.
2. Ask for short visible-scene descriptions and explicit uncertainty. Keep generated text separate from authoritative observation fields and deterministic reports.
3. Compare against a simple template generated from structured findings. Score unsupported claims, contradictions, uncertainty preservation, reviewer usefulness, latency and memory.
4. Use a separate process with a bounded queue and timeouts. Start with offline/public examples; any later local evidence integration must remain local and follow the backend plan.
5. Do not let generated text change PPE verdicts, worksite requirements, incident confirmation, severity, pose validity or motor state. Prompt instructions alone do not enforce these boundaries.
6. Fall back to the structured report when generation fails, times out or cannot be trusted. Label cached descriptions accurately.

**Deliverable:** optional AI-description panel and a comparison report against the template baseline.

**Gate:** held-out examples show a useful benefit without unsupported safety assertions; resource contention stays within an agreed measured budget. Otherwise omit the panel and retain the experiment's findings.

### Step 9 — Rehearse and assemble the submission

**Work**

1. Demonstrate a real staged observation on the Mac, then open the matching curated comparison in the Space.
2. Show one detected case, one miss/false finding and one unverified case. Explain what cropping changes and what it cannot fix.
3. Open the model card, dataset card and reproducibility report. Distinguish the pretrained SH17 contribution from the team's reviewed footwear fine-tune and pipeline engineering.
4. Show offline local execution and clearly labeled hosted execution as separate modes.
5. Record three consecutive rehearsals, including failures and recovery. Save a short backup video and final artifact revisions.
6. If showing Jetson results, first complete J1–J6 and use measured Jetson numbers. If showing hardware, describe the actual motor bench capability; do not imply integrated hazard stopping.

**Deliverable:** submission text, links, demo script, measured results and backup video.

**Gate:** every pitch claim points to a measured result or is explicitly labeled experimental/planned. Review the final diff and run required repository checks before declaring implementation complete. Commit/push only when requested.

## 4. Suggested ownership and files

These are responsibilities and proposed paths, not an assumption of available teammates or authorization to delegate.

| Responsibility | Reuse | Proposed additions |
| --- | --- | --- |
| Evaluation | `tools/eval_ppe.py`, replay tools, shared pipeline | Comparison reporting and evaluation protocol |
| Model release | `models/footwear-v1.md`, SH17 card, pinned exports | Release manifest and Hub-ready cards |
| Dataset | Existing capture/recording tools | Curated staged dataset and annotation/split manifests |
| Showcase | Shared pipeline and rendering | `showcase/huggingface/`, isolated dependency specification |
| Verification | Existing schema/replay/parity tests | Meaningful tests for report correlation, artifact verification and request bounds |
| Operational integration later | Dashboard/backend plan | Consume its documented local API; do not fork inspection semantics |

Keep models in `models/`, data in `data/`, and generated reports in `runs/` locally. Use Hub repositories for reviewed public artifacts. Do not put large artifacts into Git merely to make the Space build succeed.

New shared config keys or interfaces require the updates/checks in `integration.md`. No change to frozen schema v2 is planned. If that changes, follow the full schema-version/fixture/export/Swift workflow.

## 5. Definition of done and scope cuts

- [ ] Baseline and full test result recorded.
- [ ] Held-out evaluation protocol, dataset and support counts documented.
- [ ] Single-pass/head-crop comparison reproducible with honest failures.
- [ ] Footwear model package preserves provenance, labels and restrictions.
- [ ] Hub artifacts pinned by revision and verified by hash.
- [ ] Public Space runs or clearly labels cached results; no live rover upload.
- [ ] Public examples have sharing permission and privacy review.
- [ ] Local demonstration works with upstream internet disconnected.
- [ ] Three rehearsals and a backup video recorded.
- [ ] Final submission distinguishes implemented, measured and planned capabilities.

Cut optional SmolVLM first, then custom uploads, visual polish, Twin integration and extra hazard categories. Keep the model release, evaluation evidence, comparison Space and offline fallback. If detector quality is weak, present the measured limitation and narrow the use case; do not suppress failure examples or substitute a generated explanation for evidence.

No builder count or remaining time was confirmed, so this plan uses dependencies rather than a promised hour-by-hour schedule. Start implementation with Steps 0–3; their results determine what is credible to publish and demonstrate.

## 6. References

Hugging Face references checked during the recommendation on October 10, 2026; recheck deployment and billing details when implementing.

- [Hub model cards](https://huggingface.co/docs/hub/model-cards)
- [Dataset cards](https://huggingface.co/docs/hub/datasets-cards)
- [Revision-pinned downloads](https://huggingface.co/docs/huggingface_hub/guides/download)
- [Spaces overview](https://huggingface.co/docs/hub/spaces-overview)
- [Inference Providers pricing and billing](https://huggingface.co/docs/inference-providers/pricing) — does not establish the event credit's redemption terms.
- [SmolVLM2-500M-Video-Instruct model card](https://huggingface.co/HuggingFaceTB/SmolVLM2-500M-Video-Instruct)
- [SH17 source and license](https://github.com/ahmadmughees/SH17dataset#license)

The attached 36-hour rover build plan is product context, not evidence of implemented functionality or an instruction to begin hardware/cloud work. The current repository and its accepted interface contracts govern implementation.
