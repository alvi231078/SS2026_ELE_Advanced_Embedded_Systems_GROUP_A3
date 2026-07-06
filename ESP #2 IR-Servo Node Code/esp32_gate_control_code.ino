/*
  ESP32 #2 - Gate Control (Entry + Exit) + Raspberry Pi Server Reporting

  Two IR sensors trigger two independent Miuzei MF90 servos to simulate
  parking gate barriers opening and closing.

  Raspberry Pi integration:
    GET  /can-enter     -> entry gate asks before opening
    POST /gate-update   -> ESP32 reports entry/exit gate open/closed

  Wiring:
    IR Entry sensor OUT -> GPIO5
    IR Exit  sensor OUT -> GPIO25
    Entry servo signal  -> GPIO4
    Exit  servo signal  -> GPIO13

  IMPORTANT:
    - Entry gate will only open if Raspberry Pi says allow = true.
    - Exit gate opens normally, because cars should always be allowed to leave.
*/

#include <WiFi.h>
#include <HTTPClient.h>
#include <ESP32Servo.h>

// ---------- Wi-Fi + Raspberry Pi ----------
const char* WIFI_SSID     = "Alvi's Repeater";
const char* WIFI_PASSWORD = "Happyhome@2022";
const char* PI_BASE_URL   = "http://192.168.178.35:5000";

// ---------- Pin setup ----------
#define IR_ENTRY_PIN    5
#define IR_EXIT_PIN     25
#define SERVO_ENTRY_PIN 4
#define SERVO_EXIT_PIN  13
#define IR_ACTIVE_LOW   true

#define SERVO_PULSE_MIN 500
#define SERVO_PULSE_MAX 2500

const int GATE_OPEN_ANGLE   = 90;
const int GATE_CLOSED_ANGLE = 0;

const unsigned long SERVO_MOVE_MS   = 450;
const unsigned long SAFETY_DELAY_MS = 1000;
const unsigned long DEBOUNCE_MS     = 300;

enum GateState { IDLE, OPENING, HOLDING, CLOSING };

struct Gate {
  const char* name;
  const char* serverName;   // "entry" or "exit" for Raspberry Pi JSON
  int irPin;
  Servo servo;
  int servoPin;
  GateState state = IDLE;
  unsigned long stateChangedAt = 0;
  unsigned long lastTrigger = 0;
};

Gate entryGate = {"ENTRY", "entry", IR_ENTRY_PIN, Servo(), SERVO_ENTRY_PIN};
Gate exitGate  = {"EXIT",  "exit",  IR_EXIT_PIN,  Servo(), SERVO_EXIT_PIN};


// ---------- Wi-Fi ----------
void connectWiFi() {
  Serial.printf("Connecting to %s", WIFI_SSID);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  while (WiFi.status() != WL_CONNECTED) {
    delay(300);
    Serial.print(".");
  }

  Serial.println();
  Serial.print("WiFi connected, IP: ");
  Serial.println(WiFi.localIP());
}


// ---------- Raspberry Pi: check if entry is allowed ----------
bool canEnterFromPi() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[ENTRY] WiFi not connected -> entry denied");
    return false;
  }

  HTTPClient http;
  http.setTimeout(2000);
  http.begin(String(PI_BASE_URL) + "/can-enter");

  int code = http.GET();

  if (code != 200) {
    Serial.printf("[ENTRY] /can-enter failed, code %d -> entry denied\n", code);
    http.end();
    return false;
  }

  String payload = http.getString();
  http.end();

  Serial.print("[ENTRY] /can-enter response: ");
  Serial.println(payload);

  // Simple check for: {"allow":true}
  if (payload.indexOf("\"allow\":true") >= 0 || payload.indexOf("\"allow\": true") >= 0) {
    return true;
  }

  return false;
}


// ---------- Raspberry Pi: report gate status ----------
void reportGateStatus(const char* gateName, const char* status) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.printf("[%s] WiFi not connected, cannot report %s\n", gateName, status);
    return;
  }

  HTTPClient http;
  http.setTimeout(2000);
  http.begin(String(PI_BASE_URL) + "/gate-update");
  http.addHeader("Content-Type", "application/json");

  String body = String("{\"gate\":\"") + gateName + "\",\"status\":\"" + status + "\"}";

  int code = http.POST(body);

  if (code != 200) {
    Serial.printf("[gate-update] failed for %s -> %s, code %d\n", gateName, status, code);
  } else {
    Serial.printf("[gate-update] %s -> %s reported to Pi\n", gateName, status);
  }

  http.end();
}


// ---------- IR logic ----------
bool carDetected(int pin) {
  int val = digitalRead(pin);
  return IR_ACTIVE_LOW ? (val == LOW) : (val == HIGH);
}


// ---------- Setup ----------
void setup() {
  Serial.begin(115200);
  delay(500);

  connectWiFi();

  pinMode(IR_ENTRY_PIN, INPUT);
  pinMode(IR_EXIT_PIN, INPUT);

  ESP32PWM::allocateTimer(0);
  ESP32PWM::allocateTimer(1);

  entryGate.servo.setPeriodHertz(50);
  exitGate.servo.setPeriodHertz(50);

  entryGate.servo.attach(entryGate.servoPin, SERVO_PULSE_MIN, SERVO_PULSE_MAX);
  exitGate.servo.attach(exitGate.servoPin, SERVO_PULSE_MIN, SERVO_PULSE_MAX);

  entryGate.servo.write(GATE_CLOSED_ANGLE);
  exitGate.servo.write(GATE_CLOSED_ANGLE);

  delay(500);

  entryGate.servo.detach();
  exitGate.servo.detach();

  // Tell dashboard both gates start closed
  reportGateStatus("entry", "closed");
  reportGateStatus("exit", "closed");

  Serial.println("Gate controller ready.");
}


// ---------- Main gate state machine ----------
void updateGate(Gate &gate) {
  unsigned long now = millis();

  switch (gate.state) {

    case IDLE:
      if (carDetected(gate.irPin) && (now - gate.lastTrigger > DEBOUNCE_MS)) {
        gate.lastTrigger = now;

        // Entry gate must ask Raspberry Pi before opening.
        // Exit gate opens normally.
        if (String(gate.serverName) == "entry") {
          Serial.println("[ENTRY] Car detected -> asking Raspberry Pi /can-enter");

          if (!canEnterFromPi()) {
            Serial.println("[ENTRY] Parking full or Pi denied -> gate stays closed");
            return;
          }

          Serial.println("[ENTRY] Pi allowed entry -> opening");
        } else {
          Serial.println("[EXIT] Car detected -> opening");
        }

        gate.servo.attach(gate.servoPin, SERVO_PULSE_MIN, SERVO_PULSE_MAX);
        gate.servo.write(GATE_OPEN_ANGLE);

        // Report opening immediately to dashboard
        reportGateStatus(gate.serverName, "open");

        gate.state = OPENING;
        gate.stateChangedAt = now;
      }
      break;

    case OPENING:
      if (now - gate.stateChangedAt >= SERVO_MOVE_MS) {
        Serial.printf("[%s] Gate open\n", gate.name);
        gate.state = HOLDING;
        gate.stateChangedAt = now;
      }
      break;

    case HOLDING:
      if (carDetected(gate.irPin)) {
        // Still something in the beam.
        // Keep gate open and reset timer.
        gate.stateChangedAt = now;
      } else if (now - gate.stateChangedAt >= SAFETY_DELAY_MS) {
        Serial.printf("[%s] Closing\n", gate.name);

        gate.servo.write(GATE_CLOSED_ANGLE);

        gate.state = CLOSING;
        gate.stateChangedAt = now;
      }
      break;

    case CLOSING:
      if (now - gate.stateChangedAt >= SERVO_MOVE_MS) {
        Serial.printf("[%s] Gate closed\n", gate.name);

        gate.servo.detach();

        // Report closed after physical closing time
        reportGateStatus(gate.serverName, "closed");

        gate.state = IDLE;
      }
      break;
  }
}


// ---------- Loop ----------
void loop() {
  updateGate(entryGate);
  updateGate(exitGate);
}
