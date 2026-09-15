import time
import cv2
from typing import Optional

from backend.camera.base_camera import BaseCamera
from backend.logger import logger

class IPCamera(BaseCamera):
    """
    Network / IP Camera implementation for Smartphone camera or RTSP surveillance streams.
    Handles network reconnections and stream dropouts.
    """
    def __init__(
        self,
        camera_id: str = "CAM_02",
        name: str = "Smartphone Network Camera",
        source: str = "",
        target_fps: int = 30,
        zone_id: Optional[str] = "ZONE_C"
    ):
        super().__init__(
            camera_id=camera_id,
            name=name,
            camera_type="IP_CAMERA",
            source=source,
            target_fps=target_fps,
            zone_id=zone_id
        )
        self.reconnect_delay = 5.0

    def _run_capture_loop(self) -> None:
        """Acquisition loop for network stream."""
        logger.info(f"[{self.camera_id}] Starting IP camera loop for source '{self.source}'...")

        while self._running:
            now = time.time()
            # If recently pushed frames exist (via /push-frame or ingest_frame)
            if self.last_frame_timestamp and (now - self.last_frame_timestamp) < 4.5:
                self.status = "ONLINE"
                self.error_message = None
                time.sleep(0.5)
                continue

            # If source is empty or set to mobile web push streaming mode
            if not self.source or self.source.strip() in ("", "WEB_STREAM", "BROWSER_PUSH", "MOBILE_WEB"):
                self.status = "STANDBY"
                self.error_message = f"Waiting for {self.name} stream."
                time.sleep(1.0)
                continue

            self.status = "RECONNECTING"
            self.error_message = None

            cap = cv2.VideoCapture(self.source)
            if not cap.isOpened():
                self.status = "OFFLINE"
                self.error_message = f"Failed to connect to network stream: {self.source}"
                time.sleep(self.reconnect_delay)
                continue

            self.status = "ONLINE"
            self.error_message = None
            logger.info(f"[{self.camera_id}] Connected to IP stream: {self.source}")

            while self._running:
                t0 = time.time()
                ret, frame = cap.read()
                latency_ms = (time.time() - t0) * 1000.0

                if not ret or frame is None:
                    self.dropped_frames += 1
                    self.status = "DEGRADED"
                    self.error_message = "Network frame drop detected."
                    break

                self._update_telemetry(frame, latency_ms)

                elapsed = time.time() - t0
                sleep_time = (1.0 / self.target_fps) - elapsed
                if sleep_time > 0.001:
                    time.sleep(sleep_time)

            cap.release()
            if self._running:
                self.status = "RECONNECTING"
                time.sleep(self.reconnect_delay)

        self.status = "OFFLINE"
