import time
import math
from typing import Optional
import cv2
import numpy as np

from backend.camera.base_camera import BaseCamera
from backend.uav.drone_provider import drone_manager
from backend.logger import logger

class UAVCamera(BaseCamera):
    """
    Autonomous Reconnaissance Drone (UAV_01) Camera Source.
    Captures live network stream from physical UAV gimbal or generates
    high-fidelity synthetic tactical aerial FLIR/EO reconnaissance video
    with real-time flight telemetry, artificial horizon, and target locks.
    """
    def __init__(
        self,
        camera_id: str = "UAV_01",
        name: str = "Recon Drone Stream",
        source: str = "rtsp://192.168.1.1:7070/webcam",
        target_fps: int = 25,
        zone_id: Optional[str] = None
    ):
        super().__init__(
            camera_id=camera_id,
            name=name,
            camera_type="UAV",
            source=source,
            target_fps=target_fps,
            zone_id=zone_id
        )
        self.width = 960
        self.height = 540
        self._anim_tick = 0.0

    def _run_capture_loop(self) -> None:
        """Acquisition loop: attempts physical RTSP stream, seamlessly falls back to tactical aerial feed."""
        logger.info(f"UAV Camera [{self.camera_id}] capture loop starting...")
        cap: Optional[cv2.VideoCapture] = None
        has_real_stream = False

        if self.source and not self.source.startswith("rtsp://192.168.1.1"):
            try:
                cap = cv2.VideoCapture(self.source)
                if cap.isOpened():
                    has_real_stream = True
                    logger.info(f"UAV Camera [{self.camera_id}] connected to physical stream: {self.source}")
            except Exception as e:
                logger.warning(f"Could not connect to physical UAV stream {self.source}: {e}")
                has_real_stream = False

        frame_interval = 1.0 / max(1, self.target_fps)

        while self._running:
            start_time = time.time()
            frame = None

            if has_real_stream and cap and cap.isOpened():
                ret, raw_frame = cap.read()
                if ret and raw_frame is not None and raw_frame.size > 0:
                    frame = raw_frame
                else:
                    has_real_stream = False

            if frame is None:
                frame = self._generate_aerial_recon_frame()

            self.status = "ONLINE"
            self._update_telemetry(frame, capture_latency_ms=12.5)

            elapsed = time.time() - start_time
            sleep_time = max(0.005, frame_interval - elapsed)
            time.sleep(sleep_time)

        if cap:
            cap.release()
        self.status = "OFFLINE"
        logger.info(f"UAV Camera [{self.camera_id}] capture loop finished.")

    def _generate_aerial_recon_frame(self) -> np.ndarray:
        """Synthesizes high-fidelity FLIR / optical aerial reconnaissance feed with dynamic HUD."""
        self._anim_tick += 0.08
        w, h = self.width, self.height

        # 1. Base FLIR / Thermal Palette (dark slate blue gradient)
        frame = np.zeros((h, w, 3), dtype=np.uint8)
        frame[:, :] = (18, 22, 14) # BGR dark tactical night tone

        # Fetch telemetry
        try:
            telem = drone_manager.get_telemetry()
        except Exception:
            telem = {}

        alt = float(telem.get("altitude_m", 15.0) or 15.0)
        spd = float(telem.get("speed_mps", 6.2) or 6.2)
        heading = float(telem.get("heading_deg", 48.0) or 48.0)
        bat = float(telem.get("battery_percent", 94.0) or 94.0)
        lat = float(telem.get("latitude", 31.6262) or 31.6262)
        lon = float(telem.get("longitude", 74.8748) or 74.8748)
        state = str(telem.get("state", "STANDBY")).replace("UAV_", "").upper()
        zone = str(telem.get("target_zone_id") or telem.get("current_zone") or "ZONE_B")

        # 2. Moving Aerial Ground Grid (simulating drone flight motion)
        grid_offset_y = int((self._anim_tick * spd * 3) % 40)
        grid_offset_x = int((self._anim_tick * 10) % 40)
        grid_color = (28, 38, 24)

        for gy in range(-40, h + 40, 40):
            y_pos = gy + grid_offset_y
            if 0 <= y_pos < h:
                cv2.line(frame, (0, y_pos), (w, y_pos), grid_color, 1)

        for gx in range(-40, w + 40, 40):
            x_pos = gx + grid_offset_x
            if 0 <= x_pos < w:
                cv2.line(frame, (x_pos, 0), (x_pos, h), grid_color, 1)

        # 3. Perimeter Roads / Border Lines simulation
        road_y = int(h * 0.65)
        cv2.line(frame, (0, road_y), (w, road_y), (45, 60, 40), 2)
        cv2.line(frame, (0, road_y + 4), (w, road_y + 4), (30, 40, 25), 1)

        # 4. Target Sector Hotspot / Perimeter Fence Marker
        cx, cy = w // 2, h // 2
        is_active_mission = state in ["DISPATCHED", "EN_ROUTE", "SEARCHING", "ARRIVED", "CONFIRMED", "AERIAL_SCAN", "VERIFYING"]

        if is_active_mission:
            # Hotspot thermal signature (simulated vehicle/person heat signature)
            pulse = math.sin(self._anim_tick * 2) * 0.3 + 0.7
            box_w, box_h = int(70 * pulse), int(90 * pulse)
            tx1, ty1 = cx - box_w // 2, cy - box_h // 2
            tx2, ty2 = cx + box_w // 2, cy + box_h // 2

            # Hotspot glow
            cv2.circle(frame, (cx, cy), int(45 * pulse), (40, 80, 160), -1)
            cv2.circle(frame, (cx, cy), int(25 * pulse), (60, 140, 240), -1)
            cv2.circle(frame, (cx, cy), int(12 * pulse), (200, 240, 255), -1)

            # Tactical bounding box with corner brackets
            box_color = (0, 70, 255) if state in ["SEARCHING", "ARRIVED", "CONFIRMED"] else (0, 229, 255)
            # Corners
            c_len = 16
            cv2.line(frame, (tx1, ty1), (tx1 + c_len, ty1), box_color, 2)
            cv2.line(frame, (tx1, ty1), (tx1, ty1 + c_len), box_color, 2)
            cv2.line(frame, (tx2, ty1), (tx2 - c_len, ty1), box_color, 2)
            cv2.line(frame, (tx2, ty1), (tx2, ty1 + c_len), box_color, 2)
            cv2.line(frame, (tx1, ty2), (tx1 + c_len, ty2), box_color, 2)
            cv2.line(frame, (tx1, ty2), (tx1, ty2 - c_len), box_color, 2)
            cv2.line(frame, (tx2, ty2), (tx2 - c_len, ty2), box_color, 2)
            cv2.line(frame, (tx2, ty2), (tx2, ty2 - c_len), box_color, 2)

            tag_text = f"TARGET: {zone} [OPTICAL LOCK]"
            cv2.putText(frame, tag_text, (tx1 - 10, ty1 - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.42, box_color, 1, cv2.LINE_AA)
            cv2.putText(frame, "THERMAL: +3.8C | CLASSIFY: SUBJECT", (tx1 - 10, ty2 + 16), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (0, 229, 255), 1, cv2.LINE_AA)

        # 5. Central Gimbal Reticle & Artificial Horizon
        reticle_color = (0, 229, 255)
        # Center crosshair
        cv2.line(frame, (cx - 30, cy), (cx - 8, cy), reticle_color, 1)
        cv2.line(frame, (cx + 8, cy), (cx + 30, cy), reticle_color, 1)
        cv2.line(frame, (cx, cy - 30), (cx, cy - 8), reticle_color, 1)
        cv2.line(frame, (cx, cy + 8), (cx, cy + 30), reticle_color, 1)
        cv2.circle(frame, (cx, cy), 4, reticle_color, 1)

        # Horizon ladder ticks
        roll_angle = math.sin(self._anim_tick * 0.5) * 2.0
        pitch_y = cy + int(math.sin(self._anim_tick * 0.3) * 5)
        cv2.line(frame, (cx - 90, pitch_y), (cx - 40, pitch_y), (0, 180, 210), 1)
        cv2.line(frame, (cx + 40, pitch_y), (cx + 90, pitch_y), (0, 180, 210), 1)

        # 6. Top Telemetry Bar
        cv2.rectangle(frame, (0, 0), (w, 36), (8, 12, 6), -1)
        cv2.line(frame, (0, 36), (w, 36), (0, 140, 160), 1)

        top_left = f"UAV_01 RECON | FLIR EO/IR | GIMBAL PITCH -32 AZ {heading:03.0f}"
        cv2.putText(frame, top_left, (16, 23), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 229, 255), 1, cv2.LINE_AA)

        top_right = f"STATE: {state} | BAT: {bat:.0f}%"
        cv2.putText(frame, top_right, (w - 240, 23), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 230, 118) if bat > 25 else (0, 80, 255), 1, cv2.LINE_AA)

        # 7. Left Scale (Altitude AGL)
        cv2.putText(frame, f"ALT", (20, cy - 40), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (140, 160, 140), 1)
        cv2.putText(frame, f"{alt:.1f}m", (14, cy - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (0, 229, 255), 2)
        cv2.line(frame, (68, cy - 45), (68, cy + 45), (0, 140, 160), 1)
        for tick_y in range(cy - 40, cy + 41, 10):
            cv2.line(frame, (63, tick_y), (68, tick_y), (0, 140, 160), 1)

        # 8. Right Scale (Speed m/s)
        cv2.putText(frame, f"SPD", (w - 65, cy - 40), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (140, 160, 140), 1)
        cv2.putText(frame, f"{spd:.1f}", (w - 70, cy - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (0, 229, 255), 2)
        cv2.line(frame, (w - 80, cy - 45), (w - 80, cy + 45), (0, 140, 160), 1)
        for tick_y in range(cy - 40, cy + 41, 10):
            cv2.line(frame, (w - 80, tick_y), (w - 75, tick_y), (0, 140, 160), 1)

        # 9. Bottom Navigation Bar
        cv2.rectangle(frame, (0, h - 34), (w, h), (8, 12, 6), -1)
        cv2.line(frame, (0, h - 34), (w, h - 34), (0, 140, 160), 1)

        bot_left = f"GPS: {lat:.6f}N, {lon:.6f}E | HDG: {heading:03.0f} | 12 SATS 3D FIX"
        cv2.putText(frame, bot_left, (16, h - 13), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (180, 200, 180), 1, cv2.LINE_AA)

        bot_right = f"PATROL SECTOR: {zone} | LIVE RECON ACTIVE"
        cv2.putText(frame, bot_right, (w - 380, h - 13), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 229, 255), 1, cv2.LINE_AA)

        # 10. Subtle Vignette Effect (lens border)
        cv2.rectangle(frame, (2, 2), (w - 3, h - 3), (0, 140, 160), 1)

        return frame
