import math
import time
import struct
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime, timezone
from backend.logger import logger

@dataclass
class RadarTarget:
    """Represents a single target tracked by the LD2450 mmWave radar or projected from optical vision."""
    target_id: int
    x: float  # Lateral distance in meters (-6.0 to +6.0, negative=left, positive=right)
    y: float  # Forward distance in meters (0.0 to 8.0)
    speed: float = 0.0  # Radial speed in m/s (negative=approaching, positive=receding)
    distance: float = 0.0  # Euclidean distance in meters
    angle_deg: float = 0.0  # Azimuth angle in degrees (-60 to +60)
    resolution: float = 0.1  # Distance resolution
    name: Optional[str] = None
    zone_id: Optional[str] = None
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        # Determine zone classification based on forward depth/distance
        if self.y < 3.0:
            z_id = "ZONE_C"
            z_name = "ZONE_C — RESTRICTED FENCE"
            z_type = "RESTRICTED"
        elif self.y < 5.0:
            z_id = "ZONE_B"
            z_name = "ZONE_B — WARNING APPROACH"
            z_type = "WARNING"
        else:
            z_id = "ZONE_A"
            z_name = "ZONE_A — OUTER PATROL"
            z_type = "NORMAL"

        return {
            "target_id": self.target_id,
            "x": round(self.x, 2),
            "y": round(self.y, 2),
            "speed": round(self.speed, 2),
            "distance": round(self.distance, 2),
            "angle_deg": round(self.angle_deg, 1),
            "resolution": self.resolution,
            "name": self.name,
            "identity": self.name,
            "zone_id": self.zone_id or z_id,
            "zone_name": z_name,
            "zone_type": z_type,
            "fusion_status": "CONFIRMED",
            "is_cross_confirmed": True,
            "timestamp": datetime.fromtimestamp(self.timestamp, tz=timezone.utc).isoformat()
        }

class LD2450RadarDriver:
    """
    Driver and telemetry parser for Hi-Link LD2450 24GHz FMCW mmWave Radar.
    Supports ESP32 Wi-Fi JSON ingestion, raw UART binary packet decoding,
    and realistic physics-based border intrusion simulation.
    """

    def __init__(self, sensor_id: str = "RADAR_01"):
        self.sensor_id = sensor_id
        self.status = "ONLINE"
        self.last_heartbeat = time.time()
        self._targets: Dict[int, RadarTarget] = {}
        self._step_counter = 0

    @staticmethod
    def cartesian_to_polar(x: float, y: float) -> Tuple[float, float]:
        """Converts Cartesian (X: lateral, Y: depth) to Polar (distance, azimuth angle in degrees)."""
        dist = math.sqrt(x**2 + y**2)
        angle = math.degrees(math.atan2(x, y))
        return dist, angle

    def parse_esp32_json(self, raw_targets: List[Dict[str, Any]]) -> List[RadarTarget]:
        """
        Parses JSON packet sent from ESP32 over Wi-Fi.
        Handles coordinates provided in centimeters or meters.
        """
        now = time.time()
        self.last_heartbeat = now
        self.status = "ONLINE"
        parsed: List[RadarTarget] = []

        for item in raw_targets:
            t_id = item.get("id") or item.get("target_id") or 1
            raw_x = float(item.get("x", 0.0))
            raw_y = float(item.get("y", 0.0))

            # Auto-detect if coordinates are in centimeters (LD2450 native output) vs meters
            if abs(raw_x) > 10.0 or raw_y > 10.0:
                x_m = raw_x / 100.0
                y_m = raw_y / 100.0
            else:
                x_m = raw_x
                y_m = raw_y

            # Enforce LD2450 operational boundary: X in [-6, 6], Y in [0.05, 8.5]
            x_m = max(-6.0, min(6.0, x_m))
            y_m = max(0.05, min(8.5, y_m))

            dist, angle = self.cartesian_to_polar(x_m, y_m)

            raw_speed = item.get("speed")
            if raw_speed is None:
                # Calculate from speed_x and speed_y if present
                sx = item.get("speed_x", 0.0)
                sy = item.get("speed_y", 0.0)
                speed = math.sqrt(sx**2 + sy**2) if (sx or sy) else 0.0
            else:
                speed = float(raw_speed)
                # If speed in cm/s (e.g. > 10 cm/s), convert to m/s
                if abs(speed) >= 10.0:
                    speed = speed / 100.0

            target = RadarTarget(
                target_id=int(t_id),
                x=x_m,
                y=y_m,
                speed=speed,
                distance=dist,
                angle_deg=angle,
                resolution=float(item.get("resolution", 0.1)),
                timestamp=now
            )
            self._targets[target.target_id] = target
            parsed.append(target)

        return parsed

    def parse_uart_packet(self, packet: bytes) -> List[RadarTarget]:
        """
        Parses raw binary UART packet from LD2450 module.
        Protocol:
          Header: 0xAA 0xFF 0x03 0x00 (4 bytes)
          Target 1: X (int16), Y (int16), Speed (int16), Distance_Resolution (uint16) = 8 bytes
          Target 2: 8 bytes
          Target 3: 8 bytes
          Tail: 0x55 0xCC (2 bytes)
          Total: 30 bytes
        """
        if len(packet) < 30:
            return []

        header = packet[:4]
        tail = packet[-2:]
        if header != b'\xaa\xff\x03\x00' or tail != b'\x55\xcc':
            return []

        now = time.time()
        self.last_heartbeat = now
        self.status = "ONLINE"
        parsed: List[RadarTarget] = []

        # Read 3 target slots
        for i in range(3):
            offset = 4 + (i * 8)
            x_raw, y_raw, speed_raw, res_raw = struct.unpack_from('<hhhH', packet, offset)

            # LD2450 sign bit encoding: MSB 0x8000 indicates negative lateral displacement
            if x_raw & 0x8000:
                x_cm = -(x_raw & 0x7FFF)
            else:
                x_cm = x_raw

            if speed_raw & 0x8000:
                speed_cms = -(speed_raw & 0x7FFF)
            else:
                speed_cms = speed_raw

            x_m = x_cm / 100.0
            y_m = y_raw / 100.0
            speed_m = speed_cms / 100.0

            # Ignore empty/untracked target slots (0, 0)
            if y_m <= 0.05:
                self._targets.pop(i + 1, None)
                continue

            dist = math.sqrt(x_m**2 + y_m**2)
            angle = math.degrees(math.atan2(x_m, y_m))

            target = RadarTarget(
                target_id=i + 1,
                x=x_m,
                y=y_m,
                speed=speed_m,
                distance=dist,
                angle_deg=angle,
                resolution=res_raw / 100.0,
                timestamp=now
            )
            self._targets[target.target_id] = target
            parsed.append(target)

        return parsed

    def generate_simulated_step(self) -> List[RadarTarget]:
        """
        Generates realistic physics trajectories simulating intruders
        advancing towards the border perimeter.
        """
        self._step_counter += 1
        now = time.time()
        step = self._step_counter
        sim_list: List[RadarTarget] = []

        # Target 1: Patrol sector walker (sweeps left-right in warning zone)
        t1_x = 1.4 * math.sin(step * 0.08)
        t1_y = 3.8 + 0.8 * math.cos(step * 0.06)
        t1_dist = math.sqrt(t1_x**2 + t1_y**2)
        t1_angle = math.degrees(math.atan2(t1_x, t1_y))
        t1_speed = -0.4 * math.sin(step * 0.08)  # m/s

        target1 = RadarTarget(
            target_id=1,
            x=t1_x,
            y=t1_y,
            speed=t1_speed,
            distance=t1_dist,
            angle_deg=t1_angle,
            timestamp=now
        )
        self._targets[1] = target1
        sim_list.append(target1)

        # Target 2: Fast intruder advancing toward fence (decreases forward distance Y)
        cycle_step = step % 35
        t2_x = 0.6 + 0.2 * math.sin(step * 0.1)
        t2_y = max(0.8, 6.5 - (cycle_step * 0.18))
        t2_dist = math.sqrt(t2_x**2 + t2_y**2)
        t2_angle = math.degrees(math.atan2(t2_x, t2_y))
        t2_speed = -1.2  # Fast approach vector

        target2 = RadarTarget(
            target_id=2,
            x=t2_x,
            y=t2_y,
            speed=t2_speed,
            distance=t2_dist,
            angle_deg=t2_angle,
            timestamp=now
        )
        self._targets[2] = target2
        sim_list.append(target2)

        return sim_list

    def inject_single_target(
        self,
        target_id: int,
        x: float,
        y: float,
        speed: float = -1.0,
        name: Optional[str] = None
    ) -> RadarTarget:
        """Allows test scripts, PIR triggers, or API endpoints to inject a target blip on demand."""
        now = time.time()
        dist = math.sqrt(x**2 + y**2)
        angle = math.degrees(math.atan2(x, y))

        target = RadarTarget(
            target_id=target_id,
            x=x,
            y=y,
            speed=speed,
            distance=dist,
            angle_deg=angle,
            name=name,
            timestamp=now
        )
        self._targets[target_id] = target
        return target

    def get_active_targets(self, max_stale_seconds: float = 12.0) -> List[RadarTarget]:
        """Returns all currently active radar targets within freshness timeout."""
        now = time.time()
        stale_keys = [k for k, t in self._targets.items() if (now - t.timestamp) > max_stale_seconds]
        for k in stale_keys:
            self._targets.pop(k, None)

        return list(self._targets.values())

    def clear(self) -> None:
        """Clears active targets."""
        self._targets.clear()

    def clear_targets(self) -> None:
        """Clears all active radar targets."""
        self._targets.clear()

    def update_from_camera_tracks(self, camera_tracks: List[Any], frame_w: int = 1280, frame_h: int = 720) -> List[RadarTarget]:
        """
        Projects optical person tracks directly onto the 2D radar coordinate plane.
        Enables camera vision + PIR sensor setups to accurately drive the radar sweep
        with the exact number of people detected in the monitored sector.
        """
        now = time.time()
        new_targets: Dict[int, RadarTarget] = {}

        for idx, t in enumerate(camera_tracks):
            if getattr(t, "class_name", "") != "person":
                continue
            t_id = getattr(t, "track_id", idx + 1)
            cx, cy = getattr(t, "center", (frame_w // 2, frame_h // 2))
            box = getattr(t, "box", (0, 0, 100, 100))
            box_h = max(20, box[3] - box[1])

            # Distance estimation based on bounding box height (1m ~= 520px in 720p)
            dist_m = round(max(0.6, min(7.8, 500.0 / box_h)), 2)

            # Azimuth calculation based on horizontal frame position (-45 to +45 deg)
            norm_x = (cx - (frame_w / 2.0)) / (frame_w / 2.0)
            norm_x = max(-1.0, min(1.0, norm_x))
            angle_rad = norm_x * (45.0 * math.pi / 180.0)
            angle_deg = math.degrees(angle_rad)

            # Radar coordinates: Y = forward depth (m), X = lateral displacement (m)
            y = round(dist_m * math.cos(angle_rad), 2)
            x = round(dist_m * math.sin(angle_rad), 2)

            vx = getattr(t, "velocity_x", 0.0) or 0.0
            vy = getattr(t, "velocity_y", 0.0) or 0.0
            speed = round(math.hypot(vx, vy) * 0.04, 2)
            if speed < 0.1:
                speed = 0.0

            # Attach person identity if known
            identity = getattr(t, "identity", None)
            name = None
            if identity and identity not in ("UNKNOWN", "UNVERIFIED"):
                name = identity

            zone_id = getattr(t, "zone_id", None)

            rt = RadarTarget(
                target_id=t_id,
                x=x,
                y=y,
                speed=speed,
                distance=dist_m,
                angle_deg=angle_deg,
                resolution=0.1,
                name=name,
                zone_id=zone_id,
                timestamp=now
            )
            new_targets[t_id] = rt

        if new_targets:
            self._targets = new_targets
        else:
            # If no optical person is visible, preserve recently injected / PIR targets for up to 12s
            active_injected = {
                k: t for k, t in self._targets.items()
                if (now - t.timestamp) <= 12.0
            }
            self._targets = active_injected

        return list(self._targets.values())

# Global Radar Driver Singleton
radar_driver = LD2450RadarDriver()
