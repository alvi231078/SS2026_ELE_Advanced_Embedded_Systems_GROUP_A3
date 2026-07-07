During the development of our Smart Parking System project, we faced several practical hardware and communication issues. These issues helped us improve the final design and make the system more stable.

1. Raspberry Pi Wi-Fi and Mobile Hotspot Issue

One major problem was connecting the Raspberry Pi to an iPhone mobile hotspot. The Raspberry Pi, laptop, and command-line interface access needed to be on the same network so that we could control the Raspberry Pi from the laptop and run the project properly.

At first, the connection was unstable and difficult to manage. We had to manually configure the Raspberry Pi Wi-Fi connection and make sure that both the Raspberry Pi and laptop were connected to the same iPhone hotspot network.

2. Ultrasonic Sensor False Echo Readings

The ultrasonic sensors sometimes detected reflected echoes from nearby surfaces or unwanted objects. This created incorrect distance values and unstable parking spot detection.

To solve this, we added threshold filtering and confirmation logic:

Distance ≤ 8 cm → possible occupied
Distance < 2 cm or > 250 cm → ignored as invalid or no echo
3 continuous occupied readings → dashboard changes to occupied
5 continuous free readings → dashboard changes to free

This made the parking spot detection more reliable because the dashboard no longer changed state from a single wrong reading.

3. IR Sensor Power Issue

We also faced a power issue with the IR sensors. Two IR sensors were sharing the same 3.3V power source, but the available power was not enough for stable operation.

To fix this, we increased the power supply capacity so that the sensors could receive enough current and work reliably.

4. Resistors Added for Ultrasonic Sensors

For better signal stability and hardware protection, we added resistors for the ultrasonic sensors. Since we used three ultrasonic sensors, we added three resistors in the circuit.

This helped make the sensor wiring safer and more stable.

5. Servo Motor Rotation Problem

At the beginning, we used servo motors that did not behave as expected. Instead of rotating only to the required gate angle, some servos rotated continuously like 360-degree motors.

For our parking gate, we needed controlled angle movement, not continuous rotation. Therefore, we replaced them with 90-degree servo motors, which were more suitable for opening and closing the parking gate.

6. HTTP Latency Problem

Initially, all three nodes were running using HTTP communication. However, during testing, we found that HTTP was slower and created more latency, especially when multiple sensor updates and gate commands were happening.

Because of this, we decided to change the communication method from HTTP to MQTT. MQTT is more suitable for IoT projects because it is lightweight, faster, and works well with publish/subscribe communication.

7. Flame Sensor Removed

We also tested a flame sensor, but it gave unstable and meaningless values. The readings were not useful for our parking system, and it added unnecessary complexity.

For this reason, we removed the flame sensor from the project.

8. Temperature and Humidity Sensor Removed

We also considered using a temperature and humidity sensor, but later we realized that it was not directly related to the main purpose of the smart parking system.

Instead of using temperature and humidity sensing, we decided to add two more IR sensors to improve vehicle detection and gate-related sensing.

Final Improvement

After solving these issues, our project became more stable and practical. We improved the power supply, added sensor filtering logic, replaced unsuitable servo motors, removed unnecessary sensors, and upgraded the communication from HTTP to MQTT.

These changes helped us make the Smart Parking System more reliable, faster, and better suited for a real embedded IoT application.
