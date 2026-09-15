import time
import math
import threading
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from enum import Enum

from backend.database.database import SessionLocal
from backend.database.models import UAVStatusModel, EventModel
from backend.websocket.manager import ws_manager
from backend.logger import logger

class UAVState(str, Enum):
    STANDBY = "UAV_STANDBY"
    DISPATCHED = "UAV_DISPATCHED"
    EN_ROUTE = "UAV_EN_ROUTE"
    SEARCHING = "UAV_SEARCHING"
    CONFIRMED = "UAV_CONFIRMED"
    RETURNING = "UAV_RETURNING"
    OFFLINE = "UAV_OFFLINE"

# Base coordinates for simulated border outpost
BASE_LAT = 31.6240
BASE_LON = 74.8723

ZONE_WAYPOINTS = {
    "ZONE_A": {"lat": 31.6248, "lon": 74.8735, "name": "Outer Patrol Sector"},
    "ZONE_B": {"lat": 31.6262, "lon": 74.8748, "name": "Warning Approach Sector"},
    "ZONE_C": {"lat": 31.6280, "lon": 74.8765, "name": "Restricted Border Fence"}
}

class UAVMissionController:
    """
    Autonomous Recon Drone (UAV_01) Flight Mission Controller.
    Manages verification missions dispatched during camera sensor failures,
    perimeter blind zones, or high-priority border alarms.
    """

    def __init__(self, uav_id: str = "UAV_01"):
        self.uav_id = uav_id
        self.state: UAVState = UAVState.STANDBY
        self.target_zone: Optional[str] = None
        self.battery_percent: float = 100.0
        self.latitude: float = BASE_LAT
        self.longitude: float = BASE_LON
        self.altitude_m: float = 0.0
        self.speed_mps: float = 0.0
        self.mission_start_time: Optional[float] = None
        self.mission_reason: str = "Standby"
        self._lock = threading.Lock()
        self._running = False
        self._loop_thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Starts the UAV flight telemetry and mission progression loop."""
        with self._lock:
            if self._running:
                return
            self._running = True
            self._loop_thread = threading.Thread(
                target=self._flight_loop,
                daemon=True,
                name="UAVFlightLoop"
            )
            self._loop_thread.start()
            logger.info("UAV Mission Controller started.")

    def stop(self) -> None:
        """Stops the UAV mission controller loop."""
        with self._lock:
            self._running = False
        if self._loop_thread and self._loop_thread.is_alive():
            self._loop_thread.join(timeout=2.0)
        logger.info("UAV Mission Controller stopped.")

    def dispatch_mission(self, zone_id: str, reason: str = "Sensor anomaly confirmation") -> Dict[str, Any]:
        """Dispatches UAV from base station to inspect designated border sector."""
        with self._lock:
            if self.battery_percent < 20.0:
                raise ValueError("Insufficient UAV battery for mission (below 20%)")

            self.state = UAVState.DISPATCHED
            self.target_zone = zone_id
            self.mission_reason = reason
            self.mission_start_time = time.time()
            self.speed_mps = 6.0
            self.altitude_m = 15.0

        now_iso = datetime.now(timezone.utc).isoformat()
        logger.warning(f"[UAV CONTROLLER] Mission authorized: Dispatching UAV_01 to {zone_id}. Reason: {reason}")

        # Update Database
        self._update_db_state(self.state.value, zone_id)

        # Broadcast Mission Event
        ws_manager.broadcast_sync({
            "type": "UAV_VERIFICATION_DISPATCHED",
            "uav_id": self.uav_id,
            "state": self.state.value,
            "zone_id": zone_id,
            "reason": reason,
            "timestamp": now_iso
        })

        return self.get_telemetry()

    def abort_mission(self, reason: str = "Operator recall") -> Dict[str, Any]:
        """Aborts current mission and commands UAV to return to base (RTB)."""
        with self._lock:
            if self.state in (UAVState.STANDBY, UAVState.OFFLINE):
                return self.get_telemetry()

            self.state = UAVState.RETURNING
            self.mission_reason = f"Recalled: {reason}"
            self.speed_mps = 14.0

        logger.info(f"[UAV CONTROLLER] Mission aborted: Returning to base. ({reason})")
        self._update_db_state(self.state.value, self.target_zone)

        ws_manager.broadcast_sync({
            "type": "UAV_STATE_CHANGED",
            "uav_id": self.uav_id,
            "state": self.state.value,
            "reason": reason,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

        return self.get_telemetry()

    def _flight_loop(self) -> None:
        """Periodic simulation tick updating flight dynamics, GPS, and state machine."""
        while self._running:
            try:
                time.sleep(1.0)
                with self._lock:
                    self._update_flight_dynamics()

                # Broadcast live telemetry update
                ws_manager.broadcast_sync({
                    "type": "UAV_TELEMETRY_UPDATE",
                    "telemetry": self.get_telemetry()
                })

            except Exception as e:
                logger.error(f"[UAV CONTROLLER] Error in flight loop: {e}", exc_info=True)

    def _update_flight_dynamics(self) -> None:
        """Updates internal telemetry and transitions flight state machine."""
        now = time.time()

        if self.state == UAVState.STANDBY:
            # Recharging at base
            if self.battery_percent < 100.0:
                self.battery_percent = min(100.0, round(self.battery_percent + 0.5, 1))
            self.altitude_m = 0.0
            self.speed_mps = 0.0
            self.latitude = BASE_LAT
            self.longitude = BASE_LON
            return

        # Active flight -> Battery drain
        self.battery_percent = max(0.0, round(self.battery_percent - 0.25, 1))
        if self.battery_percent <= 15.0 and self.state != UAVState.RETURNING:
            # Automatic low-battery failsafe Return-to-Base
            self.state = UAVState.RETURNING
            logger.warning("[UAV CONTROLLER] Low battery failsafe triggered: Returning to base!")

        target_wp = ZONE_WAYPOINTS.get(self.target_zone or "ZONE_C", ZONE_WAYPOINTS["ZONE_C"])

        if self.state == UAVState.DISPATCHED:
            self.altitude_m = min(45.0, self.altitude_m + 8.0)
            self.speed_mps = 10.0
            if (now - (self.mission_start_time or now)) >= 3.0:
                self.state = UAVState.EN_ROUTE
                logger.info("[UAV CONTROLLER] UAV_01 reached cruising altitude. En route to patrol sector.")

        elif self.state == UAVState.EN_ROUTE:
            self.altitude_m = 45.0
            self.speed_mps = 14.0
            # Interpolate towards target waypoint
            self.latitude += (target_wp["lat"] - self.latitude) * 0.25
            self.longitude += (target_wp["lon"] - self.longitude) * 0.25
            if (now - (self.mission_start_time or now)) >= 8.0:
                self.state = UAVState.SEARCHING
                logger.info(f"[UAV CONTROLLER] UAV_01 on station at {self.target_zone}. Performing optical recon sweep.")

        elif self.state == UAVState.SEARCHING:
            self.altitude_m = 35.0
            self.speed_mps = 4.5
            # Loitering figure-8 orbit
            orbit_time = now * 0.8
            self.latitude = target_wp["lat"] + 0.0004 * math.sin(orbit_time)
            self.longitude = target_wp["lon"] + 0.0004 * math.cos(orbit_time)
            if (now - (self.mission_start_time or now)) >= 16.0:
                self.state = UAVState.CONFIRMED
                logger.info(f"[UAV CONTROLLER] Target visual confirmation achieved in {self.target_zone}!")

        elif self.state == UAVState.CONFIRMED:
            self.speed_mps = 3.0
            if (now - (self.mission_start_time or now)) >= 24.0:
                self.state = UAVState.RETURNING
                logger.info("[UAV CONTROLLER] Recon mission complete. Returning to base station.")

        elif self.state == UAVState.RETURNING:
            self.speed_mps = 14.0
            self.altitude_m = max(10.0, self.altitude_m - 3.0)
            self.latitude += (BASE_LAT - self.latitude) * 0.3
            self.longitude += (BASE_LON - self.longitude) * 0.3
            dist_to_base = math.sqrt((self.latitude - BASE_LAT)**2 + (self.longitude - BASE_LON)**2)
            if dist_to_base < 0.0002:
                self.state = UAVState.STANDBY
                self.target_zone = None
                self.altitude_m = 0.0
                self.speed_mps = 0.0
                self.latitude = BASE_LAT
                self.longitude = BASE_LON
                logger.info("[UAV CONTROLLER] UAV_01 safely landed and docked at base station.")

        self._update_db_state(self.state.value, self.target_zone)

    def get_telemetry(self) -> Dict[str, Any]:
        """Returns structured real-time flight telemetry."""
        return {
            "uav_id": self.uav_id,
            "state": self.state.value,
            "current_zone": self.target_zone,
            "battery_percent": round(self.battery_percent, 1),
            "altitude_m": round(self.altitude_m, 1),
            "speed_mps": round(self.speed_mps, 1),
            "latitude": round(self.latitude, 6),
            "longitude": round(self.longitude, 6),
            "reason": self.mission_reason,
            "is_airborne": self.state not in (UAVState.STANDBY, UAVState.OFFLINE),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    def _update_db_state(self, state_val: str, current_zone: Optional[str]) -> None:
        """Persists state to SQLite UAVStatusModel."""
        db = SessionLocal()
        try:
            uav = db.query(UAVStatusModel).filter(UAVStatusModel.id == self.uav_id).first()
            if uav:
                uav.state = state_val
                uav.battery_percent = int(self.battery_percent)
                uav.current_zone = current_zone
                uav.target_lat = self.latitude
                uav.target_lon = self.longitude
                uav.last_ping = datetime.now(timezone.utc)
                db.commit()
        except Exception as e:
            db.rollback()
            logger.debug(f"[UAV CONTROLLER] DB sync error: {e}")
        finally:
            db.close()

# Global UAV Controller Singleton
uav_controller = UAVMissionController()
