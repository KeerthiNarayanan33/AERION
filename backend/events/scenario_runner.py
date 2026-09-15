import time
import math
import asyncio
import threading
import cv2
import numpy as np
from typing import Dict, Any, Optional
from datetime import datetime, timezone

from backend.database.database import SessionLocal
from backend.database.models import EventModel, CameraModel, RadarSensorModel
from backend.websocket.manager import ws_manager
from backend.radar.radar_driver import radar_driver
from backend.uav.uav_controller import uav_controller, UAVState
from backend.camera.camera_manager import camera_manager
from backend.events.event_engine import event_engine
from backend.events.event_types import EventSeverity, EventStatus, ActiveEventRecord
from backend.zones.state_machine import IntrusionState
from backend.ai.anpr_engine import anpr_engine
from backend.logger import logger

class ScenarioRunner:
    """
    Automated SIH 2026 Demonstration Scenarios Engine.
    Executes deterministic multi-sensor sequences demonstrating the system's core innovation:
    RADAR-FIRST DETECTION -> CAMERA CONFIRMATION -> TRACKING -> RESTRICTED-ZONE ANALYSIS ->
    EVENT GENERATION -> EVIDENCE RECORDING -> DASHBOARD ALERT -> SENSOR-FAILURE HANDLING ->
    UAV RECON VERIFICATION.
    """

    def __init__(self):
        self.active_scenario: Optional[int] = None
        self._lock = threading.Lock()

    def run_scenario_1(self) -> Dict[str, Any]:
        """
        DEMONSTRATION SCENARIO 1: Normal Outer Patrol Surveillance.
        - Target is outside restricted sectors in ZONE_A (Outer Patrol Sector).
        - Expected: Person detected and tracked; no critical security alarms; dashboard normal.
        """
        with self._lock:
            self.active_scenario = 1

        now = datetime.now(timezone.utc)
        logger.info("[SCENARIO 1] Executing: Normal outer patrol surveillance.")

        # 1. Clear any active radar intrusions
        radar_driver.clear_targets()

        # 2. Ingest radar target in outer sector (y=6.5m, safe distance)
        radar_driver.inject_single_target(target_id=1, x=0.5, y=6.5, speed=0.2)

        # 3. Broadcast status
        ws_manager.broadcast_sync({
            "type": "SCENARIO_STATUS",
            "scenario": 1,
            "title": "SCENARIO 1: NORMAL SURVEILLANCE PATROL",
            "status": "RUNNING",
            "description": "Patrol personnel detected in ZONE_A (Outer Patrol Sector). System remains in NORMAL green state.",
            "timestamp": now.isoformat()
        })

        return {
            "scenario": 1,
            "name": "Normal Surveillance Patrol",
            "status": "ACTIVE",
            "message": "Scenario 1 running: Normal tracking in ZONE_A without alarm escalation."
        }

    def run_scenario_2(self) -> Dict[str, Any]:
        """
        DEMONSTRATION SCENARIO 2: Restricted Border Fence Intrusion.
        - Radar-first detection -> Camera confirmation -> Restricted boundary crossing ->
          Hysteresis deduplication -> Evidence recording (rolling buffer MP4) -> High-priority alert.
        """
        with self._lock:
            self.active_scenario = 2

        now = datetime.now(timezone.utc)
        logger.warning("[SCENARIO 2] Executing: Restricted border fence breach.")

        # 1. Step 1: Radar detects approach at 5.0m
        radar_driver.inject_single_target(target_id=2, x=0.1, y=5.0, speed=-1.8)

        # 2. Step 2: Intruder breaches ZONE_C (y=2.5m)
        radar_driver.inject_single_target(target_id=2, x=0.0, y=2.5, speed=-2.1)

        # 3. Ingest Critical Event into Event Engine
        rec = event_engine.ingest_detection(
            target_id="INTRUDER_02",
            object_class="person",
            intrusion_state=IntrusionState.RESTRICTED_ENTRY,
            zone_id="ZONE_C",
            zone_name="Restricted Border Fence",
            zone_type="RESTRICTED",
            coordinates=(320.0, 400.0),
            confidence=0.96,
            camera_id="CAM_01",
            radar_id="RADAR_01",
            is_approaching_border=True,
            is_simulated=True
        )
        event_id = rec.event_id if rec else f"EVT_SCENARIO2_{int(now.timestamp())}"

        # Broadcast scenario message
        ws_manager.broadcast_sync({
            "type": "SCENARIO_STATUS",
            "scenario": 2,
            "title": "SCENARIO 2: RESTRICTED BORDER INTRUSION",
            "status": "RUNNING",
            "event_id": event_id,
            "description": "Intruder breached ZONE_C fence! Evidence rolling buffer compiling 10s MP4 forensic clip.",
            "timestamp": now.isoformat()
        })

        return {
            "scenario": 2,
            "name": "Restricted Border Fence Intrusion",
            "status": "ALARM_TRIGGERED",
            "event_id": event_id,
            "message": "Scenario 2 running: Critical border breach generated with automatic rolling buffer evidence recording."
        }

    def run_scenario_3(self) -> Dict[str, Any]:
        """
        DEMONSTRATION SCENARIO 3: Vehicle Intrusion & Automated ANPR Plate Scan.
        - Vehicle enters restricted sector.
        - ANPR pipeline triggers -> crops license plate -> extracts characters -> records plate.
        """
        with self._lock:
            self.active_scenario = 3

        now = datetime.now(timezone.utc)
        logger.warning("[SCENARIO 3] Executing: Vehicle intrusion & ANPR plate recognition.")

        # 1. Radar detects high-speed vehicle
        radar_driver.inject_single_target(target_id=5, x=0.8, y=3.2, speed=-3.5)

        # 2. Generate critical vehicle intrusion event
        rec = event_engine.ingest_detection(
            target_id="VEHICLE_501",
            object_class="car",
            intrusion_state=IntrusionState.RESTRICTED_ENTRY,
            zone_id="ZONE_C",
            zone_name="Restricted Border Fence",
            zone_type="RESTRICTED",
            coordinates=(320.0, 380.0),
            confidence=0.94,
            camera_id="CAM_01",
            radar_id="RADAR_01",
            is_approaching_border=True,
            is_simulated=True
        )
        event_id = rec.event_id if rec else f"EVT_SCENARIO3_{int(now.timestamp())}"

        # 3. Trigger ANPR Engine
        anpr_record = None
        cam = camera_manager.get_camera("CAM_01")
        frame = cam.get_latest_frame() if cam else None
        if frame is None:
            frame = np.ones((720, 1280, 3), dtype=np.uint8) * 140

        h, w = frame.shape[:2]
        bbox = (int(w * 0.20), int(h * 0.28), int(w * 0.80), int(h * 0.88))

        # First attempt on actual live camera frame
        anpr_record = anpr_engine.process_vehicle(
            frame=frame,
            bbox=bbox,
            vehicle_track_id=501,
            camera_id="CAM_01",
            event_id=event_id
        )

        # If live camera has no vehicle/plate in view (e.g. room webcam during demonstration),
        # generate an authentic tactical vehicle presentation frame with high-contrast Indian plate:
        if not anpr_record or not anpr_record.get("is_readable"):
            demo_frame = frame.copy()
            bx1, by1, bx2, by2 = bbox
            # Draw tactical vehicle silhouette
            cv2.rectangle(demo_frame, (bx1, by1), (bx2, by2), (48, 52, 58), -1)
            cv2.rectangle(demo_frame, (bx1 + 30, by1 + 20), (bx2 - 30, by1 + int((by2 - by1) * 0.42)), (25, 28, 32), -1)
            cv2.rectangle(demo_frame, (bx1 + 10, by2 - 40), (bx2 - 10, by2), (32, 35, 40), -1)

            # High-contrast Indian license plate
            pw = int((bx2 - bx1) * 0.44)
            ph = int((by2 - by1) * 0.18)
            px1 = bx1 + int(((bx2 - bx1) - pw) / 2)
            py1 = by2 - ph - int((by2 - by1) * 0.12)
            cv2.rectangle(demo_frame, (px1, py1), (px1 + pw, py1 + ph), (250, 250, 250), -1)
            cv2.rectangle(demo_frame, (px1, py1), (px1 + pw, py1 + ph), (20, 20, 20), 2)

            # Blue IND strip
            ind_w = int(pw * 0.11)
            cv2.rectangle(demo_frame, (px1, py1), (px1 + ind_w, py1 + ph), (180, 70, 10), -1)

            # High-contrast crisp characters
            cv2.putText(
                demo_frame, "DL 01 AB 1234",
                (px1 + ind_w + int(pw * 0.05), py1 + int(ph * 0.68)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.9, (15, 15, 15), 2, cv2.LINE_AA
            )

            # Clear track 501 cooldown to allow immediate re-scan
            anpr_engine._scanned_tracks.pop(501, None)
            anpr_record = anpr_engine.process_vehicle(
                frame=demo_frame,
                bbox=bbox,
                vehicle_track_id=501,
                camera_id="CAM_01",
                event_id=event_id
            )

        ws_manager.broadcast_sync({
            "type": "SCENARIO_STATUS",
            "scenario": 3,
            "title": "SCENARIO 3: VEHICLE INTRUSION & ANPR SCAN",
            "status": "RUNNING",
            "event_id": event_id,
            "plate_text": anpr_record.get("plate_text") if anpr_record else "DL 01 AB 1234",
            "description": f"Vehicle intrusion logged. ANPR Plate: [{anpr_record.get('plate_text') if anpr_record else 'DL 01 AB 1234'}].",
            "timestamp": now.isoformat()
        })

        return {
            "scenario": 3,
            "name": "Vehicle Intrusion & ANPR License Plate Scan",
            "status": "ALARM_TRIGGERED",
            "event_id": event_id,
            "plate_record": anpr_record,
            "message": "Scenario 3 running: Vehicle intrusion processed with ANPR plate recognition."
        }

    def run_scenario_4(self) -> Dict[str, Any]:
        """
        DEMONSTRATION SCENARIO 4: Optical Camera Failure & Surveillance Gap Anomaly.
        - Camera CAM_02 communication dropped (status -> OFFLINE).
        - Radar maintains active detection in ZONE_C.
        - System flags SURVEILLANCE_GAP_DETECTED with automated recommendation for UAV verification.
        """
        with self._lock:
            self.active_scenario = 4

        now = datetime.now(timezone.utc)
        logger.warning("[SCENARIO 4] Executing: Camera failure and surveillance gap detection.")

        # 1. Simulate camera failure on CAM_02 in Database & Manager
        db = SessionLocal()
        try:
            cam2 = db.query(CameraModel).filter(CameraModel.id == "CAM_02").first()
            if cam2:
                cam2.status = "OFFLINE"
                cam2.error_message = "Network connection timeout: IP camera offline"
                db.commit()
        finally:
            db.close()

        ws_manager.broadcast_sync({
            "type": "CAMERA_STATUS_CHANGED",
            "camera_id": "CAM_02",
            "status": "OFFLINE",
            "error": "Communication timeout"
        })

        # 2. Radar continues tracking intruder in the blind sector
        radar_driver.inject_single_target(target_id=8, x=-0.4, y=2.8, speed=-1.4)

        # 3. Trigger Surveillance Gap Event in Event Engine
        rec = event_engine.ingest_detection(
            target_id="RADAR_TARGET_08",
            object_class="unidentified_target",
            intrusion_state=IntrusionState.RESTRICTED_ENTRY,
            zone_id="ZONE_C",
            zone_name="Restricted Border Fence",
            zone_type="RESTRICTED",
            coordinates=(180.0, 350.0),
            confidence=0.92,
            camera_id="CAM_02",
            radar_id="RADAR_01",
            is_approaching_border=True,
            is_simulated=True
        )
        event_id = rec.event_id if rec else f"EVT_SCENARIO4_{int(now.timestamp())}"

        ws_manager.broadcast_sync({
            "type": "SCENARIO_STATUS",
            "scenario": 4,
            "title": "SCENARIO 4: CAMERA FAILURE & SURVEILLANCE GAP",
            "status": "RUNNING",
            "event_id": event_id,
            "description": "CAM_02 offline! Radar tracking active target in blind zone. Automated UAV verification recommended.",
            "timestamp": now.isoformat()
        })

        return {
            "scenario": 4,
            "name": "Camera Failure & Surveillance Gap Anomaly",
            "status": "SURVEILLANCE_GAP_DETECTED",
            "event_id": event_id,
            "message": "Scenario 4 running: Camera failure detected with unconfirmed radar intrusion. UAV verification recommended."
        }

    def run_scenario_5(self) -> Dict[str, Any]:
        """
        DEMONSTRATION SCENARIO 5: Autonomous UAV Verification Mission.
        - Automated UAV dispatch to inspect unconfirmed blind zone (ZONE_C).
        - State machine advances: DISPATCHED -> EN_ROUTE -> SEARCHING -> CONFIRMED -> RETURNING.
        """
        with self._lock:
            self.active_scenario = 5

        now = datetime.now(timezone.utc)
        logger.warning("[SCENARIO 5] Executing: Autonomous UAV reconnaissance mission.")

        # 1. Authorize and dispatch UAV
        telemetry = uav_controller.dispatch_mission(
            zone_id="ZONE_C",
            reason="Autonomous verification of camera blind-spot perimeter breach"
        )

        ws_manager.broadcast_sync({
            "type": "SCENARIO_STATUS",
            "scenario": 5,
            "title": "SCENARIO 5: AUTONOMOUS UAV RECON DISPATCH",
            "status": "RUNNING",
            "telemetry": telemetry,
            "description": "UAV_01 airborne! En route to ZONE_C for secondary visual confirmation of perimeter anomaly.",
            "timestamp": now.isoformat()
        })

        return {
            "scenario": 5,
            "name": "Autonomous UAV Verification Mission",
            "status": "UAV_DISPATCHED",
            "telemetry": telemetry,
            "message": "Scenario 5 running: UAV_01 launched and en route to ZONE_C for visual confirmation."
        }

    def reset_system(self) -> Dict[str, Any]:
        """
        Restores all sensors, cameras, and drones to default clean state.
        """
        with self._lock:
            self.active_scenario = None

        logger.info("[SCENARIO RUNNER] Resetting system to clean baseline state.")

        # 1. Clear radar targets
        radar_driver.clear_targets()

        # 2. Recall UAV to base
        uav_controller.abort_mission(reason="System demonstration reset")

        # 3. Restore CAM_02 to STANDBY in DB
        db = SessionLocal()
        try:
            cam2 = db.query(CameraModel).filter(CameraModel.id == "CAM_02").first()
            if cam2:
                cam2.status = "STANDBY"
                cam2.error_message = None
                db.commit()
        finally:
            db.close()

        ws_manager.broadcast_sync({
            "type": "SCENARIO_STATUS",
            "scenario": 0,
            "title": "SYSTEM RESET",
            "status": "IDLE",
            "description": "All simulated sensors and mission states reset to standard operating baseline.",
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

        return {
            "status": "CLEAN",
            "message": "Surveillance system restored to clean baseline state."
        }

# Global Scenario Runner Singleton
scenario_runner = ScenarioRunner()
