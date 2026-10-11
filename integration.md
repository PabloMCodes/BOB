# integration.md — How `autoCV` connects to the rest of BOB

This file defines **what the computer vision branch exposes to / consumes from other parts of the project**, and the **checks that must pass before merging into `main`** so merges happen without conflicts or broken contracts.

> [!IMPORTANT]
> **Current state (2026-10-10):** local `main` was initialized at the user's request from committed `autoCV` work after merging `origin/autoCV` hardware documentation. `main` has not been published; no `origin/main` exists in the fetched remote state. This bootstrap is not a claim that all deployment gates passed. Subsequent feature integration follows the PR and pre-merge gates below once the remote baseline exists. Branch names marked *(TBD)* must be filled in the [Branch registry](#7-branch-registry) when they exist.

---

## 1. System map — where CV sits

```
                    ┌──────────────────────────── autoCV (this branch) ─────────────────────────────┐
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

These are the only ways other parts may depend on `autoCV`. Anything not listed is internal and may change without notice.

| # | Interface | Producer | Consumer(s) | Contract lives in | Versioned by |
| - | --------- | -------- | ----------- | ----------------- | ------------ |
| C1 | `FramePacket` + `PosePacket` (WS: length-prefixed JSON header + JPEG) | iOS app | `vision` server | `vision/schema/phone.py`, `schema/{frame,pose}.schema.json` + Swift mirror `ios/BOBCapture/Wire/Schema.swift`; Swift→Python golden `tests/fixtures/recordings/swift_golden.bobrec` | `schema_version` |
| C2 | `DetectionEvent` (boxes with `source: model \| derived`, pose, `pose_valid`, `pose_dt_ms`, timestamps) | `vision` | Safety supervisor, agent/alerts | `vision/schema/events.py`, `schema/detection_event.schema.json` + fixtures in `tests/fixtures/` | `schema_version` (**v2**) |
| C3 | `StreamHealth` (`stale`, `tracking_state`, `session_id`, `dropped_count`) — emitted every `timing.health_interval_ms` by `vision.server` (JSONL today); `stale` = no phone message for > `timing.stale_ms`; `dropped_count` = frames never analysed this session (phone seq gaps + server slot drops + undecodable JPEGs, the last added in Step 8 — same field, wider count, no schema change), resets with each new session | `vision` | Safety supervisor | `vision/schema/events.py`, `schema/stream_health.schema.json` | `schema_version` |
| C4 | Runtime config keys (`device`, `model`, optional `footwear_model` with `enabled/weights/weights_sha256`, `pipeline` incl. `feet_crop` and `crop.batch`, `ppe`, `training`, `server`, `timing`, `camera`, `render`) | `configs/default.yaml`; opt-in `configs/footwear.yaml` | Jetson deploy | `configs/default.yaml` | key names (rename = breaking) |
| C5 | SHA-256-pinned SH17 + optional trained footwear specialist; derived `no-safety-glasses`, `no-helmet`, `no-gloves`, `no-safety-vest`, `no-safety-boots`. Ensemble retains SH17 IDs except generic shoes (14), suppressed; specialist IDs 17 shoes / 18 safety-boots under ensemble model_id | `configs/default.yaml`, `configs/footwear.yaml` → `models/` | Jetson deploy, alerts (class names) | `models/sh17.md`, `models/footwear-v1.md` | model card |
| C6 | Python package `vision` (import path, Python 3.10) | `autoCV` | Jetson deploy | `pyproject.toml`, `uv.lock` | package version |
| C7 | Independent scene inspection output (`scene_version: 1`), image-bound or declared closed yellow floor-tape definitions, frame-linked findings; no movement authority | Still inspection, opt-in Mac server/replay; `configs/zones-yellow.yaml` profile | Future dashboard/evidence | `vision/zones.py`, `vision/tape.py`, `vision/scene.py`, `docs/restricted-zones.md` | scene contract version |
| C8 | Independent walkway obstruction contract (`walkway_version: 1`): operator quadrilateral bound to a declared-empty fixed-camera reference file, entry/exit edges, reference check + change evidence; lane findings planned; no movement authority | `vision/walkway.py`; `configs/walkway.yaml` (prototype defaults). Library only — no CLI/live output yet | Future dashboard/evidence | `vision/walkway.py`, `docs/walkway-obstruction.md` | `walkway_version` |
| C9 | **Built on the Mac (dashboard Steps 2–4); no consumer yet.** Rover edge sync: `bob-app` v1 lane records (control / track / observation, per-lane `seq`, `store_epoch`), live state, `sync_*` messages, evidence blobs by SHA-256. Rover → laptop over the local network only; read-only except inspection start/end and profile delivery; no motion, arming or fault endpoints | `bobapp/edge/` (SQLite WAL store fed by `vision.server --edge`; edge API `python -m bobapp.edge.api`, port 8770, token `BOB_EDGE_TOKEN`); `configs/edge.yaml` | Laptop hub | `bobapp/contracts/`, `schema/app/*.schema.json`, `tests/fixtures/app/` | `app_version` (**v1**) |
| C10 | **Built on the Mac (dashboard Step 6); no frontend yet.** Hub frontend API: REST + `WS /v1/live`, worksites + inspection commands, incidents, Twin (`/v1/twin/…`, debug `map.svg`), `?workspace=rover|sample` (separate databases), token as for C9 (header or `?token=`); every item states `source_mode`, `delivery`, clock domains | `bobapp/hub/` (laptop, `python -m bobapp.hub serve`, port 8780) | Future frontend | `schema/app/hub-openapi.json` (generated, drift-tested) + `bobapp/contracts/` | `app_version` |

Wire codec (`encode` / `decode`) lives in `vision/schema/wire.py`. **Non-Python consumers** should validate against `schema/*.schema.json` **and** the fixtures: JSON Schema can't express cross-field rules (rigid transform, box bounds, `pose_valid` consistency, `source`↔`cls_id`), the fixtures do.

**Pose validity in C2 (Step 7):** `pose` is the camera pose of the event's **own** ARFrame (`pose_dt_ms = 0`), never a later one. `pose_valid=false` reasons: `session_mismatch` (a newer ARKit session exists — new world origin), `stale` (> `timing.stale_ms` gap on the iPhone clock right before the frame), `tracking_not_normal`, `no_pose` (camera vertical). `dt_exceeded` is reserved. The pose is the **phone's**, not the detected person's position, and is advisory only.

**Schema v2 (Step 3):** `Box.source` added; `cls_id` is null for derived boxes. Derived boxes are **per-frame observations**, not confirmed hazards — consumers apply their own N-frame confirmation. **Absence of a violation box does not mean compliant**: subjects too small/uncertain are not judged.

**Breaking change** = removing/renaming a field, key, class name, or changing units/meaning. Breaking changes require: `schema_version` bump → fixtures updated → every consumer in [§7](#7-branch-registry) notified and its checks ([§5](#5-checks-required-in-other-branches)) run **before** merge.

## 3. File ownership — avoiding merge conflicts

Conflicts mostly happen on shared files. Rule: **each branch edits only what it owns; shared files follow the rules below.**

| Files | Owner | Rule |
| ----- | ----- | ---- |
| `vision/`, `schema/`, `tools/`, `ios/`, `tests/` (CV tests), `models/*.md` | `autoCV` | Other branches import, never edit. Request changes via issue/PR to `autoCV`. |
| `pyproject.toml` | shared | Only add your own dependencies; never bump another branch's pin without telling its owner. |
| `uv.lock` | shared | **Never hand-merge.** On conflict: take `main`'s version, then `uv lock` and commit the regenerated file. |
| `configs/default.yaml` | shared | Each part owns its own top-level keys. Don't edit another part's keys. New parts should namespace (e.g. `safety:`, `alerts:`). |
| `README.MD`, `README-CV.md` | shared | Root README is the overall overview; CV guide retains detailed progression. Each part owns its own section; don't reflow unrelated sections. |
| `AGENTS.md`, `CLAUDE.md` | shared | Append a part-specific section; global rules change only by agreement. |
| `.gitignore` | shared | Append-only. |
| `integration.md` | shared | Update §2 and §7 whenever an interface or branch changes. |

## 4. Pre-merge gate: `autoCV` → `main`

All gates must pass, in order. Run from the repo root on `autoCV`. **No direct pushes to `main`** — merge only through a PR.

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

If exit 1: merge `main` into `autoCV` locally (`git merge origin/main`), resolve using the rules in [§3](#3-file-ownership--avoiding-merge-conflicts), re-run from G1.

### G3 — Cross-branch overlap check (catch conflicts *before* they happen)

Lists files that this branch **and** any other active branch both changed relative to `main`:

```bash
ours=$(git diff --name-only origin/main...HEAD)
for b in $(git branch -r --format='%(refname:short)' | grep -v -e HEAD -e origin/main -e origin/autoCV); do
  overlap=$(comm -12 <(echo "$ours" | sort) <(git diff --name-only origin/main..."$b" | sort))
  [ -n "$overlap" ] && echo "== $b also touches:" && echo "$overlap"
done
```

Any overlap on a contract file (`vision/schema/`, `schema/`, `configs/default.yaml`, `pyproject.toml`, `uv.lock`) → coordinate with that branch's owner before merging. Decide who merges first; the second rebases onto the new `main`.

### G4 — Tests on the merged result (not just on `autoCV`)

```bash
git worktree add ../BOB-premerge origin/main
cd ../BOB-premerge
git merge --no-ff --no-edit autoCV     # local trial merge only
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
gh pr create --base main --head autoCV --title "autoCV: <step>" --body "<gates + interfaces touched>"
```

## 5. Checks required in other branches

When `autoCV` changes an interface, these checks must pass **in the consuming branch** (against `autoCV`'s new fixtures) before `autoCV` merges.

| Consumer branch | Depends on | Check to run in that branch |
| --------------- | ---------- | --------------------------- |
| Safety supervisor / nav *(TBD)* | C2, C3 | Its tests parse `tests/fixtures/*detection_event*.json` from `autoCV`. It **stops** on `pose_valid=false`, `stale=true`, or new `session_id`. |
| Agent orchestration / alerts *(TBD)* | C2, C5 | Its tests parse the `DetectionEvent` fixtures. Class names match the model card. It never outputs motor commands. |
| Jetson deploy *(TBD)* | C4, C5, C6 | `uv run pytest` passes on the Jetson with `device: cuda`. ONNX → TensorRT build succeeds on the device. |
| Sensors gas/thermal *(TBD)* | C2 (if shared) | Event fixtures validate against the shared schema version. |

How to run a consumer's tests against `autoCV` without merging:

```bash
git worktree add ../BOB-consumer origin/<consumer-branch>
cd ../BOB-consumer
git checkout origin/autoCV -- vision/schema/ schema/ tests/fixtures/   # bring in new contract only
uv sync && uv run pytest
cd - && git worktree remove --force ../BOB-consumer
```

The reverse also applies: **before any other branch merges to `main`, it runs G1–G4 and `autoCV`'s tests must still pass on the merged result.**

## 6. After merge — verify `main`

```bash
git fetch origin && git checkout main && git pull
uv sync --locked && uv run pytest
git checkout autoCV && git merge origin/main     # keep autoCV current; don't let it drift
```

If `main` is red after a merge: whoever merged last fixes or reverts (`git revert -m 1 <merge-sha>`) — do not stack new merges on a red `main`.

## 7. Branch registry

| Branch | Part | Owner | Interfaces provided | Interfaces consumed | Status |
| ------ | ---- | ----- | ------------------- | ------------------- | ------ |
| `autoCV` | Computer vision (YOLOv8 PPE + ARKit pose) | Humbertxx | C1, C2, C3, C4, C5, C6, C7, C8 | — | Active · Step 5 built; Step 3b footwear v1 trained, held-out evaluated and opt-in pipeline wired; live/worksite acceptance pending; Step 3c image/tape and Mac live/replay inspection implemented, physical tape acceptance pending; Step 3d walkway definition + reference/change evidence library built (lane check, CLI pending) |
| `main` | Overall project baseline / integration target | — | C1–C10 | all | Created locally from synchronized `autoCV`; not published; future integration by PR |
| *(TBD)* | Safety supervisor / navigation | — | motor commands (out of CV scope) | C2, C3 | Not created |
| *(TBD)* | Agent orchestration / alerts | — | alerts | C2, C5 | Not created |
| *(TBD)* | Jetson deploy / hardware | — | — | C4, C5, C6 | Not created |
