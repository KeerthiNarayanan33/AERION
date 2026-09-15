import threading
from typing import Dict, Optional, List, Any
from datetime import datetime, timezone

from backend.camera.base_camera import BaseCamera
from backend.camera.webcam import WebcamCamera
from backend.camera.ip_camera import IPCamera
from backend.camera.uav_camera import UAVCamera
from backend.config import get_settings
from backend.database.database import SessionLocal
from backend.database.models import CameraModel, SystemHealthModel
from backend.logger import logger

settings = get_settings()

class CameraManager:
    """
    Unified manager orchestrating all visual surveillance feeds.
    Provides lifecycle control, camera indexing, telemetry synchronization,
    and access for AI inference consumers.
    """
    _instance: Optional['CameraManager'] = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(CameraManager, cls).__new__(cls)
                cls._instance._cameras: Dict[str, BaseCamera] = {}
                cls._instance._initialized = False
            return cls._instance

    def initialize(self) -> None:
        """Initializes default cameras and starts background capture loops."""
        with self._lock:
            if self._initialized:
                return

            logger.info("Initializing CameraManager...")

            # 1. Primary Fixed CCTV (Webcam)
            cam1 = WebcamCamera(
                camera_id="CAM_01",
                name="Primary Fixed CCTV",
                source=str(settings.CAMERA_DEFAULT_INDEX),
                target_fps=settings.CAMERA_FPS,
                width=settings.CAMERA_WIDTH,
                height=settings.CAMERA_HEIGHT,
                zone_id="ZONE_B"
            )

            # 2. Smartphone Network / IP Camera
            cam2 = IPCamera(
                camera_id="CAM_02",
                name="Smartphone Network Camera",
                source="",
                target_fps=settings.CAMERA_FPS,
                zone_id="ZONE_C"
            )

            # 3. UAV Verification Stream (Tactical Aerial Reconnaissance Feed)
            uav_cam = UAVCamera(
                camera_id="UAV_01",
                name="Recon Drone Stream",
                source="rtsp://192.168.1.1:7070/webcam",
                target_fps=settings.CAMERA_FPS,
                zone_id=None
            )

            self._cameras = {
                "CAM_01": cam1,
                "CAM_02": cam2,
                "UAV_01": uav_cam
            }

            # Start all cameras
            cam1.start()
            cam2.start()
            uav_cam.start()
            self._initialized = True
            logger.info("CameraManager initialized with CAM_01, CAM_02, and UAV_01 (rtsp://192.168.1.1:7070/webcam).")

    def get_camera(self, camera_id: str) -> Optional[BaseCamera]:
        """Retrieves active camera instance by ID."""
        return self._cameras.get(camera_id)

    def list_cameras(self) -> List[Dict[str, Any]]:
        """Returns diagnostic health telemetry for all cameras."""
        return [cam.get_health() for cam in self._cameras.values()]

    def update_camera_source(self, camera_id: str, new_source: str) -> bool:
        """Dynamically updates the source of a camera and restarts acquisition."""
        cam = self.get_camera(camera_id)
        if not cam:
            return False

        logger.info(f"Updating Camera [{camera_id}] source from '{cam.source}' to '{new_source}'...")
        cam.stop()
        cam.source = str(new_source).strip()
        cam.start()

        # Update Database
        db = SessionLocal()
        try:
            db_cam = db.query(CameraModel).filter(CameraModel.id == camera_id).first()
            if db_cam:
                db_cam.source = cam.source
                db.commit()
        finally:
            db.close()

        return True

    def sync_to_database(self) -> None:
        """Persists current measured camera metrics and health into database."""
        db = SessionLocal()
        try:
            now = datetime.now(timezone.utc)
            for cam_id, cam in self._cameras.items():
                health = cam.get_health()
                db_cam = db.query(CameraModel).filter(CameraModel.id == cam_id).first()
                if db_cam:
                    db_cam.status = health["status"]
                    db_cam.fps = health["actual_fps"]
                    db_cam.latency_ms = health["latency_ms"]
                    db_cam.resolution = health["resolution"]
                    db_cam.error_message = health["error_message"]
                    db_cam.updated_at = now

                # Also update SystemHealthModel
                health_rec = db.query(SystemHealthModel).filter(SystemHealthModel.component_name == cam_id).first()
                if health_rec:
                    health_rec.status = health["status"]
                    health_rec.last_checked = now
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"Error syncing camera metrics to database: {e}")
        finally:
            db.close()

    def stop_all(self) -> None:
        """Shuts down all active camera threads."""
        logger.info("Stopping all camera acquisition threads...")
        for cam in self._cameras.values():
            cam.stop()
        self._cameras.clear()
        self._initialized = False

camera_manager = CameraManager()
