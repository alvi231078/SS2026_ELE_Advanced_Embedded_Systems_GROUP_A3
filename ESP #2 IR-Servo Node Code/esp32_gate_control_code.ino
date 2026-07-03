/*
  ESP32 #2 - Gate Control (Entry + Exit)
  Two IR sensors trigger two independent Miuzei MF90 servos to simulate
  parking gate barriers opening and closing.

  Wiring:
    IR Entry sensor OUT -> GPIO5
    IR Exit  sensor OUT -> GPIO25
    Entry servo signal  -> GPIO4
    Exit  servo signal  -> GPIO13

  CALIBRATION NOTE:
  SERVO_PULSE_MIN/MAX below define what pulse width = angle 0 and
  angle 180. 500-2500us is a wider range than the previous 1000-2000,
  which should let write(90) reach a truer physical 90 degrees on
  SG90-family servos like the MF90. If it's still off after this change,
  the servo horn was likely mounted while off-center — detach the horn,
  power on (servo will sit wherever last commanded), send write(90),
  then reseat the horn at that exact position before screwing it down.
*/

#include <ESP32Servo.h>

#define IR_ENTRY_PIN    5
#define IR_EXIT_PIN     25
#define SERVO_ENTRY_PIN 4
#define SERVO_EXIT_PIN  13
#define IR_ACTIVE_LOW   true

#define SERVO_PULSE_MIN 500     // pulse width (us) for angle 0
#define SERVO_PULSE_MAX 2500    // pulse width (us) for angle 180

const int GATE_OPEN_ANGLE   = 90;
const int GATE_CLOSED_ANGLE = 0;
const unsigned long SERVO_MOVE_MS   = 450;   // time allowed for servo to reach target
const unsigned long SAFETY_DELAY_MS = 1000;  // gate stays open this long AFTER IR stops detecting
const unsigned long DEBOUNCE_MS     = 300;

enum GateState { IDLE, OPENING, HOLDING, CLOSING };

struct Gate {
  const char* name;
  int irPin;
  Servo servo;
  int servoPin;
  GateState state = IDLE;
  unsigned long stateChangedAt = 0;
  unsigned long lastTrigger = 0;
};

Gate entryGate = {"ENTRY", IR_ENTRY_PIN, Servo(), SERVO_ENTRY_PIN};
Gate exitGate  = {"EXIT",  IR_EXIT_PIN,  Servo(), SERVO_EXIT_PIN};

bool carDetected(int pin) {
  int val = digitalRead(pin);
  return IR_ACTIVE_LOW ? (val == LOW) : (val == HIGH);
}

void setup() {
  Serial.begin(115200);

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

  Serial.println("Gate controller ready.");
}

void updateGate(Gate &gate) {
  unsigned long now = millis();

  switch (gate.state) {

    case IDLE:
      if (carDetected(gate.irPin) && (now - gate.lastTrigger > DEBOUNCE_MS)) {
        gate.lastTrigger = now;
        Serial.printf("[%s] Car detected -> opening\n", gate.name);
        gate.servo.attach(gate.servoPin, SERVO_PULSE_MIN, SERVO_PULSE_MAX);
        gate.servo.write(GATE_OPEN_ANGLE);
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
        // still something in the beam - keep resetting the clock,
        // so the gate stays open the whole time it's detected
        gate.stateChangedAt = now;
      } else if (now - gate.stateChangedAt >= SAFETY_DELAY_MS) {
        // IR has been clear for a full SAFETY_DELAY_MS - safe to close
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
        gate.state = IDLE;
      }
      break;
  }
}

void loop() {
  updateGate(entryGate);
  updateGate(exitGate);
}
