/*
  ESP32 #2 - Gate Control (Entry + Exit), MQTT HOTSPOT VERSION

  Hotspot Wi-Fi:
    SSID: Alvi’s iPhone
    Password: 12345678

  IMPORTANT:
    MQTT_BROKER must be the Raspberry Pi IP address on the hotspot.
    On the Pi, run: hostname -I
    Then put that IP below. iPhone hotspot often gives 172.20.10.x addresses.

  Wiring:
    IR Entry sensor OUT -> GPIO5
    IR Exit  sensor OUT -> GPIO25
    Entry servo signal  -> GPIO4
    Exit  servo signal  -> GPIO13
*/

#include <WiFi.h>
#include <PubSubClient.h>
#include <ESP32Servo.h>

// ---------- Wi-Fi ----------
const char* WIFI_SSID     = "Alvi’s iPhone";
const char* WIFI_PASSWORD = "12345678";

// ---------- MQTT broker on Raspberry Pi ----------
// CHANGE THIS if `hostname -I` on the Raspberry Pi shows a different IP.
const char* MQTT_BROKER   = "172.20.10.8";
const uint16_t MQTT_PORT  = 1883;
const char* MQTT_CLIENT_ID = "GATE1";

WiFiClient espClient;
PubSubClient mqttClient(espClient);

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
  const char* serverName;
  int irPin;
  Servo servo;
  int servoPin;
  GateState state = IDLE;
  unsigned long stateChangedAt = 0;
  unsigned long lastTrigger = 0;
};

Gate entryGate = {"ENTRY", "entry", IR_ENTRY_PIN, Servo(), SERVO_ENTRY_PIN};
Gate exitGate  = {"EXIT",  "exit",  IR_EXIT_PIN,  Servo(), SERVO_EXIT_PIN};

const char* TOPIC_ENTRY_REQUEST = "parking/gate/entry/request";
const char* TOPIC_ENTRY_ALLOW   = "parking/gate/entry/allow";
const char* TOPIC_ENTRY_STATUS  = "parking/gate/entry/status";
const char* TOPIC_EXIT_STATUS   = "parking/gate/exit/status";

volatile bool entryDecisionReceived = false;
volatile bool entryAllow = false;

void connectWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.printf("Connecting to WiFi: %s", WIFI_SSID);

  while (WiFi.status() != WL_CONNECTED) {
    delay(300);
    Serial.print(".");
  }

  Serial.println();
  Serial.print("WiFi connected, ESP32 IP: ");
  Serial.println(WiFi.localIP());
  Serial.print("MQTT broker IP: ");
  Serial.println(MQTT_BROKER);
}

void onMqttMessage(char* topic, byte* payload, unsigned int length) {
  String message;
  for (unsigned int i = 0; i < length; i++) {
    message += (char)payload[i];
  }

  if (String(topic) == TOPIC_ENTRY_ALLOW) {
    message.trim();
    message.toLowerCase();
    entryAllow = (message == "true");
    entryDecisionReceived = true;
    Serial.printf("[ENTRY] MQTT allow received: %s\n", entryAllow ? "true" : "false");
  }
}

void connectMQTT() {
  while (!mqttClient.connected()) {
    if (WiFi.status() != WL_CONNECTED) connectWiFi();

    Serial.print("Connecting to MQTT broker...");
    if (mqttClient.connect(MQTT_CLIENT_ID)) {
      Serial.println("connected");
      mqttClient.subscribe(TOPIC_ENTRY_ALLOW);
    } else {
      Serial.print("failed, rc=");
      Serial.print(mqttClient.state());
      Serial.println(" retrying in 5 seconds");
      delay(5000);
    }
  }
}

bool carDetected(int pin) {
  int val = digitalRead(pin);
  return IR_ACTIVE_LOW ? (val == LOW) : (val == HIGH);
}

bool requestEntryPermission() {
  if (!mqttClient.connected()) connectMQTT();

  entryDecisionReceived = false;
  entryAllow = false;

  bool ok = mqttClient.publish(TOPIC_ENTRY_REQUEST, "request", false);
  if (!ok) {
    Serial.println("[ENTRY] MQTT request publish failed -> entry denied");
    return false;
  }

  Serial.println("[ENTRY] Sent entry request via MQTT");
  unsigned long start = millis();

  while (!entryDecisionReceived && millis() - start < 2000) {
    mqttClient.loop();
    delay(10);
  }

  if (!entryDecisionReceived) {
    Serial.println("[ENTRY] No response from Pi -> entry denied");
    return false;
  }

  return entryAllow;
}

void reportGateStatus(const char* serverName, const char* status) {
  if (!mqttClient.connected()) connectMQTT();

  const char* topic = (strcmp(serverName, "entry") == 0) ? TOPIC_ENTRY_STATUS : TOPIC_EXIT_STATUS;
  bool ok = mqttClient.publish(topic, status, true);

  if (ok) {
    Serial.printf("[MQTT] %s -> %s reported\n", serverName, status);
  } else {
    Serial.printf("[MQTT] publish failed for %s -> %s\n", topic, status);
  }
}

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

  mqttClient.setServer(MQTT_BROKER, MQTT_PORT);
  mqttClient.setCallback(onMqttMessage);
  mqttClient.setKeepAlive(30);
  mqttClient.setSocketTimeout(5);
  connectMQTT();

  reportGateStatus("entry", "closed");
  reportGateStatus("exit", "closed");

  Serial.println("Gate controller ready - MQTT hotspot mode");
}

void updateGate(Gate &gate) {
  unsigned long now = millis();

  switch (gate.state) {
    case IDLE:
      if (carDetected(gate.irPin) && (now - gate.lastTrigger > DEBOUNCE_MS)) {
        gate.lastTrigger = now;

        if (strcmp(gate.serverName, "entry") == 0) {
          Serial.println("[ENTRY] Car detected -> asking Pi via MQTT");
          if (!requestEntryPermission()) {
            Serial.println("[ENTRY] Parking full or Pi denied -> gate stays closed");
            return;
          }
          Serial.println("[ENTRY] Pi allowed entry -> opening");
        } else {
          Serial.println("[EXIT] Car detected -> opening");
        }

        gate.servo.attach(gate.servoPin, SERVO_PULSE_MIN, SERVO_PULSE_MAX);
        gate.servo.write(GATE_OPEN_ANGLE);
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
        reportGateStatus(gate.serverName, "closed");
        gate.state = IDLE;
      }
      break;
  }
}

void loop() {
  if (!mqttClient.connected()) connectMQTT();
  mqttClient.loop();

  updateGate(entryGate);
  updateGate(exitGate);
}
