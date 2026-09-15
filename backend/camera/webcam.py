import time
import math
import cv2
import numpy as np
from typing import Optional

from backend.camera.base_camera import BaseCamera
from backend.config import get_settings
from backend.logger import logger

settings = get_settings()

class WebcamCamera(BaseCamera):
    """
    OpenCV Webcam / USB Camera implementation.
    Operates in dedicated worker thread to ensure non-blocking acquisition.
    Provides automatic reconnection and graceful simulation fallback if hardware camera is unavailable.
    """
    def __init__(
        self,
        camera_id: str = "CAM_01",
        name: str = "Primary Fixed CCTV",
        source: str = "0",
        target_fps: int = 30,
        width: int = 1280,
        height: int = 720,
        zone_id: Optional[str] = "ZONE_B"
    ):
        super().__init__(
            camera_id=camera_id,
            name=name,
            camera_type="WEBCAM",
            source=source,
            target_fps=target_fps,
            zone_id=zone_id
        )
        self.req_width = width
        self.req_height = height
        self.reconnect_delay = 3.0
        self.flip_horizontal = getattr(settings, "WEBCAM_FLIP_HORIZONTAL", False)

    def _run_capture_loop(self) -> None:
        """Continuous frame acquisition loop running on dedicated background thread."""
        logger.info(f"[{self.camera_id}] Starting capture loop for source '{self.source}'...")

        while self._running:
            # Check if simulation source explicitly requested
            if str(self.source).lower() in ("sim", "simulation", "synthetic", "test"):
                self.is_simulated = True
                self.status = "ONLINE"
                self.error_message = None
                self._run_simulation_stream()
                continue

            # Parse device index
            try:
                device_index = int(self.source)
            except ValueError:
                device_index = 0

            cap = self._open_capture(device_index)

            if cap is None or not cap.isOpened():
                self.status = "DEGRADED" if settings.SYSTEM_MODE == "SIMULATION" else "OFFLINE"
                self.error_message = f"Unable to open camera hardware index {device_index}."
                logger.warning(f"[{self.camera_id}] {self.error_message}")

                # If simulation mode is active, run synthetic visual stream
                if settings.SYSTEM_MODE == "SIMULATION":
                    self.is_simulated = True
                    self.status = "ONLINE"
                    self._run_simulation_stream()
                    continue
                else:
                    self.status = "RECONNECTING"
                    time.sleep(self.reconnect_delay)
                    continue

            # Hardware camera connected successfully
            self.status = "ONLINE"
            self.error_message = None
            self.is_simulated = False
            logger.info(f"[{self.camera_id}] Hardware camera index {device_index} active.")

            consecutive_failures = 0
            while self._running:
                t0 = time.time()
                ret, frame = cap.read()
                latency_ms = (time.time() - t0) * 1000.0

                if not ret or frame is None:
                    consecutive_failures += 1
                    self.dropped_frames += 1
                    if consecutive_failures > 5:
                        self.status = "RECONNECTING"
                        self.error_message = f"Temporary frame read failure on camera {device_index}. Reconnecting..."
                        logger.warning(f"[{self.camera_id}] {self.error_message}")
                        cap.release()
                        time.sleep(1.0)
                        break
                    time.sleep(0.05)
                    continue

                consecutive_failures = 0

                # Un-mirror webcam feed if enabled
                if self.flip_horizontal and frame is not None and frame.size > 0:
                    frame = cv2.flip(frame, 1)

                # Detect occluded sensor / closed privacy shutter
                if frame is not None and frame.size > 0:
                    mean_val = float(np.mean(frame))
                    if mean_val < 1.0:
                        h, w = frame.shape[:2]
                        # Draw clear tactical advisory box
                        box_y1 = max(10, h // 2 - 60)
                        box_y2 = min(h - 10, h // 2 + 60)
                        cv2.rectangle(frame, (20, box_y1), (w - 20, box_y2), (18, 14, 10), -1)
                        cv2.rectangle(frame, (20, box_y1), (w - 20, box_y2), (68, 23, 255), 2)
                        cv2.putText(
                            frame,
                            f"HARDWARE CAMERA ACTIVE [DEVICE INDEX {device_index}]",
                            (40, h // 2 - 25),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.65,
                            (0, 229, 255),
                            2,
                            cv2.LINE_AA
                        )
                        cv2.putText(
                            frame,
                            "SENSOR OCCLUDED / PRIVACY SHUTTER CLOSED",
                            (40, h // 2 + 8),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.6,
                            (68, 23, 255),
                            2,
                            cv2.LINE_AA
                        )
                        cv2.putText(
                            frame,
                            "Slide open the physical laptop webcam slider switch above your screen",
                            (40, h // 2 + 40),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.5,
                            (220, 220, 220),
                            1,
                            cv2.LINE_AA
                        )

                self._update_telemetry(frame, latency_ms)

                # Regulate capture rate to target FPS
                elapsed = time.time() - t0
                target_period = 1.0 / self.target_fps
                sleep_time = target_period - elapsed
                if sleep_time > 0.001:
                    time.sleep(sleep_time)

            cap.release()
            if self._running:
                self.status = "RECONNECTING"
                time.sleep(self.reconnect_delay)

        self.status = "OFFLINE"

    def _open_capture(self, device_index: int) -> Optional[cv2.VideoCapture]:
        """Attempts to open camera with DirectShow on Windows, then default backend."""
        try:
            # Try DirectShow first on Windows
            cap = cv2.VideoCapture(device_index, cv2.CAP_DSHOW)
            if cap.isOpened():
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.req_width)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.req_height)
                cap.set(cv2.CAP_PROP_FPS, self.target_fps)
                return cap

            # Fallback to default backend
            cap = cv2.VideoCapture(device_index)
            if cap.isOpened():
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.req_width)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.req_height)
                cap.set(cv2.CAP_PROP_FPS, self.target_fps)
                return cap
        except Exception as e:
            logger.error(f"[{self.camera_id}] Error opening VideoCapture({device_index}): {e}")
        return None

    def _run_simulation_stream(self) -> None:
        """
        Generates realistic synthetic surveillance CCTV feed with timestamps,
        moving patrol objects, and zone HUD overlays when hardware camera is detached.
        """
        logger.info(f"[{self.camera_id}] Running synthetic visual surveillance feed...")
        w, h = 640, 480
        step = 0

        while self._running and self.is_simulated:
            t0 = time.time()
            step += 1

            # Render synthetic security camera background
            frame = np.zeros((h, w, 3), dtype=np.uint8)
            # Sky/Ground gradient
            frame[0:int(h*0.4)] = (25, 20, 15)
            frame[int(h*0.4):] = (35, 30, 25)

            # Draw Perimeter Fence lines
            cv2.line(frame, (0, int(h*0.4)), (w, int(h*0.4)), (60, 60, 60), 2)
            for x_line in range(0, w, 40):
                cv2.line(frame, (x_line, int(h*0.4)), (x_line, h), (45, 45, 45), 1)

            # Moving simulated patrol target
            target_x = int((w / 2) + (w * 0.35) * math.sin(step * 0.05))
            target_y = int(h * 0.65 + 20 * math.cos(step * 0.08))
            cv2.circle(frame, (target_x, target_y), 16, (0, 230, 118), -1)
            cv2.circle(frame, (target_x, target_y - 24), 8, (0, 230, 118), -1)
            cv2.putText(frame, "PATROL #01", (target_x - 30, target_y - 38), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 230, 118), 1)

            # CCTV HUD Overlay
            now_str = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
            cv2.putText(frame, f"CAM_01 [CCTV PRIMARY] - {now_str}", (15, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 229, 255), 1)
            cv2.putText(frame, "ZONE_B [WARNING APPROACH]", (15, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 171, 0), 1)
            cv2.putText(frame, "[SYNTHETIC BENCH FEED]", (w - 180, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (255, 171, 0), 1)

            latency_ms = (time.time() - t0) * 1000.0
            self._update_telemetry(frame, latency_ms)

            # Regulate to 30 FPS
            elapsed = time.time() - t0
            sleep_time = (1.0 / self.target_fps) - elapsed
            if sleep_time > 0.001:
                time.sleep(sleep_time)
