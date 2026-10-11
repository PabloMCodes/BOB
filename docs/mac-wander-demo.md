# Mac continuous roaming and PPE demo

The Mac owns Bluetooth, using the same `Remote` adapter as the working arrow-key
remote. The iPhone still streams to the Jetson; the existing Mac hub relays its
live detections. No firmware upload, second model, or Jetson motor process.

Keep the usual Jetson vision server (`--detect --edge`, declared LIVE), edge API,
and iPhone stream running. Close the arrow-key remote and any other BLE client.
In the Mac repository, start the local hub if it is not already running:

```bash
cd /Users/pablomendoza/Desktop/BOB
uv run python -m bobapp.hub serve
```

In another Mac terminal:

```bash
cd /Users/pablomendoza/Desktop/BOB
uv run --with bleak==3.0.2 --with pygame==2.6.1 python -m hardware.esp32.wander
```

Unlike the standalone arrow remote, this command uses the project environment to
validate the existing hub/detection contracts. It reads the existing
`BOB_EDGE_TOKEN` from the environment or gitignored `.env`. Do not paste tokens
into commands or chat. Hub connection settings remain in the existing hub config.

Click the window and press **R once**. It keeps operating until you pause or
quit; there is no 30-second run timeout. The pattern is two 350 ms forward steps,
then one 600 ms randomly chosen left/right turn, with 200 ms observation gaps.
Speed is unchanged. This replaces repeated in-place sweeps with more forward
travel. There is no measured angle, obstacle avoidance or coverage guarantee.

A person must be a full `person` class box at confidence >= 0.75, at least 2% of
image area and 20% of image height to interrupt scanning. Isolated head/face,
small or low-confidence detections no longer cause repeated stops. These are
inspection filters, not obstacle clearance or a fix for detector accuracy.

Inspection lasts at most four seconds. A missing-PPE announcement requires the
same rule on two distinct positive frames spanning at least 0.25 seconds, associated with
a continuously overlapping person box. Only one visible person is eligible for
speech; per-subject derived violation verdicts are used, not the frame summary.
Evidence tolerates at most a 0.75-second gap for the same person; an unverified
frame never triggers speech or counts as positive. Unverified results never
become a pass or violation. Repeated model mistakes can still cause a warning.

Confirmed missing PPE plays the existing **Missing PPE** clip on the working
ControllerBench speech-1 firmware while stopped. Allow 1.5 seconds after BLE
acknowledgement for the clip, with a global 10-second speech cooldown. Original
MotorTest firmware cannot speak; it logs unsupported instead of playing a beep.

After inspection (including unverified results), the robot turns away in place
for at least one second, until the person has been absent for 0.4 seconds, then
resumes scanning automatically. A persistent person detection does not interrupt
this bounded turn. If the view has not cleared after four seconds, it stops for three seconds,
then automatically inspects again. It does not keep turning indefinitely. This does not identify or track a person across visits.

The existing Jetson archive already saves processed-frame JPEGs and syncs them
to the website's full frame gallery. The demo reuses those photos; it does not
add a new camera/photo pipeline or change the website. Each inspection writes an
entry to `runs/wander/<run>/inspections.jsonl` with the original event/session/run
IDs, original JPEG hash, confirmed rules and speech delivery status. An image hash
means saved on Jetson, not confirmed downloaded by the website. If no hash is
present, the UI/log says no saved photo; it never claims capture succeeded.
Use the full frames view rather than the selected-site-photo filter for PPE frames.

**Space/S** pauses until another R press; **Esc/Q** quits. Losing window focus
also pauses until R. Camera loss, stale/frozen detections and session changes
stop movement immediately. Once enabled, the demo automatically resumes after
two seconds of healthy, advancing detections. Explicit pauses are never undone
by an idle timer or feed recovery. BLE errors still exit instead of reconnecting
and moving unattended.

This is a supervised demonstration on a cleared, level floor with a reachable
motor power switch. It has no obstacle/drop-off sensing. An empty person-detection
result is not evidence that a path is clear. If the Mac stalls, firmware motion
expiry remains 300 ms for ControllerBench or one second for original MotorTest.

## Data and validation

Reads only existing C10 `/v1/status` and `/v1/observations` on localhost:8780,
rover workspace, LIVE source and realtime delivery. Checks run/store/session
identity and a one-second freshness budget including reported rover feed age,
record/capture age, hub receive age and local request duration. Jetson clock
values are compared only with Jetson values; Mac timers are monotonic. Repeated
identical frames expire. Delayed network delivery is not independently measured
one-way; these are demo freshness checks, not obstacle safety guarantees.

Automated checks use contract fixtures and fake motors. The actual pygame loop
is tested with fake BLE and synthetic detections:

```bash
uv run pytest -q tests/test_wander.py tests/test_keyboard_remote.py
uv run --with bleak==3.0.2 --with pygame==2.6.1 python tests/wander_window.py
```

The user confirmed basic wandering/person stops work, then reported false-person
stalls and requested more turning. The new scan/speech/turn-away sequence still
needs physical acceptance. Automated tests never move the robot.

Mac implementation note: hub validation runs in a small separate process to keep
OpenCV’s bundled SDL out of the pygame window process. It runs no inference.

Validation (2026-10-11): **20 wander tests passed**, including the spawned HTTP
feed worker. The actual pygame-loop simulation passed without SDL conflicts.
Final full suite: **740 passed, 4 optional skips**, 77.06 s. An unrelated
camera-server timing assertion failed on the preceding run and passed on the
full rerun. The local live hub was unreachable during the read-only check;
no physical Bluetooth or Jetson-feed acceptance is claimed.

Bluetooth startup follow-up (2026-10-11): initialize pygame and the feed worker
after connecting/stopping the controller, matching the working remote order.
Errors now include the failed stage and original message instead of only
`BleakError`. A read-only Mac scan, connection and status read succeeded against
BOB-ControllerBench: DISARMED, NONE fault, PWM (0,0). No motor commands were sent
in that check; the cause of the original intermittent failure is unconfirmed.

Startup-fix validation: simulated pygame/BLE loop passes; full suite
**741 passed, 4 optional skips** in 85.73 s, including the scan-error regression.

## If new photos stop saving at the archive limit

The live Jetson check on 2026-10-11 showed 2,172,448,737 store bytes (over the
configured 2 GiB cap), about 85 GB of free disk space, and no image hashes on
five fresh observations. Existing gallery images were still available. The
archive intentionally stops saving new images when this limit is reached.

To raise only that existing limit to 8 GiB, run on the Jetson from `/home/pablo/BOB`:

```bash
.venv/bin/python - <<'PYTHON'
from pathlib import Path
import yaml
path = Path('configs/edge.local.yaml')
config = (yaml.safe_load(path.read_text()) or {}) if path.exists() else {}
config.setdefault('retention', {})['max_store_bytes'] = 8 * 1024**3
path.write_text(yaml.safe_dump(config, sort_keys=False))
print('Archive cap set to 8 GiB; existing overrides preserved; no images deleted.')
PYTHON
```

Restart the existing vision-server command to load the change. If that command
uses an explicit `--edge-config` override, update that file instead. Keep its
other model/camera/edge flags. The Mac hub and edge API can remain running.
This remote setting was **not applied**: SSH authentication from the Mac was
unavailable. Saved-image and website-sync acceptance remains pending.

Scan/speech follow-up validation: **32 wander tests + 8 remote tests passed**;
actual pygame loop passed with fake BLE. Full suite **752 passed, 4 optional
skips**, 92.58 s. The preceding run hit the existing server-shutdown timing
assertion; the full rerun passed. No physical motion or speech was triggered
by these checks.

Continuous-operation validation (2026-10-11): **38 wander tests + 8 remote
tests passed**; pygame-loop simulation passes. Full suite **758 passed,
4 optional skips**, 81.34 s, after integrating current main. A subsequent
main update changed website speaker wording only. Tests cover ongoing operation
past 30 seconds, feed recovery, frozen-feed blocking, persistent manual pauses,
automatic rechecks, short uncertain gaps, stale evidence and 10-second speech
cooldown. Latest 30 queried Jetson observations reported only UNVERIFIED PPE;
this change does not relabel them as violations. Physical acceptance pending.
