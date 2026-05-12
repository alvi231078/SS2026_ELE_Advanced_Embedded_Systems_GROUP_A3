#include <ArduinoBLE.h>
#include <OneWire.h>

#define ONE_WIRE_BUS 2
OneWire ds(ONE_WIRE_BUS);

BLEService envService("181A");
BLEShortCharacteristic tempCharacteristic("2A6E", BLERead | BLENotify);

unsigned long lastUpdate = 0;
const unsigned long updateInterval = 1000;

int16_t readDS18B20() {
  byte data[9];
  ds.reset();
  ds.skip();
  ds.write(0x44, 0);
  delay(750);
  ds.reset();
  ds.skip();
  ds.write(0xBE);
  for (byte i = 0; i < 9; i++) data[i] = ds.read();
  int16_t raw = (data[1] << 8) | data[0];
  return (int16_t)(((int32_t)raw * 25) / 4);
}

void setup() {
  pinMode(LED_BUILTIN, OUTPUT);

  if (!BLE.begin()) {
    while (1) {
      digitalWrite(LED_BUILTIN, HIGH);
      delay(100);
      digitalWrite(LED_BUILTIN, LOW);
      delay(100);
    }
  }

  BLE.setLocalName("UnoTempSensor");
  BLE.setDeviceName("UnoTempSensor");
  BLE.setAdvertisedService(envService);
  envService.addCharacteristic(tempCharacteristic);
  BLE.addService(envService);
  tempCharacteristic.writeValue((int16_t)0);

  BLE.advertise();
  digitalWrite(LED_BUILTIN, HIGH);
}

void loop() {
  BLEDevice central = BLE.central();

  if (central) {
    while (central.connected()) {
      if (millis() - lastUpdate >= updateInterval) {
        lastUpdate = millis();
        tempCharacteristic.writeValue(readDS18B20());
        digitalWrite(LED_BUILTIN, LOW);
        delay(20);
        digitalWrite(LED_BUILTIN, HIGH);
      }
    }
  }
}
