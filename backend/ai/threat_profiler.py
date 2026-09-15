import time
import math
from typing import List, Tuple, Optional, Dict
import cv2
import numpy as np

from backend.ai.tracker_interface import TrackedObject
from backend.config import get_settings
from backend.logger import logger

class ThreatProfiler:
    """
    Evaluates real-time threat indices for tracked objects:
    - Analyzes loitering duration inside warning & restricted sectors.
    - Directional vector & approach velocity threat index calculation.
    - Gaussian privacy blurring for civilian data minimization (Section 46).
    """

    def __init__(self):
        self._stationary_track_positions: Dict[int, Tuple[float, float, float]] = {}  # track_id -> (cx, cy, first_stationary_ts)

    def evaluate_track_threat(
        self,
        track: TrackedObject,
        zone_type: str = "NORMAL",
        radial_speed_mps: float = 0.0,
        now: Optional[float] = None
    ) -> Tuple[float, bool]:
        """
        Calculates normalized threat score (0.05 to 0.99) and loitering flag.

        Returns:
            (threat_score, is_loitering)
        """
        settings = get_settings()
        current_time = now if now is not None else time.time()

        # 1. Base Score by Zone Classification
        if zone_type == "RESTRICTED" or track.intrusion_state in ("RESTRICTED_ENTRY", "ACTIVE_EVENT"):
            base_score = 0.82
        elif zone_type == "WARNING" or track.intrusion_state in ("WARNING", "APPROACHING"):
            base_score = 0.48
        else:
            base_score = 0.12

        # 2. Loitering Analysis
        is_loitering = False
        duration_in_zone = max(0.0, current_time - track.first_seen)
        loiter_thresh = settings.LOITERING_THRESHOLD_SECONDS

        if zone_type in ("WARNING", "RESTRICTED") and duration_in_zone >= loiter_thresh:
            is_loitering = True
            base_score += min(0.18, 0.05 + 0.02 * (duration_in_zone - loiter_thresh))

        # 3. Approach Velocity Vector Boost
        # Positive radial speed towards sensor or large negative speed (approaching border fence)
        effective_speed = abs(radial_speed_mps) if radial_speed_mps != 0 else (track.speed / 100.0)
        if effective_speed > 1.5:
            base_score += min(0.15, 0.05 * effective_speed)

        # 4. Vehicle Class Multiplier
        if track.class_name in ("car", "truck", "bus", "motorcycle"):
            base_score *= 1.10

        # Clamp between 0.05 and 0.99
        final_score = round(float(np.clip(base_score, 0.05, 0.99)), 2)
        return final_score, is_loitering

    def apply_privacy_blur(
        self,
        frame: np.ndarray,
        tracks: List[TrackedObject],
        blur_factor: int = 51
    ) -> np.ndarray:
        """
        Applies privacy-preserving Gaussian blur over human bodies/faces
        when PRIVACY_BLUR_ENABLED is toggled on (Section 46 Data Minimization).
        """
        if frame is None or frame.size == 0 or not tracks:
            return frame

        out = frame.copy()
        h, w = out.shape[:2]
        kernel_size = blur_factor if blur_factor % 2 == 1 else blur_factor + 1

        for t in tracks:
            if t.class_name == "person":
                x1, y1, x2, y2 = t.box
                # Clamp coordinates to frame
                x1, y1 = max(0, x1), max(0, y1)
                x2, y2 = min(w, x2), min(h, y2)

                if (x2 - x1) > 4 and (y2 - y1) > 4:
                    roi = out[y1:y2, x1:x2]
                    blurred = cv2.GaussianBlur(roi, (kernel_size, kernel_size), 30)
                    out[y1:y2, x1:x2] = blurred

        return out

threat_profiler = ThreatProfiler()
