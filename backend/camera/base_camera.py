import time
import threading
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, Generator, Tuple
import cv2
import numpy as np

from backend.camera.frame_buffer import RollingFrameBuffer
from backend.config import get_settings
from backend.logger import logger

settings = get_settings()

class BaseCamera(ABC):
    """
    Abstract Base Camera for all visual surveillance sources.
    Handles background capture thread, FPS telemetry, frame drops,
    rolling pre-event buffer, and MJPEG stream generation.
    """
    def __init__(
        self,
        camera_id: str,
        name: str,
        camera_type: str = "WEBCAM",
        source: str = "0",
        target_fps: int = 30,
        zone_id: Optional[str] = None
    ):
        self.camera_id = camera_id
        self.name = name
        self.camera_type = camera_type
        self.source = source
        self.target_fps = target_fps
        self.zone_id = zone_id

        # Operational Telemetry
        self.status = "OFFLINE"  # ONLINE, DEGRADED, OFFLINE, RECONNECTING
        self.actual_fps = 0.0
        self.latency_ms = 0.0
        self.resolution = "0x0"
        self.last_frame_timestamp: Optional[float] = None
        self.frame_count = 0
        self.dropped_frames = 0
        self.error_message: Optional[str] = None
        self.is_simulated = False
        self.enabled = True

        # Pre-event rolling ring buffer
        self.buffer = RollingFrameBuffer(
            fps=self.target_fps,
            buffer_seconds=settings.PRE_EVENT_SECONDS
        )

        # Threading & Control
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._lock = threading.Lock()
        self._latest_frame: Optional[np.ndarray] = None
        self._fps_timestamps: list = []

    def start(self) -> None:
        """Starts background frame acquisition thread."""
        with self._lock:
            if self._running:
                return
            self._running = True
            self.status = "RECONNECTING"
            self._thread = threading.Thread(
                target=self._run_capture_loop,
                name=f"Capture-{self.camera_id}",
                daemon=True
            )
            self._thread.start()
            logger.info(f"Camera [{self.camera_id}] capture thread started.")

    def stop(self) -> None:
        """Stops background frame acquisition."""
        with self._lock:
            self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self.status = "OFFLINE"
        logger.info(f"Camera [{self.camera_id}] capture stopped.")

    def is_running(self) -> bool:
        """Returns True if camera acquisition thread is currently executing."""
        return bool(self._running and self._thread and self._thread.is_alive())

    def get_frame(self) -> Optional[np.ndarray]:
        """Returns the most recent captured frame (copy) or None."""
        with self._lock:
            if self._latest_frame is None:
                return None
            return self._latest_frame.copy()

    def get_latest_frame(self) -> Optional[np.ndarray]:
        """Alias for get_frame."""
        return self.get_frame()

    def get_jpeg(self, quality: int = 80, annotated: bool = True) -> Optional[bytes]:
        """Encodes the latest frame as JPEG bytes, using AI annotated frame when available."""
        frame = None
        if annotated:
            try:
                from backend.ai.inference_manager import inference_manager
                frame = inference_manager.get_annotated_frame(self.camera_id)
            except Exception:
                frame = None

        if frame is None:
            frame = self.get_frame()
        if frame is None:
            frame = self._generate_offline_frame()

        success, encoded = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
        if not success:
            return None
        return encoded.tobytes()

    def generate_mjpeg_stream(self, fps_limit: int = 25, max_frames: Optional[int] = None) -> Generator[bytes, None, None]:
        """
        Yields multipart/x-mixed-replace JPEG frames for live browser streaming.
        Continuously yields live frames or tactical standby HUD frames without abrupt disconnection.
        Supports optional max_frames for finite streaming and unit tests.
        """
        delay = 1.0 / max(1, fps_limit)
        yielded_count = 0

        while True:
            if max_frames is not None and yielded_count >= max_frames:
                break

            t_start = time.time()
            jpeg_bytes = self.get_jpeg()
            if jpeg_bytes is not None:
                header = b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
                yield header + jpeg_bytes + b"\r\n"
            else:
                # Return tactical placeholder frame if camera is offline/initializing
                blank_frame = self._generate_offline_frame()
                _, encoded = cv2.imencode('.jpg', blank_frame)
                b_data = encoded.tobytes()
                header = b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
                yield header + b_data + b"\r\n"

            yielded_count += 1
            elapsed = time.time() - t_start
            # If camera is offline/standby, conserve CPU with a lower frame rate
            current_delay = delay if self.status == "ONLINE" else 0.25
            sleep_time = max(0.01, current_delay - elapsed)
            time.sleep(sleep_time)

    def _generate_offline_frame(self, text: Optional[str] = None) -> np.ndarray:
        """Generates a synthetic offline/standby HUD frame."""
        h, w = 480, 640
        frame = np.zeros((h, w, 3), dtype=np.uint8)
        # Background dark gradient
        frame[:] = (18, 12, 7)
        # Frame border
        cv2.rectangle(frame, (10, 10), (w - 10, h - 10), (40, 40, 40), 1)
        # Text
        display_text = text or f"{self.name} [{self.status}]"
        cv2.putText(frame, display_text, (40, h // 2 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (180, 180, 180), 2)
        cv2.putText(frame, f"SOURCE: {self.source}", (40, h // 2 + 25), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 100, 100), 1)
        cv2.putText(frame, time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()), (20, h - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 229, 255), 1)
        return frame

    def _update_telemetry(self, frame: np.ndarray, capture_latency_ms: float) -> None:
        """Updates FPS, latency, and pushes frame to rolling buffer."""
        now = time.time()
        with self._lock:
            self._latest_frame = frame
            self.last_frame_timestamp = now
            self.frame_count += 1
            self.latency_ms = round(capture_latency_ms, 1)

            # Update rolling FPS tracker
            self._fps_timestamps.append(now)
            cutoff = now - 1.0
            self._fps_timestamps = [t for t in self._fps_timestamps if t >= cutoff]
            self.actual_fps = round(float(len(self._fps_timestamps)), 1)

            h, w = frame.shape[:2]
            self.resolution = f"{w}x{h}"

        # Push to pre-event rolling buffer
        self.buffer.push(frame, timestamp=now)

    def ingest_frame(self, frame: np.ndarray, capture_latency_ms: float = 10.0) -> bool:
        """
        Directly injects an externally captured frame (e.g. from Mobile Phone WebRTC/HTML5 or push API).
        Automatically brings camera to ONLINE operational status and updates rolling buffers.
        """
        if frame is None or frame.size == 0:
            return False
        with self._lock:
            self.status = "ONLINE"
            self.error_message = None
        self._update_telemetry(frame, capture_latency_ms)
        return True

    def get_health(self) -> Dict[str, Any]:
        """Returns diagnostic health metrics for this camera."""
        now = time.time()
        is_stale = (
            self.last_frame_timestamp is not None
            and (now - self.last_frame_timestamp) > 3.0
        )
        effective_status = self.status
        if self._running and is_stale:
            effective_status = "DEGRADED"

        return {
            "camera_id": self.camera_id,
            "name": self.name,
            "type": self.camera_type,
            "source": self.source,
            "status": effective_status,
            "actual_fps": self.actual_fps,
            "target_fps": self.target_fps,
            "latency_ms": self.latency_ms,
            "resolution": self.resolution,
            "frame_count": self.frame_count,
            "dropped_frames": self.dropped_frames,
            "buffer_frames": self.buffer.current_size,
            "last_frame_at": self.last_frame_timestamp,
            "error_message": self.error_message,
            "is_simulated": self.is_simulated
        }

    @abstractmethod
    def _run_capture_loop(self) -> None:
        """Subclass implementation of the acquisition loop."""
        pass
