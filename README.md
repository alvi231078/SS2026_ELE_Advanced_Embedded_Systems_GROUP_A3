# Smart Driver Assistance System

**Advanced Embedded Systems Lab — Summer Term 2026**  
**Team A3:** Md Ratul Ahmed Alvi · Md Wasib Kamal Nirjon

---

## Overview

A real-time in-vehicle safety system using two wirelessly connected embedded nodes:

- **Node 1 (Raspberry Pi 4):** Monitors the driver via camera, detects drowsiness using facial landmark analysis (Eye Aspect Ratio), and triggers audio alerts.
- **Node 2 (ESP32-CAM):** Captures the road ahead, classifies traffic signs on-device using TensorFlow Lite, and transmits results to the Pi over WiFi.

---

## ⚙️ Hardware Requirements

| Component | Role | Notes |
|---|---|---|
| **Raspberry Pi 4** | Main processing unit | Runs Python, MediaPipe, socket server, audio output |
| **ESP32-CAM module** | Edge detection unit | Integrated OV2640 image sensor, runs TFLite Micro |
| **USB Webcam or RPi Camera Module** | Driver-facing camera | Connected to Raspberry Pi via USB or CSI |
| **Speaker module** | Audio alert output | Requires audio HAT or USB audio adapter on the Pi |
| **WiFi network / hotspot** | Inter-device communication | IEEE 802.11 b/g/n — connects both nodes |

---

## Software & Technologies

| Layer | Raspberry Pi (Node 1) | ESP32 (Node 2) |
|---|---|---|
| **Language** | Python 3 | C++ (Arduino framework) |
| **ML / Vision** | MediaPipe Face Mesh, OpenCV | TensorFlow Lite Micro |
| **Communication** | WiFi socket server (TCP/HTTP) | WiFi client, JSON packets |
| **Audio** | pyttsx3 / pygame | — |

---

## System States

The alert engine on the Raspberry Pi operates across four states:

```
NORMAL → DROWSY          (EAR below threshold for N consecutive frames)
NORMAL → SIGN_ALERT      (ESP32 detects sign with high confidence)
NORMAL → COMBINED_ALERT  (both conditions active; drowsiness takes priority)
Any    → NORMAL          (configurable timeout after alert clears)
```

---

## Team Responsibilities

- **Alvi** — Raspberry Pi subsystem: camera setup, MediaPipe EAR pipeline, alert decision engine, speaker output, WiFi server
- **Nirjon** — ESP32 subsystem: ESP32-CAM setup, TFLite traffic sign classifier, WiFi client, JSON packet transmission

---

## References

- [MediaPipe Face Mesh](https://google.github.io/mediapipe/solutions/face_mesh.html)
- [TensorFlow Lite Micro for ESP32](https://www.tensorflow.org/lite/microcontrollers)
- [ESP32-CAM Arduino Library](https://github.com/espressif/arduino-esp32)
- [OpenCV Python Docs](https://docs.opencv.org/4.x/d6/d00/tutorial_py_root.html)
- [GTSRB Dataset](https://benchmark.ini.rub.de/gtsrb_news.html)
