# Navigation preview on the Jetson

The first navigation stage reads the existing vision server's C2 detections and
C3 stream health. It suggests directions toward less-visited camera positions,
observes people, optionally says **Missing PPE**, and pauses for ten seconds.
**Motor output is disabled in every state.** No new ESP32 upload is needed for
preview; optional speech uses the already working `speech-1` sketch.

Only the iPhone camera is currently connected. The user reports that it is barely
angled upward and sees the floor about five inches ahead. Three mounted photos
have now been inspected and show broad floor foreground; distance and stopping
measurements remain pending. This preview command keeps motion disabled.
For the separate operator-authorized motor test, use the
[supervised driving guide](supervised-camera-driving.md). It reuses this advisory
planner and adds one short BLE pulse per explicit operator request.

## 1. Exercise the sequence without hardware

On the Jetson, from the repository root:

```bash
cd /home/pablo/BOB
.venv/bin/python -m navigation --demo
```

This prints `EXPLORE → OBSERVE → ANNOUNCE → HOLD → EXPLORE`, then a stale-input
stop and session reset. The ten-second interval is simulated, so the demo runs
quickly. It neither connects to BLE nor runs a model. Outputs are under the
printed `runs/navigation/<timestamp>/` directory: `decisions.jsonl` and `map.svg`.
Open the SVG in VS Code over SSH. Blue cells are visited camera positions, green
is the camera, and yellow is the hypothetical next goal. Blank cells have
**unknown clearance**. The final demo map is empty after the session-reset test.

## 2. Use the live phone detections

Use the existing Jetson `.venv`; do not recreate it or run `uv sync`, which may
replace the JetPack CUDA packages. Start your usual detection server with
`--detect`; retain its current model/config/edge options. This change makes
`stream_health.jsonl` line-buffered, so an already-running server must be restarted
once to pick that up. Do not start a second server on the same port.

The server prints its output directory after `->`. In a second SSH terminal,
substitute that exact directory for `PATH_TO_CURRENT_SERVER_RUN`:

```bash
cd /home/pablo/BOB
.venv/bin/python -m navigation \
  --run-dir PATH_TO_CURRENT_SERVER_RUN --source-mode LIVE
```

Move the phone by hand through a small area while streaming. This records a grid
of camera positions, not wheel odometry. Show a person to the camera: suggestions
stop immediately. A single visible person with overlapping person boxes and the
same derived PPE violation on at least three distinct frames spanning 0.4 seconds
can produce an announcement. Missing/uncertain evidence remains unverified.
Multiple people do not trigger speech because this stage has no reliable worker
identity. Three repeated model mistakes can still cause a false announcement;
temporal confirmation does not establish PPE accuracy.

The observation window is two seconds, followed by a ten-second pause. Confirmed
PPE starts the pause earlier. Suggestions resume only after the pause and one
second without a detected person; a person still visible keeps the preview in
`HOLD`. Announcements have a global 30-second cooldown, including across camera
session resets. These are experimental defaults, not calibrated worksite policy.

The run ends after 120 seconds (`--seconds` changes this) or Ctrl+C. Pose/tracking
loss, stale input, invalid JSON, and session changes stop suggestions. A new
session clears the map and evidence; retired sessions and a regressing monotonic
clock require a preview restart. Time spent stopped counts toward the run limit.

## 3. Enable the working speaker, still without motion

Exit `bob_controller`/`bob_ble.py` first: only one host should own the connection.
Install the existing pinned BLE dependency into the Jetson environment if needed:

```bash
.venv/bin/python -m pip install -r hardware/esp32/requirements.txt
.venv/bin/python -m navigation \
  --run-dir PATH_TO_CURRENT_SERVER_RUN --source-mode LIVE --ble-speech
```

The BLE adapter sends STOP on connection, verifies disarmed/zero PWM, and sends
the existing `TONE` packet for the **Missing PPE** clip. It exposes no ARM or MOTION
operation. It stops audio on invalid input and sends STOP on exit. Connection or
status errors end the process; it does not reconnect or queue announcements.
`write_acknowledged` means BLE acknowledged the command, not verified playback.
If the firmware predates `speech-1`, that packet plays its old test tone instead.

## Source and interface limits

- Run this consumer on the **same Jetson** as the vision server: C2/C3 freshness
  uses that receiver's wall-clock timestamps, never the iPhone's clock. Timers use
  monotonic time. Events older than 750 ms, future timestamps, or C3 `stale=true`
  stop suggestions; inference that is consistently slower will remain stopped.
- `--source-mode` is an operator declaration because C2/C3 do not carry source
  mode. Use `REPLAY` or `SAMPLE` for those sources. Speech is rejected in these
  modes and in the demo. Never label replay as live.
- Reads select only the latest complete line with a 256 KiB read limit. They do
  not accumulate inference or replay old frames as multiple confirmations.
  Use a new server output directory after server restarts.
- The default grid is 0.5 m cells within ±2 m of the initial camera position.
  It prefers unvisited immediate neighbors and revisits when necessary; it has
  no occupancy map, path planner, coverage guarantee, or camera-to-rover calibration.
- It consumes C2/C3 after the existing `FrameServer.admit()` path. No new phone
  decoder, weights, inference process, wire-schema fields, or Swift logic is added.
- Encoder feedback can later enter a localization/controller adapter. The pure
  preview state machine remains separate from BLE and model inference. Connecting
  directions to a motor controller requires a separate guarded executor, obstacle
  sensing and validation; removing a flag is not sufficient.
- Broader scene hazards (trip hazards, edges, unstable tools/materials) are not
  yet inputs to this preview. VLM integration and grounding evaluation remain
  separate from obstacle-stop sensing.

Automated acceptance on 2026-10-11: 63 targeted navigation/server tests passed in
10.54 s; the full Jetson suite passed **630 tests, 5 optional/platform skips** in
160.51 s. Run with `YOLO_AUTOINSTALL=false .venv/bin/python -m pytest -q`.
A separate synthetic SAMPLE stream exercised 30 live-tail decisions without BLE.
Physical camera/speech acceptance for this consumer remains to be performed;
existing manual motor/speech operation was user-confirmed before this change.
