// ===== ESP32 #1 — Parking Node: 3x HC-SR04, now reporting to the Raspberry Pi =====
// Echo pins go through 1k+2k dividers (5V -> ~3.3V). Trig is direct 3.3V.
//
// BEFORE UPLOADING: fill in your Wi-Fi name/password below.
// PI_BASE_URL is set to the Pi's known IP (192.168.178.35). If it ever
// changes, run `hostname -I` on the Pi to get the new one.

#include <WiFi.h>
#include <HTTPClient.h>

// ---- Fill these in ----
const char* WIFI_SSID     = "Alvi's Repeater";
const char* WIFI_PASSWORD = "Happyhome@2022";
const char* PI_BASE_URL   = "http://192.168.178.35:5000";

const int trigPins[3] = {5, 17, 22};   // GPIO5, GPIO17, GPIO22
const int echoPins[3] = {18, 19, 21};  // GPIO18, GPIO19, GPIO21
const char* bayName[3] = {"Bay 1", "Bay 2", "Bay 3"};
const int spotId[3] = {1, 2, 3};       // matches the Pi's spot_status keys (1,2,3)

// distance below this (cm) = car present
const float OCCUPIED_CM = 10.0;

// remembers what was last sent to the Pi, so we only POST when something
// actually changes rather than every single reading
String lastReported[3] = {"", "", ""};

long readDistanceCM(int trig, int echo) {
  digitalWrite(trig, LOW);
  delayMicroseconds(2);
  digitalWrite(trig, HIGH);
  delayMicroseconds(10);
  digitalWrite(trig, LOW);
  // timeout 30ms (~5m) so a missing echo doesn't hang the loop
  long dur = pulseIn(echo, HIGH, 30000);
  if (dur == 0) return -1;          // no echo / out of range
  return dur * 0.0343 / 2;          // speed of sound -> cm
}

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

void reportSpotStatus(int spot, const char* status) {
  if (WiFi.status() != WL_CONNECTED) return;

  HTTPClient http;
  http.setTimeout(2000);
  http.begin(String(PI_BASE_URL) + "/spot-update");
  http.addHeader("Content-Type", "application/json");
  String body = String("{\"spot\":") + spot + ",\"status\":\"" + status + "\"}";
  int code = http.POST(body);
  if (code != 200) {
    Serial.printf("spot-update failed for spot %d, code %d\n", spot, code);
  }
  http.end();
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
  Serial.println("ESP32 #1 ready - 3x HC-SR04");
}

void loop() {
  for (int i = 0; i < 3; i++) {
    long d = readDistanceCM(trigPins[i], echoPins[i]);
    Serial.print(bayName[i]);
    Serial.print(": ");

    if (d < 0) {
      Serial.print("no echo");
    } else {
      const char* status = (d <= OCCUPIED_CM) ? "occupied" : "free";
      Serial.print(d);
      Serial.print(" cm  [");
      Serial.print(status);
      Serial.print("]");

      if (lastReported[i] != status) {
        reportSpotStatus(spotId[i], status);
        lastReported[i] = status;
      }
    }
    Serial.print("   ");
    delay(15);   // small gap so sensors don't cross-talk
  }
  Serial.println();
  delay(150);
}
