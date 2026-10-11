# Arrow-key Bluetooth remote

Power on BOB and close any other BLE control script. From the repository root
on your Mac (or a Jetson with a local desktop), run:

```bash
uv run --no-project --with bleak==3.0.2 --with pygame==2.6.1 python -m hardware.esp32.remote
```

This installs the two small remote dependencies in uv's isolated environment.
Allow your terminal Bluetooth access if macOS asks. Click the remote window:

- Hold ↑ / ↓ for forward / backward.
- Hold ← / → to turn left / right.
- Release to stop. Space or S stops; Esc or Q quits.
- F/B/L/R also work without pressing Enter.

No camera, phone, server, token, or firmware upload is required. Run locally,
not through a headless SSH terminal. The computer must be within BLE range.
The first matching BOB is selected; power on only the robot you intend to drive.

It detects both existing firmware variants. MotorTest receives ASCII F/B/L/R/S
at speed 3; ControllerBench receives the existing arm and motion packets with
its existing 85/255 PWM cap. Arming happens on a fresh directional press.
Motion refreshes every 100 ms while held. Release, conflicting direction keys,
window focus loss, closing the window and exit send STOP. Space requires
releasing and pressing a direction again. Errors exit rather than reconnecting
and resuming motion. Firmware timeout remains 300 ms for ControllerBench or
one second for MotorTest if the host stops sending commands.

Point driving and its preview server option have been removed. Vision capture
and inspection can run separately and are not needed for manual movement.

Validation (2026-10-11): all eight remote protocol/input tests pass; the real
pygame window loop passes simulated release/focus/Space/exit checks with a fake
BLE client. Full `uv run pytest -q`: **720 passed, 4 optional skips** in 77.87 s.
An existing uint8 test fixture was corrected for NumPy 2; a first-run server
timing failure passed on the full rerun. Python 3.10 compatibility verified. Physical Bluetooth movement and stopping require an operator check;
no robot was moved during automated tests.

Repeat the simulated window check (no BLE connection):

```bash
uv run --no-project --with bleak==3.0.2 --with pygame==2.6.1 python tests/keyboard_remote_window.py
```
