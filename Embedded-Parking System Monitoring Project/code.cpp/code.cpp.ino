#define IR_SENSOR_PIN 4  // change to whichever GPIO you wired OUT to

void setup() {
  Serial.begin(115200);
  pinMode(IR_SENSOR_PIN, INPUT);
  Serial.println("IR sensor test started...");
}

void loop() {
  int state = digitalRead(IR_SENSOR_PIN);

  if (state == LOW) {           // most modules are active-LOW when object detected
    Serial.println("Object detected!");
  } else {
    Serial.println("No object detected");
  }

  delay(200);
}