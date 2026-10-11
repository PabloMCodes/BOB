# ESP32 motor and speaker bench test

Standalone hardware test requested alongside the CV work. It does not consume
computer vision detections or control the rover autonomously.

The separate [supervised camera step test](../../docs/supervised-camera-driving.md)
reuses the working `BOB_ControllerBench` speech firmware without another upload.
It sends one short motion pulse per operator authorization; close other BLE
clients before running it. Its physical stop/direction acceptance is pending.

The proposed off-board navigation architecture, initial BLE choice, and
encoder-ready controller boundary are recorded in
[the autonomous-driving context](../../docs/plans/autonomous-driving-context.md).

See [CONTEXT.md](../../CONTEXT.md) for the full hardware session handoff,
decisions, observed failures, and the ground connection fix.

## Hardware and wiring

ESP32 DevKit V1, TB6612FNG motor driver, MAX98357A I2S speaker amplifier.
The D labels below mean GPIO numbers, not physical header positions.

| Device | Pin | ESP32 connection |
| --- | --- | --- |
| TB6612FNG (right motor, channel A) | AIN1 | D15 |
| TB6612FNG | AIN2 | D2 |
| TB6612FNG | PWMA | D23 |
| TB6612FNG (left motor, channel B) | BIN1 | D21 |
| TB6612FNG | BIN2 | D19 |
| TB6612FNG | PWMB | D22 |
| TB6612FNG | STBY | 3.3 V directly |
| TB6612FNG | VCC | 3.3 V |
| MAX98357A | BCLK | D25 |
| MAX98357A | LRC | **D26** |
| MAX98357A | DIN | D33 |

GPIO34 is input-only and cannot drive LRC. Move that wire to GPIO26 before
testing audio. The user's module has only G, V, BCL, LRC, and DIN pins; it has
no exposed amplifier SD/EN pin. V is connected to nominal 5 V (user measured
4.16 V at the module). G must be wired to ESP32 GND and shared supply ground.
The ESP32's GND pins are internally connected, but that does not connect an
external amplifier unless its G pin is physically wired to that ground.
Leave the ESP32 EN pin alone; it controls the ESP32, not the amplifier.
MAX98357A supply range is 2.5–5.5 V. Connect the speaker across the amplifier's speaker outputs;
neither speaker output goes to ground.

Right motor positive goes to AO1, negative to AO2. Left motor positive goes to
BO1, negative to BO2. The sketch reverses the right motor's forward polarity
to account for the observed wheel orientation.

Use a suitable motor supply at VM and connect the supply, driver, amplifier,
and ESP32 grounds together. Do not power motors from ESP32 GPIOs. Lift the
wheels during the bench test. GPIO2 and GPIO15 are strapping pins: if upload
fails with the driver connected, disconnect those signal wires during upload.

## Upload from Arduino IDE

1. Install **esp32 by Espressif Systems 3.x** in Boards Manager.
2. Open `BOB_MotorTest/BOB_MotorTest.ino`.
3. Select **DOIT ESP32 DEVKIT V1** (fallback: **ESP32 Dev Module**).
4. Choose the USB port that appears when you plug in the board and upload.

Serial Monitor is optional for motor testing. Use **115200 baud** to see
connection status, speaker-test progress, or initialization failures.
Audio only initializes when requested, so the speaker can be disconnected
while testing motors.

## Connect from a Mac terminal

From the repository root, run:

```bash
cd hardware/esp32
python3 -m venv /tmp/bob-ble-env
source /tmp/bob-ble-env/bin/activate
python -m pip install -r requirements.txt
python bob_ble.py
```

Allow Bluetooth access for your terminal if macOS prompts. The script scans
for **BOB-MotorTest**, connects over BLE, and accepts one command followed by
Return. No phone app is needed. Restart the script to reconnect after an upload.

| Command | Behavior |
| --- | --- |
| `0`–`9` | Select PWM duty from off to full; stops current movement |
| `F` | Both wheels forward |
| `B` | Both wheels backward |
| `L` | Left backward, right forward; turn in place |
| `R` | Left forward, right backward; turn in place |
| `S` | Stop motors and cancel audio |
| `T` | Stop motors, play a 440 Hz tone for five seconds |
| `H` | Print status to USB Serial Monitor (not the BLE terminal) |
| `Q` | Terminal client sends stop and disconnects |

Start with `3`, then `F`. Movement expires after one second unless another
movement command arrives. Disconnects and unknown commands stop the motors.
Motor commands cancel the speaker test. Stopping electrical drive does not
guarantee instantaneous mechanical stopping.

The speaker tone uses amplitude 4000 out of 32767 with a short fade at both
ends. Audio writes run in a background task so the motor timeout can still run.
The BLE service and command UUIDs match the previous WALL-Y sketch.

## Validation status

- User reported the motor commands worked as intended after reversing the
  right motor polarity (2026-10-10).
- Speaker was initially silent despite start/end messages. The user found an
  open amplifier G → ESP32 GND connection, secured a permanent ground jumper,
  and confirmed the speaker worked (2026-10-10). The exact uploaded firmware
  revision was not independently verified; the repo uses the five-second tone.
- Python client syntax checked locally. Arduino compilation and a BLE connection
  have not been verified in the agent's Linux environment.

References: [Espressif I2S API](https://docs.espressif.com/projects/arduino-esp32/en/latest/api/i2s.html),
[ESP32 GPIO restrictions](https://docs.espressif.com/projects/esp-idf/en/latest/esp32/api-reference/peripherals/gpio.html),
[MAX98357A pinout](https://learn.adafruit.com/adafruit-max98357-i2s-class-d-mono-amp/pinouts).

## Autonomous controller bench (experimental)

Keep `BOB_MotorTest` as the known-good recovery sketch. After its motor directions,
one-second timeout, disconnect stop, explicit stop and tone pass with the reorganized
wiring, upload `BOB_ControllerBench/BOB_ControllerBench.ino`. It uses the same pins
and motor polarity but advertises **BOB-ControllerBench**. The user compiled and
uploaded it after replacing `value.data()` with `value.c_str()`, and verified BLE
connection, arming and reported disarming. After the PWM correction and
`audio-restore-2` revision, the user confirmed both motor control and audible tone.
The user subsequently confirmed the `speech-1` Missing PPE clip and motor control
working from the Jetson. The remaining fault/stopping checks await physical acceptance.

The controller-bench protocol uses binary packets that fit within the default
20-byte BLE ATT payload. Its source of truth is `hardware/controller_protocol.py`:

| Packet | Behavior |
| --- | --- |
| `STOP` | Always neutralize outputs and disarm; no session needed |
| `ARM(session)` | Arm only for the ESP32 session reported after this connection |
| `MOTION(session, sequence, lease, linear, angular)` | Accept a fresh, in-range request while armed |
| `TONE(session)` | Stop and disarm, then play the embedded "Missing PPE" speech clip (`speech-1` firmware) |
| status | Report state, fault, session, last sequence and commanded PWM |

The ESP32 generates a new random session on every connection. Motion sequences must
strictly increase. A motion lease is 100–500 ms and begins when the ESP32 receives
the packet, so no Jetson/ESP32 clock synchronization is assumed. Expiry, malformed
packets, session mismatch, replay, limits, and disconnect all neutralize the outputs
and disarm. A new motion packet cannot clear a fault; the operator must explicitly arm.
Status says encoder feedback is unavailable. Requested mm/s and mrad/s are bounded
motion intents mapped to open-loop PWM and are not measured physical velocities.

The bench sketch limits output to `85/255`, approximately digit `3` in the original
sketch. Its client sends only bounded manual trials of at most two seconds and sends
`STOP` after every trial. With the wheels raised, run from the repository root:

```bash
python3 -m venv /tmp/bob-ble-env
source /tmp/bob-ble-env/bin/activate
python -m pip install -r hardware/esp32/requirements.txt
python -m hardware.esp32.bob_controller
```

Use `STATUS`, then `ARM`, then `F`, `B`, `L`, or `R`. A duration may follow, such as
`F 0.5`; the default is 0.5 seconds. Each completed trial disarms, so enter `ARM`
again before the next. `STOP` neutralizes immediately, `TONE` tests the speaker, and
`Q` stops before disconnecting. Also test process interruption and ESP32 power-cycle;
neither should cause startup or resumed movement.

The revised client requests 85/255 PWM for each direction trial, matching the
original sketch's speed digit 3. Previously its half-scale requests produced
43/255 PWM, a possible explanation for motor hum without rotation. The firmware
cap remains 85/255. The user reports motor controls now work from the Jetson;
stopping time and link-loss acceptance still require physical checks.

The earlier `audio-diag-1` revision reported 332800 bytes written in 5207 ms;
the user subsequently reported silence with the amplifier connected. The user
also confirmed that the original sketch played sound immediately before uploading
the new one with unchanged wiring. The exact audio regression remains unresolved.

The previous sketch identified itself as `audio-restore-2` at 115200 baud. It copied
the original `BOB_MotorTest` speaker task exactly except for the printed `STOP`
command name, and queues the tone immediately after disarming under the controller
lock. Audio pins, sample rate, amplitude, task stack/priority, cancellation atomics
and I2S format match the original. `TONE` should print `Speaker: 440 Hz test tone`
and then `Speaker test ended.` or an audio error. As in the original, the ended
message can also follow cancellation; it does not prove audible playback.
The user confirmed that this restoration plays the tone and motor control works.

The current revision is `speech-1`: `TONE` now plays "Missing PPE" with the same
working I2S/task path. Speech was synthesized locally with eSpeak NG 1.50, US English,
145 words/minute. The self-contained sketch embeds 17928 bytes of mono PCM8 at
16 kHz (1.12 seconds), expanded to stereo PCM16 at playback with peak 8000/32767.
It needs no extra Arduino tab, SD card, internet, or runtime TTS engine. The voice
is synthetic/robotic. `tools/embed_bench_speech.py` documents how to regenerate it
from a locally synthesized WAV; the source WAV is not committed.
Upload this whole sketch, reconnect the Jetson client, and enter `TONE` alone.
`ARM`, motion, `STOP`, or disconnect cancels sound. The user confirmed successful
upload and audible speech from the Jetson. The new [navigation preview](../../docs/navigation-preview.md)
can use this same clip via STOP/TONE only, with motor output disabled.

Do not connect USB power and an external 5 V feed to the ESP32 simultaneously
unless the exact board's power isolation has been verified. For USB diagnostics,
power down before disconnecting the external positive feed to ESP32 5V/VIN.
The amplifier can retain its separate supply with common ground, provided its
positive rail is not also connected to the USB-powered ESP32 5 V rail.

Python verification:

```bash
.venv/bin/python -m pytest -q tests/test_controller_protocol.py tests/test_control_sim.py
```

These tests validate host packet encoding and the controller-state simulation. They
do not execute the Arduino firmware or measure physical stopping time.
