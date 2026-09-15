import time
import json
import uuid
import threading
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timezone

from backend.config import get_settings
from backend.database.database import get_db_context
from backend.database.models import SecurityIncidentModel, CameraModel, ZoneModel
from backend.geospatial.navigation_service import navigation_service
from backend.geospatial.gps_service import gps_manager
from backend.uav.drone_provider import drone_manager, DroneFlightState
from backend.websocket.manager import ws_manager
from backend.logger import logger

settings = get_settings()

# Known Camera -> Zone -> Target Coordinates Mapping (Sections 6, 13)
CAMERA_ZONE_MAPPING = {
    "CAM_01": "ZONE_B",
    "CAM-001": "ZONE_B",
    "CAM_02": "ZONE_C",
    "CAM-002": "ZONE_C",
    "CAM_03": "ZONE_A",
    "CAM-003": "ZONE_A"
}

ZONE_COORDINATES = {
    "ZONE_A": {"lat": 31.6248, "lon": 74.8735, "name": "Outer Patrol Sector"},
    "ZONE-001": {"lat": 31.6248, "lon": 74.8735, "name": "Outer Patrol Sector"},
    "ZONE_B": {"lat": 31.6262, "lon": 74.8748, "name": "Warning Approach Sector"},
    "ZONE-002": {"lat": 31.6262, "lon": 74.8748, "name": "Warning Approach Sector"},
    "ZONE_C": {"lat": 31.6280, "lon": 74.8765, "name": "Restricted Border Fence"},
    "ZONE-003": {"lat": 31.6280, "lon": 74.8765, "name": "Restricted Border Fence"}
}

class IncidentService:
    """
    Central Security Incident Management & Autonomous Drone Dispatch Engine.
    Implements Incident State Machine, Camera-to-Zone Coordinate Resolution,
    Duplicate Event Suppression, and Pre-Flight Validation (Sections 6, 13, 14, 15, 16, 44, 45).
    """
    _instance: Optional['IncidentService'] = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(IncidentService, cls).__new__(cls)
                cls._instance._active_incidents: Dict[str, Dict[str, Any]] = {}
                cls._instance._session_cooldowns: Dict[str, float] = {}
                cls._instance._cooldown_seconds = 25.0
                cls._instance._incident_counter = 1
            return cls._instance

    def resolve_camera_zone(self, camera_id: str) -> str:
        """Resolves the one dedicated zone monitored by a camera (Section 6: ONE CAMERA = ONE ZONE)."""
        cid = camera_id.strip()
        if cid in CAMERA_ZONE_MAPPING:
            return CAMERA_ZONE_MAPPING[cid]
        # Query database camera model for configured zone_id
        try:
            with get_db_context() as db:
                cam = db.query(CameraModel).filter(CameraModel.id == cid).first()
                if cam and cam.zone_id:
                    return cam.zone_id
        except Exception:
            pass
        return "ZONE_B"

    def resolve_zone_coordinates(self, zone_id: str) -> Tuple[float, float]:
        """Resolves geographic centroid coordinates for the target zone (Section 13, 18)."""
        zid = zone_id.strip()
        if zid in ZONE_COORDINATES:
            return ZONE_COORDINATES[zid]["lat"], ZONE_COORDINATES[zid]["lon"]
        # Default border sector coordinates
        return 31.6262, 74.8748

    def process_unauthorized_detection(
        self,
        camera_id: str,
        zone_id: Optional[str],
        track_id: Optional[int],
        identity: str = "UNKNOWN",
        confidence: float = 0.90,
        authorization: str = "UNAUTHORIZED"
    ) -> Optional[Dict[str, Any]]:
        """
        Ingests an unauthorized identity detection from camera inference.
        Handles duplicate suppression, creates security incident, and plans drone response.
        """
        now = time.time()
        # Ensure ONE CAMERA = ONE ZONE mapping
        resolved_zone = self.resolve_camera_zone(camera_id) if not zone_id else zone_id
        session_key = f"{camera_id}_{resolved_zone}_{identity}"

        with self._lock:
            # Duplicate Event Prevention (Section 45)
            last_time = self._session_cooldowns.get(session_key, 0.0)
            if now - last_time < self._cooldown_seconds:
                # Same unauthorized person in front of same camera; update existing incident
                for inc in self._active_incidents.values():
                    if inc.get("session_key") == session_key and inc.get("status") != "RESOLVED":
                        inc["updated_at"] = datetime.now(timezone.utc).isoformat()
                        inc["identity_confidence"] = max(inc.get("identity_confidence", 0.0), confidence)
                        return inc
                return None

            self._session_cooldowns[session_key] = now

            # Generate new incident ID: e.g. INC-001
            incident_id = f"INC-{self._incident_counter:03d}"
            self._incident_counter += 1

            target_lat, target_lon = self.resolve_zone_coordinates(resolved_zone)

            incident_record = {
                "incident_id": incident_id,
                "session_key": session_key,
                "camera_id": camera_id,
                "zone_id": resolved_zone,
                "identity": identity,
                "identity_confidence": round(confidence, 2),
                "authorization": authorization,
                "latitude": target_lat,
                "longitude": target_lon,
                "priority": "HIGH",
                "drone_id": settings.DRONE_ID,
                "status": "INCIDENT_CREATED",
                "aerial_verified": False,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat()
            }

            self._active_incidents[incident_id] = incident_record

        logger.warning(
            f"[INCIDENT ENGINE] Security Incident {incident_id} CREATED: "
            f"Camera {camera_id} -> Zone {resolved_zone} ({target_lat}, {target_lon}) | Identity: {identity} ({authorization})"
        )

        # Persist to database
        self._save_incident_to_db(incident_record)

        # Broadcast incident creation
        ws_manager.broadcast_sync({
            "type": "INCIDENT_CREATED",
            "incident": incident_record
        })

        # Evaluate and trigger drone dispatch workflow (Sections 16, 44)
        self.evaluate_drone_dispatch(incident_id)

        return incident_record

    def evaluate_drone_dispatch(self, incident_id: str) -> Dict[str, Any]:
        """
        Validates safety rules and dispatches DRONE-001 to the incident zone coordinates.
        (Sections 16, 17, 34, 35, 44).
        """
        incident = self._active_incidents.get(incident_id)
        if not incident:
            return {"status": "ERROR", "message": "Incident not found"}

        drone_telem = drone_manager.get_telemetry()
        drone_state = drone_telem.get("state", "STANDBY")
        battery = drone_telem.get("battery_percent", 0.0)
        gps_info = drone_telem.get("gps", {})
        gps_fix = gps_info.get("fix_status", "NO FIX")

        # 1. Check Battery Safety Rule (Sections 34, 35)
        if battery <= settings.UAV_RTH_BATTERY_PERCENT:
            logger.warning(
                f"[INCIDENT ENGINE] Drone dispatch DENIED for {incident_id}: "
                f"Battery {battery}% <= {settings.UAV_RTH_BATTERY_PERCENT}%. Low battery failsafe overrides mission!"
            )
            incident["status"] = "LOW_BATTERY_ABORT"
            self._save_incident_to_db(incident)
            ws_manager.broadcast_sync({
                "type": "INCIDENT_UPDATED",
                "incident": incident,
                "reason": "DRONE_BATTERY_LOW_CANNOT_DISPATCH"
            })
            return {"status": "DENIED", "reason": "LOW_BATTERY"}

        # 2. Check GPS Fix (Sections 20, 43)
        if gps_fix not in ("3D FIX", "2D FIX") and settings.GPS_MODE == "LIVE":
            logger.warning(f"[INCIDENT ENGINE] Drone dispatch DENIED for {incident_id}: GPS has NO FIX.")
            incident["status"] = "GPS_UNAVAILABLE"
            self._save_incident_to_db(incident)
            ws_manager.broadcast_sync({
                "type": "INCIDENT_UPDATED",
                "incident": incident,
                "reason": "GPS_NO_FIX"
            })
            return {"status": "DENIED", "reason": "GPS_NO_FIX"}

        # 3. Check Drone Availability (Section 16: ONLY ONE DRONE)
        if drone_state not in ("STANDBY", "CHARGING"):
            logger.warning(
                f"[INCIDENT ENGINE] {settings.DRONE_ID} currently active on mission in state '{drone_state}'. "
                f"Queueing incident {incident_id} and alerting operator."
            )
            incident["status"] = "DRONE_BUSY_QUEUED"
            self._save_incident_to_db(incident)
            ws_manager.broadcast_sync({
                "type": "INCIDENT_UPDATED",
                "incident": incident,
                "reason": "DRONE_BUSY_QUEUED"
            })
            return {"status": "QUEUED", "reason": "DRONE_BUSY"}

        # 4. Dispatch Drone to Zone Coordinates (Section 18: TARGET THE ZONE, NOT THE PERSON)
        target_lat = incident["latitude"]
        target_lon = incident["longitude"]
        zone_id = incident["zone_id"]

        try:
            dispatch_res = drone_manager.dispatch(
                target_lat=target_lat,
                target_lon=target_lon,
                zone_id=zone_id,
                incident_id=incident_id
            )
            incident["status"] = "DRONE_DISPATCHED"
            self._save_incident_to_db(incident)

            ws_manager.broadcast_sync({
                "type": "INCIDENT_UPDATED",
                "incident": incident,
                "telemetry": dispatch_res
            })

            logger.info(f"[INCIDENT ENGINE] DRONE-001 DISPATCHED to {zone_id} for {incident_id}.")
            return {"status": "DISPATCHED", "incident_id": incident_id, "drone": dispatch_res}

        except Exception as ex:
            logger.error(f"[INCIDENT ENGINE] Failed to dispatch drone: {ex}")
            incident["status"] = "DISPATCH_FAILED"
            self._save_incident_to_db(incident)
            return {"status": "FAILED", "reason": str(ex)}

    def confirm_aerial_verification(self, incident_id: str, verification_details: Dict[str, Any]) -> None:
        """Called when DRONE-001 completes aerial optical scan and confirms identity (Section 32)."""
        incident = self._active_incidents.get(incident_id)
        if incident:
            incident["aerial_verified"] = True
            incident["aerial_details"] = verification_details
            incident["status"] = "AERIAL_VERIFIED"
            incident["updated_at"] = datetime.now(timezone.utc).isoformat()
            self._save_incident_to_db(incident)

            ws_manager.broadcast_sync({
                "type": "AERIAL_VERIFICATION_COMPLETE",
                "incident_id": incident_id,
                "incident": incident,
                "verification": verification_details
            })
            logger.warning(f"[INCIDENT ENGINE] Incident {incident_id} AERIAL VERIFICATION CONFIRMED!")

    def resolve_incident(self, incident_id: str, operator: str = "Operator") -> Dict[str, Any]:
        """Marks an active incident as resolved and commands drone return home if still on site."""
        incident = self._active_incidents.get(incident_id)
        if not incident:
            return {"status": "ERROR", "message": "Incident not found"}

        incident["status"] = "RESOLVED"
        incident["updated_at"] = datetime.now(timezone.utc).isoformat()
        incident["resolved_by"] = operator
        self._save_incident_to_db(incident)

        # Recall drone if still at target
        telem = drone_manager.get_telemetry()
        if telem.get("state") in ("ARRIVED", "AERIAL_SCAN", "VERIFICATION", "TRACKING"):
            drone_manager.return_home(f"Incident {incident_id} resolved by {operator}")

        ws_manager.broadcast_sync({
            "type": "INCIDENT_RESOLVED",
            "incident_id": incident_id,
            "incident": incident
        })

        return {"status": "RESOLVED", "incident_id": incident_id}

    def get_active_incident(self) -> Optional[Dict[str, Any]]:
        """Returns the most recent active unresolved security incident."""
        for inc in reversed(list(self._active_incidents.values())):
            if inc.get("status") != "RESOLVED":
                return inc
        return None

    def list_incidents(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Returns list of recent security incidents."""
        return list(self._active_incidents.values())[-limit:]

    def _save_incident_to_db(self, inc: Dict[str, Any]) -> None:
        """Persists or updates incident record in SQLite database."""
        try:
            with get_db_context() as db:
                existing = db.query(SecurityIncidentModel).filter(
                    SecurityIncidentModel.incident_id == inc["incident_id"]
                ).first()
                if existing:
                    existing.status = inc.get("status", existing.status)
                    existing.identity_confidence = inc.get("identity_confidence", existing.identity_confidence)
                    existing.aerial_verified = inc.get("aerial_verified", existing.aerial_verified)
                    if inc.get("aerial_details"):
                        existing.aerial_details = json.dumps(inc["aerial_details"])
                else:
                    rec = SecurityIncidentModel(
                        incident_id=inc["incident_id"],
                        camera_id=inc["camera_id"],
                        zone_id=inc["zone_id"],
                        identity=inc["identity"],
                        identity_confidence=inc["identity_confidence"],
                        authorization=inc["authorization"],
                        latitude=inc["latitude"],
                        longitude=inc["longitude"],
                        priority=inc["priority"],
                        drone_id=inc["drone_id"],
                        status=inc["status"],
                        aerial_verified=inc["aerial_verified"],
                        aerial_details=json.dumps(inc["aerial_details"]) if inc.get("aerial_details") else None
                    )
                    db.add(rec)
                db.commit()
        except Exception as e:
            logger.error(f"[INCIDENT ENGINE] Failed to save incident to DB: {e}")

incident_service = IncidentService()
