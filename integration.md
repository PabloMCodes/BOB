# integration.md — How BOB components connect

This file defines **what each subsystem exposes to and consumes from the rest of the project**, and the **checks that must pass before merging into `main`** so merges happen without conflicts or broken contracts.

> [!IMPORTANT]
> **Current state (2026-10-11):** `main` is the default integration branch. The former `autoCV` branch, dashboard work and experimental controller bench are incorporated here. The local browser dashboard consumes C10 and adds measured telemetry and operational-log views. These workspace checks do not replace the clean-tree, trial-merge, iOS/deployment and PR gates below. Branch names marked *(TBD)* must be filled in the [Branch registry](#7-branch-registry) when they exist.

---

## 1. System map — where CV sits

```
                    ┌──────────────────────────── main / CV subsystem ──────────────────────────────┐
 iPhone app         │  ios/BOBCapture ──FramePacket (WS)──►  vision/ server → YOLOv8 → pose assoc.   │
 (in this branch)   └────────────────────────────────────────────────────┬──────────────────────────┘
                                                                         │ DetectionEvent (JSONL / later live)
                                                                         │ stream health: stale, tracking_state, pose_valid
                        ┌────────────────────────────────┬───────────────┴───────────────┬─────────────────────────┐
                        ▼                                ▼                               ▼                         ▼
            Safety supervisor / nav (TBD)      Agent orchestration / alerts (TBD)   Jetson deploy (TBD)     Sensors: gas/thermal (TBD)
            consumes pose validity + stale     consumes verified DetectionEvents    runs vision/ on CUDA    may share event schema
            NEVER receives raw detections      NEVER controls motors                TensorRT engine build
            as a reason to move
```

## 2. Interface contracts

These are the only ways other parts may depend on the CV and application subsystems. Anything not listed is internal and may change without notice.

| # | Interface | Producer | Consumer(s) | Contract lives in | Versioned by |
| - | --------- | -------- | ----------- | ----------------- | ------------ |
| C1 | `FramePacket` + `PosePacket` (WS: length-prefixed JSON header + JPEG) | iOS app | `vision` server | `vision/schema/phone.py`, `schema/{frame,pose}.schema.json` + Swift mirror `ios/BOBCapture/Wire/Schema.swift`; Swift→Python golden `tests/fixtures/recordings/swift_golden.bobrec` | `schema_version` |
| C2 | `DetectionEvent` (boxes with `source: model \| derived`, pose, `pose_valid`, `pose_dt_ms`, timestamps) | `vision` | Safety supervisor, agent/alerts | `vision/schema/events.py`, `schema/detection_event.schema.json` + fixtures in `tests/fixtures/` | `schema_version` (**v2**) |
| C3 | `StreamHealth` (`stale`, `tracking_state`, `session_id`, `dropped_count`) — emitted every `timing.health_interval_ms` by `vision.server` (JSONL today); `stale` = no phone message for > `timing.stale_ms`; `dropped_count` = frames never analysed this session (phone seq gaps + server slot drops + undecodable JPEGs, the last added in Step 8 — same field, wider count, no schema change), resets with each new session | `vision` | Safety supervisor | `vision/schema/events.py`, `schema/stream_health.schema.json` | `schema_version` |
| C4 | Runtime config keys (`device`, `model`, optional `footwear_model` with `enabled/weights/weights_sha256`, `pipeline` incl. `feet_crop` and `crop.batch`, `ppe` incl. `edge_margin` and per-rule `absence`, `training`, `server`, `timing`, `camera`, `render`) | `configs/default.yaml`; opt-in `configs/footwear.yaml` | Jetson deploy | `configs/default.yaml` | key names (rename = breaking) |
| C5 | SHA-256-pinned SH17 + optional trained footwear specialist; derived `no-safety-glasses`, `no-helmet`, `no-gloves`, `no-safety-vest`, `no-safety-boots`. Ensemble retains SH17 IDs except generic shoes (14), suppressed; specialist IDs 17 shoes / 18 safety-boots under ensemble model_id | `configs/default.yaml`, `configs/footwear.yaml` → `models/` | Jetson deploy, alerts (class names) | `models/sh17.md`, `models/footwear-v1.md` | model card |
| C6 | Python package `vision` (import path, Python 3.10) | `main` CV subsystem | Jetson deploy | `pyproject.toml`, `uv.lock` | package version |
| C7 | Independent scene inspection output (`scene_version: 1`), image-bound or declared closed yellow floor-tape definitions, frame-linked findings; no movement authority | Still inspection, opt-in Mac server/replay; `configs/zones-yellow.yaml` profile | Future dashboard/evidence | `vision/zones.py`, `vision/tape.py`, `vision/scene.py`, `docs/restricted-zones.md` | scene contract version |
| C8 | Independent walkway obstruction contract (`walkway_version: 1`): operator quadrilateral bound to a declared-empty fixed-camera reference file, entry/exit edges, reference check + change evidence; lane findings planned; no movement authority | `vision/walkway.py`; `configs/walkway.yaml` (prototype defaults). Library only — no CLI/live output yet | Future dashboard/evidence | `vision/walkway.py`, `docs/walkway-obstruction.md` | `walkway_version` |
| C9 | **Built on the Mac (dashboard Steps 2–4).** Rover edge sync: `bob-app` v1 lane records (control / track / observation, per-lane `seq`, `store_epoch`), live state, `sync_*` messages, evidence blobs by SHA-256. Measured two-second FPS/Hz/confidence windows travel in the existing `notice` envelope (`code=stream_metrics`, at most 1/s). Rover → laptop over the local network only; image receipts via `POST /v1/blobs/{sha256}/ack`; writes limited to receipts, inspection start/end and profile delivery; no motion, arming or fault endpoints | `bobapp/edge/` (SQLite WAL store fed by `vision.server --edge`; edge API `python -m bobapp.edge.api`, port 8770, token `BOB_EDGE_TOKEN`); `configs/edge.yaml` | Laptop hub | `bobapp/contracts/`, `schema/app/*.schema.json`, `tests/fixtures/app/` | `app_version` (**v1**, unchanged) |
| C10 | **Built and consumed by the local dashboard.** Hub API: REST + `WS /v1/live`, optional measured `status.telemetry`, operational `/v1/logs` with backwards paging, archived `/v1/frames` with image status and `status.frames` counts, worksites + explicit revision-bound inspection commands, observations/incidents (optional `latest=true`), evidence and Twin. `?workspace=rover|sample` separates databases; worksite/command routes are rover-only. Every history item states `source_mode`, `delivery` and clock domains; the browser uses token headers and bounded REST polling | `bobapp/hub/` (laptop, `python -m bobapp.hub serve`, port 8780) | `web/src/dashboard/`, `web/src/twin/` ([connection guide](docs/plans/digital-twin-frontend-guide.md)) | `schema/app/hub-openapi.json` (generated, drift-tested) + `bobapp/contracts/` | `app_version` (**v1**, unchanged); additive hub API fields/routes |
| C11 | Experimental controller-bench BLE protocol: 20-byte-or-smaller binary stop/arm/motion/tone commands and status; per-connection session, monotonic sequence and receive-time lease; no CV motion authority. `TONE` plays embedded Missing PPE on speech-1 firmware | Manual bench client; arrow-key remote and Mac scan/inspect/TONE demo (300 ms leases); preview STOP/TONE only; supervised executor sends one 100–150 ms motion packet per operator-authorized step | `BOB_ControllerBench` ESP32 firmware; status returns to host | `hardware/controller_protocol.py`, `hardware/esp32/BOB_ControllerBench/BOB_ControllerBench.ino`, `navigation/drive.py` | protocol byte `1` unchanged (experimental; manual motor/speech user-confirmed, destructive acceptance pending) |
| C14 | Experimental local navigation preview trace/map: state, reason, camera/goal cells, hypothetical direction, repeated PPE classes, announcement request, explicit disabled motor output, declared source mode and speech delivery status | `navigation/` same-host C2/C3 latest-line consumer | Operator: `runs/navigation/<run>/decisions.jsonl` and `map.svg`; no actuator consumer | `navigation/preview.py`, `navigation/__main__.py`, [guide](docs/navigation-preview.md) | Internal experiment, not a frozen/public wire schema |
| C13 | Local vision run identity (`run_info.json`: version, producer, UUID, declared source mode, receiver start time); supervised trace (`steps.jsonl`: advisory decision, operator request, delivery and controller status; wheel velocity null) | `vision.server` run identity; `navigation.supervised` trace | Same-host supervised runner; operator | `vision/server/__main__.py`, `navigation/run_source.py`, `navigation/supervised.py`, [guide](docs/supervised-camera-driving.md) | Internal run-info version 1; unchanged C1–C3 and C11 |
| C12 | **Build-time only.** Browser audit fixture (`fixture_version: 1`): recorded `vision.pipeline` boxes and per-subject verdicts for the published website stills, plus model identity, weights hash, active rules and each inactive rule's missing classes. Written by `tools/export_audit_fixture.py`; consumed only by the in-browser second-opinion panel for comparison. Precomputed prompt embeddings (`public/audit/prompt-embeddings.json`) accompany it. No runtime path, no hub or edge dependency, no motion authority; audit results stay in browser memory and are never written back, stored or treated as evidence | `tools/export_audit_fixture.py`, `web/scripts/export-prompt-embeddings.ts` | `web/src/audit/` | `web/public/media/workers/audit-fixture.json`, `web/public/audit/prompt-embeddings.json` | `fixture_version` (**v1**) |

Wire codec (`encode` / `decode`) lives in `vision/schema/wire.py`. **Non-Python consumers** should validate against `schema/*.schema.json` **and** the fixtures: JSON Schema can't express cross-field rules (rigid transform, box bounds, `pose_valid` consistency, `source`↔`cls_id`), the fixtures do.

Navigation preparation (2026-10-11): `hardware/control_sim.py` remains an isolated
simulation. `navigation/` consumes unchanged C2/C3 on the receiver host and emits
C14 motor-disabled decisions. Its optional speech adapter has STOP and speech
access only. A separate `navigation.supervised --execute` runner now gates one
short C11 pulse on explicit operator input, current observations and controller
status. Camera observations alone cannot arm or move the rover. C3 log output is
line-buffered; C13 identifies live versus replay runs and detects server restarts.
ARKit remains advisory; no obstacle-stop sensor is wired. Physical supervised
acceptance is pending. See `docs/plans/autonomous-driving-context.md`.

**Pose validity in C2 (Step 7):** `pose` is the camera pose of the event's **own** ARFrame (`pose_dt_ms = 0`), never a later one. `pose_valid=false` reasons: `session_mismatch` (a newer ARKit session exists — new world origin), `stale` (> `timing.stale_ms` gap on the iPhone clock right before the frame), `tracking_not_normal`, `no_pose` (camera vertical). `dt_exceeded` is reserved. The pose is the **phone's**, not the detected person's position, and is advisory only.

**Schema v2 (Step 3):** `Box.source` added; `cls_id` is null for derived boxes. Derived boxes are **per-frame observations**, not confirmed hazards — consumers apply their own N-frame confirmation. **Absence of a violation box does not mean compliant**: subjects too small/uncertain are not judged.

**Breaking change** = removing/renaming a field, key, class name, or changing units/meaning. Breaking changes require: `schema_version` bump → fixtures updated → every consumer in [§7](#7-branch-registry) notified and its checks ([§5](#5-checks-required-in-other-branches)) run **before** merge.

Offline-frame extension (2026-10-11): C9 adds authenticated
`POST /v1/blobs/{sha256}/ack` with `{hub_id, store_epoch}` after verified image
storage. C10 adds `GET /v1/frames` (paged original observations plus `image_status`)
and `status.frames` counts. The existing v1 `observation.evidence_sha256` points to
each archived clean JPEG; no CV or bob-app envelope/schema changes are needed.
`archive.enabled` is an additive edge config key. The hub discovers referenced
images from observations as well as sampled evidence metadata. Upgrade edge, hub
and website together for the recovered gallery; old hubs cannot acknowledge new
image receipts, so image retention is conservative. See [demo guide](docs/offline-frame-demo.md).

Site photo extension (2026-10-11): additive edge `site_photos` settings and
C9 v1 `site_photo` notices select general views independently of PPE. C10 adds
`/v1/frames?site_only=true` and nullable `site_photo` item metadata. C1–C3 and
bob-app envelopes remain unchanged. See docs/jetson-frame-handoff.md for selection
limits, delayed notice handling and the online-worker boundary.

## 3. File ownership — avoiding merge conflicts

Standing user agreement (2026-10-11): the Jetson agent pulls before feature work
and commits/pushes tested work without a separate request each time. The teammate
owns website online-LLM inference; the Jetson agent owns local capture/inference,
frame storage/transfer and rover control. Existing frame-gallery changes are kept
in their own commit. [Frame API handoff and touched website files](docs/jetson-frame-handoff.md).
This does not enable automatic main merges or a background Git daemon.

Conflicts mostly happen on shared files. Rule: **each branch edits only what it owns; shared files follow the rules below.**

| Files | Owner | Rule |
| ----- | ----- | ---- |
| `vision/`, `schema/`, `tools/`, `ios/`, `tests/` (CV tests), `models/*.md` | CV maintainers | Other feature branches import, never edit casually. Request changes through a PR to `main`. |
| `pyproject.toml` | shared | Only add your own dependencies; never bump another branch's pin without telling its owner. |
| `uv.lock` | shared | **Never hand-merge.** On conflict: take `main`'s version, then `uv lock` and commit the regenerated file. |
| `configs/default.yaml` | shared | Each part owns its own top-level keys. Don't edit another part's keys. New parts should namespace (e.g. `safety:`, `alerts:`). |
| `README.MD`, `README-CV.md` | shared | Root README is the overall overview; CV guide retains detailed progression. Each part owns its own section; don't reflow unrelated sections. |
| `AGENTS.md`, `CLAUDE.md` | shared | Append a part-specific section; global rules change only by agreement. |
| `.gitignore` | shared | Append-only. |
| `integration.md` | shared | Update §2 and §7 whenever an interface or branch changes. |

## 4. Pre-merge gate: feature branch → `main`

All gates must pass, in order. Run from the feature branch root. Merge through a PR.

### G1 — Sync

```bash
git fetch origin --prune
git status                      # must be clean
```

### G2 — Conflict dry run (doesn't touch your working tree)

```bash
git merge-tree --write-tree --name-only origin/main HEAD
# exit 0  → merges cleanly
# exit 1  → conflict; the listed files are the conflicting ones
```

If exit 1: merge `origin/main` into the feature branch locally, resolve using the rules in [§3](#3-file-ownership--avoiding-merge-conflicts), and re-run from G1.

### G3 — Cross-branch overlap check (catch conflicts *before* they happen)

Lists files that this branch **and** any other active branch both changed relative to `main`:

```bash
ours=$(git diff --name-only origin/main...HEAD)
for b in $(git branch -r --format='%(refname:short)' | grep -v -e HEAD -e origin/main); do
  overlap=$(comm -12 <(echo "$ours" | sort) <(git diff --name-only origin/main..."$b" | sort))
  [ -n "$overlap" ] && echo "== $b also touches:" && echo "$overlap"
done
```

Any overlap on a contract file (`vision/schema/`, `schema/`, `configs/default.yaml`, `pyproject.toml`, `uv.lock`) → coordinate with that branch's owner before merging. Decide who merges first; the second rebases onto the new `main`.

### G4 — Tests on the merged result

```bash
feature_branch=$(git branch --show-current)
git worktree add ../BOB-premerge origin/main
cd ../BOB-premerge
git merge --no-ff --no-edit "$feature_branch"  # local trial merge only
uv sync --locked                        # fails if uv.lock is out of date
uv run pytest
cd - && git worktree remove --force ../BOB-premerge
```

All tests from **every** branch already in `main` must pass, not only CV tests.

### G5 — Contract checks

- [ ] If `vision/schema/` changed: `schema_version` bumped, fixtures in `tests/fixtures/` updated, `uv run python -m tools.export_schema` re-run, Swift mirror in `ios/` updated in the same PR.
- [ ] Contract tests pass: `uv run pytest tests/test_schema.py` (includes JSON Schema drift check).
- [ ] No renamed/removed keys in `configs/default.yaml` (or consumers updated, see [§5](#5-checks-required-in-other-branches)).
- [ ] Model card in `models/*.md` updated if class names or weights changed.

### G6 — Jetson portability

```bash
grep -rn '"mps"' vision/ | grep -v config.py     # must print nothing
uv run python -c "import sys; assert sys.version_info[:2]==(3,10)"
```

- [ ] No macOS-only imports in `vision/`.
- [ ] (Step 8+) `.pt` vs `.onnx` parity passes: `uv run --group export pytest tests/test_handoff.py` (and `tools.parity onnx` on recordings). On the Jetson: J1–J6 in `docs/jetson-handoff.md`.

### G7 — iOS build + Swift contract tests (Step 4+)

```bash
cd ios && xcodegen generate                       # .xcodeproj is generated from project.yml (gitignored)
xcodebuild -project BOBCapture.xcodeproj -scheme BOBCapture \
  -destination 'generic/platform=iOS' -derivedDataPath build CODE_SIGNING_ALLOWED=NO build
xcodebuild -project BOBCapture.xcodeproj -scheme BOBCapture \
  -destination "id=$(xcrun simctl list devices available | grep -m1 'iPhone' | grep -oE '[0-9A-F-]{36}')" \
  -derivedDataPath build test                     # Swift decodes the shared tests/fixtures
```

If the schema changed: regenerate the Swift → Python golden recording (`TEST_RUNNER_BOB_GOLDEN_PATH=$PWD/../tests/fixtures/recordings/swift_golden.bobrec` on the test command) and re-run `uv run pytest tests/test_recording.py`.

### G8 — Docs and PR

- [ ] `README-CV.md` progression row updated with measured results; overall `README.MD` status updated where relevant.
- [ ] `integration.md` §2 / §7 updated if any interface or branch changed.
- [ ] PR opened against `main` listing: gates passed, interfaces touched, consumers notified.

```bash
gh pr create --base main --head "$(git branch --show-current)" --title "<component>: <change>" --body "<gates + interfaces touched>"
```

## 5. Checks required in other branches

When a feature changes an interface, these checks must pass **in the consuming branch** against the feature's new fixtures before it merges.

| Consumer branch | Depends on | Check to run in that branch |
| --------------- | ---------- | --------------------------- |
| Safety supervisor / nav *(TBD)* | C2, C3 | Its tests parse `tests/fixtures/*detection_event*.json` from the feature branch. It **stops** on `pose_valid=false`, `stale=true`, or new `session_id`. |
| Agent orchestration / alerts *(TBD)* | C2, C5 | Its tests parse the `DetectionEvent` fixtures. Class names match the model card. It never outputs motor commands. |
| Jetson deploy *(TBD)* | C4, C5, C6 | `uv run pytest` passes on the Jetson with `device: cuda`. ONNX → TensorRT build succeeds on the device. |
| Sensors gas/thermal *(TBD)* | C2 (if shared) | Event fixtures validate against the shared schema version. |

How to run a consumer's tests against a feature branch without merging:

```bash
git worktree add ../BOB-consumer origin/<consumer-branch>
cd ../BOB-consumer
git checkout origin/<feature-branch> -- vision/schema/ schema/ tests/fixtures/   # bring in new contract only
uv sync && uv run pytest
cd - && git worktree remove --force ../BOB-consumer
```

The reverse also applies: **before any branch merges to `main`, it runs G1–G4 and the existing CV tests must still pass on the merged result.**

## 6. After merge — verify `main`

```bash
git fetch origin && git checkout main && git pull --ff-only
uv sync --locked && uv run pytest
```

If `main` is red after a merge: whoever merged last fixes or reverts (`git revert -m 1 <merge-sha>`) — do not stack new merges on a red `main`.

## 7. Branch registry

| Branch | Part | Owner | Interfaces provided | Interfaces consumed | Status |
| ------ | ---- | ----- | ------------------- | ------------------- | ------ |
| `main` | Computer vision, edge/hub integration, local dashboard and experimental controller bench | Humbertxx | C1–C12 | C10 (browser), C12 (browser audit) | Default branch; former `autoCV` history merged and branch retired on 2026-10-11. Physical walk, PPE/worksite accuracy, incident calibration, navigation and remaining Jetson acceptance are pending. |
| `feature/dashboard-csv-export` | Conservative PPE absence/edge policies; selected website photo, dropdowns, privacy, terms and detection CSV | Humbertxx | C4 (additive PPE settings) | C10 (existing browser data) | Seven separate feature commits; publication gates reported in the PR. CV schema v2 and bob-app v1 are unchanged. Physical acceptance and automatic image expiry remain pending. |
| `feature/inspiration-journey` | Inspiration story, team origins globe and scroll motion | Humbertxx | Website route `/inspiration`; no wire changes | Existing local robot photos | Build and frontend checks passed; draft team responses labelled for confirmation. |
| `feature/navigation-preview` | Navigation preview and controller bench follow-up | — | C14 internal preview trace/map; C11 embedded speech | C2, C3; optional C11 STOP/TONE/status only | Motor-disabled consumer and deterministic demo implemented; camera/speech preview physical acceptance and all autonomous driving gates pending |
| `feature/offline-frame-sync` | Offline processed-frame archive, verified image receipts and recovered gallery | — | C9 image receipt; C10 frames/status additions | Existing C2; bob-app v1 observations and sync | 640 Python tests pass; browser offline/reconnect acceptance passes; physical Wi-Fi demo and deployment pending. Prior uncommitted navigation/hardware work preserved. |
| `feature/supervised-camera-drive` | Jetson frame recovery, existing frame gallery and supervised rover steps | — | C9 receipts, C10 frames/status, C13 internal run identity/trace | C2, C3, existing C11 v1 | Based on main 516d185; pending work packaged as focused hardware, sync, gallery, navigation and documentation commits. 684 tests pass, 5 optional/platform skips; 44 new supervisor/transport/terminal tests. Website online LLM remains teammate-owned. Physical stopping/direction acceptance pending. |
| `feature/site-photo-selection` | Diverse general site photos alongside PPE | Jetson agent | C9 selection notices; C10 gallery filter | Existing C2 poses/images | 711 Python tests pass (5 optional/platform skips); website build, frontend tests and browser filter/reconnect pass; physical threshold calibration pending; online analysis remains teammate-owned. |
| `feature/point-driving` | Retired: supervised click-to-floor driver and unused VLM cleanup | Jetson agent | C15 local preview/control | C1 metadata after admission, C2/C3, C11 bounded pulses | 47 point tests and SAMPLE browser acceptance pass; full Jetson suite 758 passed, 5 optional/platform skips. Physical geometry/direction/stopping acceptance pending; dry run default. |
| `feature/arrow-key-remote` | Direct local keyboard BLE remote; removes point driving | Jetson agent | No new wire interface | Existing C11 or legacy motor commands | Automated checks recorded in docs/remote-control.md; physical BLE acceptance pending |
| `feature/mac-wander-demo` | Mac scan/inspect/speech/turn-away demo, stacked on arrow-key remote | Jetson agent | No new interface | Existing C10 LIVE/realtime observations and C11/legacy BLE | Automated checks in docs/mac-wander-demo.md; physical acceptance pending |
| *(TBD)* | Agent orchestration / alerts | — | alerts | C2, C5 | Not created |
| *(TBD)* | Jetson deploy / hardware | — | — | C4, C5, C6 | Not created |

Arrow-key replacement (2026-10-11): `hardware.esp32.remote` consumes unchanged
C11 v1 (or legacy ASCII F/B/L/R/S on MotorTest). C15 and the point-driving
page/preview have been removed. No hub, CV schema, or app contract changes.

Mac wander demo: standalone operator process reads existing C10 status/observations
and sends existing C11 or legacy BLE commands locally. No hub motion endpoint,
new wire/config field, phone consumer, or second inference pipeline.

Mac scan follow-up: existing per-subject verdicts and JPEG hashes drive repeated
PPE confirmation and local inspection-log references. C11 TONE reuses speech-1;
no website, frame identity, model result, API or wire schema changes.

Mac continuous demo follow-up: one R enables ongoing operation; manual/focus
pauses remain latched. Camera outages stop motion and require two seconds of
healthy progressing observations before automatic recovery. Speech still uses
existing derived verdicts; uncertain PPE never becomes a violation. No wire,
model, firmware, or website changes.
