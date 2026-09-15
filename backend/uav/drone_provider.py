import time
import math
import threading
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Tuple, List
from datetime import datetime, timezone
from enum import Enum

from backend.config import get_settings
from backend.geospatial.navigation_service import navigation_service
from backend.geospatial.gps_service import gps_manager
from backend.websocket.manager import ws_manager
from backend.logger import logger

settings = get_settings()

class DroneFlightState(str, Enum):
    DISCONNECTED = "DISCONNECTED"
    STANDBY = "STANDBY"
    DISPATCHED = "DISPATCHED"
    NAVIGATING = "NAVIGATING"
    ARRIVED = "ARRIVED"
    AERIAL_SCAN = "AERIAL_SCAN"
    VERIFICATION = "VERIFICATION"
    TRACKING = "TRACKING"
    RETURNING = "RETURNING"
    LANDING = "LANDING"
    CHARGING = "CHARGING"
    EMERGENCY = "EMERGENCY"

class TargetLocalizationProvider(ABC):
    """
    Future-compatible target localization interface (Section 33).
    Allows future sensor upgrade (LD2450 mmWave / Sensor Fusion) without refactoring.
    """
    @abstractmethod
    def get_relative_target_position(self) -> Optional[Dict[str, float]]:
        pass

class CameraLocalization(TargetLocalizationProvider):
    """Visual camera optical localization for current prototype."""
    def get_relative_target_position(self) -> Optional[Dict[str, float]]:
        return {"distance_m": 8.5, "azimuth_deg": 12.0, "source": "OPTICAL_FLIR"}

class DroneProvider(ABC):
    """
    Abstract Drone Hardware/Simulation Provider (Section 25).
    """
    @abstractmethod
    def connect(self) -> bool:
        pass

    @abstractmethod
    def disconnect(self) -> None:
        pass

    @abstractmethod
    def get_status(self) -> DroneFlightState:
        pass

    @abstractmethod
    def get_position(self) -> Tuple[float, float, float]:
        pass

    @abstractmethod
    def get_battery(self) -> float:
        pass

    @abstractmethod
    def dispatch_to_target(
        self,
        target_lat: float,
        target_lon: float,
        zone_id: str,
        incident_id: str
    ) -> Dict[str, Any]:
        pass

    @abstractmethod
    def start_scan(self) -> Dict[str, Any]:
        pass

    @abstractmethod
    def return_home(self, reason: str = "Operator command") -> Dict[str, Any]:
        pass

    @abstractmethod
    def abort_mission(self, reason: str = "Operator abort") -> Dict[str, Any]:
        pass

    @abstractmethod
    def spin_blades_idle(self, duration_sec: float = 3.0, throttle: int = 15) -> bool:
        pass

    @abstractmethod
    def get_telemetry(self) -> Dict[str, Any]:
        pass

class SimulationDroneProvider(DroneProvider):
    """
    High-Fidelity Autonomous Drone Simulator (Sections 21, 25, 26, 27, 32, 34, 35, 36).
    Simulates DRONE-001 realistic flight dynamics, battery drain, GPS waypoint movement,
    arrival detection, and aerial verification.
    """
    def __init__(self, drone_id: str = "DRONE-001"):
        self.drone_id = drone_id
        self.state = DroneFlightState.STANDBY
        self.battery_percent: float = 85.0
        self.home_lat: float = settings.UAV_HOME_LAT
        self.home_lon: float = settings.UAV_HOME_LON
        self.home_alt: float = 0.0

        self.current_lat: float = self.home_lat
        self.current_lon: float = self.home_lon
        self.current_alt: float = 0.0
        self.current_speed: float = 0.0
        self.current_heading: float = 0.0

        self.target_lat: Optional[float] = None
        self.target_lon: Optional[float] = None
        self.target_zone_id: Optional[str] = None
        self.active_incident_id: Optional[str] = None
        self.mission_start_time: Optional[float] = None
        self.mission_reason: str = "Awaiting mission"

        self.arrival_radius_m: float = settings.UAV_ARRIVAL_RADIUS_M
        self.flight_trail: List[Dict[str, float]] = []
        self.aerial_verification_result: Optional[Dict[str, Any]] = None

        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start_simulation(self) -> None:
        with self._lock:
            if self._running:
                return
            self._running = True
            self._thread = threading.Thread(target=self._simulation_loop, daemon=True, name="DroneSimLoop")
            self._thread.start()
            logger.info(f"[{self.drone_id}] Simulation loop started.")

    def stop_simulation(self) -> None:
        with self._lock:
            self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def connect(self) -> bool:
        with self._lock:
            if self.state == DroneFlightState.DISCONNECTED:
                self.state = DroneFlightState.STANDBY
            return True

    def disconnect(self) -> None:
        with self._lock:
            self.state = DroneFlightState.DISCONNECTED

    def get_status(self) -> DroneFlightState:
        with self._lock:
            return self.state

    def get_position(self) -> Tuple[float, float, float]:
        with self._lock:
            return self.current_lat, self.current_lon, self.current_alt

    def get_battery(self) -> float:
        with self._lock:
            return round(self.battery_percent, 1)

    def set_battery(self, percent: float) -> None:
        """Helper for demo controls: simulate battery level (e.g. 19%)."""
        with self._lock:
            self.battery_percent = max(0.0, min(100.0, round(percent, 1)))
            logger.warning(f"[{self.drone_id}] Battery manually adjusted to {self.battery_percent}%")

    def dispatch_to_target(
        self,
        target_lat: float,
        target_lon: float,
        zone_id: str,
        incident_id: str
    ) -> Dict[str, Any]:
        """Validates mission and dispatches DRONE-001 to incident zone coordinates (Sections 16, 44)."""
        with self._lock:
            # Pre-flight safety checks (Section 35: Battery priority must override mission)
            if self.battery_percent <= settings.UAV_RTH_BATTERY_PERCENT:
                raise ValueError(
                    f"Dispatch refused: Battery {self.battery_percent}% is at or below safety minimum "
                    f"({settings.UAV_RTH_BATTERY_PERCENT}%). Return to home required."
                )

            if self.state not in (DroneFlightState.STANDBY, DroneFlightState.CHARGING):
                if self.state in (DroneFlightState.DISPATCHED, DroneFlightState.NAVIGATING, DroneFlightState.AERIAL_SCAN, DroneFlightState.TRACKING):
                    self.target_lat = target_lat
                    self.target_lon = target_lon
                    self.target_zone_id = zone_id
                    self.active_incident_id = incident_id
                    logger.info(f"[{self.drone_id}] Re-routing in-flight mission to {zone_id} ({target_lat}, {target_lon})")
                    self._sync_telemetry_broadcast()
                    return self.get_telemetry()
                raise ValueError(f"Cannot dispatch: {self.drone_id} is currently busy in state '{self.state.value}'")

            # Target validation
            if not target_lat or not target_lon or abs(target_lat) > 90 or abs(target_lon) > 180:
                raise ValueError(f"Invalid target zone coordinates: ({target_lat}, {target_lon})")

            self.target_lat = target_lat
            self.target_lon = target_lon
            self.target_zone_id = zone_id
            self.active_incident_id = incident_id
            self.mission_start_time = time.time()
            self.mission_reason = f"Intercept & verify incident {incident_id} in {zone_id}"
            self.state = DroneFlightState.DISPATCHED
            self.aerial_verification_result = None

        logger.warning(f"[{self.drone_id}] DISPATCH AUTHORIZED -> Target: {zone_id} ({target_lat}, {target_lon}) for {incident_id}")
        self._sync_telemetry_broadcast()
        return self.get_telemetry()

    def start_scan(self) -> Dict[str, Any]:
        with self._lock:
            if self.state in (DroneFlightState.ARRIVED, DroneFlightState.NAVIGATING, DroneFlightState.STANDBY):
                self.state = DroneFlightState.AERIAL_SCAN
                logger.info(f"[{self.drone_id}] Commencing aerial optical/thermal scan over {self.target_zone_id}")
        self._sync_telemetry_broadcast()
        return self.get_telemetry()

    def return_home(self, reason: str = "Operator command") -> Dict[str, Any]:
        with self._lock:
            if self.state in (DroneFlightState.STANDBY, DroneFlightState.CHARGING, DroneFlightState.DISCONNECTED):
                return self.get_telemetry()

            self.state = DroneFlightState.RETURNING
            self.mission_reason = f"Return to Base (RTH): {reason}"
            logger.info(f"[{self.drone_id}] Commencing Return-to-Home. ({reason})")

        self._sync_telemetry_broadcast()
        return self.get_telemetry()

    def abort_mission(self, reason: str = "Operator abort") -> Dict[str, Any]:
        return self.return_home(reason=reason)

    def spin_blades_idle(self, duration_sec: float = 3.0, throttle: int = 15) -> bool:
        """Simulates physical rotor verification test with low idle rotation."""
        logger.info(f"[{self.drone_id}] Simulated rotor verification active: throttle={throttle}, duration={duration_sec}s")
        # Also attempt live drone core spin if socket available
        try:
            from backend.uav.drone_comm import drone_core
            drone_core.spin_blades_idle(duration_sec=duration_sec, throttle=throttle)
        except Exception:
            pass
        return True

    def _simulation_loop(self) -> None:
        """Background thread updating drone kinematics, battery, and flight state."""
        while self._running:
            try:
                with self._lock:
                    self._tick_flight_dynamics()
                self._sync_telemetry_broadcast()
                time.sleep(1.0)
            except Exception as e:
                logger.error(f"[{self.drone_id}] Error in flight simulation tick: {e}", exc_info=True)

    def _tick_flight_dynamics(self) -> None:
        now = time.time()

        # 1. Docked Charging State (Section 36)
        if self.state in (DroneFlightState.STANDBY, DroneFlightState.CHARGING):
            if self.battery_percent < 100.0:
                self.state = DroneFlightState.CHARGING
                self.battery_percent = min(100.0, round(self.battery_percent + 0.4, 1))
            else:
                self.state = DroneFlightState.STANDBY
            self.current_alt = 0.0
            self.current_speed = 0.0
            self.current_lat = self.home_lat
            self.current_lon = self.home_lon
            gps_manager.sim_provider.update_position(self.current_lat, self.current_lon, 0.0, 0.0, 0.0)
            return

        # 2. Active Flight Battery Drain & Failsafe Rule (Section 34, 35)
        self.battery_percent = max(0.0, round(self.battery_percent - 0.2, 1))
        if self.battery_percent <= settings.UAV_RTH_BATTERY_PERCENT and self.state != DroneFlightState.RETURNING and self.state != DroneFlightState.LANDING:
            logger.warning(f"[{self.drone_id}] CRITICAL BATTERY SAFETY FAILSAFE: Battery <= {settings.UAV_RTH_BATTERY_PERCENT}%. Aborting mission -> RTH!")
            self.state = DroneFlightState.RETURNING
            self.mission_reason = f"LOW BATTERY ({self.battery_percent}%) AUTOMATIC RTH"

        # Record GPS trail
        self.flight_trail.append({"lat": round(self.current_lat, 6), "lon": round(self.current_lon, 6)})
        if len(self.flight_trail) > 50:
            self.flight_trail.pop(0)

        # 3. State Machine Transitions
        # State A: DISPATCHED -> Climbs to cruising altitude
        if self.state == DroneFlightState.DISPATCHED:
            self.current_alt = min(45.0, self.current_alt + 35.0)
            self.current_speed = 8.0
            if self.current_alt >= 35.0:
                self.state = DroneFlightState.NAVIGATING
                logger.info(f"[{self.drone_id}] Cruising altitude reached (45m AGL). Navigating to zone {self.target_zone_id}.")

        # State B: NAVIGATING -> Moves toward target zone coordinates
        if self.state == DroneFlightState.NAVIGATING:
            self.current_alt = 45.0
            self.current_speed = 14.0

            if self.target_lat and self.target_lon:
                nav = navigation_service.evaluate_navigation(
                    current_lat=self.current_lat,
                    current_lon=self.current_lon,
                    target_lat=self.target_lat,
                    target_lon=self.target_lon,
                    arrival_radius_m=self.arrival_radius_m
                )
                self.current_heading = nav["bearing_deg"]

                # Step coordinates toward target
                step_factor = 0.22
                self.current_lat += (self.target_lat - self.current_lat) * step_factor
                self.current_lon += (self.target_lon - self.current_lon) * step_factor

                # Arrival check (Section 27)
                if nav["has_arrived"]:
                    self.state = DroneFlightState.ARRIVED
                    self.current_speed = 3.0
                    logger.info(f"[{self.drone_id}] ARRIVAL DETECTED: Within {self.arrival_radius_m}m of target zone {self.target_zone_id}!")

        # State C: ARRIVED -> Safe scan state -> Transition to AERIAL_SCAN
        elif self.state == DroneFlightState.ARRIVED:
            self.current_speed = 3.0
            self.state = DroneFlightState.AERIAL_SCAN
            logger.info(f"[{self.drone_id}] Activating aerial optical camera & search sweep in {self.target_zone_id}...")

        # State D: AERIAL_SCAN -> Searches target area and visually identifies intruder (Section 32)
        elif self.state == DroneFlightState.AERIAL_SCAN:
            self.current_alt = 35.0
            self.current_speed = 4.5
            # Small search orbit
            orbit_step = (now % 30.0) * 0.25
            if self.target_lat and self.target_lon:
                self.current_lat = self.target_lat + 0.0003 * math.sin(orbit_step)
                self.current_lon = self.target_lon + 0.0003 * math.cos(orbit_step)

            # Verification trigger after 5 seconds of scanning
            if now - (self.mission_start_time or now) > 6.0 and self.aerial_verification_result is None:
                self.state = DroneFlightState.VERIFICATION
                self.aerial_verification_result = {
                    "target_zone": self.target_zone_id or "ZONE-002",
                    "person": "UNKNOWN",
                    "confidence": 0.91,
                    "authorization": "UNAUTHORIZED",
                    "status": "INCIDENT CONFIRMED",
                    "verified_at": datetime.now(timezone.utc).isoformat(),
                    "notes": "Target confirmed visually by aerial FLIR payload at target zone coordinates."
                }
                logger.warning(f"[{self.drone_id}] AERIAL VERIFICATION COMPLETE: {self.aerial_verification_result['status']}")

                # Update incident in database
                try:
                    from backend.events.incident_service import incident_service
                    if self.active_incident_id:
                        incident_service.confirm_aerial_verification(
                            self.active_incident_id, self.aerial_verification_result
                        )
                except Exception as ex:
                    logger.debug(f"[DRONE] Incident verification update bypass: {ex}")

        # State E: VERIFICATION -> TRACKING
        elif self.state == DroneFlightState.VERIFICATION:
            self.state = DroneFlightState.TRACKING
            logger.info(f"[{self.drone_id}] Target verified. Entering TRACKING / MONITORING state.")

        # State F: TRACKING / MONITORING -> Loiters over sector
        elif self.state == DroneFlightState.TRACKING:
            self.current_alt = 35.0
            self.current_speed = 3.5
            # If tracking has persisted for > 20s, automatically return home
            if now - (self.mission_start_time or now) > 28.0:
                self.state = DroneFlightState.RETURNING
                logger.info(f"[{self.drone_id}] Monitoring window elapsed. Returning to Home Outpost.")

        # State G: RETURNING -> Navigates back to home station
        elif self.state == DroneFlightState.RETURNING:
            self.current_speed = 15.0
            self.current_alt = max(15.0, self.current_alt - 2.5)

            nav = navigation_service.evaluate_navigation(
                current_lat=self.current_lat,
                current_lon=self.current_lon,
                target_lat=self.home_lat,
                target_lon=self.home_lon,
                arrival_radius_m=12.0
            )
            self.current_heading = nav["bearing_deg"]
            self.current_lat += (self.home_lat - self.current_lat) * 0.28
            self.current_lon += (self.home_lon - self.current_lon) * 0.28

            if nav["has_arrived"]:
                self.state = DroneFlightState.LANDING
                logger.info(f"[{self.drone_id}] Overhead Home Outpost. Commencing automated descent & landing.")

        # State H: LANDING -> Descends to dock
        elif self.state == DroneFlightState.LANDING:
            self.current_alt = max(0.0, self.current_alt - 5.0)
            self.current_speed = 1.0
            if self.current_alt <= 0.5:
                self.current_alt = 0.0
                self.current_speed = 0.0
                self.current_lat = self.home_lat
                self.current_lon = self.home_lon
                self.state = DroneFlightState.CHARGING
                self.target_lat = None
                self.target_lon = None
                self.target_zone_id = None
                self.active_incident_id = None
                logger.info(f"[{self.drone_id}] DOCKED at charging base station. State: CHARGING.")

        # Update simulated GPS provider with current drone coordinates
        gps_manager.sim_provider.update_position(
            lat=self.current_lat,
            lon=self.current_lon,
            alt=self.current_alt,
            speed=self.current_speed,
            heading=self.current_heading
        )

    def _sync_telemetry_broadcast(self) -> None:
        """Broadcasts real-time UAV telemetry over WebSocket."""
        try:
            ws_manager.broadcast_sync({
                "type": "UAV_TELEMETRY_UPDATE",
                "telemetry": self.get_telemetry()
            })
        except Exception:
            pass

    def get_telemetry(self) -> Dict[str, Any]:
        with self._lock:
            # Compute distance and bearing if navigating or on mission
            dist_formatted = "--"
            bearing_formatted = "--"
            dist_m = 0.0
            bearing_deg = 0.0

            if self.target_lat and self.target_lon:
                nav = navigation_service.evaluate_navigation(
                    current_lat=self.current_lat,
                    current_lon=self.current_lon,
                    target_lat=self.target_lat,
                    target_lon=self.target_lon,
                    arrival_radius_m=self.arrival_radius_m
                )
                dist_m = nav["distance_m"]
                dist_formatted = nav["distance_formatted"]
                bearing_deg = nav["bearing_deg"]
                bearing_formatted = nav["bearing_formatted"]

            gps_telem = gps_manager.get_telemetry()

            return {
                "drone_id": self.drone_id,
                "uav_id": self.drone_id,
                "mode": settings.DRONE_MODE,
                "state": self.state.value,
                "battery_percent": round(self.battery_percent, 1),
                "is_low_battery": self.battery_percent <= settings.UAV_RTH_BATTERY_PERCENT,
                "battery_status": (
                    "CHARGING" if self.state == DroneFlightState.CHARGING else (
                        "LOW BATTERY - RTH" if self.battery_percent <= settings.UAV_RTH_BATTERY_PERCENT else "NORMAL"
                    )
                ),
                "current_zone": self.target_zone_id or "BASE_STATION",
                "active_incident_id": self.active_incident_id,
                "latitude": round(self.current_lat, 6),
                "longitude": round(self.current_lon, 6),
                "altitude_m": round(self.current_alt, 1),
                "speed_mps": round(self.current_speed, 1),
                "heading_deg": round(self.current_heading, 1),
                "target_lat": round(self.target_lat, 6) if self.target_lat else None,
                "target_lon": round(self.target_lon, 6) if self.target_lon else None,
                "distance_to_target": dist_formatted,
                "distance_m": dist_m,
                "target_bearing": bearing_formatted,
                "target_bearing_deg": bearing_deg,
                "mission_reason": self.mission_reason,
                "is_airborne": self.state not in (
                    DroneFlightState.STANDBY, DroneFlightState.CHARGING, DroneFlightState.DISCONNECTED
                ),
                "flight_trail": self.flight_trail[-30:],
                "aerial_verification": self.aerial_verification_result,
                "gps": gps_telem,
                "gps_fix": gps_telem.get("fix_status", "3D DGPS FIX"),
                "fix_status": gps_telem.get("fix_status", "3D DGPS FIX"),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }


class LiveDroneProvider(DroneProvider):
    """
    Physical Hardware Drone Controller Provider for RC FPV Protocol (Section 25).
    Interfaces directly with DroneControllerCore on UDP 192.168.1.1:7099 and RTSP 7070.
    """
    def __init__(self, drone_id: str = "DRONE-001"):
        self.drone_id = drone_id
        self.state = DroneFlightState.STANDBY
        self._drone_core = None

    @property
    def core(self):
        if self._drone_core is None:
            from backend.uav.drone_comm import drone_core
            self._drone_core = drone_core
        return self._drone_core

    def connect(self) -> bool:
        logger.info("[LIVE DRONE] Connecting to physical drone at 192.168.1.1:7099...")
        res = self.core.connect()
        self.state = DroneFlightState.STANDBY if res else DroneFlightState.DISCONNECTED
        return res

    def disconnect(self) -> None:
        self.core.disconnect()
        self.state = DroneFlightState.DISCONNECTED

    def get_status(self) -> DroneFlightState:
        st = self.core.get_status()
        if not st.get("connected"):
            return DroneFlightState.DISCONNECTED
        return self.state

    def get_position(self) -> Tuple[float, float, float]:
        lat, lon = gps_manager.get_position()
        return lat, lon, gps_manager.get_altitude()

    def get_battery(self) -> float:
        return 100.0

    def spin_blades_idle(self, duration_sec: float = 3.0, throttle: int = 15) -> bool:
        """Rotates drone rotors at lowest idle speed without flying."""
        logger.info(f"[LIVE DRONE] Executing rotor idle verification: throttle={throttle}, duration={duration_sec}s")
        return self.core.spin_blades_idle(duration_sec=duration_sec, throttle=throttle)

    def dispatch_to_target(self, target_lat: float, target_lon: float, zone_id: str, incident_id: str) -> Dict[str, Any]:
        logger.info(f"[LIVE DRONE] Physical dispatch to {zone_id} ({target_lat}, {target_lon})")
        self.state = DroneFlightState.DISPATCHED
        # Trigger safe rotor test on dispatch verification
        self.spin_blades_idle(duration_sec=3.0, throttle=15)
        return self.get_telemetry()

    def start_scan(self) -> Dict[str, Any]:
        self.state = DroneFlightState.AERIAL_SCAN
        return self.get_telemetry()

    def return_home(self, reason: str = "Operator command") -> Dict[str, Any]:
        self.core.trigger_safe_land()
        self.state = DroneFlightState.RETURNING
        return self.get_telemetry()

    def abort_mission(self, reason: str = "Operator abort") -> Dict[str, Any]:
        self.core.trigger_emergency_stop()
        self.state = DroneFlightState.EMERGENCY
        return self.get_telemetry()

    def get_telemetry(self) -> Dict[str, Any]:
        lat, lon = gps_manager.get_position()
        core_st = self.core.get_status() if self._drone_core else {}
        return {
            "drone_id": self.drone_id,
            "uav_id": self.drone_id,
            "mode": "LIVE",
            "state": self.state.value,
            "battery_percent": 100.0,
            "latitude": lat,
            "longitude": lon,
            "altitude_m": gps_manager.get_altitude(),
            "speed_mps": gps_manager.get_speed(),
            "heading_deg": gps_manager.get_heading(),
            "rtsp_url": "rtsp://192.168.1.1:7070/webcam",
            "drone_core_status": core_st,
            "gps": gps_manager.get_telemetry(),
            "gps_fix": gps_manager.get_telemetry().get("fix_status", "3D DGPS FIX"),
            "fix_status": gps_manager.get_telemetry().get("fix_status", "3D DGPS FIX"),
            "notes": "PHYSICAL RC FPV DRONE INTERFACE ACTIVE (192.168.1.1:7099, RTSP 7070)"
        }


class DroneManager:
    """Singleton Drone Manager dispatching commands to active DroneProvider."""
    _instance: Optional['DroneManager'] = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(DroneManager, cls).__new__(cls)
                cls._instance.sim_provider = SimulationDroneProvider(settings.DRONE_ID)
                cls._instance.live_provider = LiveDroneProvider(settings.DRONE_ID)
                cls._instance.mode = settings.DRONE_MODE
                cls._instance._initialized = False
            return cls._instance

    def initialize(self) -> None:
        with self._lock:
            if self._initialized:
                return
            self.sim_provider.start_simulation()
            self._initialized = True
            logger.info(f"[DRONE] DroneManager initialized with {settings.DRONE_ID} in {self.mode} mode.")

    @property
    def provider(self) -> DroneProvider:
        if self.mode == "LIVE":
            return self.live_provider
        return self.sim_provider

    def set_mode(self, mode: str) -> None:
        with self._lock:
            m = mode.upper()
            if m not in ("SIMULATION", "LIVE"):
                raise ValueError("Mode must be 'SIMULATION' or 'LIVE'")
            self.mode = m
            logger.info(f"[DRONE] Drone mode set to {self.mode}")

    def get_telemetry(self) -> Dict[str, Any]:
        return self.provider.get_telemetry()

    def dispatch(self, target_lat: float, target_lon: float, zone_id: str, incident_id: str) -> Dict[str, Any]:
        return self.provider.dispatch_to_target(target_lat, target_lon, zone_id, incident_id)

    def return_home(self, reason: str = "Operator recall") -> Dict[str, Any]:
        return self.provider.return_home(reason)

    def abort(self, reason: str = "Operator abort") -> Dict[str, Any]:
        return self.provider.abort_mission(reason)

    def start_scan(self) -> Dict[str, Any]:
        return self.provider.start_scan()

    def spin_blades_idle(self, duration_sec: float = 3.0, throttle: int = 15) -> Dict[str, Any]:
        if hasattr(self.provider, "spin_blades_idle"):
            self.provider.spin_blades_idle(duration_sec=duration_sec, throttle=throttle)
        else:
            from backend.uav.drone_comm import drone_core
            drone_core.spin_blades_idle(duration_sec=duration_sec, throttle=throttle)
        return {"status": "SUCCESS", "message": "Rotors spun at lowest idle for verification (No flight)"}


drone_manager = DroneManager()
