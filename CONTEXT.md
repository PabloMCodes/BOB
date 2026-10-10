# BOB ESP32 motor and speaker context

Last updated: 2026-10-10. This is the handoff for the hardware work discussed
in this chat: what was built, the actual wiring, what worked on the robot,
what went wrong, and how to continue without repeating those mistakes.

## Current outcome

- The user confirmed motor commands work as intended after reversing the
  right motor's software polarity.
- The user confirmed the speaker works after fixing its ground connection.
- The latest committed sketch has a five-second 440 Hz speaker test at
  amplitude 4000/32767, plus natural comments explaining the implementation.
- A capacitor was discussed but was not needed to resolve this failure.
- These are manual bench tests, not autonomous navigation or safety controls.

Physical results are user-reported. The editing agent did not independently
measure the circuit or compile/upload the sketch to the user's ESP32.
The user's exact uploaded firmware revision was not independently verified.

## Project scope and source of truth

Repository: `PabloMCodes/BOB`; working branch: `autoCV`.

The main branch work described in [README.MD](README.MD) and
[AGENTS.md](AGENTS.md) is YOLOv8 PPE detection on iPhone frames with ARKit pose
association. Python owns detection and association; Swift captures and sends
frames. The Mac stands in for the Jetson, and `vision/` must remain portable to
Python 3.10 on Jetson. [integration.md](integration.md) defines CV contracts
and integration gates. See those files for current CV status rather than
assuming this hardware handoff documents all CV implementation details.

The user explicitly requested storing this standalone hardware work in the
same repository. It lives under `hardware/esp32/`, independently of `vision/`.
No CV schema, config contract, or autonomous motor interface was changed.

| File | Purpose |
| --- | --- |
| [Arduino sketch](hardware/esp32/BOB_MotorTest/BOB_MotorTest.ino) | BLE motor controls and I2S speaker test |
| [Terminal client](hardware/esp32/bob_ble.py) | Scan, connect, and send commands from the Mac |
| [Client requirements](hardware/esp32/requirements.txt) | Separate BLE dependency, `bleak==3.0.2` |
| [Hardware setup](hardware/esp32/README.md) | Wiring, upload instructions, commands, validation |
| This file | Conversation context, decisions, troubleshooting history |

Earlier versions existed only under `/tmp/BOB_MotorTest/`. Those temporary
files and chat download links are not the source of truth. Repository files
are authoritative; an Arduino IDE copy on the user's Mac must be updated and
uploaded separately. Editing GitHub does not update the running firmware.

## User preferences and collaboration

- Keep code in GitHub, not just temporary files or chat attachments. The user
  explicitly requested that any code be stored there.
- Preserve this preference across follow-up edits. Synchronize with upstream,
  preserve teammates' work, review, and publish relevant changes as authorized.
- Use the Mac terminal for Bluetooth testing. The user previously controlled
  a Love Bugs/WALL-Y robot this way and does not want a phone app requirement.
- Keep code comments natural and explanatory.
- Give concrete instructions that work on the user's Mac. This editing
  workspace is Linux and cannot directly write to the Mac's Downloads folder.
- Download links did not work for the user; pasteable terminal instructions
  or files available through GitHub are better alternatives.
- Serial Monitor is optional for normal operation, useful for diagnostics.

## Hardware

- ESP32 **DevKit V1** (classic ESP32).
- **TB6612FNG** dual motor driver.
- **MAX98357A I2S Audio Amplifier & 3W Speaker Kit**.
- User's amplifier exposes only **G, V, BCL, LRC, DIN**. Do not assume a
  breakout with extra SD/EN or GAIN pins.
- Speaker is the separate transducer connected across the amplifier's two
  speaker outputs. The amplifier is the circuit board with the I2S pins.
- Motor supply voltage, speaker impedance, and exact amplifier module vendor
  were not confirmed in this conversation.

## Wiring and direction settings

The board's D labels mean GPIO numbers, not physical header positions.

| Motor driver pin | ESP32 connection | Role |
| --- | --- | --- |
| AIN1 | D15 | Right direction input 1 |
| AIN2 | D2 | Right direction input 2 |
| PWMA | D23 | Right PWM speed |
| BIN1 | D21 | Left direction input 1 |
| BIN2 | D19 | Left direction input 2 |
| PWMB | D22 | Left PWM speed |
| STBY | 3.3 V directly | User-confirmed enable wiring |

Right motor positive connects to AO1, negative to AO2. Left motor positive
connects to BO1, negative to BO2. VCC should be 3.3 V; VM uses a suitable motor
supply. VCC and motor supply details have not been physically verified here.

```cpp
constexpr bool LEFT_FORWARD_IN1_HIGH = true;
constexpr bool RIGHT_FORWARD_IN1_HIGH = false;
constexpr int STBY = -1; // No GPIO: wired directly to 3.3 V.
```

| Amplifier label | Connection |
| --- | --- |
| G | ESP32 GND and shared supply ground |
| V | User's nominal 5 V supply |
| BCL | D25 (`AUDIO_BCLK`) |
| LRC | **D26** |
| DIN | D33 |

LRC was originally wired to D34. GPIO34 is input-only, so the user moved it
to D26 and explicitly confirmed that change. Do not ask them to repeat that
as if it remains unconfirmed.

The user measured **4.16 V between V and G at the amplifier**, steady during
the test. This is within the amplifier's 2.5–5.5 V operating range, although
lower than the intended 5 V. The supply discrepancy was not independently
diagnosed. It did not prevent sound after the ground connection was fixed.

## Critical ground distinction

**The ESP32's GND pins are connected internally, but the amplifier's G pin
still needs a physical connection to that shared ground.** Connecting supply
ground to one ESP32 GND does not automatically connect another board's G pin.

Both ESP32 GND pins do not need separate supply wires. Either can be used as
the amplifier's ground connection. A direct amplifier G → ESP32 GND jumper
resolved the user's problem. Secure that connection; do not rely on meter
probes or pressure on a loose contact to complete it.

**ESP32 EN is the ESP32's reset/enable pin.** It is not an amplifier enable
pin. Do not connect it to 3.3 V as an audio troubleshooting step. Earlier advice
about an amplifier SD/EN pin did not apply to this five-pin module.

## Arduino IDE and Mac setup

- Install **esp32 by Espressif Systems 3.x** in Boards Manager.
- Select **DOIT ESP32 DEVKIT V1**; fallback is **ESP32 Dev Module**.
- Select the USB port that appears when the ESP32 is plugged in.
- The user's screenshots showed `/dev/cu.usbserial-0001`; this is historical,
  not a fixed port name. A stale `/dev/cu.usbserial-110` showed not connected.
- Serial Monitor baud: **115200**, matching `Serial.begin(115200)`.
- GPIO2 and GPIO15 are strapping pins; connected hardware can affect boot or
  upload. If an upload fails, investigate those connections.
- Re-upload after editing firmware, then restart the BLE client to reconnect.

From the repository root on the Mac:

```bash
cd hardware/esp32
python3 -m venv /tmp/bob-ble-env
source /tmp/bob-ble-env/bin/activate
python -m pip install -r requirements.txt
python bob_ble.py
```

Allow terminal Bluetooth access if macOS prompts. The client scans for
**BOB-MotorTest** and accepts one command followed by Return. It supports
lowercase input too. It does not automatically repeat movement commands.

## BLE and commands

The old pasted sketch advertised `WALL-Y`; the new sketch advertises
`BOB-MotorTest`. Both use these custom UUIDs:

```text
Service: 12345678-1234-1234-1234-1234567890ab
Command: abcdefab-1234-5678-1234-abcdefabcdef
```

| Command | Result |
| --- | --- |
| F | Both wheels forward |
| B | Both wheels backward |
| L | Left backward, right forward; rotate left |
| R | Left forward, right backward; rotate right |
| S | Stop motors and cancel audio |
| 0–9 | Set PWM duty, stop current movement; send direction afterwards |
| T | Stop motors and request the speaker tone |
| H | Print health/state to USB Serial Monitor, not the BLE terminal |
| Q | Client-only: send S and disconnect |

Start with `3`, then `F`, with wheels lifted. Motor PWM is 1 kHz, 8-bit
(0–255); startup duty is 80. Movement times out after 1000 ms without another
movement command. H and speed changes do not extend an existing movement.
Connect/disconnect and invalid commands stop motors. These are bench-test
behaviors, not a certified safety system or instantaneous mechanical brake.

## Implementation details worth preserving

- `motorLock` serializes BLE callbacks and `loop()` motor/state changes.
- Direction changes disable PWM first and pause briefly when changing an
  active movement command.
- Audio uses `ESP_I2S.h`, standard I2S, 16 kHz, 16-bit stereo.
- Identical sine samples go to both channels so channel selection cannot
  silence a tone by choosing the other channel.
- Tone: 440 Hz, five seconds, amplitude 4000 out of 32767, 10 ms edge fades,
  followed by 200 ms of silence to flush queued audio.
- Speaker work runs in a separate FreeRTOS task. Blocking audio writes do
  not hold the motor lock or suspend the motor timeout loop.
- Audio initializes only on T, allowing motor-only testing without the amp.
- Atomic request/version counters cancel pending and playing tones. S,
  disconnects, and motor movement commands cancel sound.
- Future Jetson control was discussed: send commands to ESP32 over USB serial
  and keep PWM generation on ESP32. This is a proposed direction only; the
  current sketch accepts BLE commands and does not implement serial commands.

## Troubleshooting history and evidence

1. Initial motor behavior: F drove left forward/right backward; B did the
   reverse; L drove both backward; R drove both forward. Flipping only
   `RIGHT_FORWARD_IN1_HIGH` to false fixed this. User confirmed success.
2. Initial speaker T produced no audible tone. Serial Monitor was initially
   disconnected; choosing the active USB port exposed the diagnostic output.
3. Serial output included readable `Connected; stopped.`,
   `Speaker: 440 Hz test tone, about 1 second.`, and `Speaker test ended.`
   These confirmed command handling and no reported audio API failure;
   they did not prove correct electrical signals or speaker output.
4. Tone was extended from one second/amplitude 1000 to five seconds/amplitude
   4000 to make it easier to hear. This did not establish the root cause.
5. User confirmed amplifier V was on nominal 5 V, LRC on D26, and the actual
   module had only G/V/BCL/LRC/DIN. There was no exposed amplifier enable pin.
6. Meter lacked a continuity beep but had resistance ranges 200, 2k, 20k,
   200k, 2M. Using 200 Ω with power disconnected, signal connections read
   near zero; amplifier G → ESP32 GND read OL, indicating an open path.
7. Sound initially worked only when meter probes were touching the circuit,
   suggesting a bridged or pressure-sensitive connection. A permanent ground
   connection was secured, and the user reported: **"works now."**

For future wire checks, disconnect USB and all batteries before measuring
resistance. Probe direction does not matter for a direct wire check. Never
leave the meter in resistance mode on a powered circuit. DC voltage checks
use amplifier G as reference. Neither speaker output is a ground terminal.
A multimeter's DC reading cannot establish correct I2S data; use an
oscilloscope or logic analyzer if signal verification becomes necessary.

## Validation, publishing, and remaining work

- Motor and speaker operation are confirmed by the user on their hardware.
- Agent-side Python 3.10 syntax and Git whitespace checks passed for the code
  publication. Full pytest and Arduino compilation were unavailable in that
  environment (`uv`, pytest, and Arduino CLI were absent).
- Initial code was published on `autoCV` as commit `74a30ab` via the connected
  GitHub app. Direct `git push` lacked HTTPS credentials in the agent workspace.
- Normal Git metadata writes required elevated access because `.git` was
  read-only inside the default sandbox. Use available authorized tooling;
  do not assume this means the user must manually publish completed work.
- Later teammate commits may have advanced the branch. Pull before edits and
  preserve unrelated changes. Never force-push or push directly to main.
- Keep this context and the hardware README current when wiring, firmware,
  commands, or validation results change.
- Still unverified: full-power motor load behavior, long-duration audio/power
  stability, automated firmware build, and any future Jetson control transport.

Hardware references: [I2S API](https://docs.espressif.com/projects/arduino-esp32/en/latest/api/i2s.html),
[GPIO restrictions](https://docs.espressif.com/projects/esp-idf/en/latest/esp32/api-reference/peripherals/gpio.html),
[MAX98357A pinout and supply range](https://learn.adafruit.com/adafruit-max98357-i2s-class-d-mono-amp/pinouts).
