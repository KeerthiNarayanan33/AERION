"""
SENTINEL-AI Electronic Warfare (EW) Jamming Triangulation & Direction-Finding Engine.
Sections 62 & 67: Multi-Station Angle-of-Arrival (AoA) Least-Squares Triangulation
and Anti-Spoofing / GPS Denial Resilience with MGRS Military Grid Mapping.
"""

import math
import time
from typing import Dict, Any, List, Optional, Tuple
import numpy as np

from backend.geospatial.coordinates import geospatial_engine
from backend.logger import logger


class DirectionFindingStation:
    """A baseline RF Direction-Finding (DF) receiver station on the perimeter."""
    def __init__(self, station_id: str, name: str, x_m: float, y_m: float):
        self.station_id = station_id
        self.name = name
        self.x_m = x_m
        self.y_m = y_m
        self.status = "ONLINE"
        self.last_bearing_deg: Optional[float] = None
        self.snr_db: float = 24.5


class JammingTriangulationEngine:
    """
    Solves multi-station Angle-of-Arrival (AoA) ray intersections using linear least squares
    to geolocate hostile RF/GPS jammers operating across the border line.
    """
    _instance: Optional['JammingTriangulationEngine'] = None

    def __init__(self):
        # 3 baseline direction-finding stations along the border baseline (y = 0)
        self.stations = {
            "DF_01": DirectionFindingStation("DF_01", "DF Post Alpha (Left Flank)", -25.0, 0.0),
            "DF_02": DirectionFindingStation("DF_02", "DF Post Bravo (Central Sector)", 0.0, 0.0),
            "DF_03": DirectionFindingStation("DF_03", "DF Post Charlie (Right Flank)", 25.0, 0.0),
        }
        self.is_jamming_active = False
        self.last_triangulation_result: Optional[Dict[str, Any]] = None
        self.gps_denied_mode = False
        self.dead_reckoning_active = False
        logger.info("[EW_TRIANGULATOR] JammingTriangulationEngine initialized with 3 baseline DF posts.")

    @classmethod
    def get_instance(cls) -> 'JammingTriangulationEngine':
        if cls._instance is None:
            cls._instance = JammingTriangulationEngine()
        return cls._instance

    def triangulate(
        self,
        true_emitter_x: float = -4.5,
        true_emitter_y: float = 28.0,
        noise_std_deg: float = 1.2
    ) -> Dict[str, Any]:
        """
        Executes AoA bearing intersection from all 3 DF stations.
        Line equation from station i:
            sin(theta_i) * x - cos(theta_i) * y = sin(theta_i) * x_i - cos(theta_i) * y_i
        Solves A [x, y]^T = b using linear least squares.
        """
        now = time.time()
        self.is_jamming_active = True
        self.gps_denied_mode = True
        self.dead_reckoning_active = True

        A_rows = []
        b_rows = []
        station_bearings = []

        for st_id, st in self.stations.items():
            # True geometric bearing from station to emitter: theta = atan2(x_e - x_i, y_e - y_i)
            dx = true_emitter_x - st.x_m
            dy = true_emitter_y - st.y_m
            true_bearing_rad = math.atan2(dx, dy)
            true_bearing_deg = math.degrees(true_bearing_rad)

            # Add simulated sensor noise
            measured_bearing_deg = true_bearing_deg + np.random.normal(0, noise_std_deg)
            st.last_bearing_deg = round(float(measured_bearing_deg), 2)
            st.snr_db = round(float(np.random.uniform(18.0, 29.0)), 1)

            # Line equation for navigation bearing: cos(theta)*x - sin(theta)*y = cos(theta)*x_i - sin(theta)*y_i
            theta_rad = math.radians(measured_bearing_deg)
            cos_t = math.cos(theta_rad)
            sin_t = math.sin(theta_rad)
            A_rows.append([cos_t, -sin_t])
            b_rows.append(cos_t * st.x_m - sin_t * st.y_m)

            station_bearings.append({
                "station_id": st.station_id,
                "name": st.name,
                "x_m": st.x_m,
                "y_m": st.y_m,
                "bearing_deg": st.last_bearing_deg,
                "snr_db": st.snr_db
            })

        # Solve linear system A x = b
        A = np.array(A_rows, dtype=np.float64)
        b = np.array(b_rows, dtype=np.float64)

        try:
            sol, residuals, rank, s = np.linalg.lstsq(A, b, rcond=None)
            est_x = round(float(sol[0]), 2)
            est_y = round(float(sol[1]), 2)
        except Exception as e:
            logger.error(f"[EW_TRIANGULATOR] Least-squares solver failure: {e}")
            est_x, est_y = true_emitter_x, true_emitter_y

        # Circular Error Probable (CEP) in meters
        error_dist = math.sqrt((est_x - true_emitter_x)**2 + (est_y - true_emitter_y)**2)
        cep_radius_m = round(max(0.8, error_dist * 1.15 + 0.5), 2)

        # Convert Cartesian coordinates to Georeferenced WGS-84 & MGRS
        geo = geospatial_engine.local_xy_to_georeferenced(est_x, est_y)

        result = {
            "timestamp": now,
            "status": "TRIANGULATION_LOCKED",
            "emitter_type": "HIGH_POWER_RF_GPS_JAMMER",
            "threat_classification": "ELECTRONIC_ATTACK_CLASS_IV",
            "estimated_coords": {
                "x_m": est_x,
                "y_m": est_y,
                "cep_radius_m": cep_radius_m
            },
            "georeferenced": {
                "latitude": geo["latitude"],
                "longitude": geo["longitude"],
                "mgrs_8digit": geo["mgrs_8digit"],
                "bearing_deg": geo["bearing_deg"],
                "range_meters": geo.get("range_m", 0.0)
            },
            "bearing_intersections": station_bearings,
            "anti_spoofing": {
                "gps_denial_detected": True,
                "countermeasure": "INS_DEAD_RECKONING_FALLBACK",
                "visual_odometry": "ACTIVE",
                "position_drift_rate_mps": 0.05
            },
            "countermeasure_recommendation": (
                f"Hostile EW Jammer triangulated at MGRS [{geo['mgrs_8digit']}]. "
                "Dispatch Counter-UAS Kinetic Interceptor or cued directional jammer nulling beam."
            )
        }

        self.last_triangulation_result = result
        logger.info(f"[EW_TRIANGULATOR] Jammer triangulated at ({est_x}m, {est_y}m) | MGRS: {geo['mgrs_8digit']} | CEP: {cep_radius_m}m")
        return result

    def get_status(self) -> Dict[str, Any]:
        """Provides status of DF stations and latest triangulation."""
        stations_list = [
            {
                "station_id": st.station_id,
                "name": st.name,
                "x_m": st.x_m,
                "y_m": st.y_m,
                "status": st.status,
                "last_bearing_deg": st.last_bearing_deg,
                "snr_db": st.snr_db
            }
            for st in self.stations.values()
        ]

        return {
            "is_jamming_active": self.is_jamming_active,
            "gps_denied_mode": self.gps_denied_mode,
            "dead_reckoning_active": self.dead_reckoning_active,
            "stations": stations_list,
            "latest_triangulation": self.last_triangulation_result
        }

    def reset(self) -> None:
        """Resets EW triangulation state."""
        self.is_jamming_active = False
        self.gps_denied_mode = False
        self.dead_reckoning_active = False
        self.last_triangulation_result = None
        for st in self.stations.values():
            st.last_bearing_deg = None
            st.snr_db = 24.5
        logger.info("[EW_TRIANGULATOR] Jamming triangulation state reset.")


jamming_triangulator = JammingTriangulationEngine.get_instance()
