// ===== ESP32 #1 — Parking Node: 3x HC-SR04 test =====
// Echo pins go through 1k+2k dividers (5V -> ~3.3V). Trig is direct 3.3V.

const int trigPins[3] = {5, 17, 22};   // GPIO5, GPIO17, GPIO22
const int echoPins[3] = {18, 19, 21};  // GPIO18, GPIO19, GPIO21
const char* bayName[3] = {"Bay 1", "Bay 2", "Bay 3"};

// distance below this (cm) = car present
const float OCCUPIED_CM = 10.0;

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

void setup() {
  Serial.begin(115200);
  delay(500);
  for (int i = 0; i < 3; i++) {
    pinMode(trigPins[i], OUTPUT);
    pinMode(echoPins[i], INPUT);
    digitalWrite(trigPins[i], LOW);
  }
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
      Serial.print(d);
      Serial.print(" cm  [");
      Serial.print(d <= OCCUPIED_CM ? "OCCUPIED" : "free");
      Serial.print("]");
    }
    Serial.print("   ");
    delay(60);   // small gap so sensors don't cross-talk
  }
  Serial.println();
  delay(500);
}