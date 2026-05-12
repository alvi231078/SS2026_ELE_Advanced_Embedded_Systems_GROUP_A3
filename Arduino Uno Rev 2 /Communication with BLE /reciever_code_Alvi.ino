#include <ArduinoBLE.h>

const char* targetServiceUUID = "181A";
const char* tempCharUUID      = "2A6E";

void setup() {
  pinMode(LED_BUILTIN, OUTPUT);
  Serial.begin(9600);
  delay(2000);

  if (!BLE.begin()) {
    while (1) {
      digitalWrite(LED_BUILTIN, HIGH); delay(100);
      digitalWrite(LED_BUILTIN, LOW);  delay(100);
    }
  }

  BLE.scanForUuid(targetServiceUUID);
  digitalWrite(LED_BUILTIN, HIGH);
}

void loop() {
  BLEDevice peripheral = BLE.available();

  if (peripheral) {
    if (peripheral.localName() != "UnoTempSensor") {
      return;
    }

    BLE.stopScan();
    monitorSensor(peripheral);
    BLE.scanForUuid(targetServiceUUID);
    digitalWrite(LED_BUILTIN, HIGH);
  }
}

void monitorSensor(BLEDevice peripheral) {
  if (!peripheral.connect()) return;
  digitalWrite(LED_BUILTIN, LOW);

  if (!peripheral.discoverAttributes()) {
    peripheral.disconnect();
    return;
  }

  BLECharacteristic tempChar = peripheral.characteristic(tempCharUUID);
  if (!tempChar || !tempChar.canSubscribe()) {
    peripheral.disconnect();
    return;
  }

  tempChar.subscribe();

  while (peripheral.connected()) {
    if (tempChar.valueUpdated()) {
      int16_t tempRaw = 0;
      tempChar.readValue(tempRaw);

      Serial.print(tempRaw / 100);
      Serial.print(".");
      int frac = tempRaw % 100;
      if (frac < 10) Serial.print("0");
      Serial.println(frac);

      digitalWrite(LED_BUILTIN, HIGH); delay(20);
      digitalWrite(LED_BUILTIN, LOW);
    }
  }
}
