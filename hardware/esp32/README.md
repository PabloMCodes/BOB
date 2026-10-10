# ESP32 motor and speaker bench test

Standalone hardware test requested alongside the CV work. It does not consume
computer vision detections or control the rover autonomously.

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
testing audio. Amplifier VIN and SD/EN wiring remain unconfirmed on the user's
hardware; verify them against the module documentation. MAX98357A supply range
is 2.5–5.5 V. Connect the speaker across the amplifier's speaker outputs;
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
- User reported no audible output from the original one-second speaker test,
  although Serial Monitor showed the test starting and ending.
- The five-second tone with increased amplitude still needs physical testing.
- Python client syntax checked locally. Arduino compilation and a BLE connection
  have not been verified in the agent's Linux environment.

References: [Espressif I2S API](https://docs.espressif.com/projects/arduino-esp32/en/latest/api/i2s.html),
[ESP32 GPIO restrictions](https://docs.espressif.com/projects/esp-idf/en/latest/esp32/api-reference/peripherals/gpio.html),
[MAX98357A pinout](https://learn.adafruit.com/adafruit-max98357-i2s-class-d-mono-amp/pinouts).
