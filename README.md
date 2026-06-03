# Smart Parking System

**Advanced Embedded Systems Lab — Summer Term 2026**
**Team A3:** Md Ratul Ahmed Alvi · Md Wasib Kamal Nirjon

---

## Overview

A real-time smart parking monitoring system using Raspberry Pi and two wirelessly connected ESP32 nodes:

* **Node 1 (Raspberry Pi):** Works as the main processing unit, receives sensor data from the ESP32 nodes, processes the parking and safety status, and displays the result on a dashboard.
* **Node 2 (ESP32):** Monitors parking slot availability using ultrasonic sensors and sends the data to the Raspberry Pi over WiFi.
* **Node 3 (ESP32):** Monitors temperature, humidity, and flame status, then sends the environmental and safety data to the Raspberry Pi over WiFi.

---

## ⚙️ Hardware Requirements

| Component                         | Role                       | Notes                                                  |
| --------------------------------- | -------------------------- | ------------------------------------------------------ |
| **Raspberry Pi**                  | Main processing unit       | Runs backend server and dashboard                      |
| **2× ESP32 Development Boards**   | Sensor nodes               | Collect sensor data and send it to the Raspberry Pi    |
| **3× Ultrasonic Sensors**         | Parking slot detection     | Detect whether parking slots are available or occupied |
| **Temperature & Humidity Sensor** | Environmental monitoring   | Measures temperature and humidity                      |
| **Flame Sensor**                  | Safety monitoring          | Detects possible flame or fire risk                    |
| **Jumper Wires**                  | Sensor connections         | Used to connect sensors with ESP32 boards              |
| **MicroSD Card**                  | Raspberry Pi storage       | Stores OS and project files                            |
| **WiFi network / hotspot**        | Inter-device communication | Connects ESP32 nodes with the Raspberry Pi             |

---

## Software & Technologies

| Layer                 | Raspberry Pi          | ESP32 Nodes              |
| --------------------- | --------------------- | ------------------------ |
| **Language**          | Python 3              | C/C++                    |
| **Framework / Tools** | Flask or FastAPI      | Arduino IDE / PlatformIO |
| **Communication**     | WiFi server           | WiFi client              |
| **Data Format**       | JSON                  | JSON packets             |
| **Dashboard**         | HTML, CSS, JavaScript | —                        |

---

## System States

The Raspberry Pi processes sensor data and updates the system status across the following states:

```text
NORMAL → SLOT_OCCUPIED        (one or more parking slots are occupied)
NORMAL → SLOT_AVAILABLE       (one or more parking slots are free)
NORMAL → ENVIRONMENT_ALERT    (temperature or humidity value is outside normal range)
NORMAL → FIRE_ALERT           (flame sensor detects possible fire risk)
Any    → NORMAL               (when sensor values return to normal condition)
```

---

## Team Responsibilities

* **Nirjon** — ESP32 subsystem: ultrasonic sensor setup, temperature and humidity sensor setup, flame sensor setup, sensor testing, documentation
* **Alvi** — Raspberry Pi subsystem: backend server, data receiving logic, dashboard implementation, system integration, WiFi data transmission

Both team members will contribute to debugging, testing, GitHub updates, and final project presentation.

---

## References

* [ESP32 Arduino Core](https://github.com/espressif/arduino-esp32)
* [Raspberry Pi Documentation](https://www.raspberrypi.com/documentation/)
* [Flask Documentation](https://flask.palletsprojects.com/)
* [Arduino Documentation](https://docs.arduino.cc/)

