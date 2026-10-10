# BOB — Construction Inspection Rover

BOB is a Knight Hacks construction-inspection prototype that combines an iPhone camera and ARKit pose, local PPE detection, and an evidence backend that synchronizes with an operator laptop. The goal is to help a human reviewer inspect selected PPE conditions and controlled restricted zones, with the original observation and its uncertainty available for review.

**Current deployment:** a Mac stands in for the rover's future Jetson Orin Nano. Live phone capture, vision, local storage, rover-to-laptop synchronization and a frontend API are implemented. A browser dashboard, integrated autonomous navigation and Jetson acceptance remain pending. ESP32 motor and speaker bench tests are separate from perception.

This is a controlled demonstration, not a certified safety system. A detection does not establish PPE certification or permission for the rover to move.

## System overview

```text
iPhone: camera + ARKit pose
             |
             | local WebSocket: JPEG + timestamped pose
             v
Rover computer: Mac today, Jetson deployment planned
  shared vision pipeline -> PPE / zone observations
             |
             v
  bounded writer -> SQLite edge store + evidence
             |
             | local sync: resume, acknowledgments, evidence hashes
             v
Operator laptop: hub replica -> REST / WebSocket frontend API
                                             |
                                             v
                                 browser dashboard / 2D Twin (planned)

Separate hardware bench: Mac BLE client -> ESP32 motors + speaker
```

The operational data path stays on the local network. The hub catches up after a link interruption; backfilled observations remain distinguishable from current state. The proposed Hugging Face showcase uses separately curated public examples, not a live rover upload.

## Project status

| Workstream | Implemented / documented evidence | Remaining acceptance or work |
| --- | --- | --- |
| iPhone capture | Thin Swift app, ARKit pose, JPEG streaming, recording; documented live 1,179-frame run at 10 Hz | Physical interruption/kill-test checklist |
| Computer vision | SH17 PPE, head crops, optional footwear specialist, timestamp association, replay and ONNX parity | Own-photo/worksite PPE accuracy; full physical acceptance |
| Restricted zones | Operator-defined image zones and closed yellow floor-tape inspection, Mac live/replay output | Physical tape and foot-evidence validation |
| Walkway obstruction | Fixed-camera reference validation and change mask | People handling, lane check, CLI and physical tests |
| Edge backend | Application contracts, SQLite WAL store, bounded publication and separate sync API | Later inspection/incident workflow and calibration gates |
| Laptop hub | Replica, reconnect/backfill, evidence verification, frontend API and separate SAMPLE workspace | Browser frontend; full profile/inspection workflow acceptance |
| Local sync milestone | Documented one-Mac process test: 1,012/1,012 records matched after a 10-second link cut; 64/64 evidence blobs verified | Physical multi-device and deployment acceptance |
| Hardware | User-reported ESP32 motor operation and speaker operation after a ground connection fix | Integrated controller telemetry, navigation and supervisor |
| Jetson | Portable Python, pinned exports and handoff procedure | On-device install, TensorRT build and J1–J6 |
| Hugging Face | Step-by-step model/dataset/Space plan | Evaluation release, Hub publication and showcase implementation |

These are implementation and recorded-test summaries, not claims of field accuracy. The detailed [CV progression and measurements](README-CV.md#progression) retain the original development log, including backend milestones D1–D6.

## Quick start

Use Python 3.10 and [uv](https://docs.astral.sh/uv/). The current capture workflow uses a Mac with Xcode and a physical iPhone; ARKit does not run in the Simulator. Jetson setup has a separate [handoff guide](docs/jetson-handoff.md).

From the repository root:

```bash
uv sync
uv run pytest
```

To run phone inference with local recording and edge publication:

```bash
uv run python -m vision.server --detect --record --edge
```

Connect the iPhone app to the server's reachable local address. See the [CV guide](README-CV.md) for iOS setup, signing, camera orientation, replay, model configuration and physical checklists.

Run the edge API and laptop hub in separate terminals:

```bash
uv run python -m bobapp.edge.api
```

```bash
uv run python -m bobapp.hub serve
```

The default edge API port is `8770`; the hub API port is `8780`. Without an access token, API binding is loopback-only. For separate machines, configure the local edge address and authentication using [edge settings](configs/edge.yaml), [hub settings](configs/hub.yaml) and the [backend plan](docs/plans/dashboard-twin-integration-plan.md). Keep local overrides and tokens out of Git. The hub currently serves an API, not a finished dashboard.

## Documentation

| Guide | Contents |
| --- | --- |
| [Computer vision guide](README-CV.md) | Original detailed README: capture, PPE, model evaluation, replay, measured progression and backend milestone log |
| [Backend and Twin plan](docs/plans/dashboard-twin-integration-plan.md) | Local storage/sync, frontend contracts, worksite profiles, incident semantics and remaining gates |
| [Hugging Face implementation plan](docs/plans/hugging-face-implementation-plan.md) | Reproducible model release, rover-view dataset, comparison Space and optional evidence descriptions |
| [Restricted-zone inspection](docs/restricted-zones.md) | Image/tape conventions, uncertainty and physical acceptance |
| [Walkway inspection](docs/walkway-obstruction.md) | Fixed-camera scope and unfinished lane assessment |
| [Jetson handoff](docs/jetson-handoff.md) | Installation, engine export and on-device acceptance |
| [ESP32 hardware](hardware/esp32/README.md) | Wiring, BLE commands and motor/speaker bench results |
| [Model cards](models/sh17.md) / [footwear specialist](models/footwear-v1.md) | Provenance, hashes, label meanings, licensing and measured limitations |
| [Integration guide](integration.md) | Interfaces, ownership, branch registry and merge gates |

## Repository layout

| Path | Responsibility |
| --- | --- |
| `vision/` | Shared perception, pose association and phone server |
| `ios/` | Thin iPhone capture/streaming app and Swift wire contract |
| `bobapp/contracts/` | Separately versioned application contracts |
| `bobapp/edge/` | Rover-side persistence, publication and sync API |
| `bobapp/hub/` | Laptop replica, synchronization and frontend API |
| `hardware/esp32/` | Standalone motor/speaker bench tools |
| `configs/`, `schema/`, `tests/` | Configuration, generated contracts and automated checks |
| `tools/` | Evaluation, training, replay, schema export and parity tools |
| `docs/` | Feature guides and implementation plans |
| `data/`, `models/`, `runs/` | Local datasets, weights and outputs; large artifacts are gitignored |

## Interpretation and limits

- **Unverified is not compliant.** Small, occluded or unsupported subjects must not become assumed passes or violations.
- SH17 detects eyewear generally; it cannot certify safety glasses. The footwear specialist recognizes the documented visual boot convention, not protective certification.
- ARKit pose locates the camera observation within a session. It does not locate the worker or establish a persistent site map.
- Zone and walkway findings have no movement authority. No integrated hazard-stop behavior is claimed.
- Keep LIVE, REPLAY, SAMPLE and NOT INTEGRATED sources explicit. A disconnected rover has unknown current state.
- Ultralytics, SH17 and footwear data have different license terms. Consult the model cards; the project is not uniformly permissively licensed.

## Development and branches

`main` is the local overall-project baseline created from the committed `autoCV` work and its upstream hardware documentation. `autoCV` remains the CV development branch. This initialization does not publish `main` or change the GitHub default branch.

Follow [AGENTS.md](AGENTS.md) and [integration.md](integration.md): preserve existing work, synchronize before feature changes, run required checks, and use reviewed PRs for subsequent integration into `main`. Update the [detailed progression](README-CV.md#progression) with measured results and keep this overview aligned with actual project capabilities.
