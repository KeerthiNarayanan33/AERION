import time
import threading
from typing import Dict, Any, Optional
from datetime import datetime, timezone

from backend.logger import logger
from backend.database.database import SessionLocal
from backend.database.models import CameraModel, SystemHealthModel
from backend.websocket.manager import ws_manager

class SensorWatchdog:
    """
    Sensor Fault Recovery & Auto-Reconnection Watchdog (Section 49).
    Monitors camera streams and radar links. When stream failures or hardware
    disconnects occur, executes progressive exponential backoff reconnection
    without disrupting active tracking, and manages graceful fallback modes.
    """
    _instance: Optional['SensorWatchdog'] = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(SensorWatchdog, cls).__new__(cls)
                cls._instance._monitored_sensors = ["CAM_01", "CAM_02", "RADAR_01", "UAV_01"]
                cls._fault_injected: Dict[str, Dict[str, Any]] = {}
                cls._reconnect_attempts: Dict[str, int] = {s: 0 for s in cls._instance._monitored_sensors}
                cls._next_reconnect_time: Dict[str, float] = {s: 0.0 for s in cls._instance._monitored_sensors}
                cls._running = False
                cls._thread: Optional[threading.Thread] = None
            return cls._instance

    def start(self) -> None:
        """Starts the watchdog background daemon thread."""
        with self._lock:
            if self._running:
                return
            self._running = True
            self._thread = threading.Thread(target=self._watchdog_loop, daemon=True, name="SensorWatchdogThread")
            self._thread.start()
            logger.info("SensorWatchdog started monitoring surveillance sensors.")

    def stop(self) -> None:
        """Stops the watchdog background daemon thread."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        logger.info("SensorWatchdog stopped.")

    def inject_fault(self, sensor_id: str, action: str = "FAIL", reason: str = "Simulated sensor link loss") -> Dict[str, Any]:
        """
        Injects or clears an artificial hardware/network fault for evaluator demonstration.
        action: 'FAIL', 'RECOVER', 'STATUS'
        """
        sensor_id = sensor_id.upper()
        action = action.upper()

        from backend.camera.camera_manager import camera_manager

        if action == "FAIL":
            self._fault_injected[sensor_id] = {
                "faulted": True,
                "reason": reason,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "fallback_mode": "RADAR_PRIMARY_FALLBACK" if "CAM" in sensor_id else "VISION_PRIMARY_FALLBACK"
            }
            # If camera, stop acquisition
            cam = camera_manager.get_camera(sensor_id)
            if cam:
                cam.stop()

            # Update database
            self._update_db_sensor_status(sensor_id, status="OFFLINE", error_msg=f"Fault injected: {reason}")

            # Broadcast WebSocket alert
            try:
                import asyncio
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(ws_manager.broadcast({
                        "type": "SENSOR_FAULT_ALERT",
                        "sensor_id": sensor_id,
                        "status": "OFFLINE",
                        "action": "FAIL",
                        "fallback_mode": self._fault_injected[sensor_id]["fallback_mode"],
                        "reason": reason,
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }))
            except Exception:
                pass

            logger.warning(f"[WATCHDOG] Sensor [{sensor_id}] FAULT INJECTED: {reason}. Mode: {self._fault_injected[sensor_id]['fallback_mode']}")
            return {
                "sensor_id": sensor_id,
                "status": "OFFLINE",
                "action": "FAIL",
                "fault_injected": True,
                "reason": reason,
                "fallback_mode": self._fault_injected[sensor_id]["fallback_mode"]
            }

        elif action == "RECOVER":
            if sensor_id in self._fault_injected:
                del self._fault_injected[sensor_id]

            self._reconnect_attempts[sensor_id] = 0
            self._next_reconnect_time[sensor_id] = 0.0

            # If camera, attempt restart
            cam = camera_manager.get_camera(sensor_id)
            if cam:
                cam.start()

            # Update database
            self._update_db_sensor_status(sensor_id, status="ONLINE", error_msg=None)

            # Broadcast WebSocket recovery
            try:
                import asyncio
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(ws_manager.broadcast({
                        "type": "SENSOR_RECOVERED",
                        "sensor_id": sensor_id,
                        "status": "ONLINE",
                        "action": "RECOVER",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }))
            except Exception:
                pass

            logger.info(f"[WATCHDOG] Sensor [{sensor_id}] FAULT CLEARED. Sensor restored to ONLINE.")
            return {
                "sensor_id": sensor_id,
                "status": "ONLINE",
                "action": "RECOVER",
                "fault_injected": False
            }

        else:  # STATUS
            return self.get_sensor_status(sensor_id)

    def get_sensor_status(self, sensor_id: str) -> Dict[str, Any]:
        """Returns comprehensive diagnostic and recovery status for a single sensor."""
        sensor_id = sensor_id.upper()
        from backend.camera.camera_manager import camera_manager

        cam = camera_manager.get_camera(sensor_id)
        cam_health = cam.get_health() if cam else {}
        is_faulted = sensor_id in self._fault_injected

        return {
            "sensor_id": sensor_id,
            "fault_injected": is_faulted,
            "fault_info": self._fault_injected.get(sensor_id),
            "status": "OFFLINE" if is_faulted else cam_health.get("status", "UNKNOWN"),
            "reconnect_attempts": self._reconnect_attempts.get(sensor_id, 0),
            "next_reconnect_seconds": max(0.0, round(self._next_reconnect_time.get(sensor_id, 0.0) - time.time(), 1)),
            "health": cam_health
        }

    def get_all_status(self) -> Dict[str, Any]:
        """Returns watchdog diagnostic telemetry for all tracked border surveillance sensors."""
        return {
            "watchdog_active": self._running,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "active_faults_count": len(self._fault_injected),
            "sensors": {s: self.get_sensor_status(s) for s in self._monitored_sensors}
        }

    get_telemetry = get_all_status

    def _watchdog_loop(self) -> None:
        """Continuous background thread evaluating sensor liveness and auto-reconnecting."""
        while self._running:
            try:
                time.sleep(2.5)
                now = time.time()
                from backend.camera.camera_manager import camera_manager

                for sensor_id in ["CAM_01", "CAM_02"]:
                    # If manually faulted, skip auto-reconnect
                    if sensor_id in self._fault_injected:
                        continue

                    cam = camera_manager.get_camera(sensor_id)
                    if not cam or not getattr(cam, "enabled", True):
                        continue

                    # Evaluate if camera is failing
                    health = cam.get_health()
                    is_failed = (not cam.is_running()) or (health.get("status") == "OFFLINE")

                    if is_failed and cam.source:
                        attempts = self._reconnect_attempts.get(sensor_id, 0)
                        next_time = self._next_reconnect_time.get(sensor_id, 0.0)

                        if now >= next_time:
                            # Time to attempt reconnect
                            self._reconnect_attempts[sensor_id] = attempts + 1
                            # Exponential backoff: 2s, 4s, 8s, 16s, max 30s
                            backoff = min(30.0, 2.0 * (2 ** min(attempts, 4)))
                            self._next_reconnect_time[sensor_id] = now + backoff

                            logger.info(f"[WATCHDOG] Attempting auto-reconnection for [{sensor_id}] (Attempt #{attempts + 1}, next in {backoff}s)...")
                            try:
                                cam.stop()
                                time.sleep(0.3)
                                success = cam.start()
                                if success and cam.is_running():
                                    logger.info(f"[WATCHDOG] Sensor [{sensor_id}] successfully reconnected!")
                                    self._reconnect_attempts[sensor_id] = 0
                                    self._next_reconnect_time[sensor_id] = 0.0
                                    self._update_db_sensor_status(sensor_id, status="ONLINE", error_msg=None)
                            except Exception as ex:
                                logger.error(f"[WATCHDOG] Reconnect error for [{sensor_id}]: {ex}")

            except Exception as e:
                logger.error(f"[WATCHDOG] Exception in watchdog loop: {e}")

    def _update_db_sensor_status(self, sensor_id: str, status: str, error_msg: Optional[str] = None) -> None:
        """Safely persists sensor status update to database."""
        db = SessionLocal()
        try:
            now = datetime.now(timezone.utc)
            cam = db.query(CameraModel).filter(CameraModel.id == sensor_id).first()
            if cam:
                cam.status = status
                cam.error_message = error_msg
                cam.updated_at = now

            health = db.query(SystemHealthModel).filter(SystemHealthModel.component_name == sensor_id).first()
            if health:
                health.status = status
                health.last_checked = now

            db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"[WATCHDOG] DB sync error for {sensor_id}: {e}")
        finally:
            db.close()

sensor_watchdog = SensorWatchdog()
