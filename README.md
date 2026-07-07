# 🚗 Smart Parking System

**Advanced Embedded Systems Lab — Summer Term 2026**
Team A3 · Md Ratul Ahmed Alvi · Md Wasib Kamal Nirjon

A real-time, MQTT-based parking monitoring and gate control system built on one Raspberry Pi and two ESP32 nodes. The system detects free/occupied parking bays, manages entry/exit gate barriers, and streams live status to a web dashboard over Server-Sent Events (SSE).

---

## Table of Contents

- [Overview](#overview)
- [System Architecture](#system-architecture)
- [Hardware Requirements](#hardware-requirements)
- [Software & Technologies](#software--technologies)
- [MQTT Communication](#mqtt-communication)
- [Parking Bay Sensor Logic](#parking-bay-sensor-logic)
- [Gate Control Logic](#gate-control-logic)
- [System States](#system-states)
- [Dashboard](#dashboard)
- [Getting Started](#getting-started)
- [Issues & Fixes Log](#issues--fixes-log)
- [Team Responsibilities](#team-responsibilities)
- [References](#references)

---

## Overview

The system uses **MQTT publish/subscribe** for all inter-node communication — replacing an earlier HTTP-based version that suffered from higher latency.

| Node | Role |
|---|---|
| **Node 1 — Raspberry Pi** | Central server. Runs the Mosquitto MQTT broker, Flask backend, and live web dashboard. Aggregates MQTT messages from both ESP32 nodes, maintains system state, and pushes live updates to the browser via SSE. |
| **Node 2 — ESP32 Parking Bay Node** | Reads three ultrasonic sensors to monitor three parking bays and publishes free/occupied status. |
| **Node 3 — ESP32 Gate Controller Node** | Reads two IR sensors at the entry/exit gates and drives two servo-controlled barriers. The entry gate requests permission from the Raspberry Pi before opening. |

---



All three nodes communicate over a shared WiFi network (mobile hotspot in the current demo setup).

---

## Hardware Requirements

| Component | Role | Notes |
|---|---|---|
| Raspberry Pi | Central server | Runs Flask backend, dashboard, and MQTT broker |
| 2× ESP32 Dev Boards | Wireless embedded nodes | One for bay sensing, one for gate control |
| 3× Ultrasonic Sensors | Parking bay detection | Free/occupied status for Bay 1–3 |
| 2× IR Sensors | Vehicle detection | Entry and exit gate triggers |
| 2× 90° Servo Motors | Gate control | Entry and exit barrier actuation |
| Resistors | Sensor stability | Used in the ultrasonic sensor circuit |
| External/Stable Power Source | Power supply | Provides sufficient current for sensors + servos |
| Jumper Wires | Wiring | Connects sensors/actuators to ESP32 boards |
| MicroSD Card | Raspberry Pi storage | Hosts Raspberry Pi OS + project files |
| WiFi Network / Mobile Hotspot | Wireless comms | All devices must share the same network |

---

## Software & Technologies

| Layer | Raspberry Pi | ESP32 Nodes |
|---|---|---|
| **Language** | Python 3 | C/C++ |
| **Framework/Tools** | Flask, Mosquitto MQTT Broker, Paho MQTT | Arduino IDE / ESP32 Arduino Core |
| **Communication** | MQTT publish/subscribe over WiFi | MQTT client over WiFi |
| **Dashboard Updates** | Server-Sent Events | — |
| **Data Format** | MQTT topic payloads + JSON state | MQTT payloads |
| **Demo Network** | iPhone hotspot | iPhone hotspot |

---

## MQTT Communication

The Raspberry Pi subscribes to bay/gate status topics and entry requests, updates internal state, and publishes an allow/deny response for the entry gate.

**Topic patterns:**

```
parking/spot/+/status
parking/gate/+/status
parking/gate/entry/request
parking/gate/entry/allow
```

**Live topics used:**

```
parking/spot/1/status
parking/spot/2/status
parking/spot/3/status
parking/gate/entry/status
parking/gate/exit/status
parking/gate/entry/request
parking/gate/entry/allow
```

**Example payloads:** `free` · `occupied` · `open` · `closed` · `request` · `true` · `false`

---

## Parking Bay Sensor Logic

**Pin mapping:**

| Sensor | Trigger | Echo |
|---|---|---|
| Bay 1 | GPIO5 | GPIO18 |
| Bay 2 | GPIO17 | GPIO19 |
| Bay 3 | GPIO22 | GPIO21 |

**Classification thresholds:**

| Distance | Interpretation |
|---|---|
| ≤ 8 cm | Possible occupied |
| < 2 cm or > 250 cm | Invalid reading — ignored |

**Debouncing:** to filter ultrasonic echo noise, status changes require sustained confirmation rather than a single reading:

- **3** consecutive occupied readings → bay marked `occupied`
- **5** consecutive free readings → bay marked `free`

A status is only published when the confirmed state actually changes, e.g.:

```
parking/spot/1/status → occupied
parking/spot/2/status → free
parking/spot/3/status → occupied
```

**Scan timing:** 60 ms between sensors + 250 ms after each full pass:

```
3 × 60 ms + 250 ms = 430 ms  →  ≈ 2.3 full scans/second
```

> Actual throughput may be lower if a `pulseIn()` call hits its timeout while waiting for an echo.

---

## Gate Control Logic

**Pin mapping:**

| Function | Pin |
|---|---|
| Entry IR sensor | GPIO5 |
| Exit IR sensor | GPIO25 |
| Entry servo | GPIO4 |
| Exit servo | GPIO13 |

IR sensors are active-low.

**Entry flow:**
1. Vehicle detected → ESP32 publishes `parking/gate/entry/request → request`
2. Raspberry Pi checks whether at least one bay is free
3. Pi publishes `parking/gate/entry/allow → true` (free bay available) or `false` (no free bay)
4. Entry servo opens **only** on `true`

**Exit flow:**
Exit IR detects a vehicle → exit servo opens immediately (no permission check).

**Gate status topics:** `parking/gate/entry/status` and `parking/gate/exit/status` → `open` / `closed`

---

## System States

**Initial state:**

```
Bay 1        = unknown
Bay 2        = unknown
Bay 3        = unknown
Entry gate   = closed
Exit gate    = closed
```

**Valid states:**

| Entity | Possible values |
|---|---|
| Parking bay | `unknown`, `free`, `occupied` |
| Gate | `open`, `closed` |

**End-to-end behavior:**

```
Ultrasonic reading → confirmed status change → MQTT publish
    → Pi updates state → dashboard updates via SSE

Entry IR trigger → permission request → Pi checks free-bay count
    → allow/deny response → servo opens only if allowed

Exit IR trigger → exit servo opens → gate status published
```

---

## Dashboard

Served by Flask directly from the Raspberry Pi, showing:

- Available / occupied bay counts
- Individual Bay 1 / 2 / 3 status
- Entry and exit gate status
- Live event log
- Last update timestamp & latency info
- Light/dark mode toggle

Accessible from any device on the same hotspot:

```
http://172.20.10.8:5000
```

> If the Raspberry Pi's IP changes, update the MQTT broker IP in **both** ESP32 sketches.

---

## Getting Started

**1. Start the Raspberry Pi server:**

```bash
cd ~
source .venv/bin/activate
python3 app.py
```

**2. Open the dashboard** from a device on the same network:

```
http://172.20.10.8:5000
```

**3. Flash the ESP32 boards:**

| File | Target |
|---|---|
| `ultrasonic_node-1.ino` | ESP32 Parking Bay Node |
| `ir_servo-node-2.ino` | ESP32 Gate Controller Node |

**Network configuration (current demo):**

```
SSID:            Alvi's iPhone
Password:        12345678
MQTT Broker IP:  172.20.10.8
```

---

## Issues & Fixes Log

| Issue | Fix |
|---|---|
| Hotspot connectivity | All devices joined the same hotspot; Pi IP checked via `hostname -I` and matched in both ESP32 sketches |
| Ultrasonic false echoes | Lowered occupied threshold to 8 cm, ignored readings < 2 cm or > 250 cm, added confirmation counters |
| Ultrasonic cross-talk | Added inter-sensor delay to reduce interference |
| Power instability | Moved sensors/servos to a dedicated stable power source |
| Continuous-rotation servos | Replaced with 90° positional servos for barrier control |
| HTTP latency | Replaced HTTP polling with MQTT publish/subscribe |

---

## Team Responsibilities

| Member | Focus |
|---|---|
| **Md Wasib Kamal Nirjon** | ESP32 hardware subsystem — ultrasonic setup, IR sensor setup, servo testing, wiring, node-level testing |
| **Md Ratul Ahmed Alvi** | Raspberry Pi & software subsystem — Mosquitto setup, Flask backend, dashboard, MQTT message handling, gate permission logic, hotspot setup, system integration |

Both members contributed to debugging, testing, documentation, GitHub updates, and the final presentation.

---

## References

- [ESP32 Arduino Core](https://github.com/espressif/arduino-esp32)
- [Raspberry Pi Documentation](https://www.raspberrypi.com/documentation/)
- [Flask Documentation](https://flask.palletsprojects.com/)
- [Mosquitto MQTT Broker](https://mosquitto.org/)
- [Eclipse Paho MQTT Python Client](https://www.eclipse.org/paho/)
- [PubSubClient MQTT Library](https://github.com/knolleary/pubsubclient)
- [Arduino Documentation](https://docs.arduino.cc/)
