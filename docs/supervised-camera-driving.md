# Supervised camera driving test

The Jetson can now propose short exploration steps and send each one to the
working ESP32 **after a SPACE press**. It stops between steps, pauses for people,
and can play the existing “Missing PPE” clip after repeated derived PPE evidence.
This is a supervised stepping demo, not hands-free obstacle avoidance. No new
ESP32 upload or encoders are required. Physical pulse distance and stopping tests
are still pending; no robot movement was performed during implementation.

## What the mounted images show

Inspected the three local JPEGs in `test_images/` on 2026-10-11. Each is
5712×4284; the HEICs are alternative copies, not three more test scenes.

| Image | Visible coverage | Implication for the test |
| --- | --- | --- |
| `IMG_0344.jpg` | Broad floor foreground, central doorway, boxes and chair base on the left, furniture base on the right | There is usable forward floor coverage. The open-looking central area still needs a person to check its width and clearance. |
| `IMG_0345.jpg` | Floor foreground plus a close chair leg near the left edge; boxes ahead | Turning can sweep a wheel or body corner into a side obstacle even when the center looks open. |
| `IMG_0346.jpg` | Floor foreground, hallway to the left, shelving, cables, scratching-post base and sofa edge ahead/right | Small objects, cables and side clearance need attention; the center of the image alone is insufficient. |

The photos support your correction that the camera sees the floor. Floor covers
roughly the lower quarter to third of these views, with interruptions at furniture
bases. They do **not** measure the nearest visible ground distance, robot width,
turning footprint, lens calibration, or stopping distance. Five inches ahead is
your reported distance, not a measurement from these images. There are no people
in these samples, so they do not establish head/feet visibility for PPE at demo
distances. Check those using the actual capture app: its orientation, resolution
and crop may differ from a still photograph.

The existing pinned SH17 pipeline was evaluated locally on all three at 1920×1440
with the current CUDA configuration. It returned **zero boxes on each**. Model
inference times were 199.6, 73.1 and 72.5 ms respectively; these three sequential
still-image timings are not a live latency or accuracy benchmark. Results:
`runs/navigation/camera_assessment/mounted_images.json`.

Zero PPE boxes does not mean no obstacles: the photos visibly contain furniture.
No floor-color heuristic or VLM was added to grant movement. Bright patches,
shadows, patterned flooring and similarly colored cardboard would need separate
evaluation. The current checkout has SH17 weights; the optional trained footwear
weights are absent, so this measured run leaves the boots rule inactive.

## Start the existing camera pipeline

On the Jetson, use the working capture app and the working `speech-1` firmware.
Close `bob_controller.py`, `bob_ble.py`, or any other BLE client first. The stepping
process owns the controller connection exclusively.

If the server is already running with a fresh `run_info.json`, use that run's
directory below. An older running server needs one restart to write the new local
run identity. Stop it with Ctrl-C in its terminal before launching another server
on port 8765. Start a dedicated run in terminal 1:

```bash
cd /home/pablo/BOB
DRIVE_RUN="runs/server/drive_$(date +%Y%m%d_%H%M%S)"
echo "$DRIVE_RUN"
YOLO_AUTOINSTALL=false .venv/bin/python -m vision.server \
  --detect --no-view --edge --source-mode LIVE --run-dir "$DRIVE_RUN"
```

Keep your existing validated `--config` and other model flags if using a different
working profile. This command uses `configs/local.yaml` (CUDA) and the installed
default SH17 model. Do not add `--config configs/footwear.yaml` until its pinned
weights exist locally. `--edge` retains the offline frame archive and website
publication; it does not require a connected website. The separate edge/hub
processes still need to run for website sync; see [offline demo](offline-frame-demo.md).

Connect the iPhone to the Jetson as usual. Copy the printed run directory into
terminal 2; the shell variable in terminal 1 is not shared across terminals.

## First dry run, then a physical step

In an interactive Jetson terminal (VS Code Remote SSH's terminal is fine):

```bash
cd /home/pablo/BOB
# Replace this path with the directory printed by the running server.
.venv/bin/python -m navigation.supervised \
  --run-dir runs/server/drive_YYYYMMDD_HHMMSS
```

This defaults to **DRY RUN** and opens no Bluetooth connection. Wait for normal
camera tracking, press **R**, then wait for **READY: forward/turn_left/turn_right**.
Press **SPACE** to simulate one chosen step. Check that a person entering view
causes OBSERVE/HOLD, and that pausing the camera causes PAUSED. Quit with **Q**.

For the first powered test, raise the wheels securely with nobody near them.
Use a three-step limit, check which direction the wheels actually turn, and verify
they return to neutral after each pulse. The phone must keep tracking normally;
if raising the platform breaks tracking, resolve that before movement rather than
disabling the check.

```bash
.venv/bin/python -m navigation.supervised \
  --run-dir runs/server/drive_YYYYMMDD_HHMMSS \
  --execute --steps 3 --seconds 30
```

Once those directions/stops are verified, use a cleared, level floor patch with
room around the entire turning footprint, away from stairs and drop-offs. Keep
the motor power switch reachable and a person beside the rover. Start with one
SPACE, measure its travel and coast after power stops, and verify that the visible
clear area is larger than that travel plus the robot's footprint and a margin.
Do not use furniture, a person, a pet or a stair edge as the stopping target.

For the short PPE demo after that check:

```bash
.venv/bin/python -m navigation.supervised \
  --run-dir runs/server/drive_YYYYMMDD_HHMMSS \
  --execute --speech --seconds 60 --steps 20
```

| Key | Behavior |
| --- | --- |
| **R** | Release a host pause if current observations allow it. This does not arm or move the ESP32. |
| **SPACE** | Authorize exactly one currently proposed step while READY. Check both forward clearance and the side/rear sweep of a turn first. |
| **S** or **Esc** | Stop and latch a pause; requires R again after checking the cause. |
| **Q**, **Ctrl-C** | Stop, disconnect and exit. |

Press SPACE deliberately for each step. Input during movement, settling, person
inspection or stale tracking is discarded, never queued for later. A held key
can generate new input when READY returns, so do not rest anything on the keyboard.
**R plus SPACE typed together only releases the pause.** Arrow keys include Esc
and stop the test. Do not run the driving process with `nohup` or an unattended
service: terminal loss/SIGHUP is intended to end it.

## Actual limits and behavior

- Default 100 ms **single** motion packet, then STOP/disarm and at least one
  second stationary. `--pulse-ms` accepts only 100–150 ms. There is no continuous
  lease refresher. The firmware expires the command independently after its
  receive-time lease if the host stalls. Actual wheel coast is unmeasured.
- The existing working firmware maps the command to at most **85/255 PWM**.
  Open-loop “200 mm/s” and “500 mrad/s” fields are nominal intents, not measured
  speeds. Slow stepping limits duty cycle; it does not establish low peak speed.
  If a pulse only hums, stop and use the manual bench test to diagnose it.
- Default limit 60 seconds / 20 step attempts, hard caps 120 seconds / 30 attempts.
  No reverse travel command is selected. A pivot still reverses one wheel.
- Before READY: three distinct current observations over at least 0.2 seconds,
  receiver timestamps at most 0.5 seconds old, normal tracking and valid pose.
  After a pulse, the next eligible frame must have been **received after** the
  settling interval. These are Jetson wall-clock times; iPhone clocks are not
  subtracted from them.
- Invalid/stale data, a camera session change or operator stop latches a host
  pause; fresh data alone cannot restart movement. A changed server identity,
  changed BLE session, controller error or clock regression ends the test. There
  is no automatic BLE reconnect. A packet already in radio transit can still
  arrive; the ESP32 lease starts at receipt, not at the operator's keypress.
- Camera poses guide a small 25 cm visited-cell map within advisory ±0.75 m
  bounds. This is **not a physical geofence, occupancy map or collision check**.
  Heading/distance may drift, and the rigid phone mount and turn direction still
  need physical validation. Each proposed direction needs human clearance.
- A detected person/head/face interrupts movement. Repeated supported derived PPE
  findings for one overlapping person can request “Missing PPE” once, followed by
  a ten-second hold; a person still in view keeps the hold. Speech has a global
  30-second cooldown. Unverified PPE is never called missing. Once observations
  permit exploration again, a **new SPACE** is still required.

PPE processing and `--edge` frame storage continue in their own server throughout
the driving test. With no new model loaded, this adds file polling, a small visit
grid and BLE IO, not another GPU model. Website connectivity never grants movement.
During the Wi-Fi-off demo, the robot also stops if the driving terminal loses SSH;
the separately running vision server can keep capturing. To show capture recovery
without interrupting local camera input, keep iPhone and Jetson on their network.

## Records, verification and encoder upgrade

The printed `runs/navigation/supervised_.../` directory contains `steps.jsonl`,
`settings.json` and an advisory `map.svg`. Logs distinguish a step request, a BLE
write acknowledgment and controller-reported zero PWM. **Measured wheel velocity
remains null**. A write acknowledgment does not prove movement or audible sound.

Automated checks use synthetic admitted events, fake BLE and an actual pseudo
terminal; they never operate the rover. Validation on 2026-10-11: **44 new tests
passed** in 5.69 s; full repository suite **684 passed, 5 optional/platform skips**
in 170.63 s, with one existing FastAPI dependency deprecation warning. Python 3.10
syntax and whitespace checks pass. Record physical results separately: pulse
travel, turn direction, stop/coast distance, stale-camera stop, operator stop,
disconnect/lease expiry and a live person/PPE pause. Those measurements are pending.

Keep the planner and operator gate in `navigation/step.py` separate from the
`StepLink` transport in `navigation/drive.py`. Encoders can later add per-wheel
feedback and closed-loop speed in a new controller adapter, retaining the same
step/stop/announcement boundary. Any richer firmware status requires an explicit
protocol revision; do not silently reinterpret C11 v1. Encoders improve speed and
odometry but do not detect obstacles or drop-offs. Hands-free exploration needs
an evaluated obstacle-stop path and new physical acceptance tests.
