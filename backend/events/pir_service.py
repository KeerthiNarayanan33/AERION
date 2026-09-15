import time
import math
import threading
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone

from backend.config import get_settings
from backend.websocket.manager import ws_manager
from backend.logger import logger

settings = get_settings()

class PIRService:
    """
    Single PIR Passive Infrared Motion Sensor Service with ESP32 Serial & ByteTrack Radar Projection.
    - Monitors ESP32 hardware motion detector on COM6 serial.
    - When motion is detected, uses ByteTrack / YOLO AI tracker to identify person
      and calculates their position, injecting and rendering the target on the Radar UI.
    """
    _instance: Optional['PIRService'] = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(PIRService, cls).__new__(cls)
                cls._instance.sensor_id = "PIR-001"
                cls._instance.zone_id = settings.PIR_ZONE_ID
                cls._instance.mode = settings.PIR_MODE
                cls._instance.serial_port = getattr(settings, "PIR_SERIAL_PORT", "COM6")
                cls._instance.serial_baud = getattr(settings, "PIR_SERIAL_BAUD", 115200)
                cls._instance.is_motion_detected = False
                cls._instance.last_motion_time = 0.0
                cls._instance.trigger_count = 0
                cls._instance._serial_running = False
                cls._instance._serial_thread: Optional[threading.Thread] = None
                cls._instance._serial_connected = False
            return cls._instance

    def initialize(self) -> None:
        """Starts background ESP32 serial listener on COM6."""
        with self._lock:
            if self._serial_running:
                return
            self._serial_running = True
            self._serial_thread = threading.Thread(
                target=self._serial_listener_worker,
                daemon=True,
                name="ESP32-PIR-Serial"
            )
            self._serial_thread.start()
            logger.info(f"[PIR SENSOR] Serial listener thread started for port {self.serial_port}.")

    def _serial_listener_worker(self) -> None:
        """Reads serial stream from ESP32 over COM6 and triggers motion events."""
        try:
            import serial
        except ImportError:
            logger.warning("[PIR SENSOR] pyserial not installed; ESP32 live serial reader inactive.")
            return

        while self._serial_running:
            ser = None
            try:
                ser = serial.Serial(self.serial_port, self.serial_baud, timeout=1.0)
                self._serial_connected = True
                logger.info(f"[PIR SENSOR] Connected to ESP32 on {self.serial_port} @ {self.serial_baud} baud.")

                while self._serial_running:
                    line = ser.readline()
                    if line:
                        decoded = line.decode('utf-8', errors='ignore').strip()
                        if decoded:
                            logger.debug(f"[PIR SERIAL RAW] {decoded}")
                            # Recognize any common PIR detection signal from ESP32 firmware
                            upper = decoded.upper()
                            if any(k in upper for k in ["MOTION", "PIR", "TRIGGER", "DETECT", "1", "ALERT", "INTRUSION"]):
                                logger.info(f"[PIR SENSOR] ESP32 Motion event detected on {self.serial_port}: '{decoded}'")
                                self.trigger_motion(source=f"ESP32_{self.serial_port}")
                    time.sleep(0.02)
            except Exception as e:
                self._serial_connected = False
                logger.debug(f"[PIR SENSOR] Serial port {self.serial_port} waiting or idle: {e}")
                time.sleep(3.0)
            finally:
                if ser:
                    try:
                        ser.close()
                    except Exception:
                        pass

    def trigger_motion(self, source: Optional[str] = None) -> Dict[str, Any]:
        """
        Records a motion event from ESP32 / simulated PIR.
        Runs ByteTrack person localization, extracts target coordinate, and maps to Radar UI.
        """
        now = time.time()
        src = source or self.mode

        with self._lock:
            self.is_motion_detected = True
            self.last_motion_time = now
            self.trigger_count += 1

        # 1. ByteTrack & Person Localization Pipeline
        target_x = 0.4
        target_y = 3.6
        person_name = "PERSON"
        person_track_id = 1
        speed = -0.7

        try:
            from backend.ai.inference_manager import inference_manager
            tracks = inference_manager.get_latest_tracks("CAM_01")
            person_tracks = [t for t in tracks if getattr(t, "class_name", "") == "person"]

            if person_tracks:
                pt = person_tracks[0]
                person_track_id = pt.track_id
                person_name = getattr(pt, "identity", None) or "PERSON"
                cx, cy = pt.center
                bx1, by1, bx2, by2 = pt.box
                bh = max(30, by2 - by1)

                # Convert camera 2D coordinate to physical ground coordinate for Radar UI
                # Frame width is 1280, height is 720. Range: X in [-5.0, 5.0] meters, Y in [1.0, 7.5] meters
                norm_x = (cx / 1280.0) - 0.5
                target_x = round(norm_x * 6.0, 2)
                # Distance estimation based on bounding box height
                est_dist = 7.0 * (160.0 / bh)
                target_y = round(max(0.8, min(7.5, est_dist)), 2)
                speed = round(getattr(pt, "speed", 10.0) / 30.0, 2)
                if speed < 0.2:
                    speed = -0.6
            else:
                # Default active sector coordinates for PIR zone
                target_x = round(0.5 * math.sin(self.trigger_count * 0.4), 2)
                target_y = 3.5
        except Exception as ai_err:
            logger.debug(f"[PIR SENSOR] Optical ByteTrack correlation note: {ai_err}")

        # 2. Inject target into Radar Driver for immediate Radar HUD rendering
        try:
            from backend.radar.radar_driver import radar_driver
            radar_target = radar_driver.inject_single_target(
                target_id=person_track_id,
                x=target_x,
                y=target_y,
                speed=speed,
                name=person_name
            )
            logger.info(f"[PIR SENSOR] Person plotted on Radar UI -> T#{person_track_id} ({person_name}) at X={target_x}m, Y={target_y}m")

            # Broadcast Radar Target update
            active_targets = radar_driver.get_active_targets()
            ws_manager.broadcast_sync({
                "type": "RADAR_TARGETS_UPDATE",
                "sensor_id": "PIR_RADAR_FUSION",
                "targets": [t.to_dict() for t in active_targets],
                "pir_triggered": True,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
        except Exception as radar_err:
            logger.debug(f"[PIR SENSOR] Radar injection bypass: {radar_err}")

        payload = {
            "sensor_id": self.sensor_id,
            "zone_id": self.zone_id,
            "status": "MOTION_DETECTED",
            "source": src,
            "trigger_count": self.trigger_count,
            "tracked_person": {
                "track_id": person_track_id,
                "name": person_name,
                "x_meters": target_x,
                "y_meters": target_y,
                "speed_mps": speed
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "notes": f"PIR motion detected. ByteTrack tracked person '{person_name}' positioned at ({target_x}m, {target_y}m) on Radar UI."
        }

        logger.warning(f"[PIR SENSOR] Motion triggered on {self.sensor_id} ({self.zone_id}) via {src}.")

        # Broadcast over WebSocket
        ws_manager.broadcast_sync({
            "type": "PIR_MOTION_ALERT",
            "data": payload
        })

        return payload

    def get_status(self) -> Dict[str, Any]:
        """Returns current status and telemetry of PIR-001."""
        now = time.time()
        with self._lock:
            active = (now - self.last_motion_time) < 10.0 if self.last_motion_time > 0 else False
            return {
                "sensor_id": self.sensor_id,
                "zone_id": self.zone_id,
                "mode": self.mode,
                "serial_port": self.serial_port,
                "serial_baud": self.serial_baud,
                "serial_connected": self._serial_connected,
                "is_active": active,
                "status": "MOTION_DETECTED" if active else "QUIESCENT",
                "trigger_count": self.trigger_count,
                "last_motion_time": self.last_motion_time,
                "last_motion_iso": datetime.fromtimestamp(self.last_motion_time, timezone.utc).isoformat() if self.last_motion_time > 0 else None
            }

    def set_mode(self, mode: str) -> None:
        with self._lock:
            m = mode.upper()
            if m not in ("SIMULATION", "LIVE"):
                raise ValueError("PIR mode must be SIMULATION or LIVE")
            self.mode = m

pir_service = PIRService()
pir_service.initialize()
