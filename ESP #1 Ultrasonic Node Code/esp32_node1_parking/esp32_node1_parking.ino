// ===== ESP32 #1 — Parking Node: 3x HC-SR04, MQTT + FALSE-DETECTION FILTER =====
// Hotspot Wi-Fi:
//   SSID: Alvi’s iPhone
//   Password: 12345678
//
// IMPORTANT:
//   MQTT_BROKER must be the Raspberry Pi IP address on the hotspot.
//   On the Pi, run: hostname -I
//   Then put that IP below. iPhone hotspot often gives 172.20.10.x addresses.

#include <WiFi.h>
#include <PubSubClient.h>

// ---------- Wi-Fi ----------
const char* WIFI_SSID     = "Alvi’s iPhone";
const char* WIFI_PASSWORD = "12345678";

// ---------- MQTT broker on Raspberry Pi ----------
// CHANGE THIS if `hostname -I` on the Raspberry Pi shows a different IP.
const char* MQTT_BROKER   = "172.20.10.8";
const uint16_t MQTT_PORT  = 1883;

// ---------- Ultrasonic sensor pins ----------
const int trigPins[3] = {5, 17, 22};
const int echoPins[3] = {18, 19, 21};

const char* bayName[3] = {"Bay 1", "Bay 2", "Bay 3"};
const int spotId[3] = {1, 2, 3};

// Distance below this = possible car present.
// 8cm is safer than 10cm because it rejects more random short echoes.
const float OCCUPIED_CM = 8.0;

// Ignore impossible/noisy readings outside this range.
const float MIN_VALID_CM = 2.0;
const float MAX_VALID_CM = 250.0;

// Software filter / debounce for ultrasonic noise:
// Bay becomes occupied only after 3 continuous occupied readings.
// Bay becomes free only after 5 continuous free readings.
const int OCCUPIED_CONFIRM_COUNT = 3;
const int FREE_CONFIRM_COUNT = 5;

String lastReported[3] = {"unknown", "unknown", "unknown"};
int occupiedCount[3] = {0, 0, 0};
int freeCount[3] = {0, 0, 0};

WiFiClient espClient;
PubSubClient mqttClient(espClient);

long readDistanceCM(int trig, int echo) {
  digitalWrite(trig, LOW);
  delayMicroseconds(2);
  digitalWrite(trig, HIGH);
  delayMicroseconds(10);
  digitalWrite(trig, LOW);

  long dur = pulseIn(echo, HIGH, 30000);
  if (dur == 0) return -1;
  return dur * 0.0343 / 2;
}

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

void connectMQTT() {
  while (!mqttClient.connected()) {
    if (WiFi.status() != WL_CONNECTED) {
      connectWiFi();
    }

    Serial.print("Connecting to MQTT broker...");
    const char* clientId = "PARK1";

    if (mqttClient.connect(clientId)) {
      Serial.println("connected");
    } else {
      Serial.print("failed, rc=");
      Serial.print(mqttClient.state());
      Serial.println(" retrying in 5 seconds");
      delay(5000);
    }
  }
}

void reportSpotStatus(int spot, const char* status) {
  if (!mqttClient.connected()) connectMQTT();

  String topic = String("parking/spot/") + spot + "/status";
  bool ok = mqttClient.publish(topic.c_str(), status, true);

  if (ok) {
    Serial.printf("MQTT publish OK: %s -> %s\n", topic.c_str(), status);
  } else {
    Serial.printf("MQTT publish FAILED: %s -> %s\n", topic.c_str(), status);
  }
}

void setup() {
  Serial.begin(115200);
  delay(500);

  for (int i = 0; i < 3; i++) {
    pinMode(trigPins[i], OUTPUT);
    pinMode(echoPins[i], INPUT);
    digitalWrite(trigPins[i], LOW);
  }

  connectWiFi();
  mqttClient.setServer(MQTT_BROKER, MQTT_PORT);
  mqttClient.setKeepAlive(30);
  mqttClient.setSocketTimeout(5);
  connectMQTT();

  Serial.println("ESP32 #1 ready - ultrasonic MQTT stable-filter mode");
}

void loop() {
  if (!mqttClient.connected()) connectMQTT();
  mqttClient.loop();

  for (int i = 0; i < 3; i++) {
    long d = readDistanceCM(trigPins[i], echoPins[i]);

    Serial.print(bayName[i]);
    Serial.print(": ");

    if (d < MIN_VALID_CM || d > MAX_VALID_CM) {
      Serial.print("invalid/no echo - ignored");
      // Do not change counters on invalid/no echo. This prevents flicker.
    } else {
      bool rawOccupied = (d <= OCCUPIED_CM);

      if (rawOccupied) {
        occupiedCount[i]++;
        freeCount[i] = 0;
      } else {
        freeCount[i]++;
        occupiedCount[i] = 0;
      }

      String stableStatus = lastReported[i];

      if (occupiedCount[i] >= OCCUPIED_CONFIRM_COUNT) {
        stableStatus = "occupied";
      }

      if (freeCount[i] >= FREE_CONFIRM_COUNT) {
        stableStatus = "free";
      }

      Serial.print(d);
      Serial.print(" cm raw=");
      Serial.print(rawOccupied ? "occupied" : "free");
      Serial.print(" stable=");
      Serial.print(stableStatus);
      Serial.print(" occCnt=");
      Serial.print(occupiedCount[i]);
      Serial.print(" freeCnt=");
      Serial.print(freeCount[i]);

      if (lastReported[i] != stableStatus) {
        reportSpotStatus(spotId[i], stableStatus.c_str());
        lastReported[i] = stableStatus;
      }
    }

    Serial.print("   ");
    delay(60);  // more gap between sensors to reduce cross-talk
  }

  Serial.println();
  delay(250);
}
