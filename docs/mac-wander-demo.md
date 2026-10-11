# Mac wander-until-person demo

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

Click the window and press **R** to start a 30-second search. Each movement requests a
250 ms burst, followed by at least 600 ms stopped and a new detection before another
burst. Directions are randomly selected: forward 60%, left 20%, right 20%; no
reverse. Speed is the working remote's existing speed 3 / controller cap.

Any model person, head or face box at confidence >= 0.5 stops movement and latches
**PERSON FOUND**. PPE processing continues on the Jetson; the window displays its
existing per-frame verdicts. Unknown evidence stays unverified. This demo does
not approach/follow a person or introduce new speech/PPE decisions. After the
person leaves, press R to deliberately start another search.

**Space/S** stops; **Esc/Q** quits. Losing window focus pauses. Feed loss, stale or
frozen detections, session/run changes, and the time limit stop the search; none
resume automatically. A restored feed needs another R press. BLE errors exit.

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

Physical wander/person-stop acceptance is pending. The user confirmed the
underlying arrow-key Bluetooth remote works before this feature.

Mac implementation note: hub validation runs in a small separate process to keep
OpenCV’s bundled SDL out of the pygame window process. It runs no inference.

Validation (2026-10-11): **20 wander tests passed**, including the spawned HTTP
feed worker. The actual pygame-loop simulation passed without SDL conflicts.
Final full suite: **740 passed, 4 optional skips**, 77.06 s. An unrelated
camera-server timing assertion failed on the preceding run and passed on the
full rerun. The local live hub was unreachable during the read-only check;
no physical Bluetooth or Jetson-feed acceptance is claimed.
