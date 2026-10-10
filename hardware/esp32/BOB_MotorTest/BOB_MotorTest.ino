// Arduino IDE: esp32 by Espressif Systems, version 3.x.
// ESP32 DevKit V1: channel A = RIGHT motor; channel B = LEFT motor.
// Each motor uses two pins to choose direction and a PWM pin to set speed.
// Send one text command at a time over BLE:
// F = forward, B = backward, L/R = turn in place, S = stop everything,
// 0..9 = choose motor speed, T = test speaker, H = print status over USB.
// Repeat movement commands more often than once per second to keep moving.
// You can test the motors without connecting the speaker.

// These libraries handle Bluetooth, digital audio, and background tasks.
#include <Arduino.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <ESP_I2S.h>
#include <atomic>
#include <math.h>
#include <freertos/FreeRTOS.h>
#include <freertos/semphr.h>
#include <freertos/task.h>

// Dxx labels on this board correspond to GPIO numbers, not header positions.
// Channel A goes to the right motor: positive at AO1, negative at AO2.
constexpr int AIN1 = 15;
constexpr int AIN2 = 2;
constexpr int PWMA = 23;
// Channel B goes to the left motor: positive at BO1, negative at BO2.
constexpr int BIN1 = 21;
constexpr int BIN2 = 19;
constexpr int PWMB = 22;
// TB6612FNG STBY is wired directly to 3.3 V; no GPIO control.
// A value of -1 tells the sketch to skip writing to a standby GPIO.
constexpr int STBY = -1;
static_assert(AIN1 >= 0 && AIN2 >= 0 && PWMA >= 0 &&
              BIN1 >= 0 && BIN2 >= 0 && PWMB >= 0,
              "Set the six motor GPIOs after confirming board and driver.");

// These IDs let your BLE app find the same service and command endpoint
// used in the previous WALL-Y sketch. Write commands to COMMAND_UUID.
constexpr char SERVICE_UUID[] = "12345678-1234-1234-1234-1234567890ab";
constexpr char COMMAND_UUID[] = "abcdefab-1234-5678-1234-abcdefabcdef";
// PWM switches motor power on and off 1,000 times per second.
// Its duty value sets the on-time fraction, not a measured wheel speed.
constexpr uint32_t PWM_HZ = 1000;
// A movement command expires after one second unless another one arrives.
constexpr uint32_t COMMAND_TIMEOUT_MS = 1000;
// Both motors: positive lead at OUT1, negative lead at OUT2.
// Wheel testing showed the right motor needs the opposite electrical
// polarity to move the chassis forward. These settings account for that.
constexpr bool LEFT_FORWARD_IN1_HIGH = true;
constexpr bool RIGHT_FORWARD_IN1_HIGH = false;

// Bluetooth callbacks and loop() can run at the same time. This lock lets
// only one of them change the motor pins and shared motor state at a time.
SemaphoreHandle_t motorLock;
bool connected = false;
char movement = 'S';
uint8_t speedDuty = 80; // 0..255; start at about 31% duty.
uint32_t lastMotionMs = 0;

// MAX98357A: MOVE LRC FROM D34 TO D26 (GPIO34 is input-only).
constexpr int AUDIO_BCLK = 25;
constexpr int AUDIO_LRC = 26;
constexpr int AUDIO_DIN = 33;
// The tone uses 16,000 samples per second. Amplitude controls its level
// separately from the motor speed; start low when trying a new speaker.
constexpr uint32_t AUDIO_RATE = 16000;
constexpr int TONE_AMPLITUDE = 4000; // More audible test level, out of 32767.
constexpr uint32_t TONE_SECONDS = 5;
constexpr uint32_t TONE_FRAMES = AUDIO_RATE * TONE_SECONDS;
// Each audio request gets the current version number. Changing that number
// cancels older requests, including a tone already running in another task.
// Atomic variables let both tasks read and update these values safely.
std::atomic<uint32_t> audioEpoch{1};
std::atomic<uint32_t> toneRequest{0};
bool audioTaskReady = false;

void cancelAudio() {
  // Invalidate the playing tone and clear any tone waiting to start.
  audioEpoch.fetch_add(1);
  toneRequest.store(0);
}

// Separate task: I2S writes never hold motorLock or block motor timeout checks.
// Audio is initialized ONLY on T, so motors can be tested without the amp.
void speakerTask(void*) {
  I2SClass audio;
  audio.setPins(AUDIO_BCLK, AUDIO_LRC, AUDIO_DIN);
  constexpr uint32_t CHUNK_FRAMES = 128;
  // Each frame has a left and right sample, so we reserve two entries per frame.
  int16_t samples[CHUNK_FRAMES * 2];
  while (true) {
    // Pick up a request once, then clear the pending slot. Zero means none.
    uint32_t token = toneRequest.exchange(0);
    if (token == 0 || token != audioEpoch.load()) {
      // Let other tasks run while we wait for the next speaker command.
      vTaskDelay(pdMS_TO_TICKS(10));
      continue;
    }
    // Start the clocks only when requested. The amplifier doesn't need
    // to be attached during the motor-only test.
    if (!audio.begin(I2S_MODE_STD, AUDIO_RATE, I2S_DATA_BIT_WIDTH_16BIT,
                     I2S_SLOT_MODE_STEREO)) {
      Serial.println("Audio initialization failed; motor test still available.");
      audio.end();
      continue;
    }
    Serial.println("Speaker: 440 Hz test tone, about 5 seconds. S cancels.");
    bool writeFailed = false;
    // Same samples on both channels work with left/right/mixed amp selection.
    // Finish with 200 ms of zeros to flush queued sound before ending I2S.
    for (uint32_t start = 0; start < TONE_FRAMES + AUDIO_RATE / 5;
         start += CHUNK_FRAMES) {
      if (token != audioEpoch.load()) break;
      for (uint32_t i = 0; i < CHUNK_FRAMES; ++i) {
        uint32_t n = start + i;
        float gain = 0.0f;
        if (n < TONE_FRAMES) {
          // Fade the first and last 10 ms to soften clicks at the tone's edges.
          gain = 1.0f;
          if (n < 160) gain = n / 160.0f;
          if (n >= TONE_FRAMES - 160) gain = (TONE_FRAMES - n) / 160.0f;
        }
        // Generate a 440 Hz sine wave directly; no sound file is needed.
        int16_t sample = int16_t(TONE_AMPLITUDE * gain *
            sinf(6.28318530718f * 440.0f * n / AUDIO_RATE));
        samples[2 * i] = sample;
        samples[2 * i + 1] = sample;
      }
      // uint8_t cast also supports earlier 3.x I2S write signatures.
      if (audio.write(reinterpret_cast<uint8_t*>(samples), sizeof(samples))
          != sizeof(samples)) {
        writeFailed = true;
        break;
      }
      vTaskDelay(1);
    }
    // Release the audio peripheral after this test, or after cancellation.
    audio.end();
    Serial.println(writeFailed ? "Audio write failed." : "Speaker test ended.");
  }
}

// All motor/state functions run with motorLock held after setup.
void stopMotors() {
  // This is also our stop-everything action: cancel sound, remove motor
  // PWM, then clear the direction inputs. It doesn't guarantee instant
  // mechanical stopping; the wheels may take time to stop.
  cancelAudio();
  ledcWrite(PWMA, 0);
  ledcWrite(PWMB, 0);
  if (STBY >= 0) digitalWrite(STBY, LOW);
  digitalWrite(AIN1, LOW);
  digitalWrite(AIN2, LOW);
  digitalWrite(BIN1, LOW);
  digitalWrite(BIN2, LOW);
  movement = 'S';
}

void setDirection(int in1, int in2, bool forward, bool forwardIn1High) {
  // Swap the two input levels for reverse. The per-wheel setting accounts
  // for motor orientation without needing to swap wires.
  bool high = forward ? forwardIn1High : !forwardIn1High;
  digitalWrite(in1, high ? HIGH : LOW);
  digitalWrite(in2, high ? LOW : HIGH);
}

void drive(char command) {
  // Starting a motor test cancels the speaker test.
  cancelAudio();
  // Disable PWM before changing direction; pause on direction changes.
  char previous = movement;
  ledcWrite(PWMA, 0);
  ledcWrite(PWMB, 0);
  if (previous != 'S' && previous != command) delay(20);
  // Forward/backward drive both wheels together. Turning drives one wheel
  // forward and the other backward so the robot rotates in place.
  bool leftForward = command == 'F' || command == 'R';
  bool rightForward = command == 'F' || command == 'L';
  setDirection(AIN1, AIN2, rightForward, RIGHT_FORWARD_IN1_HIGH);
  setDirection(BIN1, BIN2, leftForward, LEFT_FORWARD_IN1_HIGH);
  if (STBY >= 0) digitalWrite(STBY, HIGH);
  ledcWrite(PWMA, speedDuty);
  ledcWrite(PWMB, speedDuty);
  movement = command;
  // Only movement commands refresh this timer; H cannot keep motors running.
  lastMotionMs = millis();
}

// The BLE library calls these methods when a phone connects or disconnects.
class ServerCallbacks : public BLEServerCallbacks {
  void onConnect(BLEServer*) override {
    xSemaphoreTake(motorLock, portMAX_DELAY);
    // A new connection starts stopped instead of resuming an old command.
    stopMotors();
    connected = true;
    xSemaphoreGive(motorLock);
    Serial.println("Connected; stopped.");
  }
  void onDisconnect(BLEServer*) override {
    xSemaphoreTake(motorLock, portMAX_DELAY);
    connected = false;
    stopMotors();
    xSemaphoreGive(motorLock);
    Serial.println("Disconnected; stopped.");
    // Make the device visible again so the phone can reconnect.
    BLEDevice::startAdvertising();
  }
};

// This callback receives text written to the BLE command characteristic.
class CommandCallbacks : public BLECharacteristicCallbacks {
  void onWrite(BLECharacteristic* characteristic) override {
    auto value = characteristic->getValue();
    // One ASCII command per write, optionally with trailing CR/LF.
    if (value.length() == 0) return;
    char command = value[0];
    // Accept lowercase commands too, such as f instead of F.
    if (command >= 'a' && command <= 'z') command -= 'a' - 'A';
    bool validPacket = true;
    // Allow line endings from a BLE app, but reject combined commands like FT.
    for (size_t i = 1; i < value.length(); ++i) {
      if (value[i] != '\r' && value[i] != '\n') validPacket = false;
    }
    xSemaphoreTake(motorLock, portMAX_DELAY);
    if (!connected || !validPacket) {
      stopMotors();
    } else if (command == 'F' || command == 'B' ||
               command == 'L' || command == 'R') {
      drive(command);
    } else if (command == 'T') {
      // Stop the wheels first, then ask the background task to play sound.
      // The callback returns without waiting for the five-second tone.
      stopMotors();
      if (audioTaskReady) {
        toneRequest.store(audioEpoch.load());
      } else {
        Serial.println("Audio task unavailable; motor test still available.");
      }
    } else if (command >= '0' && command <= '9') {
      // Changing speed stops motion; send a movement command afterwards.
      stopMotors();
      speedDuty = (command - '0') * 255 / 9;
      // Map the text digit to the 8-bit PWM range: 0 = off, 9 = full duty.
      Serial.printf("PWM duty: %u/255\n", speedDuty);
    } else if (command == 'H') {
      // Status goes to Arduino Serial Monitor at 115200 baud, not back over BLE.
      Serial.printf("ONLINE; command=%c; PWM=%u/255\n", movement, speedDuty);
    } else {
      stopMotors(); // S and unknown commands both stop.
    }
    xSemaphoreGive(motorLock);
  }
};

void setup() {
  // setup() runs once after power-on or reset.
  Serial.begin(115200);
  // Start with every motor control output low before enabling Bluetooth.
  const int pins[] = {AIN1, AIN2, PWMA, BIN1, BIN2, PWMB};
  for (int pin : pins) {
    pinMode(pin, OUTPUT);
    digitalWrite(pin, LOW);
  }
  if (STBY >= 0) {
    pinMode(STBY, OUTPUT);
    digitalWrite(STBY, LOW);
  }
  // Attach hardware PWM to each speed pin. Eight bits gives values 0..255.
  bool pwmAReady = ledcAttach(PWMA, PWM_HZ, 8);
  bool pwmBReady = ledcAttach(PWMB, PWM_HZ, 8);
  if (!pwmAReady || !pwmBReady) {
    Serial.println("PWM initialization failed. BLE disabled; reset to retry.");
    while (true) delay(1000);
  }
  stopMotors();
  // Create the shared lock before callbacks or background tasks can run.
  motorLock = xSemaphoreCreateMutex();
  if (!motorLock) {
    Serial.println("Mutex allocation failed; reset to retry.");
    while (true) delay(1000);
  }
  // Start a background worker that waits quietly until T is received.
  // Failure here leaves the motor test available and reports on T.
  audioTaskReady = xTaskCreate(speakerTask, "speaker-test", 4096, nullptr,
                               1, nullptr) == pdPASS;
  // This is the device name shown when scanning in your BLE app.
  BLEDevice::init("BOB-MotorTest");
  BLEServer* server = BLEDevice::createServer();
  server->setCallbacks(new ServerCallbacks());
  BLEService* service = server->createService(SERVICE_UUID);
  // Accept both writes that request a BLE acknowledgment and writes that don't.
  BLECharacteristic* command = service->createCharacteristic(
      COMMAND_UUID, BLECharacteristic::PROPERTY_WRITE |
                    BLECharacteristic::PROPERTY_WRITE_NR);
  command->setCallbacks(new CommandCallbacks());
  service->start();
  // Advertise the service so a phone can discover and connect to it.
  BLEAdvertising* advertising = BLEDevice::getAdvertising();
  advertising->addServiceUUID(SERVICE_UUID);
  advertising->setScanResponse(true);
  BLEDevice::startAdvertising();
  Serial.println("BLE ready: F B L R S H; speed 0..9. Repeat movement <1s.");
  Serial.println("T = speaker test (LRC must be on D26); S cancels audio too.");
}

void loop() {
  // loop() keeps running while BLE callbacks handle incoming commands.
  // Check for disconnects and expired movement commands about every 10 ms.
  xSemaphoreTake(motorLock, portMAX_DELAY);
  if (!connected || (movement != 'S' &&
      uint32_t(millis() - lastMotionMs) >= COMMAND_TIMEOUT_MS)) {
    // Subtracting unsigned timestamps also handles millis() wrapping around.
    stopMotors();
  }
  xSemaphoreGive(motorLock);
  delay(10);
}
