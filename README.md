---
title: AERION Autonomous Border Surveillance
emoji: 🛰️
colorFrom: blue
colorTo: cyan
sdk: docker
app_port: 7860
pinned: false
---

# 🛰️ AERION | SENTINEL-AI
### Next-Gen Autonomous Multi-Sensor Border Surveillance & Intrusion Intercept System
**Smart India Hackathon 2026 Prototype — Edge Computing & Defense Perimeter Intelligence**

<div align="center">

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109%2B-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![YOLOv8](https://img.shields.io/badge/YOLOv8-Ultralytics-FF6B6B?logo=yolo&logoColor=white)](https://docs.ultralytics.com)
[![PyTorch](https://img.shields.io/badge/PyTorch-GPU%20Accelerated-EE4C2C?logo=pytorch&logoColor=white)](https://pytorch.org)
[![OpenCV](https://img.shields.io/badge/OpenCV-Computer%20Vision-5C3EE8?logo=opencv&logoColor=white)](https://opencv.org)
[![ESP32](https://img.shields.io/badge/Hardware-ESP32%20%2B%20LD2450%20mmWave-E7352C?logo=espressif&logoColor=white)](https://www.espressif.com)
[![Radar](https://img.shields.io/badge/Radar-24GHz%20FMCW-00E5FF)](#-hardware-architecture--bill-of-materials-bom)
[![WebSocket](https://img.shields.io/badge/Streaming-Zero--Latency%20WebSocket-4CAF50)](backend/websocket/manager.py)
[![Tests](https://img.shields.io/badge/Test%20Suite-72%2F72%20Passed-brightgreen)](tests/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**[Key Features](#-key-capabilities--innovations) • [System Architecture](#-system-architecture) • [Hardware & BOM](#-hardware-architecture--bill-of-materials-bom) • [Quick Start](#-quick-start-guide) • [SIH Demo Guide](#-3-minute-live-hackathon-demonstration-script) • [API Reference](#-rest-api--websocket-reference)**

</div>

---

## 📌 Executive Summary

Traditional border security infrastructures rely almost exclusively on optical CCTV systems. In real-world border environments, optical sensors are severely compromised by **dense fog, zero-light nights, sandstorms, smoke, and physical tampering**, while operator fatigue is exacerbated by **up to 95% false alarm rates** caused by wind-blown vegetation and wildlife.

**AERION (SENTINEL-AI)** introduces an operational paradigm shift:
$$\mathbf{RADAR\text{-}FIRST\ DETECTION} \longrightarrow \mathbf{CAMERA\ CONFIRMATION} \longrightarrow \mathbf{YOLOv8\ TRACKING} \longrightarrow \mathbf{ZONE\ ANALYSIS} \longrightarrow \mathbf{FORENSIC\ BUFFER} \longrightarrow \mathbf{AUTONOMOUS\ UAV\ INTERCEPT}$$

By leveraging **24GHz FMCW mmWave radar** as an always-on, weather-independent early warning trigger, AERION maintains continuous situational awareness regardless of lighting or atmospheric conditions. When an optical camera is blinded, obscured, or drops offline, AERION automatically identifies the **surveillance gap** and scrambles an **autonomous reconnaissance UAV** equipped with FLIR thermal optics to intercept and confirm the target.

---

## 🖥️ Command Center HUD Showcase

<div align="center">

### 1. Tactical Command Center HUD (Primary Dashboard)
*Real-time multi-camera tactical annotations, live health telemetry, threat counters, and instant SIH demo triggers.*
![Tactical Command Center HUD](dashboard_screen.png)

---

### 2. Top-Down 2D Tactical Radar Sweep Display
*High-precision 24GHz FMCW mmWave polar radar canvas showing azimuth sweep, velocity vectors, and zone boundaries.*
![Top-Down Radar Sweep Display](radar_sweep_screen.png)

---

### 3. Autonomous UAV Reconnaissance HUD & Waypoint Intercept
*Aerial reconnaissance station featuring simulated GPS waypoint navigation, gimbal FLIR optical/thermal reticle, and auto-dispatch.*
![UAV Reconnaissance HUD](tab_uav_screen.png)

---

### 4. Dynamic Polygonal Surveillance Sectors & Breach State Machine
*Configurable polygonal perimeter zones (Normal, Warning Approach, Restricted Fence) with Ray-Casting point-in-polygon logic.*
![Dynamic Polygonal Surveillance Sectors](zones_screen.png)

---

### 5. Forensic Security Events & Pre-Incident Rolling Video Timeline
*Tamper-evident incident registry with pre-breach rolling MP4 buffer evidence, severity scoring, and 1-click forensic review.*
![Forensic Security Events & Video Timeline](tab_events_screen.png)

</div>

---

## ⚡ Key Capabilities & Innovations

### 📡 1. All-Weather 24GHz mmWave Radar Tracking
- Powered by the **Hi-Link LD2450 24GHz FMCW radar module** interfaced via high-speed UART (`256,000 baud`) to an **ESP32 IoT Node**.
- Transmits real-time micro-Doppler Cartesian coordinates $(X, Y)$ and radial velocity vectors at $10\text{ Hz}$.
- Penetrates total darkness, torrential rain, heavy smog, and sandstorms without losing track.

### 🎯 2. JDL Level 1 & Level 2 Spatial Sensor Fusion
- Employs **Joint Directors of Laboratories (JDL)** fusion principles.
- Transforms radar Cartesian targets into optical camera viewport space $(u, v)$.
- Performs cross-sensor gating: optical detections cross-validated by radar receive an immediate confidence boost, reducing false positives by over **98%**.

### ⚡ 3. Edge-Accelerated AI Object Detection & Tracking
- State-of-the-art **YOLOv8** deep learning model with tactical inference running locally on **NVIDIA RTX GPUs / CUDA**.
- Automatic zero-configuration fallback to CPU with OpenMP threading if GPU is unavailable.
- IoU-based multi-object tactical tracker preserves unique track IDs, velocity estimates, and motion trails across camera viewports.

### 📹 4. 10-Second Pre-Incident Rolling Ring Buffer
- Solves the critical forensic problem of missed pre-incident context.
- Maintains an in-memory rolling frame ring buffer for all active visual streams.
- Upon a restricted zone breach, automatically packages **10 seconds before the breach + duration of incident** into a timestamped, watermarked MP4 evidence file.

### 🛸 5. Surveillance Gap Detection & Autonomous UAV Intercept
- Built-in watchdog monitors optical feed health, heartbeat frequencies, and camera tamper status.
- If a camera drops offline while radar maintains contact, the system triggers `SURVEILLANCE_GAP_DETECTED`.
- Generates an instant dispatch directive for **UAV_01 (Autonomous Drone)** with GPS coordinates to inspect the blind spot via simulated FLIR thermal camera.

### 🪪 6. Edge ANPR & License Plate Intelligence
- Vehicle gating pipeline detects cars, trucks, and motorcycles.
- Applies morphological transforms, edge localization, and OCR character extraction with anti-hallucination syntax filters.

### 🔊 7. Synthesized Tactical Mil-Spec Audio Sirens
- Browser-native tactical alarm synthesizer utilizing the **Web Audio API**.
- Zero external audio file latency; generates phased multi-frequency warble sirens during critical breaches.

### 🛡️ 8. Air-Gapped & Offline-First Edge Deployment
- **100% cloud-independent**: SQLite local storage, on-premise FastAPI service, and local WebSocket broker.
- Strict **14-day automated media retention manager** prevents disk exhaustion and ensures defense data compliance.

---

## 🏗️ System Architecture

```
                                 ┌─────────────────────────────────┐
                                 │   LD2450 24GHz FMCW Radar       │
                                 └────────────────┬────────────────┘
                                                  │ (256,000 bps UART)
                                 ┌────────────────▼────────────────┐
                                 │   ESP32 Microcontroller Node    │
                                 └────────────────┬────────────────┘
                                                  │ (HTTP JSON / LAN)
                                                  ▼
┌───────────────────────────┐    ┌─────────────────────────────────┐    ┌───────────────────────────┐
│ Primary Optical CCTV      │    │  JDL Level 1 & Level 2 Fusion   │    │ Secondary Mobile / IP Cam │
│ (CAM_01 - USB / Integrated)├──►│  Spatial Gating & Projection    │◄───┤ (CAM_02 - RTSP / HTTP)    │
└─────────────┬─────────────┘    └────────────────┬────────────────┘    └─────────────┬─────────────┘
              │                                   │                                   │
              ▼                                   ▼                                   ▼
┌───────────────────────────┐    ┌─────────────────────────────────┐    ┌───────────────────────────┐
│ Local YOLOv8 Edge AI Engine│   │  Polygonal Zone State Machine   │    │ Surveillance Gap Watchdog │
│ (RTX GPU / CPU Fallback)  │    │  (Ray-Casting Algorithm)        │    │ (Camera Blind-Spot Detect)│
└─────────────┬─────────────┘    └────────────────┬────────────────┘    └─────────────┬─────────────┘
              │                                   │                                   │
              └───────────────────┬───────────────┴───────────────────────────────────┘
                                  ▼
                     ┌──────────────────────────┐
                     │ Event Deduplication &    │
                     │ Threat Priority Scoring  │
                     └────────────┬─────────────┘
                                  │
         ┌────────────────────────┼────────────────────────┐
         ▼                        ▼                        ▼
┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│ Pre-Event Buffer │    │ Unified WebSocket│    │ Autonomous UAV   │
│ Watermarked MP4  │    │ Real-Time Feed   │    │ Recon Dispatch   │
│ Forensic Storage │    │ (HUD / Canvas)   │    │ (FLIR Waypoints) │
└──────────────────┘    └──────────────────┘    └──────────────────┘
```

---

## 🛠️ Hardware Architecture & Bill of Materials (BOM)

A key highlight of AERION is its **ultra-low cost-to-performance ratio**. The complete functional physical prototype was assembled for **under ₹1,800 (~$22 USD)**:

| System Component | Prototype Hardware Used | Scale-Up Military Equivalent (BSF / Armed Forces) | Prototype Cost (INR) |
|:---|:---|:---|:---:|
| **Radar Node Controller** | ESP32 DevKit V1 (Tensilica Xtensa Dual-Core) | Ruggedized IoT Sensor Gateway (LoRaWAN / 4G LTE) | ₹450 |
| **Primary mmWave Radar** | Hi-Link LD2450 24GHz FMCW Radar Module | S-Band / X-Band Tactical Border Perimeter Radar | ₹1,200 |
| **Wiring & Base Enclosure** | Jumper Wires, Micro-USB Cable & Breadboard | Mil-Spec Sealed Weatherproof Enclosure (IP67) | ₹150 |
| **AI Command Hub** | Laptop (AMD Ryzen / NVIDIA RTX 3050) | NVIDIA Jetson AGX Orin 64GB Industrial Edge Unit | *Existing* |
| **Fixed Optical Surveillance**| USB HD Webcam / Laptop Camera (`CAM_01`) | Long-Range Thermal/Day-Night PTZ Turret | *Existing* |
| **Secondary Patrol Camera** | Smartphone Camera over Wi-Fi (`CAM_02`) | Mobile Border Patrol Vehicle Mounted Camera | *Existing* |
| **Reconnaissance Drone** | SITL Autonomous UAV Simulation (`UAV_01`) | Mil-Spec Autonomous Quadcopter / VTOL UAV with FLIR | *Software* |
| **TOTAL** | **Full Multi-Sensor Edge Prototype** | | **₹1,800 (~$22 USD)** |

---

## 🚀 Quick Start Guide

### Prerequisites
- **OS:** Windows 10/11 64-bit or Linux (Ubuntu 20.04+)
- **Python:** Version 3.10 to 3.14 (AMD64)
- **GPU (Optional):** NVIDIA GeForce GTX/RTX for CUDA acceleration (CPU auto-fallback supported)

### 1. Clone & Install Dependencies
```bash
# Clone the repository
git clone https://github.com/KeerthiNarayanan33/AERION.git
cd AERION

# Install Python requirements
python -m pip install -r requirements.txt
```

### 2. Configure Environment (`.env`)
A sample configuration is pre-configured in `.env`:
```ini
SYSTEM_MODE=SIMULATED        # Options: SIMULATED (no external hardware needed) or REAL
CAMERA_DEFAULT_INDEX=0       # Local webcam index
AI_INFERENCE_FPS=15
DETECTION_CONFIDENCE=0.50
RADAR_ENABLED=true
```

### 3. Launch the Surveillance Command Center
You can double-click **`start_system.bat`** or run via command line:
```bash
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

Open your browser and navigate to:
👉 **`http://localhost:8000`**

---

## 🎮 Dual Operational Modes

| Feature | Simulation Mode (`SYSTEM_MODE=SIMULATED`) | Real Mode (`SYSTEM_MODE=REAL`) |
|:---|:---|:---|
| **Purpose** | **Instant Hackathon Demonstration** without needing external radar modules or test tracks | **Field Deployment** with live physical sensors and cameras |
| **Radar Feed** | Synthetic targets following realistic trajectories across sectors with Doppler velocity | Real-time binary/JSON packets ingested from ESP32 + LD2450 |
| **Optical Video** | Local webcam or synthetic test pattern stream | Live USB CCTV (`CAM_01`) + Smartphone RTSP (`CAM_02`) |
| **Hardware Reqd** | Standard laptop only | Laptop + ESP32 + LD2450 Radar + Webcam |
| **Toggle** | Click the **SIMULATED / REAL** mode pill in the top HUD header at any time |

---

## 🎯 3-Minute Live Hackathon Demonstration Script

For jury evaluation and live presentations, AERION includes a built-in **SIH 2026 Demo Suite** accessible directly from the top HUD toolbar:

```
[ SIH 2026 DEMO SUITE ] ─► [ 1. PATROL ]  [ 2. BORDER BREACH ]  [ 3. SENSOR FUSION ]  [ 4. CAM FAILURE ]  [ 5. UAV RECON ]  [ RESET ]
```

### ⏱️ Minute 1: The Unified HUD & Radar Sweep
1. **Open Dashboard (Tab 1):** Point out the live video feed with tactical bounding boxes, track IDs, motion vectors, and real-time FPS/latency telemetry.
2. **Open Radar Sweep (Tab 3):** Show the animated 2D top-down polar radar canvas. Demonstrate the $120^\circ$ FOV azimuth sweep and dynamic target telemetry table showing $(X, Y, R, \theta, V)$.

### ⏱️ Minute 2: Border Breach & Forensic Video Evidence
1. **Trigger "2. BORDER BREACH":**
   - An intruder crosses from Outer Patrol (`ZONE_A`) into Warning Approach (`ZONE_B`) and penetrates Restricted Fence (`ZONE_C`).
   - The tactical audio synthesizer triggers a military-grade warble siren.
   - The alert level escalates to **CRITICAL**.
2. **Review Forensic Evidence (Tab 5):**
   - Click the alert card's **REVIEW** button.
   - Show the watermarked MP4 video clip generated by the **rolling frame ring buffer**, demonstrating how AERION preserved the crucial moments *before* the intrusion took place.

### ⏱️ Minute 3: Surveillance Gap & Autonomous UAV Intercept
1. **Trigger "4. CAM FAILURE & GAP":**
   - Optical camera `CAM_02` drops offline (simulating sabotage or power failure).
   - Radar maintains track of the intruder in the blind sector.
   - System automatically detects the breach without optical coverage and triggers `SURVEILLANCE_GAP_DETECTED`.
2. **Trigger "5. UAV RECON" (Tab 6):**
   - UAV `UAV_01` is authorized and scrambled immediately.
   - Drone ascends to altitude, navigates GPS waypoints to `ZONE_C`, and locks onto the intruder with its FLIR thermal reticle.
3. **Click "RESET":**
   - Recalls drone to dock, flushes tracks, and restores nominal baseline state.

---

## 📡 REST API & WebSocket Reference

### Core Endpoints
| Method | Endpoint | Description |
|:---|:---|:---|
| `GET` | `/api/system/health` | Subsystem status (FastAPI, OpenCV, YOLO, Radar, CPU/GPU, DB) |
| `GET` | `/api/system/metrics` | Real-time performance metrics (FPS, Latency, Queue Depth) |
| `GET` | `/api/cameras` | Registry of visual sensors, status, and resolution |
| `GET` | `/api/cameras/{id}/stream` | Low-latency MJPEG video stream with tactical overlays |
| `POST`| `/api/radar/ingest` | High-frequency telemetry ingestion from ESP32 LD2450 node |
| `GET` | `/api/radar/targets` | List of currently tracked radar targets |
| `GET` | `/api/zones` | Geometric polygonal boundaries and threat classification policies |
| `GET` | `/api/events` | Historical log of security events with filterable parameters |
| `GET` | `/api/events/{id}/video` | Direct streaming of forensic watermarked MP4 incident clip |
| `POST`| `/api/uav/verification-request`| Dispatches autonomous UAV reconnaissance mission |
| `WS`  | `/ws/live` | Bidirectional WebSocket broadcasting telemetry, blips, and alerts |

---

## 📂 Repository Structure

```
AERION/
├── backend/                        # FastAPI High-Performance Backend
│   ├── ai/                         # YOLOv8 Detector, Tracker & Spatial Fusion
│   │   ├── detector.py             # Inference manager with GPU/CPU auto-switching
│   │   ├── tracker.py              # Tactical IoU object tracking & velocity vectors
│   │   └── annotator.py            # Mil-spec bounding box & vector renderer
│   ├── api/                        # REST API Router Endpoints
│   │   ├── camera_routes.py        # Video acquisition & MJPEG streams
│   │   ├── radar_routes.py         # Radar packet ingestion & coordinate mapping
│   │   ├── system_routes.py        # System health, telemetry & metrics
│   │   └── uav_routes.py           # UAV mission directives & telemetry
│   ├── camera/                     # Video capture abstraction (Webcam / IP / RTSP)
│   ├── database/                   # SQLite database & retention policies
│   ├── radar/                      # LD2450 mmWave driver & ESP32 parser
│   ├── uav/                        # UAV mission state machine & FLIR proxy
│   ├── websocket/                  # High-frequency WebSocket broadcast broker
│   ├── zones/                      # Polygonal Ray-Casting zone state engine
│   ├── config.py                   # Pydantic system settings & environment loader
│   └── main.py                     # Application entry point & lifecycle hooks
├── frontend/                       # Tactical Cyber-Command Dashboard (Vanilla Web Stack)
│   ├── css/                        # Design tokens, cybernetic theme & HUD layout
│   ├── js/                         # Modular client scripts (Radar canvas, UAV, Events)
│   │   ├── radar_view.js           # 2D top-down polar radar canvas renderer
│   │   ├── uav_view.js             # Drone telemetry HUD & waypoint map
│   │   ├── audio_synth.js          # Web Audio API military siren synthesizer
│   │   └── demo_scenarios.js       # 1-click SIH presentation scenario runner
│   └── index.html                  # Single-page multi-tab command center
├── esp32/                          # ESP32 C++ / Arduino Firmware
│   └── esp32_ld2450_node.ino       # UART radar reader & Wi-Fi HTTP transmitter
├── storage/                        # Persistent media directory (14-day auto-retention)
│   ├── clips/                      # Forensic MP4 incident video recordings
│   └── snapshots/                  # High-res forensic JPEG breach captures
├── tests/                          # Automated Pytest & Headed Browser Test Suite
├── start_system.bat                # 1-Click launcher for Windows
├── requirements.txt                # Python dependencies
└── README.md                       # Master Documentation
```

---

## 🧪 Verification & Test Suite

AERION includes a rigorous automated test suite covering all critical subsystems:
- **72 Automated Unit & Integration Tests**: Validating YOLO inference fallback, ring buffer serialization, Ray-Casting zone state transitions, radar packet parsing, and WebSocket connection recovery.
- **Full Headed Browser Suite**: Automated verification of all 12 command center tabs, audio synthesizer triggers, canvas resizing, and modal workflows.

To run the automated test suite:
```bash
# Run backend pytest suite
pytest tests/ -v

# Run live system health check
python tests/test_api_health.py
```

---

## 👥 Smart India Hackathon 2026 Team

- **Project:** AERION (SENTINEL-AI)
- **Problem Statement:** Multi-Sensor Border Surveillance, Intrusion Detection & Threat Intercept
- **Target Deployment:** Border Security Force (BSF), Defense Bases & Remote Perimeter Installations
- **Repository:** [KeerthiNarayanan33/AERION](https://github.com/KeerthiNarayanan33/AERION)

---

## 📄 License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.