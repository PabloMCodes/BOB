# BOB dashboard, rover-to-laptop sync and 2D Twin integration plan

Planning date: October 10, 2026 (revision 2). Status: **Steps 0–9 implemented on `autoCV` on the Mac (Milestones A, B, C in software); physical Twin walk test and incident calibration pending; Steps 10–11 not started.** The progression row "D" in [README-CV.md](../../README-CV.md) is the source of truth for what is built, tested and measured. Revision 2 adds the rover-to-laptop data link (store locally on the rover, resynchronize when the link returns) and a frontend-ready backend API, and corrects the revision 1 inventory against the current `autoCV` tree.

## 1. Scope

Requested in this revision:

1. Feed data produced on the rover computer (Jetson; the Mac today) back to the operator laptop so it can drive the CV dashboard and the 2D Twin.
2. Deliver a **backend only**: a documented API and live feed that a frontend can plug into. No frontend is built here.
3. Rover-side behavior similar to a car that records on board and uploads when it reconnects: the rover keeps working and recording when the laptop link drops, and the laptop catches up when the link returns.
4. Carry the evidence images that the worksite's required checks depend on.

Earlier user-confirmed decisions still apply: CV dashboard first, read-only 2D Twin after; three hazard categories (PPE, person in path, marked restricted zone) with clearly labeled sample data where no producer exists; worksite requirement checkboxes with saved changes applying at the **next explicitly started inspection** (§4).

User-confirmed on October 10, 2026 for this revision: **D1** phone ↔ rover computer stays on a rover-local link; **D2** no cloud or internet upload; **D3** assessments and incidents are computed on the rover. **D7** (incident confirmation) was delegated to this plan and is defined in §8 with parameters still to be calibrated.

No deadline or team capacity is confirmed, so the plan uses dependencies and gates, not a schedule. Revision 1 reviewed two downloaded planning documents (`safety-twin-integration-plan(1).md`, the 36-hour build plan); revision 2 did not re-read them.

## 2. Corrections to the request and to revision 1

| # | Assumption | What the repository shows | Consequence for this plan |
| --- | --- | --- | --- |
| 1 | Data is already pulled from the WebSocket integration | The only WebSocket is **inbound C1: phone → server** (`FrameServer`, binary, port 8765). It never sends results out, and it counts C2/C3 messages sent on it as bad input. All outputs go to local files under `runs/server/<time>/`; no process or machine receives them over the network. | Keep WebSocket as the technology, but add a **new, separate outbound endpoint** on the rover with resume, acknowledgment and gap semantics (§5). Do not reuse or extend the frozen C1 connection (§5.6). |
| 2 | Jetson data is available to feed back | No Jetson deployment exists. J1–J6 in [jetson-handoff.md](../jetson-handoff.md) are marked not run. The Mac runs `vision.server`. | Build and test the rover role as a separate process on the Mac now; move it to the Jetson unchanged after J1–J6 pass. |
| 3 | The rover reconnects "to the internet" to update the feed | The working link is a local network (iPhone hotspot used in Step 5). No cloud service exists. | "Reconnect" means **rover ↔ laptop over the local network**. No cloud upload (D2, confirmed). |
| 4 | The Twin shows the rover's position | The pose is the **phone camera's** ARKit pose in a session-local frame; there is no phone-to-rover transform. | The Twin labels the marker "Phone camera"; pins mean "observed from here", never the person's position (§7). |
| 5 | The rover's track is already available | Standalone pose packets reach only the associator; they are not published or stored. C2 carries a pose only for frames that were processed. | Add a track sidecar fed from `FrameServer.admit()` (Step 3). |
| 6 | Required checks determine which images are captured | Requirements are an inspection policy. The detector, rules and raw observations are independent of them. | Capture evidence from raw observations; apply requirements in the assessment layer. Unchecking a requirement never deletes evidence (§4). |
| 7 | Revision 1: the Swift sender is a placeholder | `StreamSender` is implemented; a 117.8 s live iPhone run streamed 1179 frames with 0 sequence gaps (README Step 5). | Live phone input is available on the Mac; physical kill tests are still pending. |
| 8 | Revision 1: association means nearest pose within 50 ms | Each frame carries its own ARFrame pose (`pose_dt_ms = 0`). `timing.pose_tolerance_ms` is unused; `dt_exceeded` is reserved (README Step 7). | Track and pins use the same `associate()` validity rules. No pose buffer is introduced. |
| 9 | Revision 1: marked zones are sample-only | C7 restricted-zone inspection (`scene_findings.jsonl`, `scene_version: 1`) runs on the Mac live and in replay; physical tape acceptance is pending. C8 walkway is a library with no CLI or live output yet. | Marked zone is a **real prototype producer** (show as LIVE/REPLAY with "physical acceptance pending"). Person in path and walkway stay NOT INTEGRATED / SAMPLE. |
| 10 | Revision 1: ESP32 integration not started | A standalone ESP32 BLE motor/speaker bench test exists, driven from a Mac terminal ([hardware/esp32](../../hardware/esp32/README.md)). Status prints go to USB serial only; no telemetry returns over BLE. | Controller feedback stays NOT INTEGRATED. Neither the rover API nor the laptop service may import or call the BLE client. |
| 11 | Live video can be forwarded as-is | The phone sends about 259 KB per 1920×1440 frame at 10 Hz (2.66 MB/s measured). | Forward a reduced live preview; send full-resolution images only as evidence, with a bandwidth cap (§5.4). |

Still true from revision 1: C2 omits per-subject verdicts and rule availability; there is no browser UI, no FastAPI dependency, no incident store and no confirmation policy.

## 3. Verified starting point

| Area | Implemented today | Not available yet |
| --- | --- | --- |
| Capture | Swift ARKit capture, `StreamSender` (1 frame in flight, reconnect), `.bobrec` recording | Physical kill tests (a–d) |
| Transport | `vision/server/`: `FrameServer` (latest-frame-wins slot, `admit()`, C3 every 100 ms), `tools/replay_client.py` | Any outbound publication to other processes or machines |
| Inference | `server --detect`: shared `Pipeline` → C2 `DetectionEvent` per processed frame, per-rule verdicts in memory (`Detection.verdicts`) | Verdicts or active/inactive rules in any published message |
| Pose | Frame-bundled pose with `associate()` validity reasons | Published pose track; phone-to-rover transform |
| Scene | C7 zones via `SceneInspector` + bounded `SceneWriter` | Walkway lane check/CLI; person-in-path producer |
| Persistence | JSONL run files, `summary.json`, `.bobrec` | Durable store, resumable cursor, evidence images tied to observations |
| Rover computer | Mac stand-in | Jetson install, engine, J1–J6 |
| Hardware | ESP32 BLE bench test (manual terminal) | Controller telemetry, supervisor |
| Dashboard | None | Any web service or frontend |

## 4. Confirmed product semantics (unchanged)

These are user-confirmed requirements for the future application, not claims that it exists.

| Requirement setting | Condition | Meaning |
| --- | --- | --- |
| Unchecked | Any | **Not required**; no missing-item incident under this profile |
| Checked | Supported rule, sufficient subject evidence | **Detected / Not detected**; incident confirmation handled separately |
| Checked | Subject occluded, absent, small or uncertain | **Not assessed / Unverified**; never a pass or an assumed violation |
| Checked | Producer/class unavailable (e.g. boots with SH17 only) | **Required — assessment unavailable**, with reason |
| All unchecked | — | **No PPE requirements selected**, not an all-clear |

- Saving creates an immutable profile revision. Saved changes apply only when an operator **explicitly starts the next inspection**; the inspection binds atomically to that revision. Reconnecting a browser or phone, resetting ARKit, or reconnecting the rover link never starts an inspection or activates pending edits.
- Historical observations, evidence and incidents keep their original revision. Re-assessing under another profile is a separately labeled analysis.
- Python validates and applies profiles; the browser submits edits and displays results. A box-visibility filter is separate from requirements.
- Starting an inspection is an application action. It does not arm or move the rover.
- Every view distinguishes **LIVE / REPLAY / SAMPLE / NOT INTEGRATED**. Freshness and delivery (real-time vs backfilled, §5.5) are separate properties.

## 5. Rover-to-laptop architecture

### 5.1 Roles

```
 iPhone (on rover)                ROVER COMPUTER (Mac today → Jetson)                        OPERATOR LAPTOP
 ┌───────────────┐  C1 WS   ┌──────────────────────────────────────────────┐   sync    ┌──────────────────────────────┐
 │ ARKit capture │────────► │ vision.server  (unchanged frame path)         │  link     │ bob hub                      │
 └───────────────┘          │   Pipeline → C2 / verdicts / C7 / pose track │ (LAN,     │  sync client → replica store │
                            │        │ bounded hand-off (never blocks)     │  may drop)│  evidence cache              │
                            │        ▼                                     │           │  worksite profile authoring  │
                            │ edge writer thread → EDGE STORE (SQLite WAL  │◄─────────►│  frontend API: REST + WS     │
                            │   + evidence JPEG files)                     │           │  OpenAPI + fixtures          │
                            │        ▲ read-only                           │           └──────────────┬───────────────┘
                            │ edge API process (sync, live, blobs,         │                          │ HTTP/WS
                            │   inspection start/end, profile delivery)    │                          ▼
                            └──────────────────────────────────────────────┘                  browser (future frontend)
```

| Role | Runs on | Owns | Must not |
| --- | --- | --- | --- |
| `vision.server` + publication hook | Rover | Frames, inference, association, C2/C3/C7 (CV-owned) | Wait on storage, the network or clients |
| Edge writer + edge store | Rover | Durable, ordered records; evidence files; inspection binding; assessments; incident policy | Live inside `vision/` detection logic |
| Edge API | Rover, separate process | Serving the store to the hub; accepting inspection/profile commands | Expose motion, arming or fault-clearing endpoints; run inference |
| Hub | Laptop | Replica, link state, profile authoring, frontend API | Invent confirmation or severity; talk to BLE/ESP32 |
| Frontend | Browser | Rendering | Connect to the rover directly |

Rationale:

- **The rover is the source of truth.** Assessments, incidents and evidence are produced on the rover, so an inspection completed while the laptop is out of range is just as complete after resync.
- **The laptop pulls (subscribes); the rover does not push.** The rover never needs to know the laptop's address, a dead laptop costs the rover nothing, and the Jetson serves one consumer (the hub), never one stream per browser.
- **The SQLite file is the process boundary.** One writer thread in `vision.server`, readers in the edge API (WAL mode allows concurrent readers with one writer). A crashed or slow edge API cannot stall inference. `sqlite3` is in the Python standard library, so this adds no Jetson dependency. Revision 1 proposed JSONL first; SQLite is recommended here because resume-from-cursor, acknowledgment and retention pruning are simple queries rather than custom indexing.
- **On the Mac today, all of it runs on one machine**: `vision.server --detect`, the edge API and the hub as three processes, fed by the live phone or `tools/replay_client.py`.

### 5.2 Identity and ordering

| Field | Meaning |
| --- | --- |
| `edge_id` | Stable rover-computer identity (configured) |
| `store_epoch` | UUID created with the store. A wiped or replaced store gets a new epoch; the hub must not merge across epochs. |
| `run_id` | One `vision.server` start (matches the run directory) |
| `lane`, `seq` | Per-lane monotonic sequence, continuing across restarts within an epoch. `(edge_id, store_epoch, lane, seq)` is the deduplication key. |
| `source_mode` | LIVE / REPLAY / SAMPLE, set by the operator at server start (generalizing the existing `--zones-source-mode`). The server cannot detect that a replay client is feeding it, so this label is declared, not inferred. |
| `session_id`, `seq_id`, `event_id` | Unchanged C1/C2 identities for frame and session association |
| `inspection_id`, `profile_revision` | Bound at explicit inspection start (§4) |

Clocks: order by `seq`, never by time. Record rover wall time and rover monotonic time with each record, plus a `clock_synced` flag (unknown when it cannot be determined; an offline Jetson's wall clock may be wrong). The hub stamps its own receive time. Never subtract laptop and rover clocks to compute latency, as with the existing iPhone/Mac rule.

### 5.3 What travels, by class

| Class | Contents | Delivery | Rover retention |
| --- | --- | --- | --- |
| **Live state** (latest wins, never backfilled) | Preview JPEG of the latest processed frame with its `event_id`; current pose and validity; C3 health; feed ages (last frame, last result, last pose); edge status (disk, writer drops) | Pushed at a capped rate; dropped when the socket is busy | Memory / single row |
| **Control lane** | Inspection start/end, profile revisions received, assessments, incident transitions, evidence metadata, gap and drop notices | Ordered, at-least-once, cursor resume; highest priority | Until acknowledged by the hub **and** past retention |
| **Track lane** | Downsampled valid pose points per session (§7) | Ordered, cursor resume | Same |
| **Observation lane** | Per processed frame: C2 event plus a versioned sidecar (per-subject verdicts, active/inactive rules, C7 reference) | Ordered, cursor resume; lowest priority on backfill | Bounded; the first lane pruned under disk pressure, with a gap notice |
| **Blobs** | Evidence JPEGs, content-addressed by SHA-256 | Pulled by the hub after their metadata arrives | Same as control lane |
| **Bulk** | `.bobrec` raw recordings | Manual operator copy only; never automatic | Per retention decision (D4) |

Separate lanes let the hub catch up on incidents and the track before replaying thousands of per-frame observations, without breaking ordering inside a lane.

### 5.4 Sync protocol (the "reconnect and catch up" behavior)

1. **Hello.** The hub opens `WS /v1/sync` with its last committed cursor per lane. The edge replies with `edge_id`, `store_epoch`, oldest available and head `seq` per lane, rover clock information and `source_mode` of the current run.
2. **Epoch check.** A different `store_epoch` means a new store: the hub archives the old replica view and starts fresh, never merging.
3. **Gap check.** If the hub's cursor is older than the oldest retained `seq`, the edge sends an explicit `gap` record ("records n–m pruned on the rover before sync"). The UI shows the gap; it never closes silently.
4. **Live first, then backfill.** The edge sends live state immediately, then backfill batches in lane priority (control → track → observations), then tails new records as they are written.
5. **Acknowledge after commit.** The hub acknowledges the highest contiguous `seq` per lane only after committing to its replica. The edge prunes only acknowledged records, except under disk pressure, where it prunes the oldest observation records first and writes a notice.
6. **Blobs.** The hub fetches `GET /v1/blobs/{sha256}` for evidence it lacks, rate-limited, and verifies the hash. A missing or failed blob leaves the metadata visible with "evidence missing".
7. **Bandwidth cap.** Backfill and blob transfer obey a configurable byte-rate cap. If the phone and the laptop share one hotspot, unbounded catch-up competes with the phone's 2.66 MB/s stream and would show up as slot drops and stale frames on the rover. The cap is a starting value to measure, not a known-safe number.
8. **Idempotence.** Replays of the same records do not create duplicates or inflate counts.

Hub link states shown to the frontend: **CONNECTED** · **CATCHING UP** (records behind, per lane) · **DISCONNECTED** (last contact time; rover state since then unknown) · **NEW STORE** (epoch changed). A disconnected rover is shown as **unknown**, never as stopped or idle.

### 5.5 Real-time versus backfilled

Each record carries rover observation times; the hub adds receive time and a derived `delivery: realtime | backfilled`. Backfilled observations appear in history and as historical track segments. They never update "current" status cards, never count as live, and are never presented as current worksite conditions.

### 5.6 Why a new WebSocket endpoint instead of the phone's

| Need | Reuse C1 phone socket (port 8765) | New sync endpoint (`/v1/sync`) |
| --- | --- | --- |
| Direction | Phone → vision only; outbound C2/C3 are rejected as bad input | Rover → laptop, with laptop → rover acknowledgments |
| Contract | Frozen v2 binary framing; changes need a schema bump and a Swift mirror | Own versioned envelopes; the phone and Swift are untouched |
| Phone stream protection | Extra clients compete with the phone's one-frame-in-flight flow and latest-frame-wins slot | Separate process reading the store; cannot stall capture or inference |
| Laptop out of range | No storage or resume | Records already stored; resume from per-lane cursor |
| Ordering, duplicates, gaps | Not defined for consumers | `seq` per lane, deduplication key, explicit `gap` records |

The hub connects to the rover, so the rover never needs the laptop's address. A slow hub receives the latest live state and catches up on durable lanes; it never builds a queue on the rover.

### 5.7 Security boundary

Bind the edge API to the rover network, require a pre-shared token kept in `.env` (never committed or printed), and keep it read-only except for: start/end inspection and deliver a profile revision. No endpoint may move, arm, stop, clear faults on or otherwise command the rover. Requested and reported controller states remain future read-only adapters (Step 11).

## 6. Frontend-ready API (served by the hub)

The browser talks only to the hub. The hub publishes an OpenAPI description and a fixture set for every envelope, including SAMPLE fixtures, so a frontend can be built before the rover link is ready.

| Endpoint | Purpose |
| --- | --- |
| `GET /v1/status` | Link state, per-lane lag, source mode, feed freshness (video, results, pose, health), capability matrix: rules active/inactive with reason, producers integrated / prototype / NOT INTEGRATED |
| `WS /v1/live` | Snapshot on connect, then deltas: preview frame reference, live pose, health, new records, link-state changes. Slow clients receive the latest state, not a queue. |
| `GET/PUT /v1/worksites/{id}` | Profile authoring; `PUT` requires the expected revision and returns `409` on conflict |
| `GET /v1/worksites/{id}/revisions/{rev}` | Immutable revision |
| `POST /v1/inspections` / `POST /v1/inspections/{id}/end` | Forwarded to the edge; fails honestly when the link is down or another inspection is active |
| `GET /v1/inspections`, `/v1/assessments`, `/v1/incidents`, `/v1/observations` | Paged history with cursors, filtered by inspection, session, source mode and delivery |
| `GET /v1/evidence/{sha256}` | Image, or a status (pending sync / missing / hash mismatch) |
| `GET /v1/twin/sessions`, `/v1/twin/sessions/{id}/track`, `/v1/twin/sessions/{id}/pins` | Twin data (§7) |
| `GET /v1/preview/latest` | Latest annotated preview JPEG with its `event_id` |

Envelope rules: every response states `source_mode`, `delivery`, freshness and the clock domain of each timestamp. Unknown values are `null` with a reason, never zero or a default. Boxes stay in upright-image pixels with `image_size`, so an overlay can scale them exactly or the preview can be used as rendered.

Recommended stack: FastAPI for the hub and the edge API (generates the OpenAPI description the frontend needs; pure Python, so it runs on the Jetson). It is a new dependency for both. Install uvicorn without optional C extensions on the Jetson unless they are verified there.

## 7. Twin data specification

**Projection.** ARKit world: right-handed, +Y up, origin and initial facing at session start; `yaw_rad = 0` faces the session's initial −Z, positive turns left. Map coordinates: east = `x_m`, north = −`z_m`. In SVG (y down): `svg_x = x_m · scale`, `svg_y = z_m · scale`; heading arrow = (−sin yaw, −cos yaw). Map "up" is the direction the phone faced at session start, not compass north. Height (`y_m`) is ignored.

**Track points** are created on the rover from admitted pose and frame packets, using the same validity rules as C2 (`associate()`): current session, tracking `normal`, not stale, yaw defined. Invalid poses end the current segment. Proposed downsampling, to be measured: emit when moved ≥ 5 cm, turned ≥ 2°, or 1 s elapsed while valid. Retention per session is bounded.

**Sessions.** A new `session_id` starts a new map; old sessions remain viewable but are never merged or drawn on the new one.

**Pins.** An observation, assessment or incident with `pose_valid = true` is pinned at the camera position of its own frame, labeled "observed from here", optionally with a heading wedge. Invalid association → listed as unlocalized with its reason; never placed using the latest pose.

**Staleness and the link.** Stale pose → last known position labeled with its age, no extrapolation. Link down → "last synced at *t*; rover position since then unknown". After reconnect, the backfilled segment appears in a distinct historical style.

**Later enablers, not in scope:** phone-to-rover mount transform (with the navigation owner); person or hazard world positions (would need range, e.g. the iPhone's LiDAR depth, which is not streamed today); registered route or zone geometry.

## 8. Incident confirmation policy (D7)

Status: defined in this revision at the user's request. The structure below is the definition; the parameter values are **starting values to calibrate** (§8.6), not measured results. The policy runs on the rover in the application layer (D3), outside `vision/`.

### 8.1 Why a policy is needed and what it confirms

- A derived box is one frame's observation. Step 6 measured that JPEG noise alone flips a borderline glasses detection between frames, so single frames both over- and under-report.
- Nothing tracks subjects across frames: the pipeline does not know that a face in frame *n* is the same person in frame *n + 1*. The policy therefore confirms a **condition** ("someone in view is missing required eyewear"), not a violation by a specific worker. Counting workers is deferred together with worker identity.

### 8.2 Inputs and classification

Each processed frame contributes one value per rule: the existing `frame_verdict` (any judged subject `not_wearing` → `not_wearing`; else any `wearing` → `wearing`; else `unverified`). Window timing uses `iphone_frame_ts_ns` (the same-session phone clock), so replaying a recording gives the same incidents regardless of processing speed. Episodes are keyed by **(inspection, session, rule)** for PPE and **(inspection, session, zone id)** for zones.

| Bound profile / run state | Policy behavior |
| --- | --- |
| Requirement checked, rule active | Produces incidents |
| Requirement checked, rule inactive or producer missing | No incidents; one capability notice per inspection: "Required — assessment unavailable" |
| Requirement unchecked | Observations stored; no incidents |
| No inspection running | Observations stored; no incidents |
| Restricted-zone profile active in the run | Zone incidents; the zone profile hash is recorded |

| Frame class | PPE rule | Restricted zone (C7) |
| --- | --- | --- |
| Positive | `not_wearing` | Region `recognized` and ≥ 1 `possible_person_in_zone` |
| Negative | `wearing` | Region `recognized`, no positive finding. Means "not observed", never "zone clear" |
| Neutral (never counts either way) | `unverified` | Region `unverified` |

Judged frames = positive + negative.

### 8.3 States

```
               first positive frame                 criteria met                 end condition
   (nothing) ─────────────────────► CANDIDATE ───────────────────► CONFIRMED ───────────────────► ENDED (reason)
                                        │                              ▲                              │
                                        │ no positive for window_s     └──── REOPENED ◄───────────────┘
                                        ▼                                    (re-confirmed within merge_gap_s)
                                    DISCARDED
```

Every transition is an append-only record in the control lane. Records are never edited or deleted.

### 8.4 Rules and initial parameters

| Parameter | Initial value | Basis |
| --- | --- | --- |
| `window_s` | 2.0 s | About 20 frames at the phone's 10 Hz |
| `confirm_min_frames` | 5 positive frames in the window | At least 0.5 s of evidence at 10 Hz; isolated noisy frames cannot confirm |
| `confirm_min_fraction` | 0.8 of judged frames in the window | Same 80 % criterion as the Step 6 on/off test |
| `clear_window_s`, `clear_min_frames`, `clear_min_fraction` | 3.0 s, 8 negative frames, 0.8 | Ending needs stronger evidence than starting, which limits flapping |
| `lost_after_s` | 5.0 s without a judged frame | Subject left, became occluded or too small, or input stopped |
| `merge_gap_s` | 10.0 s | A quick re-confirmation continues the same incident |
| `min_processing_hz` | 2.5 Hz (= `confirm_min_frames` / `window_s`) | Below this, confirmation is impossible; report it instead of failing silently |

1. **Candidate.** The first positive frame for a key opens a candidate. It is shown as "candidate", never as confirmed.
2. **Confirm.** In the trailing `window_s`: positives ≥ `confirm_min_frames` **and** positives ÷ judged ≥ `confirm_min_fraction`. Neutral frames are excluded from both counts.
3. **Discard.** A candidate with no positive frame for `window_s` is discarded. Its observations remain in history.
4. **End.** A confirmed incident ends with exactly one reason:
   - `condition_not_observed`: the trailing `clear_window_s` meets the clear criteria. Display "no longer observed", never "resolved" or "compliant"; a different person may now be in view.
   - `not_assessed`: no judged frame for `lost_after_s`. Long `unverified` stretches end here; they never count as clearing.
   - `session_changed`: a new ARKit session invalidated coordinates. A new incident may confirm in the new session.
   - `inspection_ended`.
   - `source_stopped`: the run ended or the rover service restarted. Open incidents are closed at startup, never resumed from memory.
5. **Reopen.** If the same key re-confirms within `merge_gap_s` after `condition_not_observed` or `not_assessed`, the same incident is reopened with the interruption recorded. Otherwise a new incident starts.
6. **Retired sessions.** Frames of a retired session (`pose_invalid_reason = session_mismatch`, or arriving after the switch) never open or extend an episode in the new session.
7. **Low rate.** If the processed rate for a session drops below `min_processing_hz`, the status shows "confirmation unavailable: processing rate" until it recovers. Candidates are still listed.
8. **Confidence.** No extra confidence threshold beyond the rules' existing subject thresholds. Derived-box confidence is not a probability that PPE is absent.

### 8.5 What an incident records

- Incident ID; key (inspection, bound profile revision, session, rule or zone id plus zone profile hash); `source_mode`; policy version and parameter hash.
- Every state transition with its phone-clock observation time and rover times.
- Counts of positive, negative and neutral frames, and the `event_id`s of the frames that caused each transition.
- Evidence, bounded to 10 images per incident: first positive frame, confirming frame, highest subject-confidence positive frame, last positive frame, plus at most one every 30 s while open.
- Location: camera pose of the first, confirming and last positive frames where `pose_valid`; otherwise "unlocalized" with the reason. The Twin pin uses the confirming frame's pose ("observed from here").
- Not included in v1: severity or ranking (a separate product decision), and operator review. A later "acknowledged" or "dismissed as false positive" note is stored separately and never changes policy records.

Person in path and walkway have no producer, so they have no policy yet. Define theirs when a producer exists (Step 11); until then they stay SAMPLE.

### 8.6 Tests, calibration and proposed acceptance

- **Implementation shape:** a pure, deterministic function from ordered observations to transitions, plus a replay tool that runs it over `tools/replay_detect` output.
- **Synthetic timeline tests** (same style as `tests/test_association.py`): a single noisy frame → nothing; alternating frames at 60 % positive → no confirmation; 1 s of sustained positives → confirmed; neutral gaps; `lost_after_s` timeout; session change; reopen versus new incident; retired-session frames; low-rate status; replayed duplicate records → no extra incidents.
- **Calibration data:** the Step 6 live on/off recordings for glasses, helmet and vest (capture still pending), plus a restricted-zone recording.
- **Proposed acceptance, for agreement before calibration:** 0 confirmed incidents during any `wearing` segment; every `not_wearing` segment of ≥ 10 s confirmed within 3 s of its start, provided the model judged the subject; each incident ends within `clear_window_s` + 1 s of the PPE being put back on.
- **Configuration:** parameters live in an application-owned file (e.g. `configs/incidents.yaml`), never under CV keys. Changing them creates a new policy version; past incidents keep the version that produced them.

## 9. Step-by-step implementation plan

Each step is independently demonstrable. Steps 1–7 need neither a Jetson nor a frontend.

### Step 0 — Baseline and decisions

**Work:** settle the remaining open decisions in §11 (D1–D3 confirmed; D7 defined in §8). Agree the §8.6 acceptance targets. Land or isolate in-progress walkway work. Record the baseline commit. Decide owners: CV hook (CV owner), edge/hub (application owner).
**Gate:** every dashboard and Twin field in §6–7 has a named source or is marked NOT INTEGRATED.

**Recorded October 10, 2026.** Baseline commit `bd0d6d7` (walkway Step 3d landed separately), `uv run pytest` 378 passed. Scope for this round: Steps 1–9 on the Mac (Milestone C); physical gates stay pending. Stack: FastAPI + uvicorn (no `[standard]` extras). D4/D5/D6/D8 and the §8.6 targets accepted as recommended (§11). Owners: CV hook — Humbertxx (CV owner); edge store, edge API and hub — built on `autoCV` by Humbertxx in the meantime, **application owner still to be named**.

| §6–7 field | Source |
| --- | --- |
| Link state, per-lane lag | Hub sync client (Step 5) |
| `source_mode` | Declared at `vision.server` start (`--source-mode`, Step 3) |
| Freshness: video / results / pose / health | Edge live state: last processed frame, last C2, last admitted pose, latest C3 (Step 3) |
| Capability matrix — rules | `Pipeline.rules` vs configured `ppe.rules` (inactive reason = missing classes), observation sidecar (Step 3) |
| Capability matrix — producers | PPE: prototype (LIVE/REPLAY). Restricted zone (C7): prototype, physical acceptance pending. Person in path: **NOT INTEGRATED**. Walkway (C8): **NOT INTEGRATED** (library only). Controller / supervisor telemetry: **NOT INTEGRATED** |
| Preview frame | Edge writer, 640 px, ≤ 5 Hz (Step 3, D5) |
| Profiles and revisions | Hub (Step 7) |
| Inspections, assessments | Edge (Step 7, D3) |
| Incidents | Edge policy §8 (Step 8), labeled "policy uncalibrated" |
| Observations | C2 + `bob-app` observation sidecar (Step 3) |
| Evidence | Edge blob store (Step 3 capture, Step 8 incident frames) |
| Twin track | Track hook at `FrameServer.admit()` (Step 3), served by the Twin API (Step 9) |
| Twin pins / unlocalized | C2 `pose_valid` / `pose_invalid_reason` of each observation's own frame (Step 9) |
| Rover position, heading | **NOT INTEGRATED** — the marker is the phone camera (no phone-to-rover transform) |
| Person / hazard world position | **NOT INTEGRATED** (no range data) |

### Step 1 — Contracts and fixtures

**Work:** define separately versioned envelopes (`bob-app` v1): observation sidecar (C2 `event_id` reference, per-subject verdicts, active/inactive rules with reasons), track point, evidence metadata, profile revision, inspection, assessment, incident, live state, and the sync messages (hello, batch, ack, gap, blob status). Valid/invalid fixtures, each invalid fixture breaking one rule. Frozen v2 C1/C2/C3 and C7 stay untouched. Draft as new interfaces for `integration.md` §2 (proposed C9 edge sync, C10 hub API) when Step 2 lands.
**Gate:** fixtures validate; one consumer can read SAMPLE, REPLAY and LIVE envelopes without branching on source.

### Step 2 — Edge store library

**Work:** SQLite (WAL) store: lanes with monotonic `seq`, `store_epoch`, blob files written atomically and addressed by SHA-256, acknowledgment table, retention and disk-pressure pruning with gap notices, single writer thread with a bounded input queue that counts drops (same pattern as `SceneWriter`).
**Gate:** unit tests for restart continuity (no reused `seq`), crash mid-write (no partial records), full disk (visible error, inference callers never block), pruning produces gap records.

### Step 3 — Publication hook in `vision.server` (CV-owned)

**Work:** after `detect_frame()`, hand references (event, verdicts, rule availability, upright image, C7 record) to the edge writer's bounded queue; encoding and disk I/O happen on the writer thread. Add a track hook at `FrameServer.admit()` that only enqueues (it runs on the receive thread). Evidence capture policy (D6): save the clean upright frame for frames with any derived box or scene finding, rate-limited per rule per session, with pixel hash and C2 identity. Preview JPEG at a capped rate. Generalize the source-mode flag. Use the same hook from `tools/replay_detect.py` so offline runs fill a store too.
**Gate:** `uv run pytest`; replay determinism and `detections.jsonl` unchanged; a deliberately blocked writer leaves rx→event p95 within tolerance of the Step 8 measurement and counts every dropped record; destructive suite still passes.

### Step 4 — Edge API process

**Work:** read-only sync service over the store: `/v1/sync` (hello, lanes, live, tail), `/v1/blobs/{sha256}`, token check, inspection start/end, profile delivery. Dual-stack listening (the IPv6-only hotspot lesson from Step 5).
**Gate:** killing or stalling the edge API changes nothing in inference or the store; no motion endpoint exists (route-list test).

### Step 5 — Hub sync client and replica

**Work:** connect, resume per lane, dedupe, acknowledge after commit, epoch and gap handling, blob fetcher with byte-rate cap and hash check, link state machine.
**Gate:** a test proxy between hub and edge cuts the link for a timed interval during a replay; after reconnect the replica equals the edge store record-for-record, counts are not inflated, backfilled records are labeled, gaps appear when retention is forced, and an epoch change is detected.

**Milestone A — rover-to-laptop link on one Mac:** replay → `vision.server --detect` → edge store → edge API → hub, surviving link cuts. Demonstrate with a small CLI (`hub status` / `hub tail`) rather than a frontend.

### Step 6 — Frontend API and sample workspace

**Work:** hub REST + `WS /v1/live` (§6), OpenAPI, a fixture-driven "sample edge" that speaks the same sync protocol with `source_mode = SAMPLE` into a separate workspace (person in path, walkway, confirmed-incident examples).
**Gate:** contract tests against the OpenAPI schema; sample records never appear in live counts or on real poses; a closed or slow browser never affects the hub or the rover.

### Step 7 — Worksite profiles and inspection lifecycle

**Work:** profile authoring and immutable revisions on the hub (editable while the rover is offline). At explicit start, the hub sends the full revision to the edge, which verifies its hash, binds `inspection_id`, and applies it to observations in Python. Assessments use §4 semantics.
**Gate:** check/uncheck, unsupported requirement, no-requirements state, conflicting edits (`409`), saved-but-pending revisions, in-flight results keeping their revision, and reconnects/ARKit resets that do not start inspections or activate edits.

**Milestone B — frontend-ready backend:** a frontend developer can build every dashboard view against the hub using LIVE/REPLAY data from the Mac and SAMPLE data for missing producers.

### Step 8 — Incidents and evidence

**Work:** implement the §8 policy on the edge as a pure function with versioned parameters; write transitions and evidence references to the control lane; add the replay calibration tool. Until it passes calibration, label incidents "policy uncalibrated".
**Gate:** §8.6 synthetic timeline tests; calibration against the on/off recordings meets the agreed targets; replayed messages do not create extra incidents; evidence matches its source frame (pixel hash); missing evidence and restart recovery (`source_stopped`) are visible.

### Step 9 — Twin backend

**Work:** track lane, session list, pins and unlocalized lists (§7).
**Gate (physical):** walk the phone forward, turn left, turn right and press Reset: no mirrored map, correct heading, new session = new map, stale tracking stops the path, invalid frames stay unlocalized. Record observed results in the README.

**Milestone C — dashboard and Twin data complete on the Mac.**

### Step 10 — Move the rover role to the Jetson

**Prerequisite:** J1–J6 pass. **Work:** run `vision.server` + edge API as systemd services; laptop runs the hub. Measure inference latency with the edge writer and API on and off, store growth per hour, and catch-up time after a timed disconnect.
**Gate (physical):** with the phone on the rover-local link (D1), carry the laptop out of range during an inspection and back: phone capture and inference continue uninterrupted, the hub shows DISCONNECTED → CATCHING UP → CONNECTED, the track and incidents fill in as backfilled, and the phone stream shows no added drops attributable to catch-up.

### Step 11 — Later producers and telemetry

Person in path, walkway (C8 once it has output), controller and supervisor telemetry as read-only adapters with requested and reported state shown separately and missing feedback shown as unknown. Each new producer gets its own §8-style confirmation policy before its SAMPLE label is removed. No cloud upload (D2).

## 10. Acceptance gates

| Gate | Evidence |
| --- | --- |
| Contracts | Valid/invalid fixtures; frozen v2 untouched; unknown values tested |
| Non-blocking | Blocked/slow writer, dead edge API, full disk: inference latency within tolerance, all drops counted |
| Sync integrity | Timed link cuts: replica equals store; no duplicates; gaps explicit; epoch change detected |
| Honest delivery | Backfilled records never shown as current; disconnected rover state shown as unknown |
| Worksite semantics | All §4 cases including revision binding and reconnect/reset non-activation |
| Incident policy | §8.6 timeline tests; calibration targets met on recordings; deterministic replay |
| Evidence | Pixel hash matches source frame; missing evidence visible; incidents not inflated by replays |
| Twin | Physical forward/left/right/reset test; session separation; unlocalized fallback |
| Isolation and authority | No motion/arming/fault endpoints anywhere; no BLE access from edge or hub |
| Offline | Works with no internet; frontend assets and fonts served locally |
| Jetson | Same replay suite on the device; resource use with sync on and off recorded |

Run `uv run pytest` at each implementation step; record measured results in the README progression; run `integration.md` G1–G8 when merging. No threshold above is an achieved measurement.

## 11. Decisions

| # | Decision | Status |
| --- | --- | --- |
| D1 | Rover network topology | **Confirmed:** phone ↔ rover computer on a rover-local link (rover access point/router, or the phone hotspot carried on the rover); the laptop leaving range never breaks capture. Which device provides that network is still to be chosen. |
| D2 | Cloud or internet upload | **Confirmed: no.** The system works entirely on the local network. |
| D3 | Where assessments and incidents are computed | **Confirmed:** on the rover (edge), so offline inspections are complete. |
| D4 | Rover storage budget and retention | **Confirmed (starting values, to measure):** store cap 2 GiB; acknowledged records older than 24 h are pruned; over the cap or below 1 GiB free disk, the oldest observation records are pruned first with a gap notice. Control lane and evidence are kept until acknowledged. |
| D5 | Live preview size and rate | **Confirmed (starting values):** annotated upright preview, 640 px wide, ≤ 5 Hz, JPEG quality 70, latest wins. Full resolution only as evidence. |
| D6 | Evidence capture policy | **Confirmed:** clean full-resolution upright frame for frames with any derived box or scene finding, at most one per 2 s per rule per session, plus the §8.5 incident frames (bounded to 10 per incident), each with pixel hash and C2 identity. |
| D7 | Incident confirmation policy | **Defined in §8** at the user's request. **§8.6 acceptance targets agreed**; parameters still need calibration on recordings, so incidents are labeled "policy uncalibrated". |
| D8 | Link authentication | **Confirmed:** pre-shared token `BOB_EDGE_TOKEN` in `.env` (never committed or printed). |
| D9 | Frontend stack | Open; the backend is stack-agnostic. |

## 12. Scope cuts

If time is short, keep in this order: honest source/freshness labels → rover store with link-cut resync → evidence correlation → profile/inspection binding → Twin. Drop map styling, route registration and hardware panels before compromising evidence correlation or labeling. Deferred: 3D reconstruction, persistent maps across sessions, worker identity, hazard world positions from image boxes, remote driving, route editing, compliance percentages.
