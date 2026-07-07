Smart Parking System

Advanced Embedded Systems Lab — Summer Term 2026
Team A3: Md Ratul Ahmed Alvi · Md Wasib Kamal Nirjon

⸻

Overview

A real-time MQTT-based smart parking monitoring and gate control system using one Raspberry Pi and two ESP32 nodes connected through WiFi.

The system detects whether parking bays are free or occupied, controls entry and exit gates, and displays the live status on a web dashboard. The final project uses MQTT publish/subscribe communication instead of direct HTTP communication from the ESP32 nodes.

* Node 1 — Raspberry Pi:
    Works as the central server. It runs the Mosquitto MQTT broker, Python Flask backend, and live web dashboard. It receives MQTT messages from the ESP32 nodes, stores the current parking and gate status, and sends live updates to the browser using Server-Sent Events.
* Node 2 — ESP32 Parking Bay Node:
    Uses three ultrasonic sensors to monitor three parking slots. It detects whether each bay is free or occupied and publishes the result to MQTT topics.
* Node 3 — ESP32 Gate Controller Node:
    Uses two IR sensors to detect vehicles at the entry and exit gates. It controls two servo motors for the gate barriers. For the entry gate, it requests permission from the Raspberry Pi before opening.

⸻

Hardware Requirements

Component	Role	Notes
Raspberry Pi	Central server	Runs Flask backend, dashboard, and MQTT broker
2× ESP32 Development Boards	Wireless embedded nodes	One for parking bay sensing, one for gate control
3× Ultrasonic Sensors	Parking bay detection	Detect free or occupied status for Bay 1, Bay 2, and Bay 3
2× IR Sensors	Vehicle detection	Detect cars at entry and exit gates
2× 90-degree Servo Motors	Gate control	Open and close the entry and exit barriers
Resistors	Sensor connection/stability	Used with the ultrasonic sensor setup
External/Stable Power Source	Power supply support	Helps provide enough current for sensors and servos
Jumper Wires	Connections	Used for wiring sensors and actuators to ESP32 boards
MicroSD Card	Raspberry Pi storage	Stores Raspberry Pi OS and project files
WiFi Network / Mobile Hotspot	Wireless communication	Raspberry Pi, laptop, and ESP32 nodes must be on the same network

⸻

Software & Technologies

Layer	Raspberry Pi	ESP32 Nodes
Language	Python 3	C/C++
Framework / Tools	Flask, Mosquitto MQTT Broker, Paho MQTT	Arduino IDE / ESP32 Arduino Core
Communication	MQTT publish/subscribe over WiFi	MQTT client over WiFi
Dashboard Update Method	Server-Sent Events	—
Data Format	MQTT topic payloads and JSON state for dashboard	MQTT payloads
Network Used in Demo	Alvi’s iPhone hotspot	Alvi’s iPhone hotspot

⸻

MQTT Communication

The project uses MQTT for communication between the ESP32 nodes and the Raspberry Pi.

The ESP32 parking node publishes bay status messages. The ESP32 gate node publishes gate status messages and sends entry requests. The Raspberry Pi subscribes to these topics, updates the internal state, and publishes an allow/deny response for the entry gate.

Main MQTT topics used in the current project:

parking/spot/+/status
parking/gate/+/status
parking/gate/entry/request
parking/gate/entry/allow

Example real topics:

parking/spot/1/status
parking/spot/2/status
parking/spot/3/status
parking/gate/entry/status
parking/gate/exit/status
parking/gate/entry/request
parking/gate/entry/allow

Example payloads:

free
occupied
open
closed
request
true
false

⸻

Parking Bay Sensor Logic

The ESP32 parking bay node reads three ultrasonic sensors.

The ultrasonic sensors are connected using separate trigger and echo pins:

Trigger pins: GPIO5, GPIO17, GPIO22
Echo pins:    GPIO18, GPIO19, GPIO21

Each parking bay is classified using distance measurement:

Distance <= 8 cm               → possible occupied
Distance below 2 cm or >250 cm → invalid/no echo, ignored

To reduce false detection from ultrasonic echo noise, the code does not immediately change the bay status from one reading. It uses confirmation counters:

3 continuous occupied readings → bay becomes occupied
5 continuous free readings     → bay becomes free

The parking bay node publishes the result only when the stable status changes.

Example:

parking/spot/1/status → occupied
parking/spot/2/status → free
parking/spot/3/status → occupied

The current code waits 60 ms between sensors and 250 ms after each full scan, so the approximate full scan interval is:

3 × 60 ms + 250 ms = 430 ms

So the parking bay node performs about:

1 / 0.43 ≈ 2.3 full scans per second

The actual speed can be slower if an ultrasonic reading waits for the maximum pulseIn() timeout.

⸻

Gate Control Logic

The ESP32 gate node uses:

Entry IR sensor → GPIO5
Exit IR sensor  → GPIO25
Entry servo     → GPIO4
Exit servo      → GPIO13

The IR sensors are configured as active-low sensors.

When a vehicle is detected at the entry gate, the ESP32 publishes:

parking/gate/entry/request → request

The Raspberry Pi checks whether at least one parking bay is free.

If a bay is free, the Raspberry Pi publishes:

parking/gate/entry/allow → true

If no bay is free, it publishes:

parking/gate/entry/allow → false

The entry gate opens only when the response is true.

For the exit gate, the system opens the exit barrier when the exit IR sensor detects a vehicle.

Gate status is published using:

parking/gate/entry/status → open / closed
parking/gate/exit/status  → open / closed

⸻

System States

The Raspberry Pi stores the current status of all bays and gates.

Initial state:

Bay 1 = unknown
Bay 2 = unknown
Bay 3 = unknown
Entry gate = closed
Exit gate = closed

Possible parking bay states:

unknown
free
occupied

Possible gate states:

open
closed

Main system behavior:

ESP32 parking node reads ultrasonic sensors
→ publishes free/occupied status only after stable confirmation
→ Raspberry Pi receives MQTT message
→ Flask server updates internal state
→ dashboard updates live through Server-Sent Events
Entry IR detects car
→ ESP32 gate node asks Raspberry Pi for permission
→ Raspberry Pi checks if any bay is free
→ Raspberry Pi publishes true or false
→ entry servo opens only if allowed
Exit IR detects car
→ exit servo opens
→ gate status is published to dashboard

⸻

Dashboard

The Raspberry Pi serves a web dashboard using Flask.

The dashboard shows:

Available parking spaces
Occupied parking spaces
Bay 1 / Bay 2 / Bay 3 status
Entry gate status
Exit gate status
Live event log
Last update time
Latency / live update information
Light/dark mode button

The dashboard is opened from a laptop or phone connected to the same hotspot:

http://172.20.10.8:5000

If the Raspberry Pi IP changes, the ESP32 MQTT broker IP must be updated in both Arduino sketches.

⸻

Project Issues and Fixes

During development, several issues were found and solved:

* iPhone hotspot connection issue:
    The Raspberry Pi, ESP32 nodes, and laptop had to be connected to the same hotspot/network. The Raspberry Pi IP was checked using hostname -I, and the ESP32 MQTT broker IP was updated to match it.
* Ultrasonic false echo readings:
    The ultrasonic sensors sometimes received reflected echoes. The solution was to use a smaller occupied threshold of 8 cm, ignore invalid readings below 2 cm or above 250 cm, and use continuous confirmation counters.
* Ultrasonic cross-talk:
    A delay was added between reading each ultrasonic sensor to reduce interference between sensors.
* Power stability issue:
    The sensor and servo setup needed a stable power source because shared low-current supply caused unreliable behavior.
* Servo motor issue:
    The first servo motors were not suitable because they rotated continuously. The project was changed to use 90-degree servos for gate barriers.
* HTTP latency issue:
    The first version used HTTP, but it was slower and had more latency. The final version uses MQTT publish/subscribe communication.

⸻

Team Responsibilities

* Md Wasib Kamal Nirjon — ESP32 hardware subsystem: ultrasonic sensor setup, IR sensor setup, servo motor testing, hardware wiring, and embedded node testing.
* Md Ratul Ahmed Alvi — Raspberry Pi and software subsystem: Mosquitto MQTT setup, Flask backend, dashboard, MQTT message handling, gate permission logic, hotspot setup, and system integration.

Both team members contributed to debugging, testing, documentation, GitHub updates, and final project presentation.

⸻

How to Run

On the Raspberry Pi:

cd ~
source .venv/bin/activate
python3 app.py

Open the dashboard from a device connected to the same hotspot:

http://172.20.10.8:5000

Flash these files to the ESP32 boards:

ultrasonic_node-1.ino     → ESP32 parking bay node
ir_servo-node-2.ino       → ESP32 gate controller node

Both ESP32 sketches currently use:

SSID: Alvi’s iPhone
Password: 12345678
MQTT Broker IP: 172.20.10.8

⸻

References

* ESP32 Arduino Core
* Raspberry Pi Documentation
* Flask Documentation
* Mosquitto MQTT Broker
* Eclipse Paho MQTT Python Client
* PubSubClient MQTT Library
* Arduino Documentation
