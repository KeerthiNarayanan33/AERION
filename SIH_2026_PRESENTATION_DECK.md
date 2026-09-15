# SENTINEL-AI: Multi-Sensor Border Surveillance & Intrusion Detection System
## Smart India Hackathon 2026 — Master Presentation Deck & Evaluator Guide

---

## 1. Executive Summary & Problem Statement

### The Operational Challenge
Traditional border surveillance infrastructures rely almost exclusively on optical CCTV cameras. This creates severe operational vulnerabilities:
- **Environmental Vulnerability:** Dense fog, sandstorms, zero-light conditions, and smoke blind optical sensors.
- **Physical & Technical Occlusion:** Tampering, lens obstruction, and camera power/network drops create unmonitored blind spots.
- **Operator Fatigue & False Alarms:** 95%+ of perimeter alerts in traditional systems are caused by wildlife, swaying vegetation, or camera noise.

### The Sentinel-AI Innovation
Sentinel-AI introduces a **radar-first, sensor-resilient edge architecture**:
$$\text{RADAR-FIRST DETECTION} \to \text{CAMERA CONFIRMATION} \to \text{YOLO TRACKING} \to \text{ZONE ANALYSIS} \to \text{EVENT DEDUPLICATION} \to \text{ROLLING BUFFER FORENSICS} \to \text{SURVEILLANCE GAP DETECTION} \to \text{AUTONOMOUS UAV VERIFICATION}$$

1. **Non-Visual Early Warning:** 24GHz FMCW mmWave radar detects movement up to 8 meters (scalable to kilometers) through total darkness and weather.
2. **Multi-Sensor Fusion (JDL Level 1 & 2):** Projects radar Cartesian space into camera viewport coordinates, cross-validating targets and boosting detection confidence.
3. **Automated Evidence Compilation:** Rolling frame buffer captures 10 seconds of video *before* a breach occurs, automatically generating court-admissible, watermarked MP4 forensic clips.
4. **Surveillance Gap & Blind Spot Resilience:** If an optical camera fails or drops offline, the system detects unconfirmed radar intrusions and automatically recommends an autonomous UAV aerial reconnaissance mission.

---

## 2. Hardware Architecture & Prototype Mapping

| Prototype Component | Hardware Device Used | Scale-Up Equivalent (BSF / Armed Forces) |
|:---|:---|:---|
| **AI Command Hub** | Laptop (AMD Ryzen / NVIDIA RTX 3050) | Mil-Spec Edge Compute (NVIDIA Jetson AGX Orin) |
| **Primary mmWave Radar** | Hi-Link LD2450 24GHz FMCW Radar Module | S-Band / X-Band Tactical Perimeter Radar |
| **Radar Ingestion Node** | ESP32-WROOM-32 DevKit (256,000 baud UART) | Ruggedized IoT Sensor Gateway (LoRaWAN / 4G) |
| **Fixed Optical CCTV** | USB / Integrated HD Camera (`CAM_01`) | Long-Range Day/Night Optical & IR PTZ Camera |
| **Mobile Perimeter Camera** | Smartphone Camera over HTTP/RTSP (`CAM_02`) | Mobile Border Patrol Vehicle Mounted Camera |
| **Reconnaissance UAV** | Software-in-the-Loop Flight Controller (`UAV_01`) | Autonomous Quadcopter / VTOL Drone with FLIR Camera |

---

## 3. End-to-End Technical Pipeline

```
               ┌───────────────────────┐
               │ LD2450 mmWave Radar   │
               └───────────┬───────────┘
                           │ (UART 256k baud)
               ┌───────────▼───────────┐
               │ ESP32 Wi-Fi Node      │
               └───────────┬───────────┘
                           │ (HTTP JSON 5Hz)
                           ▼
               ┌───────────────────────┐
┌─────────────►│ JDL Level 1 & 2       │◄─────────────┐
│              │ Multi-Sensor Fusion   │              │
│              └───────────┬───────────┘              │
│                          │                          │
│                          ▼                          │
│              ┌───────────────────────┐              │
│              │ Polygonal Zone Engine │              │
│              │ (Ray-Casting Algorithm)              │
│              └───────────┬───────────┘              │
│                          │                          │
│                          ▼                          │
│              ┌───────────────────────┐              │
│              │ Deduplicating Event   │              │
│              │ Engine & Scoring      │              │
│              └───────────┬───────────┘              │
│                          │                          │
│                          ▼                          │
│              ┌───────────────────────┐              │
│              │ Rolling Ring Buffer   │              │
│              │ Forensic MP4 Compiler │              │
│              └───────────────────────┘              │
│                                                     │
│ (Real-Time Video 30 FPS)                            │ (RTSP Video Stream)
┌──────────────┴────────────┐             ┌───────────┴───────────────┐
│ Fixed Camera (CAM_01)     │             │ Mobile IP Camera (CAM_02) │
│ YOLOv8n Object Detection  │             │ Perimeter Secondary Feed  │
└───────────────────────────┘             └───────────────────────────┘
```

---

## 4. 3-Minute Live Hackathon Demonstration Script

### Minute 1: Command HUD & Optical/Radar Overview
1. **Show Command Dashboard (Tab 1):**
   - Point out live camera stream (`CAM_01`), real-time YOLOv8 object detection with tactical bounding boxes, track IDs, and velocity trails.
   - Point out real-time FPS counter, inference latency, and system health status.
2. **Show Radar Sweep (Tab 3):**
   - Switch to the top-down 2D radar sweep console. Show the animated sweep beam and target table with Cartesian $(X,Y)$ and polar $(R,\theta)$ coordinates.

### Minute 2: Border Breach & Forensic Video Evidence
1. **Click "2. BORDER BREACH" in Demo Toolbar:**
   - Synthetic target moves from radar detection $\to$ camera tracking $\to$ crosses restricted border fence (`ZONE_C`).
   - Acoustic alarm sounds through the tactical audio synthesizer.
   - Priority escalates immediately to **CRITICAL**.
2. **Review Forensic Video:**
   - Click the alert card's **REVIEW** button.
   - Show the watermarked MP4 video clip generated by the rolling frame buffer, demonstrating how the system captures the moments *before* the breach occurred.

### Minute 3: Surveillance Gap Anomaly & Autonomous UAV Dispatch
1. **Click "4. CAM FAILURE & GAP":**
   - Camera `CAM_02` drops offline. Radar maintains contact in the blind sector.
   - System automatically detects the surveillance gap and flags `SURVEILLANCE_GAP_DETECTED`.
2. **Click "5. UAV RECON" (or switch to Tab 6):**
   - System authorizes and launches `UAV_01`.
   - Watch the drone climb to altitude, follow GPS waypoints to `ZONE_C`, and lock onto the target with the FLIR HUD reticle.
3. **Click "RESET"**:
   - System flushes synthetic tracks, recalls the drone to base, and returns to baseline state.

---

## 5. Key Competitive Differentiators

| Feature | Conventional CCTV | Sentinel-AI Prototype |
|:---|:---|:---|
| **Zero-Light / Fog Operation** | ❌ Fails completely | ✅ 24GHz mmWave radar penetration |
| **Camera Tampering / Blind Spots** | ❌ Completely unmonitored | ✅ Surveillance gap detection + UAV dispatch |
| **Pre-Incident Video Context** | ❌ Lost unless 24/7 continuous recording | ✅ 10-second rolling ring buffer |
| **Vehicle Intelligence** | ❌ Manual review | ✅ Automated ANPR with anti-hallucination fallback |
| **Acoustic Tactical Alerts** | ❌ Silent or simple beeps | ✅ Web Audio API synthesized military sirens |
| **Data Minimization & Privacy** | ❌ Indiscriminate recording | ✅ 14-day retention + Privacy blur mode |
| **Edge Hardware Footprint** | ❌ Heavy server clusters | ✅ Standard laptop + ESP32 + $15 mmWave radar |

---

## 6. Bill of Materials (BOM)

| Item | Component Description | Cost (INR) |
|:---|:---|:---|
| 1 | ESP32 DevKit V1 Microcontroller | ₹450 |
| 2 | Hi-Link LD2450 24GHz mmWave Radar Module | ₹1,200 |
| 3 | Jumper Wires & Breadboard / Enclosure | ₹150 |
| 4 | USB Webcam / Laptop Camera | Existing |
| 5 | Smartphone (for auxiliary IP stream) | Existing |
| **TOTAL** | **Hardware Prototype Total Cost** | **₹1,800 (~$22 USD)** |

---

## 7. Anticipated Technical Questions & Answers (Judge Q&A)

**Q1: How does the system handle high wind or heavy rain?**
> *A:* The LD2450 24GHz mmWave radar operates on FMCW micro-Doppler radar principles, ignoring stationary swaying foliage and small raindrops. Additionally, the multi-sensor fusion engine requires spatial correlation between radar targets and visual tracks before escalating alerts.

**Q2: What happens if the laptop loses internet connectivity?**
> *A:* Sentinel-AI is architected with an **offline-first design** (Section 50). Local YOLOv8 inference runs on the CPU/RTX GPU, SQLite database runs locally, and WebSockets operate over the local LAN. No cloud APIs or external internet access are required.

**Q3: How is data privacy handled?**
> *A:* In compliance with Section 46 (Data Minimization), Sentinel-AI only retains footage associated with confirmed security incidents, automatically pruning unflagged buffer frames and enforcing a strict 14-day rolling retention policy. Furthermore, an optional Privacy Blurring mode applies Gaussian redaction to non-threatening civilian faces.
