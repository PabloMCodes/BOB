# Supervised point driving on the Jetson

This is a flat-floor, short-range operator demo. Local PPE and site-photo capture
continue. Camera poses guide steering; the operator checks the route and holds
the drive control. There is no obstacle-stop sensor or measured wheel velocity.
No encoder or firmware change is required.

## Internal interface (C15)

`vision.server --detect --point-preview` writes one atomic `point_frame.json` in
its run directory from the original admitted frame and its exact detection result.
It includes run/source identity, C2, C1 camera metadata, resolved orientation and
a clean reduced JPEG. A bounded latest-only writer performs encoding and disk IO;
inference never waits for it. This is local preview metadata, not a new phone
transport or a CV wire-schema change. No raw phone messages bypass FrameServer.admit.

`python -m navigation.point_drive --run-dir ... --camera-height-m ...` serves a
separate operator page on loopback port 8790. A Mac accesses it through an SSH
tunnel. The existing hub C10 API still has no motion endpoints. The page uses the
existing BOB_EDGE_TOKEN, held only in browser memory, for frame requests and a
single authenticated control WebSocket. Camera clicks name the displayed event
ID; stale or unknown IDs are refused. Source REPLAY/SAMPLE is dry-run only.

Floor projection uses source camera intrinsics, the exact frame transform and
explicit measured camera height. Image rotation is inverted before projection.
The fixed floor plane is reset with the camera session; targets farther than
1.5 m, above the horizon or with an insufficient downward angle are rejected.
Heading uses an explicit camera-to-rover yaw offset for physical execution.
Targets refer to the camera's horizontal position, with a 0.20 m arrival radius;
this is not calibrated chassis clearance or collision geometry.

Holding the control renews a short authorization lease; release, tab blur,
disconnect, expired heartbeat, stale/frozen input, invalid pose, a new session or
run, person/PPE interruption and controller failures stop or inhibit movement.
Fresh data alone cannot restore a revoked hold: release and press again. Tracking
loss/session changes invalidate the target. One 100 ms pulse is followed by at
least one second stopped and fresh observations. Maximum 30 pulses / 120 seconds
per process; dry run is the default. No reconnect or queued movement commands.

Setup and automated acceptance are recorded below. Physical acceptance remains
separate from the software checks.

## Start a dry run

The user measured the fixed camera height as **4.3 inches / 0.10922 m** on
2026-10-11. That is the CLI default; measure to the camera lens and override
`--camera-height-m` if the mount changes. The reported upward mount angle is not
hard-coded: each ARKit transform supplies actual camera pitch/roll/yaw.
The user reconfirmed this height and camera/rover forward alignment during the
implementation review. Automated tests do not measure the physical mount.

On the Jetson, stop the old vision server in its terminal, then restart with the
additional point-preview flag and a known run directory (retain any extra model
or zone flags from your existing command):

```bash
cd /home/pablo/BOB
.venv/bin/python -m vision.server --detect --no-view --edge --point-preview --run-dir runs/point-demo
```

Keep the existing edge API/hub/website services running for PPE and site photos.
In a second Jetson terminal:

```bash
cd /home/pablo/BOB
.venv/bin/python -m navigation.point_drive --run-dir runs/point-demo
```

On the Mac, open the SSH tunnel in its own terminal:

```bash
ssh -N -L 8790:127.0.0.1:8790 pablo@10.6.3.3
```

Open **http://127.0.0.1:8790** on the Mac and enter the existing BOB_EDGE_TOKEN.
The page is separate from the inspection dashboard; its heading must show
**DRY_RUN**. Click visible level floor, then move the rover by hand: the green
target marker should stay on the selected floor location, the arrow should turn
in the correct direction, and distance should decrease when approaching it.
Above-horizon, stale, too-near or distant clicks are refused. At this low camera
height, the 8-degree downward-ray minimum limits usable flat-floor targets to
roughly 0.78 m even though the absolute maximum is 1.5 m.

After validating that the camera points along the rover's forward axis, the
explicit physical command is:

```bash
.venv/bin/python -m navigation.point_drive --run-dir runs/point-demo --execute --forward-yaw-offset-deg 0
```

Exit any other BLE controller/speech runner first. A nonzero yaw offset must be
measured if camera forward differs from chassis forward. Hold the button or Space
only after checking the complete wheel sweep and route. Release, Escape, STOP,
tab blur or closing the page ends authorization. A blocked hold is discarded;
release and press again once the page is ready. This prototype does not replace
independent obstacle sensing. Validate wheel direction, stopping distance and
arrival manually before driving toward a real target.

The original camera and current C3 must be at most 0.5 s old; operator replies
expire after 0.3 s. The page exchanges one single-use server ticket per control
message, so delayed/buffered heartbeats cannot replay old driving permission.
Only one operator connection is accepted. JPEGs and projection data are bounded
local previews and are not sent through the dashboard's evidence/backfill route.
The run's `point_drive_*.jsonl` records target source metadata, calibration,
authorized pulses and controller acknowledgments; firmware PWM is open loop.

Physical motion has not been performed by the automated checks. The default
height is user-reported; ground projection and camera/chassis alignment require
the hand-moved check above. Encoder feedback can later replace open-loop pulse
execution while retaining the target geometry and operator lease.

## Implementation and automated acceptance (2026-10-11)

The work was reviewed in order: exact-frame projection and metadata, operator
authorization and pulse handling, browser interaction, then full-repository
validation. The final review tightened release/blur/STOP behavior, cancels pending
selection on stop, prevents replaced sockets from authenticating, stops preview
polling after disconnect and faults the driver if its monitor unexpectedly exits.
Authenticated preview responses are never cached. Startup and target traces
include the declared source run and mount calibration.

- Point-driving Python suite: **47 passed in 6.43 s**, covering image orientations,
  scaled intrinsics, pitch/roll/yaw, provenance, invalid clicks, interrupted holds,
  session/floor reset, fake radio, encoding failures, latest-only writing, auth and
  actual recorded-frame replay through the server. No physical hardware is used.
- Full Jetson Python suite: **758 passed, 5 skipped in 179.79 s**. Three export
  tests need the optional export group; one prelabel test needs labeling; one MPS
  test is Apple-only. The existing Starlette/httpx deprecation warning remains.
- Headless SAMPLE browser acceptance passed: image-bound selection, hold/pulse,
  release, Space/blur, rejected horizon click, replacement/reconnect without a
  restored hold, expired ticket rejection and no persisted token.
- Python 3.10 runtime/syntax and `git diff --check` pass. CV v2, bob-app v1,
  controller v1, model weights and inference backends are unchanged.

To repeat the checks using this Jetson's existing NVIDIA environment:

```bash
YOLO_AUTOINSTALL=false .venv/bin/python -m pytest -q tests/test_point_driving.py
YOLO_AUTOINSTALL=false .venv/bin/python -m pytest -q
node tests/point-driving.browser.mjs
```

The browser script needs Playwright and its Chromium download. If installed
outside the project, set `BOB_PLAYWRIGHT_MODULE` to its `index.mjs`. The script
starts and removes an isolated SAMPLE server, uses a test-only token and never
opens BLE. Local reports are `runs/point-driving-pytest.log` and
`runs/point-driving-browser.png`; they are gitignored. `uv` is unavailable on this
host, so checks used the existing Python 3.10 environment without replacing
NVIDIA's torch build. No physical motion or live-service restart was performed.
