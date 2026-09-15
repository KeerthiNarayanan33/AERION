# SENTINEL-AI / AERION — Complete System Tech Flow & Architecture Guide
**Smart India Hackathon 2026: Multi-Sensor Border Surveillance & Autonomous Intrusion Response System**

---

## 1. Executive Summary & Core Philosophy

**SENTINEL-AI (AERION)** is an enterprise-grade military-spec border surveillance and perimeter defense system designed to operate in adverse weather, complete darkness, and remote terrain.

### The Core Problem It Solves
Traditional surveillance relying solely on optical cameras fails under:
- **Zero-visibility conditions**: Fog, dust storms, smoke, dense foliage, and complete darkness.
- **Human operator fatigue**: Missed intrusions due to monitoring dozens of screens.
- **Slow response times**: Manual alarm verification and dispatch can take minutes, allowing intruders to escape.

### The Solution: Radar-First Multi-Sensor Fusion
SENTINEL-AI flips the paradigm from "camera-first" to **"radar-first multi-sensor fusion"**:

```
[ mmWave Radar (LD2450) ] ──┐
[ PIR Ground Motion ]     ──┼──► [ Sensor Fusion (EKF) ] ──► [ AI Vision (YOLOv8 + YuNet) ]
[ Optical Cameras ]       ──┘            │                               │
                                         ▼                               ▼
                             [ Polygonal Zone Engine ] ◄── [ Identity & Posture Check ]
                                         │
                                         ▼
                               [ Threat Evaluation ]
                                  ├──► [ Event Deduplication & SQLite DB ]
                                  ├──► [ Tamper-Proof Cryptographic Video Vault ]
                                  ├──► [ Automated Deterrence (Sirens / Strobes) ]
                                  ├──► [ Autonomous Drone (UAV_01) Aerial Recon ]
                                  └──► [ Live Tactical HUD (WebSockets @ 1-2 Hz) ]
```

---

## 2. End-to-End Technical Flow: The "Life of an Intrusion"

Here is the exact step-by-step lifecycle of an intrusion event across the entire stack:

### Step 1: Physical Detection (Perimeter Contact)
1. An intruder approaches the border fence 7 meters away in thick fog.
2. The **Hi-Link LD2450 24GHz FMCW mmWave radar** emits radar chirps. The micro-Doppler reflections hit the intruder's body and bounce back.
3. The radar measures:
   - **X (Lateral distance)**: e.g., `-1.8m` (1.8 meters to the left).
   - **Y (Depth/Forward distance)**: e.g., `6.2m`.
   - **Speed (Radial velocity)**: e.g., `-1.2 m/s` (moving toward the sensor).

### Step 2: Edge Sensor Ingestion
- **Wi-Fi Ingestion**: The **ESP32 microcontroller** reads UART frames from the LD2450 at `256,000 bps`, packages them into a JSON payload, and HTTP POSTs to:
  `POST http://<server-ip>:8000/api/radar/ingest`
- **Direct Serial/Simulation Ingestion**: Alternatively, the Python backend reads directly via `pyserial` on `COM3`, or generates realistic kinematic targets in `SIMULATED` mode.

### Step 3: Sensor Fusion & Cross-Confirmation
- The **Sensor Fusion Engine (`ekf_tracker.py` & `fusion_engine.py`)** receives the radar coordinates.
- It runs an **Extended Kalman Filter (EKF)** to smooth the noisy radar measurements and predict the target's trajectory.
- **Slew-to-Cue (`slew_director.py`)**: The system calculates the exact azimuth and pitch needed for the nearest optical camera (`CAM_01` or `CAM_02`) to look at the target.

### Step 4: Computer Vision & AI Inference
- The **Camera Manager (`camera_manager.py`)** captures frames from:
  - `CAM_01`: Fixed USB / integrated webcam (`webcam.py`).
  - `CAM_02`: Mobile smartphone camera (`mobile.html` streaming over HTTPS/WebRTC port `8443`).
- The **Inference Manager (`inference_manager.py`)** pushes the frame through:
  1. **YOLOv8 Nano (`yolov8n.pt`)**: Detects bounding boxes for `person`, `car`, `truck`, `dog`, etc.
  2. **Tactical Tracker (`tracker.py`)**: Assigns a persistent `Track ID` using IoU (Intersection over Union) + Centroid distance, generating a velocity vector trail.
  3. **YuNet Face Detector (`face_detection_yunet_2023mar.onnx`)**: Crops the person's head region and detects facial landmarks.
  4. **SFace Face Recognizer (`face_recognition_sface_2021dec.onnx`)**: Extracts a 128-dimensional biometric embedding vector and compares it against the authorized database (`authorized_persons`) using **Cosine Similarity**.
  5. **Posture Classifier (`posture_classifier.py`)**: Analyzes bounding box aspect ratio and velocity to classify movement as `STANDING`, `CROUCHING`, `CRAWLING`, or `PRONE`.

### Step 5: Polygonal Geofence & Zone Validation
- **Zone Engine (`zone_manager.py`)**: Uses the **Ray-Casting Point-in-Polygon** algorithm to determine if the target's coordinates fall within:
  - `ZONE_A`: Outer Patrol (Safe / Public)
  - `ZONE_B`: Warning Approach (Medium Security)
  - `ZONE_C`: Restricted Perimeter Fence (Critical / No-Entry)
- If an unidentified person enters `ZONE_C`, or an authorized person enters a zone not listed in their `allowed_zones`, a violation flag is raised.

### Step 6: Event Generation, Deduplication & Recording
- **Event Engine (`event_engine.py`)**:
  - Checks **Alert Rules (`alert_rules`)** and computes a threat priority score (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`).
  - Runs **Hysteresis Deduplication (`deduplicator.py`)** with a 10-second cooldown window so the operator is not spammed with 30 alerts per second for the same target.
  - Generates an incident ID (e.g., `INC_20260915_041200_A9B1`).
  - Logs the event to SQLite (`surveillance.db`).
- **Evidence Vault (`evidence_recorder.py` & `evidence_vault.py`)**:
  - Pulls pre-event frames from the **circular ring buffer (`FrameBuffer`)** (last 10 seconds).
  - Records the live event + 15 seconds post-event.
  - Stitches them into a watermarked MP4 video clip and saves a high-res JPG snapshot.
  - Computes a **SHA-256 cryptographic hash** stored in the database for tamper-proof forensic auditability.

### Step 7: Autonomous UAV Dispatch & Deterrence
- **Counter-UAS / Drone Controller (`drone_provider.py` & `uav_controller.py`)**:
  - If the radar target has no optical confirmation (e.g., camera blind spot, smoke, fence blockage), the system marks the contact as `RADAR_UNVERIFIED`.
  - The system automatically triggers **DRONE-001 (UAV_01)** to launch from standby, translate target local coordinates into GPS Latitude/Longitude (`geospatial_engine`), and fly to the waypoint to provide an aerial verification feed.
- **Deterrence Matrix (`deterrence.py`)**: Activates automated deterrent playbooks (strobe illumination, audio acoustic siren, high-intensity spotlight).

### Step 8: Real-Time HUD Broadcast
- The **WebSocket Manager (`ws_manager.py`)** broadcasts the updated state over `/ws/live` to all connected browser dashboards.
- The UI instantly renders:
  - The target on the **2D Polar Radar Canvas** with animated sweep.
  - Bounding boxes and identity tags on the **Live Video Quad-Grid**.
  - A flashing red card with siren sound on the **Alert Feed**.
  - Drone flight path on the **GIS Leaflet Tactical Map**.

---

## 3. AI Models & Computer Vision Architecture

The AI subsystem lives in `backend/ai/` and operates as an asynchronous, decoupled pipeline so camera ingestion is never blocked by GPU/CPU inference.

```
Incoming Video Frame (1280x720)
       │
       ▼
[ YOLOv8 Nano (yolov8n.pt) ] ──► Bounding Boxes: [x1, y1, x2, y2, conf, class_id]
       │
       ▼
[ Tactical Tracker (tracker.py) ] ──► Persistent Track IDs & History Trails
       │
       ├──────────────────────────────────────────┬─────────────────────────────┐
       ▼                                          ▼                             ▼
[ Crop Person Upper Body ]            [ Bounding Box Aspect Ratio ]    [ Vehicle Classes ]
       │                                          │                             │
       ▼                                          ▼                             ▼
[ YuNet (OpenCV Face Detector) ]      [ Posture Classifier ]            [ ANPR Engine ]
       │                               - Standing                       - Morphological Filter
       ▼                               - Crouching                      - Contour Plate Crop
[ SFace (OpenCV 128D Embeddings) ]     - Crawling                       - OCR Number Read
       │                               - Prone
       ▼
[ Cosine Similarity vs Gallery ]
  - If similarity >= 0.38: Match (e.g., "Keerthi (STAFF)")
  - If similarity < 0.38: "UNKNOWN / INTRUDER"
```

### Detailed Breakdown of AI Models

| Model / Component | Artifact / File | Role & Technique | Inference Speed |
|:---|:---|:---|:---|
| **YOLOv8 Nano** | `yolov8n.pt` | Primary multi-class object detection (person, car, truck, bicycle, dog). Runs via Ultralytics with auto-fallback: PyTorch CUDA GPU (RTX 3050) or OpenVINO/CPU. | ~8–15 ms (GPU)<br>~35–50 ms (CPU) |
| **YuNet Face Detector** | `models/face_detection_yunet_2023mar.onnx` | High-speed edge face detector built into OpenCV DNN (`cv2.FaceDetectorYN`). Detects 5 facial landmarks (eyes, nose, mouth corners) even in partial occlusion or angles. | ~4–7 ms |
| **SFace Face Recognizer** | `models/face_recognition_sface_2021dec.onnx` | Deep biometric feature extractor built into OpenCV DNN (`cv2.FaceRecognizerSF`). Generates 128-dimensional normalized embedding vectors. Match score calculated via Cosine Similarity (`cv2.FaceRecognizerSF.match`). | ~6–10 ms |
| **Tactical Multi-Object Tracker** | `backend/ai/tracker.py` | Associates bounding boxes across frames using Spatial IoU, Euclidean Centroid Distance, and Velocity Vector smoothing. Eliminates ID switching. | < 1 ms |
| **Posture Classifier** | `backend/ai/posture_classifier.py` | Computes bounding box aspect ratio ($W/H$), centroid height relative to ground line, and velocity to detect stealth tactical maneuvers (crawling under fence wires). | < 0.5 ms |
| **ANPR Engine** | `backend/ai/anpr_engine.py` | Gates vehicle bounding boxes, applies bilateral filtering, adaptive thresholding, Sobel edge detection, and contour extraction to read license plates. | ~15–20 ms |
| **Person Re-ID Handover** | `backend/ai/reid_handover.py` | Color histogram + spatial feature fingerprinting to track an individual transitioning from `CAM_01` (Fixed) to `CAM_02` (Mobile) to `UAV_01` (Drone). | ~2 ms |

---

## 4. Hardware & Sensor Ecosystem

| Hardware Component | Model / Spec | Connection Protocol | Physical Role |
|:---|:---|:---|:---|
| **Primary mmWave Radar** | Hi-Link LD2450 (24GHz FMCW) | UART @ 256,000 bps or Wi-Fi (via ESP32) | 120° Azimuth FOV, up to 8m distance. Detects X/Y coordinates and speed of up to 3 simultaneous targets without any camera vision. |
| **Microcontroller Node** | ESP32-WROOM-32 | 802.11 b/g/n Wi-Fi & Hardware Serial | Sits next to radar, parses binary packets, transmits JSON over Wi-Fi to FastAPI backend. |
| **Fixed CCTV Camera (CAM_01)** | Integrated / USB HD Webcam | Direct DirectShow / OpenCV (`cv2.VideoCapture(0)`) | Primary optical confirmation feed covering entry gate / main sector. |
| **Mobile Perimeter Camera (CAM_02)** | Any Android / iPhone Smartphone | HTTPS / WebRTC on Port 8443 (`/mobile.html`) or RTSP/MJPEG | Acts as a tactical deployed sentry camera transmitting live video directly over Wi-Fi. |
| **Recon Drone (UAV_01)** | Quadcopter (DRONE-001) | MAVLink / Simulated Telemetry Flight State Machine | Dispatched for blind-spot verification, loitering perimeter surveillance, and aerial tracking. |
| **PIR Sensor** | Passive Infrared Sensor | USB-UART COM port or Simulated GPIO | Motion confirmation trigger in restricted Zone B. |
| **GPS Module** | NEO-6M / NMEA Serial | COM4 @ 9600 bps or Simulated GPS Engine | Real-time ground station georeferencing and drone positioning. |

---

## 5. Backend Architecture & Engine Modules

The backend is built with **FastAPI**, running on **Python 3.10+** (tested on 3.14), structured into modular, decoupled micro-engines:

```
backend/
├── main.py                    # Entry point: Lifespan manager, background tasks, dual HTTP/HTTPS servers
├── config.py                  # Pydantic Settings (loads from .env with fallback defaults)
├── logger.py                  # Centralized structured logger
│
├── ai/                        # AI & Vision Processing Subsystem
│   ├── inference_manager.py   # Thread pool coordinator running YOLO & Tracker per camera
│   ├── yolo_detector.py       # YOLOv8 wrapper (CUDA GPU / CPU auto-selection)
│   ├── identity_service.py    # YuNet + SFace face recognition & gallery matching
│   ├── tracker.py             # IoU centroid tactical tracker
│   ├── posture_classifier.py  # Aspect ratio & posture analysis (crawl, crouch, stand)
│   ├── anpr_engine.py         # License plate detection & OCR
│   ├── reid_handover.py       # Multi-camera cross-tracking
│   └── annotator.py           # Tactical HUD bounding box & velocity vector overlay renderer
│
├── camera/                    # Video Acquisition Subsystem
│   ├── camera_manager.py      # Master camera registry (CAM_01, CAM_02, UAV_01)
│   ├── webcam.py              # Low-latency threaded OpenCV webcam capture
│   ├── ip_camera.py           # Network/mobile phone RTSP/MJPEG ingestion
│   ├── frame_buffer.py        # Thread-safe circular ring buffer (retains pre-event footage)
│   └── fault_recovery.py      # Sensor watchdog & auto-reconnection circuit breaker
│
├── radar/                     # Radar & RF Subsystem
│   ├── radar_driver.py        # LD2450 mmWave parser (UART binary + ESP32 JSON + optical projection)
│   ├── rf_integrity.py        # RF signal health & anti-jamming detector
│   ├── counter_uas.py         # Drone radar signature detection
│   └── terrain_los.py         # Line-of-sight radar horizon & shadow calculator
│
├── fusion/                    # Sensor Fusion Subsystem
│   ├── fusion_engine.py       # JDL Level 1/2 fusion of radar, camera, and PIR
│   ├── ekf_tracker.py         # Extended Kalman Filter trajectory estimator
│   └── slew_director.py       # Slew-to-cue PTZ camera pointing director
│
├── zones/                     # Geofencing & Spatial Logic
│   └── zone_manager.py        # Ray-casting point-in-polygon & zone transition state machine
│
├── events/                    # Alert & Forensic Storage Subsystem
│   ├── event_engine.py        # Rule evaluator, threat scoring & alert dispatch
│   ├── deduplicator.py        # Sliding-window hysteresis deduplication
│   ├── evidence_recorder.py   # Watermarked MP4 video & snapshot clip generator
│   ├── evidence_vault.py      # SHA-256 tamper-proof forensic hash manager
│   ├── deterrence.py          # Acoustic siren & strobe control manager
│   └── tactical_playbooks.py  # SOP (Standard Operating Procedure) execution matrix
│
├── uav/                       # Drone Recon Subsystem
│   ├── drone_provider.py      # Drone manager (Simulation & live MAVLink flight controller)
│   ├── uav_controller.py      # Verification dispatch workflow engine
│   └── swarm_manager.py       # Multi-UAV swarm coordinator
│
├── geospatial/                # Tactical Mapping & Coordinates
│   ├── coordinates.py         # Local (X, Y) to GPS (Lat, Lon) & MGRS 8-digit converter
│   └── gps_service.py         # Serial NMEA / Simulated GPS driver
│
├── database/                  # Data Persistence (SQLite + SQLAlchemy)
│   ├── database.py            # SQLite connection pool, session maker & schema initializer
│   └── models.py              # ORM models (Cameras, Radar, Zones, Events, Persons, UAV)
│
├── api/                       # REST API Endpoints (36+ modular routers)
│   ├── system_routes.py       # Health checks, CPU/RAM/GPU telemetry, system mode
│   ├── camera_routes.py       # Video streams (/live, /snapshot), camera configurations
│   ├── radar_routes.py        # Radar ingestion (/ingest) and target telemetry
│   ├── event_routes.py        # Security event query, resolve, video playback
│   ├── zone_routes.py         # Polygonal zone definitions & security levels
│   ├── drone_routes.py        # UAV dispatch, waypoint navigation, RTH commands
│   ├── persons_routes.py      # Authorized personnel management & photo enrollment
│   ├── anpr_routes.py         # License plate log query & blacklist checks
│   └── ...                    # Playbooks, Replay, GIS, Mesh, RF integrity routers
│
└── websocket/                 # Real-Time Telemetry
    └── manager.py             # Thread-safe WebSocket connection manager & broadcaster
```

---

## 6. Frontend Command Center (Tactical HUD)

The frontend is a zero-dependency, ultra-fast **Single-Page Application (SPA)** written in pure HTML5, Vanilla CSS, and modular ES6 JavaScript. It delivers a **military-spec dark aesthetic** with glassmorphic cards and tactical green/amber/red accents.

### Directory Structure
```
frontend/
├── index.html                 # Main Surveillance Dashboard (HUD)
├── mobile.html                # Smartphone Camera WebRTC / HTTPS Transmitter
├── css/
│   ├── style.css              # Core typography, dark palette, CSS grid layouts
│   └── components.css         # Glassmorphic cards, radar canvas, video feeds, buttons
└── js/
    ├── app.js                 # Master UI controller, tab router & event bus
    ├── websocket.js           # Auto-reconnecting resilient WebSocket client
    ├── radar_view.js          # 2D Polar canvas renderer (sweep line, blips, velocity vectors)
    ├── alert_feed.js          # Audio-visual alert cards, priority badges, acknowledge buttons
    ├── zone_map.js            # Leaflet GIS Tactical Map (GPS tracks, MGRS grid, zones)
    ├── uav_view.js            # Drone telemetry HUD (Altitude, Battery, Speed, Slew-to-Cue)
    ├── persons_manager.js     # Enrolled personnel management, photo upload & enrollment modal
    ├── metrics.js             # Real-time FPS, latency gauges, and CPU/RAM/GPU telemetry
    └── audio_alert.js         # Web Audio API procedural synthesizer (no external MP3 needed)
```

### Dashboard Tabs & Views
1. **HUD (Main Command Center)**: Real-time 4-camera video grid, 2D polar radar display, live alert stream, and system health status.
2. **Live Cameras Tab**: Full-screen layout with interactive pan, digital zoom, optical/radar cross-confirmation badges, and privacy blur toggles.
3. **Radar Sweep Tab**: Dedicated high-resolution radar canvas with polar range rings (2m, 4m, 6m, 8m), azimuth grid lines (-60° to +60°), and target data tables.
4. **Zones & Geofencing Tab**: Interactive visual polygon editor to draw, resize, and configure security rules for `ZONE_A`, `ZONE_B`, and `ZONE_C`.
5. **UAV Recon Tab**: Live aerial drone video feed, battery indicator, altitude/speed instruments, and manual/autonomous dispatch buttons.
6. **Security Events Tab**: Searchable history of all security incidents, filterable by severity (`CRITICAL`, `HIGH`, `MEDIUM`), with instant snapshot inspection and recorded MP4 playback.
7. **Authorized Persons Tab**: Manage friendly personnel vs watchlist intruders, upload reference photos, view biometric detection statistics, and assign allowed zones.
8. **Timeline Blackbox Replay**: Rewind and replay past surveillance situations frame-by-frame with synchronized radar, camera, and alert states.
9. **System Config & Demo Scenarios**: One-click launcher for SIH evaluation scenarios (e.g., Scenario 1: Normal Patrol, Scenario 2: Blind-spot Perimeter Breach, Scenario 3: Watchlist Match).

---

## 7. Complete API Reference & WebSocket Protocol

### 1. System & Health APIs
- `GET /api/system/health`: Subsystem statuses (Database, Radar, Cameras, AI Engine, UAV, Disk Storage).
- `GET /api/system/metrics`: Hardware metrics (CPU %, RAM %, GPU utilization, FPS, inference latency).
- `GET /api/system/mode`: Current operational mode (`REAL` or `SIMULATED`).
- `POST /api/system/mode`: Switch operational mode dynamically.

### 2. Camera & Video APIs
- `GET /api/cameras`: List all registered cameras, resolutions, FPS, and online status.
- `GET /api/cameras/{camera_id}/stream`: MJPEG live video stream with real-time tactical AI annotations.
- `GET /api/cameras/{camera_id}/snapshot`: High-res JPEG snapshot with bounding boxes.
- `POST /api/cameras/{camera_id}/toggle`: Enable or disable camera source.

### 3. Radar & Ingestion APIs
- `POST /api/radar/ingest`: Ingestion endpoint for ESP32 mmWave radar JSON frames:
  ```json
  {
    "sensor_id": "RADAR_01",
    "targets": [
      { "id": 1, "x": -1.25, "y": 4.50, "speed": -0.85, "resolution": 0.1 }
    ]
  }
  ```
- `GET /api/radar/targets`: List of currently tracked radar targets.
- `GET /api/radar/status`: Connection status, baud rate, and heartbeat timestamp.

### 4. Zone & Geofence APIs
- `GET /api/zones`: List all polygonal zones with vertices and authorization levels.
- `POST /api/zones`: Create or update a polygonal zone definition.
- `DELETE /api/zones/{zone_id}`: Remove a zone.

### 5. Security Events & Forensic Media APIs
- `GET /api/events`: Query events with pagination, severity filter, date range, and zone filters.
- `GET /api/events/{event_id}`: Detailed event record including tamper-proof SHA-256 hash.
- `POST /api/events/{event_id}/resolve`: Operator acknowledgment and resolution notes.
- `GET /storage/evidence/{video_filename}`: Direct stream of the recorded watermarked evidence MP4.

### 6. UAV / Drone APIs
- `GET /api/uav/telemetry`: Drone state, battery percentage, GPS coordinates, altitude, and current flight mode.
- `POST /api/uav/verification-request`: Dispatch UAV to coordinates of an unverified radar contact.
- `POST /api/uav/rth`: Command drone to Return To Home (RTH).

### 7. Authorized Persons & Face Biometrics APIs
- `GET /api/persons`: List all enrolled personnel, roles, access levels, and detection history.
- `POST /api/persons`: Enroll a new person with metadata and allowed zones.
- `POST /api/persons/{person_id}/photo`: Upload reference portrait photo to compute YuNet/SFace biometric embedding.
- `DELETE /api/persons/{person_id}`: Revoke access and remove from biometric gallery.

### 8. Real-Time WebSocket (`ws://<host>:8000/ws/live`)
Clients receive real-time updates broadcast at 1-2 Hz:
- `RADAR_TARGETS_UPDATE`: Polar/Cartesian coordinates, target IDs, velocities, and georeferenced MGRS positions.
- `TELEMETRY_HEARTBEAT`: CPU/GPU stats, camera FPS, mesh network status, and UAV telemetry.
- `SECURITY_EVENT`: Instant alert triggered upon zone breach, loitering, or watchlist match.
- `UAV_STATUS_UPDATE`: Drone flight updates and waypoint progress.

---

## 8. Operational Modes: REAL vs SIMULATED

The system includes a dual-pipeline engine toggled via the dashboard header or `.env`:

| Feature | SIMULATION Mode (`SYSTEM_MODE=SIMULATED`) | REAL Mode (`SYSTEM_MODE=REAL`) |
|:---|:---|:---|
| **Hardware Required** | None (Laptop only). | ESP32, LD2450 Radar, Webcam / Mobile Camera. |
| **Radar Targets** | Mathematically generated kinematic targets walking realistic perimeter patrol and breach paths. | Decoded in real-time from ESP32 Wi-Fi HTTP packets or raw UART binary streams. |
| **Camera Feeds** | Optical-driven radar projection or synthetic video feeds. | Real USB webcam (`CAM_01`) and Smartphone WebRTC (`CAM_02`). |
| **AI Inference** | Fully active! Detects any person in front of your webcam or in test videos. | Fully active! Live YOLOv8 + YuNet + SFace running on real feeds. |
| **Purpose** | Flawless, zero-risk hackathon demonstration and offline testing. | Production military/perimeter deployment. |

---

## 9. Technology Stack Summary

```
┌────────────────────────────────────────────────────────────────────────┐
│                          SENTINEL-AI TECH STACK                        │
├─────────────────┬──────────────────────────────────────────────────────┤
│ Programming     │ Python 3.10+, Modern ES6+ JavaScript, C++ (ESP32)   │
├─────────────────┼──────────────────────────────────────────────────────┤
│ Web Framework   │ FastAPI, Uvicorn, Starlette, Pydantic v2             │
├─────────────────┼──────────────────────────────────────────────────────┤
│ Computer Vision │ OpenCV (cv2), Ultralytics YOLOv8, PyTorch, ONNX      │
├─────────────────┼──────────────────────────────────────────────────────┤
│ Deep Learning   │ YOLOv8 Nano (Detection), YuNet (Face Detection),     │
│ Models          │ SFace (Biometric Embeddings), Cosine Similarity      │
├─────────────────┼──────────────────────────────────────────────────────┤
│ Sensor Fusion   │ Extended Kalman Filter (EKF), JDL Level 1/2, Polar    │
├─────────────────┼──────────────────────────────────────────────────────┤
│ Hardware & IoT  │ Hi-Link LD2450 mmWave Radar, ESP32, USB Webcam,      │
│                 │ Smartphone WebRTC, GPS NEO-6M, PIR Motion Sensor     │
├─────────────────┼──────────────────────────────────────────────────────┤
│ Database & ORM  │ SQLite 3, SQLAlchemy 2.0                             │
├─────────────────┼──────────────────────────────────────────────────────┤
│ Frontend UI     │ Vanilla HTML5 / CSS3 (Glassmorphism), Canvas 2D API, │
│                 │ Leaflet.js (GIS Map), Web Audio API (Synthesizer)    │
├─────────────────┼──────────────────────────────────────────────────────┤
│ Networking      │ WebSockets (Full Duplex), HTTP REST, WebRTC, HTTPS   │
└─────────────────┴──────────────────────────────────────────────────────┘
```

---
*Created for Smart India Hackathon 2026 — Aerion Surveillance Architecture Team.*
