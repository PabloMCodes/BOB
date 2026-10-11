# BOB autonomous-driving context

Last updated: 2026-10-11. This document records the agreed direction for the
navigation workstream. A camera-based preview and operator-authorized short BLE
steps are implemented. Physical step acceptance and hands-free obstacle avoidance
remain pending. [Current test guide](../supervised-camera-driving.md).

## Step 0 checkpoint: controller simulation

Implemented on 2026-10-11: `hardware/control_sim.py` is an isolated, standard-library
simulation with a local `ControllerLink` boundary and linear/angular requests.
It has no radio, motor, CV, or navigation connections. Run from the repository root:

```bash
.venv/bin/python -m hardware.control_sim
.venv/bin/python -m pytest -q tests/test_control_sim.py
```

The demo prints explicitly labeled SIMULATION states: connected/disarmed, a
fresh request, command expiry, refusal to resume from a fault, reconnect while
disarmed, and explicit stop. All 21 deterministic tests pass, including stale,
duplicate, reordered, non-finite, malformed and excessive requests, disconnect,
and delayed delivery that must not extend the original command lifetime.
Full repository validation: 394 passed, 5 optional/platform skips in 62.83 seconds
using the existing Jetson `.venv`; whitespace checks passed.

The simulator uses one injected monotonic clock and checks deadlines when stepped
or read. It is not a real-time watchdog and does not test process termination on
hardware. Its numeric speed/lease limits are test values, not approved operating
limits. `measured_wheel_velocity` stays unavailable; requested speed is not actual
speed. These internal Python types are experimental, not a published ESP32 wire
protocol or a change to the frozen CV schema.

Step 1 implementation prepared on 2026-10-11: the original `BOB_MotorTest` remains
unchanged as the recovery sketch. `BOB_ControllerBench/BOB_ControllerBench.ino`,
`hardware/controller_protocol.py`, and `hardware/esp32/bob_controller.py` add an
experimental binary BLE protocol, explicit arm, per-connection random session,
strict sequences, 100–500 ms receive-time leases, bounded open-loop mixing,
status/fault feedback, disconnect stop, and a bounded manual client. All packets
fit the default 20-byte ATT payload. This avoids comparing the unsynchronized host
and ESP32 clocks: a lease begins at valid receipt, while BLE ordering and sequence
checks reject replays. Host protocol and simulation tests pass.

Automated validation after Step 1: 39 targeted controller/protocol tests passed;
the full repository suite passed with 412 tests and 5 optional/platform skips in
61.86 seconds. The Jetson workspace does not contain Arduino CLI or the ESP32
Arduino headers, so the new `.ino` has not been compiled here. Arduino IDE 3.x
compilation and physical behavior remain part of the wheels-raised acceptance.

Physical Step 1 is partially observed: the user uploaded the controller sketch
after the Arduino String `c_str()` correction and connected from the Jetson.
Motor commands work after raising client requests to the firmware's existing
85/255 PWM cap. The user confirmed that `audio-restore-2`, which restores the
original speaker task, also plays the tone successfully. `speech-1` now replaces
that tone with an embedded, locally generated "Missing PPE" clip using the same
audio task. The user confirmed that both motor control and the spoken clip now
work from the Jetson with the uploaded sketch.
Remaining wheels-raised acceptance includes session mismatch/replay stopping,
independent lease expiry, disconnect/process death, reconnect without
motion, and actual stopping time. See the ESP32 README for the current test steps.

## Camera-only checkpoint: navigation preview

The user confirmed the iPhone camera is the only obstacle-related sensor currently
available. `python -m navigation` therefore implements a **motor-disabled preview**:
latest C2/C3 observations, an advisory visited-camera grid, hypothetical directions,
person observation, repeated derived PPE evidence, optional BLE speech, ten-second
pause and global announcement cooldown. Session changes discard the map and
evidence. Missing/stale/invalid observations stop suggestions. It loads no models
and sends no ARM or MOTION commands. [Run and acceptance guide](../navigation-preview.md).

This exercises inspection and exploration decisions before the physical motion
gates below. It does not claim route clearance, worker identity, measured wheel
velocity, localization accuracy, or scene-VLM hazard detection. No encoders are
required for this stage. Future wheel feedback belongs in a separate localization
and controller adapter; motion still needs an obstacle-stop supervisor.

## Intended behavior

Hackathon checkpoint (2026-10-11): the user authorized a slow, supervised
camera-only test. `python -m navigation.supervised` defaults to dry run;
`--execute` enables one 100 ms pulse per SPACE press while READY, followed by a
one-second stop and fresh camera observations. The existing firmware is reused.
R releases a host pause without moving; S/Esc stops; Q exits. Human clearance of
the proposed direction is mandatory; absence of detections never grants motion.
The model-free host consumes C2/C3, keeps the prior person/PPE inspection behavior,
and leaves vision/edge capture running. This limited test does not implement the
hands-free navigation target or bypass the later collision-avoidance acceptance.

BOB should explore a bounded work area in a Roomba-like way: prefer unvisited
reachable space, revisit only when needed to reach another frontier, and stop
when its localization or obstacle data is not trustworthy. While exploring it
continues the existing PPE inspection workflow.

When BOB sees a person, it should stop at a configured distance, observe several
fresh frames, assess PPE, announce a confirmed missing-PPE finding once, wait
about ten seconds, and then resume exploration if the navigation supervisor says
motion is allowed. A person/location cooldown should prevent repeated messages.
The speaker should use approved templates derived from confirmed rule results;
free-form model text must not be announced.

Navigation hazards and semantic scene findings are different:

- Fresh range/depth data, bump sensing, controller health, and stale-data checks
  may stop or limit motion.
- PPE detections and a future scene VLM produce inspection observations. They do
  not issue wheel commands or establish that a route is safe.
- A possible unguarded edge, unstable material, obstruction, or exposed sharp
  tool should cause a conservative inspection stop and a report for review. BOB
  must not approach a suspected hazard merely to improve the image.

## First prototype: compute off the rover

For the first controlled test, the Jetson may remain stationary off the rover.
The iPhone sends frames and ARKit pose over Wi-Fi to the Jetson as it does now.
The Jetson sends short-lived motion requests to the ESP32 over BLE. The ESP32,
motor driver, speaker, iPhone, and battery remain on the rover.

```text
iPhone -- Wi-Fi frames/pose --> off-board Jetson
                                      |
                         desired motion / stop
                                      |
                                     BLE
                                      |
                                      v
                         ESP32 --> TB6612FNG --> motors
                           |
                           +--> MAX98357A speaker
```

This arrangement is only for a nearby, supervised, low-speed prototype in a
controlled flat area. Loss of either Wi-Fi or BLE, stale phone frames, invalid
ARKit tracking, process failure, or command timeout must result in a stop.
Networking and software stops do not replace a physical emergency stop.

## BLE now, Wi-Fi later if justified

Use BLE first: the current `BOB_ControllerBench` firmware/client has user-confirmed
motor and speech operation, explicit arm, receive-time command leases and status.
The original `BOB-MotorTest` sketch remains a recovery baseline. This avoids adding
and debugging a second ESP32 transport before navigation behavior is understood.

The legacy single-character protocol is a bench-test interface, not the final
autonomy contract. `F/B/L/R` plus a shared PWM digit cannot express gradual arcs,
independent wheel effort, sequence numbers, acknowledgments, controller faults,
or future encoder feedback. The controller bench now supplies a binary protocol
and status. Future navigation execution should retain a transport-neutral
controller interface rather than letting planners write BLE packets directly.

Wi-Fi may become preferable when BOB needs richer telemetry, longer range,
multiple consumers, remote diagnostics, or ROS-native networking. It also adds
access-point dependence, addressing/reconnection work, and another failure path.
Changing BLE to Wi-Fi later should replace only the transport adapter, not the
planner, supervisor, or motor-controller contract.

## Stable interfaces for adding encoders later

Navigation should request body motion, not PWM values:

```text
MotionRequest
  sequence
  issued_at
  valid_for_ms
  linear_velocity_mps
  angular_velocity_radps

ControllerStatus
  last_sequence
  controller_state
  left_command / right_command
  fault_flags
  encoder_ticks / wheel_velocity   # unavailable at first, added later
```

During the encoder-free prototype, an ESP32 adapter maps bounded linear/angular
requests to open-loop left/right PWM. The reported controller state must say
that wheel motion is unmeasured. Adding encoders later changes the ESP32 adapter
to closed-loop wheel-velocity control and populates odometry feedback; it does
not change the navigation request format.

Likewise, localization should expose a generic odometry source with quality and
freshness. Initially it can use session-local ARKit pose as advisory odometry.
Later, wheel encoder and IMU measurements can be fused without changing the
exploration state machine. A new ARKit session invalidates its coordinate map;
it must never be silently joined to the previous origin.

## Proposed component boundary

```text
exploration goal selector
        |
        v
map / localization --> path planner --> local controller
                                           |
person/PPE event --> inspection state ------+--> safety supervisor
range/depth data --> collision monitor -----+          |
tracking/data freshness --------------------+          v
                                             transport adapter
                                             (BLE first)
                                                     |
                                                     v
                                              ESP32 watchdog
                                                     |
                                                     v
                                                   motors
```

The safety supervisor is the only component allowed to forward motion requests.
It should distinguish requested state, transmitted command, controller-reported
state, and measured wheel motion. Until encoders exist, measured wheel motion is
unknown even after a successful BLE write.

## Exploration and inspection states

Suggested high-level states:

1. `DISARMED`: no autonomous motion; startup and fault-reset state.
2. `READY`: sensors are fresh and the operator may begin a mission.
3. `EXPLORE`: choose a reachable unvisited frontier and follow a slow path.
4. `PERSON_STOP`: stop and establish a safe stationary observation.
5. `PPE_OBSERVE`: collect several fresh frames; do not decide from one frame.
6. `ANNOUNCE`: play one approved message when a violation is confirmed.
7. `WAIT`: remain stopped for roughly ten seconds and maintain collision checks.
8. `RESUME`: revalidate all motion prerequisites, apply cooldown, then explore.
9. `HAZARD_STOP`: stay stopped for navigation danger or possible scene hazard.
10. `FAULT`: latched stop for stale sensors, invalid tracking, lost controller,
    low battery, process failure, or explicit emergency stop.
11. `COMPLETE`: no reachable frontiers remain; stop and await the operator.

Leaving a stop state must always re-check current sensor freshness and controller
health. A timer expiring never grants motion by itself.

## Sensors and current limitations

The encoder-free version can demonstrate approximate exploration and inspection,
but it cannot guarantee complete coverage, precise turns, docking, or return to
home. Open-loop motion changes with battery voltage, surface, load, and wheel
slip. ARKit can reduce drift but remains an advisory visual-inertial estimate and
may lose or reset tracking.

Earlier notes described an approximately 20 cm-high mount tilted upward for PPE.
The user clarified on 2026-10-11 that the current camera is barely angled upward
and can see the floor about five inches (13 cm) ahead. The three mounted images
`IMG_0344/0345/0346.jpg` have now been inspected: broad floor foreground is visible,
along with boxes, chair legs and furniture bases. The lower quarter to third is
mostly floor. The nearest visible ground distance is still user-reported; camera
calibration, robot footprint, side/rear coverage and stopping distance have not
been measured. At 1920×1440 the installed SH17 pipeline emitted no boxes in these
three empty-room photos, including no furniture detections: it is not an obstacle
detector. See the [assessment and test guide](../supervised-camera-driving.md).
Obstacle/drop-off stopping remains unvalidated. The audible LiPo alarm is not
machine-readable, so early
missions need a conservative time limit until battery telemetry is available.

## Development sequence and acceptance gates

Keep this work outside the CV motor-safety boundary and integrate through
explicit observation and telemetry interfaces.

1. **Transport bench:** wheels raised; repeated short-lived BLE requests, stop,
   disconnect, malformed packet, and process-kill tests all result in neutral
   motor output within a measured bound.
2. **Open-loop motion calibration:** controlled flat floor, low PWM, measure
   straight motion and turns at several battery levels. Record variability; do
   not describe PWM as velocity.
3. **Supervised remote driving:** dead-man input, physical emergency stop, and
   controller status visible. No autonomous exploration yet.
4. **Automatic obstacle stop:** independent range/depth data stops the rover
   before an obstacle at the maximum configured test speed.
5. **Person inspection:** automatic stop, multi-frame PPE assessment, simulated
   announcement first, cooldown, ten-second wait, and guarded resume.
6. **Bounded exploration:** small marked flat test area, approximate visited map,
   slow frontier selection, no stairs or public traffic.
7. **Encoder upgrade:** per-wheel feedback, closed-loop speed, odometry fusion,
   and repeat all stopping and exploration tests before expanding the area.

For every physical test, record the firmware revision, transport, command rate,
timeout, PWM/speed limit, surface, battery state, sensor configuration, observed
stopping distance, and whether the result was automatic or user-reported.

## Current repository facts

- `hardware/esp32/BOB_MotorTest/BOB_MotorTest.ino` implements BLE motor commands,
  a one-second command timeout, disconnect stop, and a speaker test.
- The user confirmed motor direction and speaker operation on 2026-10-10.
- `BOB_ControllerBench` adds the C11 binary protocol and status characteristic;
  `bob_controller.py` refreshes leases during bounded manual trials and disarms
  after each trial. Motor and embedded speech operation are user-confirmed.
- The firmware has no encoder input, Wi-Fi transport, obstacle sensor, or onboard
  navigation. The original preview has STOP/speech access only. The separate
  supervised executor has single-pulse motion access after explicit operator input,
  a declared LIVE run, fresh observations and controller status checks.
- PPE, pose association, recording, and detections remain owned by the current
  computer-vision pipeline. Motor control remains a separate workstream.

## Unresolved choices

- Exact forward/downward obstacle sensor and mounting geometry
- Physical emergency-stop implementation
- Physical operating distance for the off-board Jetson BLE link
- Initial maximum PWM and measured maximum speed
- Physical validation of the existing C11 protocol, status and lease limits
- Obstacle-aware planning beyond the preview's bounded camera-visit grid
- Battery-voltage telemetry and mission stop threshold
- Further speaker messages and calibration of confirmation/cooldown defaults;
  the preview uses a global cooldown because persistent worker identity is absent
