# CLAUDE.md — BOB project guide

@AGENTS.md

## Purpose and reading order

BOB is a construction-worksite inspection project: observe people and PPE, assess observations against the worksite's selected requirements, preserve matching evidence, and eventually show observations in a session-local 2D Twin. Future rover integration adds navigation, supervisor and controller telemetry through explicit interfaces. A useful demonstration must make clear what was observed, what remains unknown, and which components are actually connected.

This file supplies durable product context and Claude's collaboration workflow. The imported [AGENTS.md](AGENTS.md) supplies the detailed engineering rules; keep it authoritative for those rules rather than maintaining a second copy here.

| Source | Use it for |
| --- | --- |
| [README.MD](README.MD) | Overall project, architecture, workstream status and entry points |
| [README-CV.md](README-CV.md) | Detailed CV progression, run commands, measured results and outstanding acceptance tests |
| [AGENTS.md](AGENTS.md) | CV architecture, schema discipline, data handling, platform constraints and team workflow |
| [integration.md](integration.md) | Interface contracts, ownership, branch registry and integration gates |
| [Dashboard/Twin plan](docs/plans/dashboard-twin-integration-plan.md) | Confirmed product decisions, planned application boundaries and acceptance criteria |
| [Autonomous-driving context](docs/plans/autonomous-driving-context.md) | Planned exploration behavior, off-board BLE prototype, safety boundary and encoder-ready interfaces |
| [SH17 model card](models/sh17.md), [footwear model card](models/footwear-v1.md) | Model provenance, class meanings, limitations, licenses and evaluation evidence |
| [Runtime defaults](configs/default.yaml), [footwear override](configs/footwear.yaml) | Actual configuration and optional specialist activation |

Read the relevant source before changing its component. Inspect the current code and working tree to establish what exists. Planning documents and attachments describe proposals unless implementation and validation demonstrate otherwise; they are not authorization to implement every feature they mention. In particular, the dashboard plan's historical starting-point inventory must be rechecked against the current repository.

Do not copy milestone counts, latency measurements or training scores into this guide. Update their source documents when new evidence changes them. If sources disagree about behavior or ownership, identify the discrepancy and resolve it before making a dependent change; do not silently choose the most convenient interpretation.

## Authorization and collaboration

- **Explain and plan by default. Write application code only when the user explicitly requests implementation or a change.** An explicit request to implement, fix or change behavior authorizes the necessary work within that scope; it does not require the literal phrase “write code.” A question or planning request alone does not authorize implementation. A documentation request authorizes the requested documentation edits.
- Before a new milestone, establish the intended outcome, affected components, constraints and test method. Ask focused questions for material knowledge gaps. Reuse answers already given; do not repeatedly ask about settled decisions or require approval for each routine edit within an authorized task.
- Distinguish user-confirmed decisions, implementation recommendations and unresolved assumptions. Explain material tradeoffs in plain language. Do not invent deadlines, team capacity, hardware readiness or acceptance thresholds.
- Unless the user requests otherwise, make authorized implementation demonstrable: a reproducible command or scenario, understandable output, honest empty/error states and a clear path to inspect results. Prefer a small complete demonstration over unrelated feature expansion.
- Check the branch and working tree, and follow the synchronization workflow in AGENTS.md before implementation. Start feature branches from `main` unless instructed otherwise. Preserve other sessions' changes; coordinate or isolate overlapping work instead of overwriting it. Never restart a teammate-owned server merely to demonstrate a documentation change.
- Commit and push only when requested. Explain what changed, how it was checked, and what remains unvalidated. A successful build is not proof of correct physical-device behavior.

## Whole-project scope and branch boundaries

The intended progression is **CV dashboard first, evidence and inspection workflows, then a read-only 2D Twin**, with later hardware adapters. The dashboard can become useful on the Mac before Jetson deployment or throttle integration. Recheck hardware progress rather than assuming that a referenced Jetson, ESP32 or supervisor is already implemented.

| Responsibility | Boundary |
| --- | --- |
| iPhone capture | Swift captures and streams image, timestamp, session and tracking/pose metadata. Python owns detection and inspection logic. A phone preview is not evidence that server inference or returned boxes are enabled. |
| CV on `main` | Python ingestion, shared inference pipeline, model/derived boxes, per-subject verdicts, frame/pose association, recording/replay and observation outputs. The Mac is the development stand-in for the Jetson. |
| Dashboard and inspection application | Planned consumers of CV observations: worksite profiles, inspection lifecycle, presentation, incident confirmation and evidence. Establish ownership and contracts before implementing them; the CV branch context alone does not authorize these features. |
| Read-only Twin | Presents session-local position, heading, path and appropriately located observations. No motion authority or actuator endpoints. |
| Future hardware/control | Navigation, motor commands, safety supervisor, interlocks and ESP32 control belong to their own workstream. CV observations and ARKit pose do not establish that movement is safe. |

Keep runtime inference shared through `vision.pipeline.Pipeline`; use the existing live/replay frame path and message-admission rules from AGENTS.md. Do not create a second detector implementation for the dashboard or a detector instance per browser. Preserve Python/Jetson portability and the thin Swift boundary.

The three intended hazard categories are **PPE, person in path, and marked restricted zones**. A person box alone does not prove a person is in the rover's path. A drawn polygon does not prove a marked boundary was detected or registered. Where a producer is unavailable, demonstrate it with clearly labeled sample data rather than presenting an implemented capability.

## Worksite inspection semantics — confirmed product decisions

The planned dashboard lets an operator select required eyewear, helmet, gloves, high-visibility vest and safety boots. These are inspection requirements, distinct from visual filters that hide bounding boxes.

- Unchecked means **Not required** for that worksite, not detected or compliant.
- Checked and supported means assess the subject using the actual model/rule evidence.
- Checked with missing model capability means **Required — assessment unavailable**. Keep the requirement visible; do not silently substitute another class.
- Occluded, absent, tiny or uncertain subjects remain **Unverified / Not assessed**. An empty violation list does not prove compliance.
- All requirements unchecked means **No PPE requirements selected**, not an all-clear result.

**Saved requirement changes apply at the next explicitly started inspection.** Bind each inspection to an immutable worksite-profile revision. Saving changes leaves the current inspection and its in-flight observations on their original revision. Reconnecting a browser or phone, or resetting ARKit, does not start an inspection or activate pending requirements.

Keep raw observations and historical evidence intact. New requirements must not rewrite old incidents, alter model confidence thresholds, clear faults or resume motion. Python validates and applies profiles; the browser submits edits and displays results. Starting an inspection is an application action, not a command to arm the rover. These semantics are requirements for the future application, not a claim that the profile service already exists.

## Observations, evidence and presentation

Keep these meanings separate: raw model detection, derived PPE observation, worksite assessment, temporally confirmed incident and actual controller response. A derived box is a per-frame observation; incident confirmation requires an explicitly defined application policy. Confidence on a derived box is not a calibrated probability that PPE is absent.

Every view must distinguish **LIVE**, **REPLAY**, **SAMPLE** and **NOT INTEGRATED**. Freshness is a separate property. Never mix sample events into live counts, attach them to real poses, or use replay as evidence of current worksite conditions. Track video/result freshness separately from pose-packet activity.

Associate evidence with the exact source frame, session and model identity. If an image cannot be saved or found, retain the observation metadata and show that evidence is missing. Dashboard rendering, slow browsers and evidence storage must not create an unbounded inference backlog or block future control loops.

Respect the frozen CV contracts and change process in AGENTS.md. The dashboard plan proposes separately versioned application envelopes for verdicts, requirements and incidents; do not append unversioned fields to frozen messages. Document new consumer interfaces in integration.md before integration.

## Twin and localization meaning

The first Twin is a **read-only, session-local 2D map**, not 3D reconstruction or a persistent site map. The source pose describes the phone camera until a validated phone-to-rover transform exists. A detection's observation position is not the detected person's or hazard's world position.

Use the source frame's validated pose association. Invalid association leaves an observation unlocalized; never fill it with the latest available pose. Session changes invalidate coordinate-dependent state and registration. Preserve old evidence in its original session rather than moving it onto the new map. Stale positions must be labeled as last known, without invented motion.

For future telemetry, show supervisor-requested state and controller-reported state separately. Missing feedback is unknown. A command acknowledgment or neutral output is not proof of physical standstill. Dashboard and Twin interactions must not clear faults or issue motion commands.

## Models, reviewed data and evaluation

Use the model cards and actual configured class mapping when interpreting outputs. SH17 recognizes eyewear generally; detected glasses do not establish protective certification. The optional footwear specialist follows the accepted visual boot convention, which includes some ordinary, hiking and winter boots; its class name is not proof of certified safety footwear.

Reviewed training data is not yet a trained model, a saved checkpoint is not automatically the active runtime model, and held-out dataset metrics are not worksite acceptance. Verify the selected weights, hash, runtime configuration and active rules at each handoff. Preserve the existing PPE model when adding a footwear specialist so unrelated classes are not lost through incomplete training labels.

Follow AGENTS.md for human-over-assisted review precedence, training/evaluation isolation, licenses and artifact storage. Under the approved footwear review policy, ambiguous examples remain pending; recognized fashion/rain boots are shoes, unclear rubber boots remain pending, and the first run excludes images containing unresolved or drop-image boxes. Do not quietly convert pending examples into training labels. Changing the label convention requires an explicit decision and documented dataset/model version.

## Development and completion checks

- Use `uv run` for Python commands and the repository's pinned environment. Use the device resolver and configuration instead of assuming a Mac GPU or an installed Jetson runtime.
- Work through the applicable README progression and define measurable acceptance before implementing a milestone. Use fixtures and recorded replay for deterministic checks; retain physical-device checks where required.
- For an implementation milestone, run `uv run pytest` and relevant interface/platform checks from AGENTS.md and integration.md. Update the README progression row and step section with observed results and remaining gates. Never claim that an unexecuted or skipped check passed.
- For documentation-only changes, verify factual consistency, referenced paths and the diff. Do not mark a software milestone complete or report previously run tests as newly executed.
- Keep Swift minimal. Edit the XcodeGen source specification rather than the generated project. Automate supported build/setup checks where available; give precise manual instructions for remaining device trust, permission, signing or physical-test actions instead of claiming all Xcode setup is inherently manual.
- Before handing off, separate **implemented**, **automatically tested**, **physically validated** and **planned**. Report the actual configuration, artifact or command the next person needs, with material limitations and ownership clearly stated.
