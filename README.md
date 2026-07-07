Smart Parking System

Advanced Embedded Systems Lab — Summer Term 2026
Team A3: Md Ratul Ahmed Alvi · Md Wasib Kamal Nirjon

⸻

Overview

A real-time MQTT-based smart parking monitoring and gate control system using a Raspberry Pi and two wirelessly connected ESP32 nodes.

The system detects parking slot availability, controls entry and exit gates, and displays the live parking status on a web dashboard. Communication between the Raspberry Pi and ESP32 nodes is handled using the MQTT publish/subscribe protocol over WiFi.

* Node 1 — Raspberry Pi:
    Works as the central server. It runs the MQTT broker, Flask backend, and live web dashboard. It receives parking slot and gate updates from the ESP32 nodes, processes the current parking state, and displays the result on the dashboard.
* Node 2 — ESP32 Bay Node:
    Monitors three parking slots using ultrasonic sensors. It detects whether each slot is free or occupied and publishes the slot status to the Raspberry Pi through MQTT.
* Node 3 — ESP32 Gate Node:
    Controls the entry and exit gates using servo motors. It uses IR sensors to detect vehicles at the gates and communicates gate events with the Raspberry Pi through MQTT.

⸻

Hardware Requirements

Component	Role	Notes
Raspberry Pi	Central server	Runs MQTT broker, Flask backend, and dashboard
2× ESP32 Development Boards	Wireless embedded nodes	One ESP32 for parking bays, one ESP32 for gate control
3× Ultrasonic Sensors	Parking slot detection	Detect whether each parking bay is free or occupied
2× IR Sensors	Vehicle detection at gates	Detect vehicle presence at entry and exit points
2× Servo Motors	Gate actuation	Open and close entry and exit barriers
Resistors	Sensor signal protection/stability	Used with ultrasonic sensor connections
External/Stable Power Source	Power support	Provides enough current for sensors and servos
Jumper Wires	Hardware connections	Used to connect sensors and actuators with ESP32 boards
MicroSD Card	Raspberry Pi storage	Stores Raspberry Pi OS and project files
WiFi Network / Mobile Hotspot	Wireless communication	Connects Raspberry Pi and ESP32 nodes on the same network

⸻

Software & Technologies

Layer	Raspberry Pi	ESP32 Nodes
Language	Python 3	C/C++
Framework / Tools	Flask, Mosquitto MQTT Broker	Arduino IDE / PlatformIO
Communication	MQTT publish/subscribe over WiFi	MQTT client over WiFi
Data Format	MQTT topic payloads / JSON-style status data	MQTT topic payloads
Dashboard	HTML, CSS, JavaScript, Server-Sent Events	—
Network	Local WiFi / iPhone hotspot	Local WiFi / iPhone hotspot

⸻

MQTT Communication

The system uses MQTT instead of HTTP to reduce latency and improve real-time communication between the Raspberry Pi and ESP32 nodes.

The ESP32 nodes publish sensor and gate messages to MQTT topics. The Raspberry Pi subscribes to these topics and updates the dashboard whenever new data arrives.

Example MQTT topics:

parking/spot/1/status
parking/spot/2/status
parking/spot/3/status
parking/gate/entry/status
parking/gate/exit/status
parking/node/bay/status
parking/node/gate/status

Example payloads:

free
occupied
open
closed
online
offline

⸻

Sensor Logic

The parking bay node uses ultrasonic sensors to detect whether each parking slot is occupied or free.

To avoid false readings from reflected echoes or invalid sensor values, threshold and filtering logic is used:

Distance <= 8 cm              → possible occupied
Distance below 2 cm or >250 cm → ignored as invalid/no echo
3 continuous occupied readings → dashboard changes to occupied
5 continuous free readings     → dashboard changes to free

This prevents sudden incorrect changes caused by noise, weak echoes, or temporary sensor errors.

The ultrasonic sensors are sampled approximately every 200 ms, meaning the parking bay node performs about 5 full scan cycles per second.

⸻

Gate Logic

The gate node uses IR sensors to detect vehicles at the entry and exit points.

* When a vehicle is detected at the entry gate, the ESP32 asks the Raspberry Pi whether parking space is available.
* If at least one valid parking bay is free, the entry servo opens.
* If all bays are occupied, the entry gate remains closed.
* When a vehicle is detected at the exit gate, the exit servo opens to allow the vehicle to leave.

The gate IR logic also uses debounce protection to avoid repeated false triggering from the same vehicle.

⸻

System States

The Raspberry Pi processes MQTT messages and updates the system status across the following states:

SYSTEM_READY → SLOT_FREE          (one or more parking slots are available)
SYSTEM_READY → SLOT_OCCUPIED      (one or more parking slots are occupied)
SYSTEM_READY → PARKING_FULL       (all valid parking slots are occupied)
SYSTEM_READY → ENTRY_GATE_OPEN    (entry gate opens for an allowed vehicle)
SYSTEM_READY → ENTRY_GATE_CLOSED  (entry gate remains closed when parking is full)
SYSTEM_READY → EXIT_GATE_OPEN     (exit gate opens for a leaving vehicle)
Any          → NODE_OFFLINE       (ESP32 node disconnects or stops sending updates)
NODE_OFFLINE → SYSTEM_READY       (node reconnects and sends valid data again)

For safety, if a parking sensor node disconnects, the affected bay status should be treated as unknown instead of being trusted as free.

⸻

Project Improvements and Design Decisions

During development, several issues were found and solved:

* WiFi hotspot connection issue:
    Raspberry Pi and laptop had to be connected to the same hotspot/network so that the command-line interface and ESP32 communication worked properly.
* Ultrasonic echo noise:
    Ultrasonic sensors sometimes detected reflected echoes. A threshold and continuous-reading confirmation method was added to avoid false occupied/free changes.
* Power issue with IR sensors:
    Two IR sensors sharing the same 3.3 V supply were not stable enough, so the power source was improved.
* Servo motor issue:
    Initial servo motors rotated 360 degrees, which was not suitable for gate barriers. They were replaced with 90-degree servo motors.
* HTTP latency issue:
    The first version used HTTP communication between nodes, but it had higher latency. The final version was reframed using MQTT publish/subscribe communication.
* Removed sensors:
    Flame, temperature, and humidity sensors were removed because they did not match the final project scope. The project focus became parking slot detection and gate control.

⸻

Team Responsibilities

* Nirjon — ESP32 subsystem: ultrasonic sensor setup, IR sensor setup, servo motor testing, sensor threshold testing, hardware wiring, and embedded code testing.
* Alvi — Raspberry Pi subsystem: MQTT broker setup, Flask backend, dashboard implementation, MQTT data handling, gate access logic, system integration, WiFi/hotspot setup, and final documentation.

Both team members contributed to debugging, testing, hardware integration, GitHub updates, and final project presentation.

⸻

References

* ESP32 Arduino Core
* Raspberry Pi Documentation
* Flask Documentation
* Mosquitto MQTT Broker
* Eclipse Paho MQTT Python Client
* Arduino Documentation
