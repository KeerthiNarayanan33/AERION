import math
import time
from typing import List, Dict, Tuple, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.radar.radar_driver import RadarTarget, radar_driver
from backend.logger import logger

@dataclass
class FusedTrack:
    """Represents a unified multi-sensor track produced by fusing radar and camera data."""
    fused_id: str
    camera_track_id: Optional[str] = None
    radar_target_id: Optional[int] = None
    class_name: str = "unknown"
    confidence: float = 0.0
    radar_x_m: float = 0.0
    radar_y_m: float = 0.0
    camera_u: float = 0.5  # Normalized [0, 1] horizontal position
    camera_v: float = 0.5  # Normalized [0, 1] vertical position
    radial_speed_mps: float = 0.0
    distance_m: float = 0.0
    is_cross_confirmed: bool = False
    fusion_status: str = "UNCONFIRMED"  # CONFIRMED, UNCONFIRMED_RADAR_ONLY, CAMERA_ONLY
    zone_id: Optional[str] = None
    last_updated: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fused_id": self.fused_id,
            "camera_track_id": self.camera_track_id,
            "radar_target_id": self.radar_target_id,
            "class_name": self.class_name,
            "confidence": round(self.confidence, 2),
            "radar_x": round(self.radar_x_m, 2),
            "radar_y": round(self.radar_y_m, 2),
            "camera_u": round(self.camera_u, 3),
            "camera_v": round(self.camera_v, 3),
            "speed": round(self.radial_speed_mps, 2),
            "distance": round(self.distance_m, 2),
            "is_cross_confirmed": self.is_cross_confirmed,
            "fusion_status": self.fusion_status,
            "zone_id": self.zone_id,
            "last_updated": datetime.fromtimestamp(self.last_updated, tz=timezone.utc).isoformat()
        }

class RadarCameraFusionEngine:
    """
    Real-time Multi-Sensor Data Fusion Engine (Level 1 & Level 2 JDL Fusion).
    Performs spatial projection between 24GHz radar polar space and optical camera viewport,
    cross-sensor track gating, fused confidence scoring, and camera blind spot failure detection.
    """

    def __init__(
        self,
        camera_hfov_deg: float = 70.0,
        radar_max_range_m: float = 8.0,
        association_gating_distance: float = 0.28
    ):
        self.camera_hfov_deg = camera_hfov_deg
        self.radar_max_range_m = radar_max_range_m
        self.association_gating_distance = association_gating_distance
        self._fused_tracks: Dict[str, FusedTrack] = {}

    def project_radar_to_camera(self, x_m: float, y_m: float) -> Tuple[float, float]:
        """
        Projects 2D radar Cartesian coordinates (X: lateral, Y: depth)
        into normalized camera viewport coordinates (u, v) in [0.0, 1.0].
        """
        depth = max(0.2, y_m)
        half_fov_rad = math.radians(self.camera_hfov_deg / 2.0)
        tan_half = max(0.01, math.tan(half_fov_rad))

        # Horizontal coordinate u: centered at 0.5
        norm_u = 0.5 + (x_m / (2.0 * depth * tan_half))
        norm_u = max(0.0, min(1.0, norm_u))

        # Vertical coordinate v: objects closer to sensor appear lower in frame (higher v)
        norm_v = 0.95 - 0.65 * (depth / self.radar_max_range_m)
        norm_v = max(0.1, min(0.98, norm_v))

        return norm_u, norm_v

    def fuse_frame(
        self,
        camera_tracks: List[Dict[str, Any]],
        radar_targets: List[RadarTarget],
        camera_status: str = "ONLINE"
    ) -> List[FusedTrack]:
        """
        Core fusion cycle:
        1. Projects radar targets into camera coordinate space.
        2. Computes Euclidean distance matrix in normalized viewport.
        3. Matches camera tracks with radar targets using spatial gating.
        4. Detects blind spots (unconfirmed radar targets while camera is degraded/missing).
        """
        now = time.time()
        fused_results: List[FusedTrack] = []
        matched_cam_ids = set()
        matched_radar_ids = set()

        # 1. Project all radar targets
        projected_radar: List[Tuple[RadarTarget, float, float]] = []
        for rt in radar_targets:
            u, v = self.project_radar_to_camera(rt.x, rt.y)
            projected_radar.append((rt, u, v))

        # 2. Match radar targets with camera tracks
        for rt, r_u, r_v in projected_radar:
            best_match = None
            best_dist = float('inf')

            for ct in camera_tracks:
                c_id = str(ct.get("track_id", ""))
                if c_id in matched_cam_ids:
                    continue

                # Camera normalized center
                c_u = ct.get("norm_x", 0.5)
                c_v = ct.get("norm_y", 0.5)

                spatial_dist = math.sqrt((r_u - c_u)**2 + (r_v - c_v)**2)
                if spatial_dist < best_dist and spatial_dist <= self.association_gating_distance:
                    best_dist = spatial_dist
                    best_match = ct

            if best_match is not None:
                # CROSS-CONFIRMED FUSED TRACK
                c_id = str(best_match.get("track_id", ""))
                matched_cam_ids.add(c_id)
                matched_radar_ids.add(rt.target_id)

                c_conf = float(best_match.get("confidence", 0.8))
                fused_conf = min(0.99, round(0.6 * c_conf + 0.4 * 0.90 + 0.12, 2))

                fused = FusedTrack(
                    fused_id=f"FUSED_RAD{rt.target_id}_CAM{c_id}",
                    camera_track_id=c_id,
                    radar_target_id=rt.target_id,
                    class_name=best_match.get("class_name", "person"),
                    confidence=fused_conf,
                    radar_x_m=rt.x,
                    radar_y_m=rt.y,
                    camera_u=best_match.get("norm_x", r_u),
                    camera_v=best_match.get("norm_y", r_v),
                    radial_speed_mps=rt.speed,
                    distance_m=rt.distance,
                    is_cross_confirmed=True,
                    fusion_status="CONFIRMED",
                    zone_id=best_match.get("zone_id"),
                    last_updated=now
                )
                fused_results.append(fused)
                self._fused_tracks[fused.fused_id] = fused

            else:
                # UNCONFIRMED RADAR-ONLY TRACK (Potential Camera Blind Spot / Occlusion)
                matched_radar_ids.add(rt.target_id)
                fused = FusedTrack(
                    fused_id=f"FUSED_RAD{rt.target_id}_ONLY",
                    camera_track_id=None,
                    radar_target_id=rt.target_id,
                    class_name="unidentified_target",
                    confidence=0.75,
                    radar_x_m=rt.x,
                    radar_y_m=rt.y,
                    camera_u=r_u,
                    camera_v=r_v,
                    radial_speed_mps=rt.speed,
                    distance_m=rt.distance,
                    is_cross_confirmed=False,
                    fusion_status="UNCONFIRMED_RADAR_ONLY",
                    zone_id="ZONE_B" if rt.y > 4.0 else "ZONE_C",
                    last_updated=now
                )
                fused_results.append(fused)
                self._fused_tracks[fused.fused_id] = fused

        # 3. Add Unmatched Camera Tracks (Optical Only, e.g. edge of camera FOV outside radar)
        for ct in camera_tracks:
            c_id = str(ct.get("track_id", ""))
            if c_id not in matched_cam_ids:
                fused = FusedTrack(
                    fused_id=f"FUSED_CAM{c_id}_ONLY",
                    camera_track_id=c_id,
                    radar_target_id=None,
                    class_name=ct.get("class_name", "person"),
                    confidence=float(ct.get("confidence", 0.7)),
                    radar_x_m=0.0,
                    radar_y_m=0.0,
                    camera_u=ct.get("norm_x", 0.5),
                    camera_v=ct.get("norm_y", 0.5),
                    radial_speed_mps=0.0,
                    distance_m=3.0,
                    is_cross_confirmed=False,
                    fusion_status="CAMERA_ONLY",
                    zone_id=ct.get("zone_id"),
                    last_updated=now
                )
                fused_results.append(fused)
                self._fused_tracks[fused.fused_id] = fused

        # 4. Check for Blind Zone Failure Anomaly
        self._check_blind_zone_anomalies(fused_results, camera_status)

        return fused_results

    def _check_blind_zone_anomalies(
        self,
        fused_list: List[FusedTrack],
        camera_status: str
    ) -> None:
        """
        Detects critical surveillance gap when radar targets breach perimeter
        without camera confirmation (e.g. camera offline, lens obscured, or dark).
        """
        unconfirmed = [f for f in fused_list if f.fusion_status == "UNCONFIRMED_RADAR_ONLY" and f.distance_m <= 6.0]
        if unconfirmed and camera_status != "ONLINE":
            for track in unconfirmed:
                logger.warning(
                    f"[FUSION BLIND ZONE] Radar detected unconfirmed target #{track.radar_target_id} "
                    f"at {track.distance_m}m while camera is {camera_status}! Dispatching UAV recommendation."
                )

    def get_latest_fused_tracks(self) -> List[Dict[str, Any]]:
        """Returns all currently active multi-sensor fused tracks."""
        now = time.time()
        # Clean tracks stale for > 3.0 seconds
        stale_keys = [k for k, t in self._fused_tracks.items() if (now - t.last_updated) > 3.0]
        for k in stale_keys:
            self._fused_tracks.pop(k, None)

        return [t.to_dict() for t in self._fused_tracks.values()]

# Global Fusion Engine Singleton
fusion_engine = RadarCameraFusionEngine()
sensor_fusion_engine = fusion_engine
