// BOB autonomous-controller BLE bench firmware, Arduino ESP32 core 3.x.
// Upload only after the original BOB_MotorTest sketch passes its wiring check.
// Lift the wheels: this firmware is for bounded manual trials, not autonomy.

#include <Arduino.h>
#include <BLE2902.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <ESP_I2S.h>
#include <atomic>
#include <esp_system.h>
#include <math.h>
#include <freertos/FreeRTOS.h>
#include <freertos/semphr.h>
#include <freertos/task.h>

// Wiring is identical to the physically tested BOB_MotorTest sketch.
constexpr int AIN1 = 15, AIN2 = 2, PWMA = 23;   // right motor
constexpr int BIN1 = 21, BIN2 = 19, PWMB = 22; // left motor
constexpr bool LEFT_FORWARD_IN1_HIGH = true;
constexpr bool RIGHT_FORWARD_IN1_HIGH = false;
constexpr uint32_t PWM_HZ = 1000;
constexpr int MAX_BENCH_PWM = 85; // About speed digit 3 in BOB_MotorTest.

constexpr int AUDIO_BCLK = 25, AUDIO_LRC = 26, AUDIO_DIN = 33;
constexpr uint32_t AUDIO_RATE = 16000;
constexpr int TONE_AMPLITUDE = 4000;
constexpr uint32_t TONE_SECONDS = 5;

constexpr char SERVICE_UUID[] = "12345678-1234-1234-1234-1234567890ab";
constexpr char COMMAND_UUID[] = "abcdefab-1234-5678-1234-abcdefabcdef";
constexpr char STATUS_UUID[] = "fedcbafe-4321-8765-4321-fedcbafedcba";

constexpr uint8_t PROTOCOL_VERSION = 1;
enum PacketType : uint8_t { STOP = 0, ARM = 1, MOTION = 2, TONE = 3 };
enum ControllerState : uint8_t { DISARMED = 0, ARMED = 1, MOVING = 2, FAULTED = 3 };
enum Fault : uint8_t {
  NO_FAULT = 0, DISCONNECTED = 1, BAD_PACKET = 2, SESSION_MISMATCH = 3,
  NOT_ARMED = 4, COMMAND_EXPIRED = 5, REPLAYED_SEQUENCE = 6,
  OUTSIDE_LIMITS = 7
};

constexpr int16_t MAX_LINEAR_MMPS = 200;       // Request limit, uncalibrated.
constexpr int16_t MAX_ANGULAR_MRADPS = 500;    // Request limit, uncalibrated.
constexpr uint16_t MIN_LEASE_MS = 100;
constexpr uint16_t MAX_LEASE_MS = 500;
constexpr size_t SESSION_PACKET_SIZE = 6;
constexpr size_t MOTION_PACKET_SIZE = 16;
constexpr size_t STATUS_PACKET_SIZE = 16;

SemaphoreHandle_t controlLock;
BLECharacteristic* statusCharacteristic = nullptr;
bool connected = false, armed = false, hasSequence = false, leaseActive = false;
uint32_t sessionId = 0, lastSequence = 0, lastMotionMs = 0;
uint16_t activeLeaseMs = 0;
int16_t leftPwm = 0, rightPwm = 0;
Fault fault = NO_FAULT;
std::atomic<uint32_t> audioEpoch{1};
std::atomic<uint32_t> toneRequest{0};
bool audioTaskReady = false;

uint16_t readU16(const uint8_t* p) {
  return uint16_t(p[0]) | (uint16_t(p[1]) << 8);
}

int16_t readI16(const uint8_t* p) {
  return int16_t(readU16(p));
}

uint32_t readU32(const uint8_t* p) {
  return uint32_t(p[0]) | (uint32_t(p[1]) << 8) |
         (uint32_t(p[2]) << 16) | (uint32_t(p[3]) << 24);
}

void writeU16(uint8_t* p, uint16_t value) {
  p[0] = value & 0xff;
  p[1] = (value >> 8) & 0xff;
}

void writeU32(uint8_t* p, uint32_t value) {
  p[0] = value & 0xff;
  p[1] = (value >> 8) & 0xff;
  p[2] = (value >> 16) & 0xff;
  p[3] = (value >> 24) & 0xff;
}

void cancelAudio() {
  audioEpoch.fetch_add(1);
  toneRequest.store(0);
}

void setMotor(int in1, int in2, int pwmPin, int16_t signedPwm,
              bool forwardIn1High) {
  ledcWrite(pwmPin, 0);
  if (signedPwm == 0) {
    digitalWrite(in1, LOW);
    digitalWrite(in2, LOW);
    return;
  }
  bool in1High = signedPwm > 0 ? forwardIn1High : !forwardIn1High;
  digitalWrite(in1, in1High ? HIGH : LOW);
  digitalWrite(in2, in1High ? LOW : HIGH);
  ledcWrite(pwmPin, abs(signedPwm));
}

void neutralOutputs() {
  cancelAudio();
  ledcWrite(PWMA, 0);
  ledcWrite(PWMB, 0);
  digitalWrite(AIN1, LOW);
  digitalWrite(AIN2, LOW);
  digitalWrite(BIN1, LOW);
  digitalWrite(BIN2, LOW);
  leftPwm = rightPwm = 0;
  leaseActive = false;
  activeLeaseMs = 0;
}

void disarm(Fault reason) {
  neutralOutputs();
  armed = false;
  fault = reason;
}

void applyMotion(int16_t linear, int16_t angular, uint16_t leaseMs) {
  cancelAudio();
  float drive = float(linear) / MAX_LINEAR_MMPS;
  float turn = float(angular) / MAX_ANGULAR_MRADPS;
  float left = drive - turn;
  float right = drive + turn;
  float scale = fmaxf(1.0f, fmaxf(fabsf(left), fabsf(right)));
  leftPwm = int16_t(lroundf(MAX_BENCH_PWM * left / scale));
  rightPwm = int16_t(lroundf(MAX_BENCH_PWM * right / scale));
  setMotor(BIN1, BIN2, PWMB, leftPwm, LEFT_FORWARD_IN1_HIGH);
  setMotor(AIN1, AIN2, PWMA, rightPwm, RIGHT_FORWARD_IN1_HIGH);
  lastMotionMs = millis();
  activeLeaseMs = leaseMs;
  leaseActive = true;
}

void publishStatus(bool notifyClient = true) {
  if (!statusCharacteristic || !controlLock) return;
  uint8_t packet[STATUS_PACKET_SIZE] = {};
  xSemaphoreTake(controlLock, portMAX_DELAY);
  ControllerState state = fault != NO_FAULT ? FAULTED :
      (armed ? ((leftPwm || rightPwm) ? MOVING : ARMED) : DISARMED);
  uint8_t flags = (connected ? 1 : 0) | (armed ? 2 : 0) |
                  (hasSequence ? 4 : 0); // bit 3 stays zero: no encoders.
  packet[0] = PROTOCOL_VERSION;
  packet[1] = state;
  packet[2] = fault;
  packet[3] = flags;
  writeU32(packet + 4, sessionId);
  writeU32(packet + 8, lastSequence);
  writeU16(packet + 12, uint16_t(leftPwm));
  writeU16(packet + 14, uint16_t(rightPwm));
  xSemaphoreGive(controlLock);
  statusCharacteristic->setValue(packet, sizeof(packet));
  if (notifyClient && connected) statusCharacteristic->notify();
}

void speakerTask(void*) {
  I2SClass audio;
  audio.setPins(AUDIO_BCLK, AUDIO_LRC, AUDIO_DIN);
  constexpr uint32_t CHUNK = 128;
  constexpr uint32_t FRAMES = AUDIO_RATE * TONE_SECONDS;
  int16_t samples[CHUNK * 2];
  while (true) {
    uint32_t token = toneRequest.exchange(0);
    if (!token || token != audioEpoch.load()) {
      vTaskDelay(pdMS_TO_TICKS(10));
      continue;
    }
    if (!audio.begin(I2S_MODE_STD, AUDIO_RATE, I2S_DATA_BIT_WIDTH_16BIT,
                     I2S_SLOT_MODE_STEREO)) {
      Serial.println("Audio initialization failed.");
      audio.end();
      continue;
    }
    for (uint32_t start = 0; start < FRAMES + AUDIO_RATE / 5; start += CHUNK) {
      if (token != audioEpoch.load()) break;
      for (uint32_t i = 0; i < CHUNK; ++i) {
        uint32_t n = start + i;
        float gain = n < FRAMES ? 1.0f : 0.0f;
        if (n < 160) gain = n / 160.0f;
        if (n >= FRAMES - 160 && n < FRAMES) gain = (FRAMES - n) / 160.0f;
        int16_t sample = int16_t(TONE_AMPLITUDE * gain *
            sinf(6.28318530718f * 440.0f * n / AUDIO_RATE));
        samples[2 * i] = samples[2 * i + 1] = sample;
      }
      if (audio.write(reinterpret_cast<uint8_t*>(samples), sizeof(samples))
          != sizeof(samples)) break;
      vTaskDelay(1);
    }
    audio.end();
    Serial.println("Speaker test ended.");
  }
}

class ServerCallbacks : public BLEServerCallbacks {
  void onConnect(BLEServer*) override {
    xSemaphoreTake(controlLock, portMAX_DELAY);
    neutralOutputs();
    connected = true;
    armed = false;
    hasSequence = false;
    lastSequence = 0;
    fault = NO_FAULT;
    sessionId = esp_random();
    xSemaphoreGive(controlLock);
    Serial.printf("Connected, stopped, session=%08lx.\n", sessionId);
    publishStatus();
  }

  void onDisconnect(BLEServer*) override {
    xSemaphoreTake(controlLock, portMAX_DELAY);
    connected = false;
    disarm(DISCONNECTED);
    xSemaphoreGive(controlLock);
    publishStatus(false);
    Serial.println("Disconnected; stopped and disarmed.");
    BLEDevice::startAdvertising();
  }
};

class CommandCallbacks : public BLECharacteristicCallbacks {
  void onWrite(BLECharacteristic* characteristic) override {
    auto value = characteristic->getValue();
    const uint8_t* data = reinterpret_cast<const uint8_t*>(value.data());
    size_t size = value.length();
    bool requestTone = false;
    xSemaphoreTake(controlLock, portMAX_DELAY);
    if (size < 2 || data[0] != PROTOCOL_VERSION) {
      disarm(BAD_PACKET);
    } else if (data[1] == STOP && size == 2) {
      disarm(NO_FAULT);
    } else if ((data[1] == ARM || data[1] == TONE) &&
               size == SESSION_PACKET_SIZE) {
      uint32_t packetSession = readU32(data + 2);
      if (packetSession != sessionId) {
        disarm(SESSION_MISMATCH);
      } else if (data[1] == ARM) {
        neutralOutputs();
        armed = true;
        fault = NO_FAULT;
      } else {
        disarm(NO_FAULT);
        requestTone = audioTaskReady;
      }
    } else if (data[1] == MOTION && size == MOTION_PACKET_SIZE) {
      uint32_t packetSession = readU32(data + 2);
      uint32_t sequence = readU32(data + 6);
      uint16_t leaseMs = readU16(data + 10);
      int16_t linear = readI16(data + 12);
      int16_t angular = readI16(data + 14);
      if (packetSession != sessionId) {
        disarm(SESSION_MISMATCH);
      } else if (!armed) {
        disarm(NOT_ARMED);
      } else if (hasSequence && sequence <= lastSequence) {
        disarm(REPLAYED_SEQUENCE);
      } else if (leaseMs < MIN_LEASE_MS || leaseMs > MAX_LEASE_MS ||
                 abs(linear) > MAX_LINEAR_MMPS ||
                 abs(angular) > MAX_ANGULAR_MRADPS) {
        disarm(OUTSIDE_LIMITS);
      } else {
        hasSequence = true;
        lastSequence = sequence;
        fault = NO_FAULT;
        applyMotion(linear, angular, leaseMs);
      }
    } else {
      disarm(BAD_PACKET);
    }
    if (requestTone) toneRequest.store(audioEpoch.load());
    xSemaphoreGive(controlLock);
    publishStatus();
  }
};

void setup() {
  Serial.begin(115200);
  const int pins[] = {AIN1, AIN2, PWMA, BIN1, BIN2, PWMB};
  for (int pin : pins) {
    pinMode(pin, OUTPUT);
    digitalWrite(pin, LOW);
  }
  if (!ledcAttach(PWMA, PWM_HZ, 8) || !ledcAttach(PWMB, PWM_HZ, 8)) {
    Serial.println("PWM initialization failed; BLE disabled.");
    while (true) delay(1000);
  }
  controlLock = xSemaphoreCreateMutex();
  if (!controlLock) {
    Serial.println("Mutex allocation failed; BLE disabled.");
    while (true) delay(1000);
  }
  xSemaphoreTake(controlLock, portMAX_DELAY);
  neutralOutputs();
  sessionId = esp_random();
  xSemaphoreGive(controlLock);
  audioTaskReady = xTaskCreate(speakerTask, "speaker-test", 4096, nullptr,
                               1, nullptr) == pdPASS;

  BLEDevice::init("BOB-ControllerBench");
  BLEServer* server = BLEDevice::createServer();
  server->setCallbacks(new ServerCallbacks());
  BLEService* service = server->createService(SERVICE_UUID);
  BLECharacteristic* command = service->createCharacteristic(
      COMMAND_UUID, BLECharacteristic::PROPERTY_WRITE);
  command->setCallbacks(new CommandCallbacks());
  statusCharacteristic = service->createCharacteristic(
      STATUS_UUID, BLECharacteristic::PROPERTY_READ |
                   BLECharacteristic::PROPERTY_NOTIFY);
  statusCharacteristic->addDescriptor(new BLE2902());
  publishStatus(false);
  service->start();
  BLEAdvertising* advertising = BLEDevice::getAdvertising();
  advertising->addServiceUUID(SERVICE_UUID);
  advertising->setScanResponse(true);
  BLEDevice::startAdvertising();
  Serial.println("BOB-ControllerBench ready; stopped and disarmed.");
}

void loop() {
  bool expired = false;
  xSemaphoreTake(controlLock, portMAX_DELAY);
  if (leaseActive && uint32_t(millis() - lastMotionMs) >= activeLeaseMs) {
    disarm(COMMAND_EXPIRED);
    expired = true;
  }
  xSemaphoreGive(controlLock);
  if (expired) {
    Serial.println("Motion lease expired; stopped and disarmed.");
    publishStatus();
  }
  delay(10);
}
