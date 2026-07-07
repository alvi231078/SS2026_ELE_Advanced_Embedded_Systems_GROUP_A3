# Development Log: Issues & Fixes

**Smart Parking System — Advanced Embedded Systems Lab, Summer Term 2026**
Team A3 · Md Ratul Ahmed Alvi · Md Wasib Kamal Nirjon

During development, we ran into several practical hardware and communication issues. Working through them shaped the final design and made the system considerably more stable. This log documents each issue and how it was resolved.

---

## 1. Raspberry Pi Wi-Fi & Mobile Hotspot

**Problem:** The Raspberry Pi, laptop, and CLI access all needed to sit on the same network so the Pi could be controlled remotely and the project run end-to-end. The initial connection to an iPhone mobile hotspot was unstable and hard to manage.

**Fix:** Manually configured the Raspberry Pi's Wi-Fi connection and confirmed both the Pi and laptop were joined to the same iPhone hotspot network before every session.

---

## 2. Ultrasonic Sensor False Echo Readings

**Problem:** The ultrasonic sensors occasionally picked up reflected echoes from nearby surfaces or objects, producing incorrect distance values and unstable parking-spot detection.

**Fix:** Added threshold filtering plus confirmation logic before trusting a reading:

| Condition | Result |
|---|---|
| Distance ≤ 8 cm | Possible occupied |
| Distance < 2 cm or > 250 cm | Ignored — invalid / no echo |
| 3 continuous occupied readings | Dashboard updates to `occupied` |
| 5 continuous free readings | Dashboard updates to `free` |

This stopped the dashboard from flipping state on a single bad reading, making bay detection far more reliable.

---

## 3. IR Sensor Power Issue

**Problem:** Two IR sensors shared the same 3.3V power source, and the available current wasn't enough for stable operation.

**Fix:** Increased the power supply capacity so both sensors received sufficient current to operate reliably.

---

## 4. Resistors Added for Ultrasonic Sensors

**Problem:** The ultrasonic sensor wiring needed better signal stability and hardware protection.

**Fix:** Added one resistor per ultrasonic sensor — three resistors total for the three sensors — making the wiring safer and more stable.

---

## 5. Servo Motor Rotation Problem

**Problem:** The initial servo motors didn't behave as expected — instead of rotating to a fixed gate angle, some spun continuously like 360° motors.

**Fix:** The gate barrier needed controlled, fixed-angle movement, not continuous rotation. Replaced the motors with **90° servo motors**, which matched the open/close requirement.

---

## 6. HTTP Latency Problem

**Problem:** All three nodes initially communicated over HTTP. Testing showed this introduced noticeable latency, especially when multiple sensor updates and gate commands overlapped.

**Fix:** Switched communication from HTTP to **MQTT**. MQTT's lightweight publish/subscribe model is a better fit for IoT workloads and significantly reduced latency.

---

## 7. Flame Sensor — Removed

**Problem:** A flame sensor was tested as a potential addition but produced unstable, meaningless readings that added no value to the parking use case.

**Fix:** Removed the flame sensor entirely to reduce unnecessary complexity.

---

## 8. Temperature & Humidity Sensor — Removed

**Problem:** A temperature/humidity sensor was considered, but it didn't serve the core purpose of the smart parking system.

**Fix:** Dropped it in favor of **two additional IR sensors**, which directly improved vehicle detection and gate-related sensing.

---

## Final Outcome

Resolving these issues made the project more stable and practical overall:

- Improved power supply distribution
- Added sensor filtering and confirmation logic
- Replaced unsuitable servo motors with 90° servos
- Removed sensors that added no value (flame, temperature/humidity)
- Upgraded communication from HTTP to MQTT

Together, these changes made the Smart Parking System more reliable, faster, and better suited to a real embedded IoT application.
