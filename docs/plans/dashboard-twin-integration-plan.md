# BOB dashboard and 2D Twin integration plan

Planning date: October 10, 2026. Status: proposed implementation plan; no application implementation performed for this plan.

## 1. Scope and planning basis

User-confirmed sequence: **CV dashboard first; read-only 2D Twin follows.** Present the three original hazard categories—PPE, person in path, and marked restricted zone—with clearly labeled sample data wherever a real producer is unavailable. Treat this repository as the complete implementation inventory. Jetson deployment and ESP32/throttle integration have not started.

Additional user requirement: the dashboard lets an operator check or uncheck which PPE conditions are required for a worksite, such as eyewear protection and safety boots. This configures inspection requirements; it is not merely a display filter. The Twin remains read-only. Requirement changes do not grant actuator authority.

No deadline or available builder count was confirmed. Therefore this plan uses dependencies and acceptance gates, not the earlier document's hour-22/hour-26 schedule. Ownership below denotes responsibilities, not an assumption that separate people are available.

Reviewed sources:

- `/Users/hboho/Downloads/safety-twin-integration-plan(1).md`, in full.
- `/Users/hboho/Downloads/Knight Hacks 2026 Construction-Safety Rover  36-Hour Executable Build Plan.md`, in full.
- Repository `AGENTS.md`, `README.MD`, `integration.md`, runtime configuration, Swift capture implementation, Python transport work, perception pipeline, recording/replay, and C1/C2/C3 schema definitions.

The downloaded documents are planning inputs. Their statements about existing services, proposed repositories, ownership, and schedules are not evidence of implemented capabilities or instructions to start implementation.

### Changes recommended to the attached plan

1. Build the dashboard on the Mac now; do not wait for a moving rover.
2. Establish replay and sample scenarios early so integration can be tested without hardware.
3. Start the Twin only after a working CV/evidence dashboard, but allow phone-only localization validation before the rover is ready.
4. Keep the existing BOB repository and frozen CV contracts. Do not create or rename a repository to match the old proposal.
5. Establish one incident/evidence service; none exists to reuse yet. Begin with JSONL and JPEGs, consistent with the repository's local recording approach. SQLite is an optional later storage implementation, not a prerequisite for a map.
6. Replace “safe to move” UI language with individual observed readiness/fault states. Missing hardware telemetry must remain unknown.

## 2. Verified starting point

| Area | What exists | What the dashboard cannot yet assume |
| --- | --- | --- |
| Perception | `vision.pipeline.Pipeline`, bounding boxes, derived PPE observations, per-subject verdicts, active/inactive rules, Mac webcam display | A live iPhone-to-inference service or validated real-world accuracy |
| iPhone | ARKit preview, JPEG/pose encoding, `.bobrec` recording, statistics | A working sender: `CaptureController.emit` still has the Step 5 sender placeholder; no detection overlay |
| Transport | Working-tree receiver, `tools/replay_client.py`, and `tests/test_server.py`; the receiver moved from `vision/server.py` toward `vision/server/` during this review | An accepted completed milestone. The inspected receiver displayed frames and health, not inference results; recheck the completed refactor before implementation |
| Contracts | Frozen v2 C1 frames/poses, C2 `DetectionEvent`, C3 `StreamHealth` | Incident severity, evidence links, controller state, or a complete PPE-verdict transport |
| Localization | ARKit camera transform to metric phone pose/yaw | Timestamp pose association, calibrated phone-to-rover transform, registered route or zone map |
| Persistence | `.bobrec` support and receiver health JSONL work | A durable incident/evidence store |
| Hardware/control | Planned in documentation | Implemented Jetson service, navigation, hazard supervisor, ESP32 feedback, throttle or measured standstill |
| Browser UI | None found | An existing dashboard service or frontend stack |

The current SH17 model supports person and several PPE classes. The boots rule is inactive without a model containing `safety-boots`. A person box does not establish person-in-path status. A derived PPE box is a per-frame observation, not a temporally confirmed incident. The current C2 payload contains boxes but omits `FrameResult.verdicts` and rule availability.

The working tree changed during this read-only assessment. This inventory describes inspected behavior, not a tested or frozen revision. Step 1 must recheck the transport refactor and its tests before any implementation depends on it.

## 3. Product shape

Use one local browser application with three views added in sequence:

| View | First useful content | Later connection |
| --- | --- | --- |
| Live CV | Annotated image, PPE observations, three hazard-category cards, source mode, model/rule availability, stream and inference health | Live iPhone inference; actual person-in-path and zone observations |
| Evidence | Selected observation/incident, matching snapshot, timestamps, source, reason, downloadable metadata | Confirmed incidents and correlated supervisor/controller responses |
| Twin | Session-local 2D pose, heading, bounded path and observation-position incident pins | Calibrated rover pose, registered route, waypoints/zones, real navigation and hardware telemetry |

The operator opens the dashboard on the Mac initially. The same browser application can later be opened by another device on the private LAN. An in-app Swift bounding-box overlay is a separate optional deliverable; it is not necessary for this browser dashboard and is not included in this plan.

Every view distinguishes **LIVE**, **REPLAY**, **SAMPLE**, and **NOT INTEGRATED**. Freshness is separate: a live source can be stale, disconnected, or invalid. A disabled model rule is not the same as an unverified subject or an absent producer.

Sample scenarios run in a separate, visibly labeled workspace. If a category card is shown beside live CV before its producer exists, it displays “Not integrated”; opening its sample demonstration must not pin a sample event to a real pose or overlay it on a real frame. Sample/replay data never enter live counts or operational state.

### Worksite requirements panel — included in the first dashboard

Provide a named worksite profile with checkboxes for eyewear protection, helmet, gloves, high-visibility vest, and safety boots. Show saved requirements and any pending edits clearly. Recommend persisting profiles locally so requirements can be reused across inspections; scope profiles by worksite and bind each inspection to a specific revision.

| Requirement setting | Assessment condition | Dashboard meaning |
| --- | --- | --- |
| Unchecked | Any observation | **Not required** for this worksite; no missing-item inspection incident is raised under this policy |
| Checked | Supported model/rule with sufficient subject evidence | Show **Detected** or **Not detected**, with candidate/confirmed incident status handled separately |
| Checked | Subject occluded, absent, too small, or uncertain | **Not assessed / Unverified**; never a pass or an assumed violation |
| Checked | Required producer/class is unavailable | **Required — assessment unavailable**, with the reason; keep the requirement visible |

For example, a worksite may require eyewear and a helmet while leaving gloves optional. Bare hands then do not create a worksite missing-gloves incident. Selecting safety boots while SH17 is active preserves that requirement but displays that the current model cannot assess it. Capability limitations remain visible: the existing glasses class recognizes eyewear generally, so detection alone cannot verify protective certification.

Keep raw detections and detector observations intact. Python applies the worksite profile to inspection results and incident generation; the browser renders the result and submits profile edits. A separate visibility filter may hide boxes without changing requirements. Unchecking PPE must not erase past incidents, change detector confidence thresholds, disable person-in-path or zone protection, clear physical faults, or resume motion.

Use an explicit “Save for next inspection” action rather than treating an unsaved checkbox change as active policy. Show the selected worksite and active requirement revision on CV, evidence, and Twin views, with saved changes labeled “Pending — next inspection.” Publish saved revisions to all connected browsers and reject conflicting edits rather than silently overwriting a newer revision.

**User-confirmed decision:** saved changes apply at the next inspection. When an operator explicitly starts a new inspection, the backend atomically binds its inspection ID to the selected worksite's latest saved requirement revision. All observations, assessments, and incidents in that inspection use that immutable revision, including work still in flight when a newer profile is saved. Unsaved edits do not apply. Saving a profile, reconnecting a browser or phone, and resetting the ARKit session do not themselves start a new inspection or activate pending requirements. Historical results always retain their original policy; any replay under different requirements is a separately labeled analysis. Starting an inspection is an application-level action and does not arm or move the rover.

## 4. Step-by-step implementation sequence

### Step 1 — Establish the baseline and ownership

**Work:** review and land or explicitly isolate the in-progress transport work; identify a known baseline revision; record implemented versus planned capabilities. Assign owners for CV publication, dashboard/evidence, localization, and eventual hardware adapters. Preserve unrelated working-tree edits.

Use an isolated dashboard worktree/feature branch based on the accepted BOB baseline. Do not assume `main` or the old plan's `safety` branch exists. Establish the integration branch with the repository owner, then update the branch registry and apply `integration.md` gates when applicable.

**Deliverable:** capability inventory, ownership table, baseline revision, and consumer interfaces.

**Gate:** the team can identify the source of every proposed dashboard field, including fields that currently have no producer.

### Step 2 — Define dashboard contracts and deterministic scenarios

**Work:** define a separately versioned observation envelope around the unchanged C2/C3 messages. Specify source identity, source mode, session, source frame sequence, event identity, image dimensions, evidence references, observation timestamps and their clock domains, verdicts, and capability/freshness states.

Define a separate versioned worksite-requirements contract: worksite/profile identity, revision, selected PPE requirements, and activation boundary. Reference the applied revision from inspection assessments and incidents without modifying frozen CV messages. Add scenarios for unchecked requirements, checked-but-unsupported requirements, all requirements unchecked, profile switching, and pending versus active edits.

Create fixtures for all three hazard categories, including normal observation, candidate/confirmed incident, unverified PPE, inactive boots rule, missing evidence, tracking loss, stale source, disconnect, source restart, and session reset. A confirmed sample event is sample data, not a confirmation algorithm.

Keep `wearing`, `not_wearing`, and `unverified` per subject/rule. Do not infer a positive PPE verdict from an empty list of violation boxes. Treat confidence on a derived box as the subject's confidence, not a calibrated probability that PPE is absent.

**Deliverable:** contract descriptions, small labeled fixtures, and a source/capability matrix. No motor-command interface is introduced.

**Gate:** the same dashboard consumer can read sample and future real envelopes without changing page components; source mode and provenance are always visible.

### Step 3 — Build the first CV dashboard using sample and recorded inputs

**Work:** build the local browser service, annotated frame panel, hazard cards, connection/tracking status, rule availability, and a compact recent-observation list. Use a separate scenario view for unavailable hazard categories. Include explicit empty, loading, stale, and error states from the start.

Include the worksite requirements panel in this first dashboard milestone. Make requirement checkboxes distinct from box-visibility filters. Persist saved profiles through a Python-owned configuration service, with backend validation and a visible save result. If no PPE requirements are selected, display “No PPE requirements selected” rather than an all-clear result.

Recommended stack: a new FastAPI browser/API service plus locally served HTML/CSS/JavaScript; use WebSocket for observations and a correlated image delivery path. Retain the existing phone WebSocket receiver rather than rewriting C1 in FastAPI. FastAPI supports WebSocket endpoints; it is a new dependency here, not an existing repository service. See the [official WebSocket documentation](https://fastapi.tiangolo.com/advanced/websockets/).

Keep image and result identity together. Prefer initially sending a server-annotated upright image produced from the exact inference frame. The browser may resize it without independently shifting boxes. If separate browser overlays are added later, apply the image's exact scale and letterbox offsets and reject unmatched frame IDs.

**Deliverable:** an offline-capable dashboard that visibly demonstrates all three categories, plus a recorded-input path.

**Gate:** no boxes or metadata are displayed on the wrong frame; samples are unmistakable; missing producers never display a healthy/clear state. Closing or reconnecting a browser does not affect the producer.

### Step 4 — Connect real Python inference before depending on live phone transport

**Work:** pass recorded frames, and optionally the existing Mac camera source, through the existing `Pipeline`. Publish its boxes, verdicts, active/inactive rules, model identity, inference timing, and matching annotated image. Run inference once per frame and share results with clients; never instantiate a detector per browser.

Apply the active worksite requirement revision in the Python inspection layer. Preserve the original pipeline verdicts and derived observations; generate worksite assessments only for required checks, preserving unavailable/unverified states. The default operator overlay should reflect required inspection checks, while a clearly identified diagnostic view can expose raw detections independently.

Assemble C2 events through a CV-owned adapter. Where valid timestamp association is not yet available, emit the correct invalid-pose state rather than filling it from the latest pose. Map placement remains disabled for those observations.

**Deliverable:** a functioning CV dashboard showing actual PPE/person observations in replay or Mac-camera mode. Person-in-path and marked-zone categories remain sample-only until their producers are implemented.

**Gate:** a fixed recording produces reproducible semantic results within declared numeric tolerances; video/result correlation remains correct under slow inference; unverified and inactive rules are visible.

### Step 5 — Complete and validate live iPhone-to-Mac streaming

**Work:** complete the thin Swift sender; validate local-network permission, reconnect behavior, bounded send work, and session changes. Connect the receiver's latest-frame slot to `Pipeline`, then the dashboard publication adapter. Continue dropping superseded frames rather than accumulating latency.

Expose capture, receive, inference, and display rates separately. A healthy pose-packet stream must not make frozen video appear fresh: track last frame age, last inference-result age, tracking quality, and stream packet age independently. Existing `StreamHealth.stale` reflects accepted packet activity and is insufficient by itself for all these indicators.

**Deliverable:** real phone video with Python-generated boxes displayed in the browser on the Mac.

**Gate:** on a physical iPhone, test portrait/landscape, full person versus partial body/hands, near and intended operating distances, no person, camera occlusion, background/foreground, disconnect, and session reset. Verify honest UI states and frame alignment; record detector misses separately from transport/UI failures. No promise that every visible hand or person will be detected.

### Step 6 — Add incident handling and durable evidence

**Work:** introduce one application-layer incident/evidence service. It owns observation-to-incident policy and persistence; the frontend does not invent confirmation, severity, or actions. Keep this separate from `vision/` detection logic and from future motor authority.

Define a bounded temporal-confirmation policy per real producer before promoting observations to confirmed incidents. Specify repeated-observation grouping, duplicate suppression, episode end, reset behavior, and maximum history. Avoid counting each detected frame as a new incident. Until a policy exists, display observations rather than confirmed hazards.

Persist the worksite identity and applied requirement revision with each assessment/incident and retain the corresponding immutable profile revision. A later checkbox change must not relabel or delete historical evidence. Report requirement changes separately from hazard resolution.

Use one writer for incident JSONL and JPEG snapshots. Publish metadata independently of snapshot success. Add storage limits, retention, restart recovery, and missing-image/write-failure states. Existing `.bobrec` files are useful input recordings; they are not already an incident store. If SQLite later becomes necessary, put it behind the same repository interface and retain a single writer; [SQLite WAL documentation](https://sqlite.org/wal.html) describes its single-writer limit.

**Deliverable:** selectable incident/observation history with source-frame evidence and export.

**Gate:** metadata survives restart; the evidence frame matches the source; duplicate/replayed messages do not inflate incident counts; disk/image failure is visible and cannot stall inference or future control.

**Milestone A: usable CV dashboard.** This milestone ends here. Jetson, motors, and the Twin are not prerequisites.

### Step 7 — Establish localization and coordinate meaning

**Work:** implement and validate the repo's timestamp association milestone: nearest eligible pose to the source frame's `iphone_frame_ts_ns`, same session, normal tracking, within configured tolerance (currently 50 ms). Invalid association leaves the observation unlocalized. A new session clears buffers and pending associations; late work from a retired session must not appear in the active view.

The current pose is the **phone camera pose**. Validate a 2D projection in meters using the repository's +Y-up ARKit convention. Preserve the documented positive-left yaw and test the display with measured forward travel and turns. Define the phone-to-rover mounting transform with the navigation owner later; do not label an uncalibrated phone marker as the rover center.

**Deliverable:** validated phone-localization output, frame/session identity, and projection specification.

**Gate:** forward/left/right tests show no mirrored map or inverted heading; stale/limited tracking stops path updates; reset starts a new coordinate frame. Association failures keep their images and observations.

### Step 8 — Add the read-only 2D Twin

**Work:** add an SVG map with position, heading, meter scale, bounded breadcrumbs, and selectable incident pins linked to the evidence view. Before mounting calibration, label the moving marker “Phone camera.” Pins mean **observed from here**, not the person's or hazard's world position.

Show unlocalized incidents in a list. Show the last valid position as stale without extrapolating. Route/waypoint and zone geometry may be sample or schematic first; distinguish that from geometry registered to the active session. Reset invalidates route/zone registration and starts a fresh trail. Older incidents remain available in their own session views.

Propose a maximum initial map refresh of 5 Hz and measure the effect; this is a UI budget, not a control timeout. Downsample path points and bound retention independently of source capture rate.

**Deliverable:** a phone-driven or replay-driven operational Twin that works before the rover moves.

**Gate:** every pin resolves to the correct event/evidence/session; no cross-session paths; unknown positions stay unlocalized; a failed or disabled Twin leaves CV and evidence functional.

**Milestone B: CV dashboard plus read-only 2D Twin.** Neither live throttle nor Jetson deployment is required.

### Step 9 — Replace sample producers one category at a time

**Work:** integrate actual person-in-path and marked-zone producers when their owners build them. A person box is input to a future path policy, not a stop decision. A displayed map polygon is not proof of boundary detection. Define producer-owned region/marker semantics, confirmation, availability, and evidence correlation before connecting each feed.

Register any new non-PPE hazard contract separately with the integration owners. The README anticipates a v3 change for scene findings; that requires an explicit contract decision. Do not silently put scene hazards into v2 or treat a UI envelope as approval to change CV semantics.

**Gate:** each real category passes repeatable positive, negative, stale, and missing-input cases before its sample badge is removed. Live and sample histories remain separate.

### Step 10 — Connect Jetson and controller telemetry when available

**Work:** deploy the same application boundaries on the Jetson; verify its actual Python/JetPack/runtime compatibility and device resolution. Keep target-engine creation/parity in the CV deployment milestone. Rerun the dashboard fixture/replay suite and measure target-device throughput with UI/Twin off and on.

Add read-only adapters for navigation, supervisor requests, and ESP32 reports. Display requested state/reason, actual reported mode/fault/output, command/ack correlation, timestamp and freshness separately. Missing telemetry remains “Not integrated” or “Unknown,” never a fabricated zero throttle, disarmed state, or successful stop.

A controller acknowledgment or neutral actuator output does not establish physical standstill. Show physical-stop timing as “Not measured” unless an independently validated measurement exists. Hardware commissioning and all actual movement gates remain owned by the hardware/supervisor workstream; this dashboard plan does not authorize or implement them.

**Deliverable:** connected real producers using the same UI contracts and views.

**Gate:** substitutions require adapter/configuration changes rather than redesigned pages; no sample state leaks into live operation; dashboard failures do not delay the independently tested hardware response.

## 5. Contracts that make later integration cheaper

| Feed | Reuse or add | Essential information |
| --- | --- | --- |
| Phone capture | Reuse C1 v2 | Session, sequence, source timestamp, image metadata, pose/tracking |
| Detection result | Reuse C2 v2 | Event/frame identity, model and derived boxes, upright dimensions, validity and inference timing |
| Stream health | Reuse C3 v2 | Stream session, stale flag, drops, last reception and tracking; supplement frame/result freshness outside C3 |
| PPE presentation | New separately versioned sidecar | C2 event reference, per-subject verdicts, active/inactive rules, source mode |
| Worksite requirements | New Python-owned configuration contract | Worksite/profile ID, immutable revision, selected checks, next-inspection activation, pending/active status |
| Inspection lifecycle | New application contract | Inspection ID, worksite, bound requirement revision, explicit start/end; independent of ARKit session identity |
| Worksite assessment | New application contract | Source observation, worksite and applied profile revision, required/not-required status, assessment availability and result |
| Confirmed incident/evidence | New application contract | Incident ID, source observations, hazard, confirmation state, evidence status, occurrence times, location meaning |
| Twin configuration | New read-only contract | Session/frame identity, units, transform revision, route/zone registration status |
| Navigation/supervisor | Future producer contract | Requested state/reason, waypoint/error, producer sequence, observation time, related incident |
| Controller feedback | Future producer contract | Reported mode/fault/output, acknowledged command sequence, report receipt time; unavailable fields remain null/unknown |

Do not append fields to existing frozen messages: their validators reject extras. Any actual `vision/schema/` change must follow the version bump, fixture, exported JSON Schema, and Swift-mirror requirements together. Sidecars have their own version and tests, and are documented as new interfaces in `integration.md`.

Keep original recorded identities available for evidence; use a separate playback/run identity for replay instances. Reconnect obtains a current snapshot and a bounded history, with explicit gaps and event deduplication. Do not merge records from different runs solely because sequence numbers match.

## 6. Runtime isolation and timing

Use a producer/consumer boundary: capture and Python inference publish observations; the dashboard/evidence layer consumes them; the browser renders them. Future supervisor/controller feeds enter through observation-only adapters.

- Keep browser fan-out, image encoding, disk persistence, and history queries outside inference and future control loops. A separate process with bounded publication is the recommended starting boundary.
- Coalesce high-rate frame/pose state to the latest value. Treat incident metadata separately so any overflow or persistence loss is reported explicitly.
- The receiver inspected before the in-progress refactor wrote optional recordings and health callbacks synchronously on its receive/event-loop path. Recheck the final implementation and do not reuse that pattern as proof of nonblocking evidence delivery before adding dashboard persistence/fan-out.
- Never launch model inference or one evidence writer per browser. Limit client queues, image sizes, and history queries; disconnect or resynchronize slow consumers.
- Browser routes expose observation, history, replay controls, and worksite inspection-profile editing. Python validates and applies profile changes. Neither profile nor replay controls can send actuator commands, alter live route/motor-safety policy, clear faults, or resume motion. The Twin itself remains read-only.
- Use same-host monotonic measurements for processing durations, wall time for human-readable occurrence dates, and phone timestamps for same-phone association. State the clock domain for each field.
- The existing `jetson_receive_ts_ns` means receiver time even on the Mac; preserve its contract and label the host correctly in the UI. Do not relabel Mac metrics as Jetson results.
- Receiver “added latency” is relative to a minimum observed offset, not absolute phone-to-host latency. Do not subtract device clocks or present inference duration as end-to-end latency.

## 7. Acceptance and delivery gates

| Gate | Evidence required |
| --- | --- |
| Contract integrity | Valid/invalid fixtures, unchanged v2 fixtures unless deliberately versioned, source modes and unknown values tested |
| CV display | Matching frame and boxes under resize, slow inference, rotations and reconnects; per-subject unverified states preserved |
| Worksite requirements | Check/uncheck semantics, persisted/reloaded profiles, unsupported requirements, no-requirements state, revision conflict handling; saved edits leave the current inspection unchanged and activate only on explicit next-inspection start; reconnects/ARKit resets do not activate edits; historical and in-flight results retain their bound revision |
| Incident integrity | Temporal policy documented; duplicate suppression; matching snapshot; missing evidence and restart recovery tested |
| Twin integrity | Measured direction/scale checks; correct session association; reset/stale handling; unlocalized fallback |
| Isolation | Slow/closed browser, killed UI worker, full storage, missing JPEG, producer restart and disconnected source remain bounded and visible |
| Offline readiness | With upstream internet disconnected but private LAN intact, assets, video, map, evidence and history work without CDN/cloud dependencies |
| Hardware handoff | Same replay scenarios pass on the Jetson; real telemetry provenance; controller requests/reports separate; on/off resource measurements recorded |

Run required repository tests and relevant new consumer tests at implementation milestones, and G1–G8 when integrating as applicable. Record actual physical-iPhone results in the README rather than treating simulator tests as device validation. Performance thresholds should be agreed after a baseline run; none of the proposed refresh budgets are achieved measurements.

For implementation planning, proposed ownership boundaries are `dashboard/` for service/static UI/adapters, a separate application incident/evidence module, dashboard-specific tests, and `docs/` for contracts/runbooks. No application modules or implementation directories were created for this plan. CV-owned changes stay with the CV owner. Namespace future configuration under the relevant component and document interfaces before merging.

## 8. Recommended work order and scope cuts

Critical path: baseline/contracts → sample dashboard → real recorded CV → live phone CV → incidents/evidence → timestamp localization → 2D Twin → additional real hazard adapters → hardware deployment/telemetry.

Independent work can proceed concurrently: the dashboard shell can consume fixtures while the CV owner completes phone transport; localization tests can be prepared before the Twin UI. With one builder, follow the critical path in order. Do not divert the future hardware owner into map styling.

If time becomes tight, retain annotated CV, source labels, freshness, and evidence first. Keep unavailable hazards as explicit sample demonstrations. Defer the map before compromising evidence correlation, and defer route registration or hardware panels before pretending they are connected. A recorded demo must retain its REPLAY label.

Defer 3D reconstruction, persistent mapping across resets, worker identity, inferred metric hazard positions from image boxes alone, cloud services, remote driving, route editing, thermal/gas feeds, and speculative compliance percentages.

The first acceptance target is specific: **open a browser on the Mac, play a known recording through the real Python pipeline, see correctly aligned detections and honest PPE status, and demonstrate the other two hazard categories in a clearly separate sample workspace.** Then connect live iPhone data, establish durable incident evidence, and extend the same contracts into the 2D Twin.
