"""
SENTINEL-AI: Intruder Intent & Kinematics Trajectory Prediction Engine
Sections 27, 47, & 63: Constant Turn Rate & Velocity (CTRV/CTRA) Kinematic Extrapolation,
Predicted Point of Infiltration (PPI) Geo-Intersection, and Estimated Time to Breach (ETB).

Predicts future path waypoints of incoming ground infiltrators approaching the BSF fence,
pinpointing the exact physical border fence intersection (MGRS grid / Lat-Lon) and
warning operators in advance of perimeter fence penetration.
"""

import math
import time
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from backend.geospatial.coordinates import geospatial_engine
from backend.websocket.manager import ws_manager
from backend.logger import logger

# BSF Barbed Wire Fence is configured along Y = 5.0m in local coordinate space (running East-West)
DEFAULT_FENCE_Y_M = 5.0

class KinematicsPredictor:
    """
    Evaluates target velocity and turn rate to forecast future path vectors,
    calculates Predicted Point of Infiltration (PPI) and Estimated Time to Breach (ETB).
    """
    def __init__(self, fence_y_m: float = DEFAULT_FENCE_Y_M):
        self.fence_y_m = fence_y_m
        self.predictions_cache: Dict[str, Dict[str, Any]] = {}

    def predict_trajectory(
        self,
        target_id: str,
        x_m: float,
        y_m: float,
        vx_mps: float,
        vy_mps: float,
        turn_rate_dps: float = 0.0
    ) -> Dict[str, Any]:
        """
        Calculates future waypoints at T+2s, T+5s, T+10s, T+15s and determines
        the Estimated Time to Breach (ETB) and Predicted Point of Infiltration (PPI).
        """
        now = datetime.now(timezone.utc).isoformat()
        current_speed = math.sqrt(vx_mps * vx_mps + vy_mps * vy_mps)
        current_heading_deg = math.degrees(math.atan2(vx_mps, vy_mps))
        omega_rad = math.radians(turn_rate_dps)

        # 1. Extrapolate future waypoints
        horizons_sec = [2.0, 5.0, 10.0, 15.0]
        future_waypoints = []

        for t in horizons_sec:
            if abs(omega_rad) < 1e-4:
                # Constant Velocity (CV) straight line
                pred_x = x_m + vx_mps * t
                pred_y = y_m + vy_mps * t
            else:
                # Constant Turn Rate (CTR) circle arc
                theta_0 = math.atan2(vx_mps, vy_mps)
                theta_t = theta_0 + omega_rad * t
                pred_x = x_m + (current_speed / omega_rad) * (math.sin(theta_t) - math.sin(theta_0))
                pred_y = y_m + (current_speed / omega_rad) * (math.cos(theta_0) - math.cos(theta_t))

            # Georeference waypoint
            geo_pt = geospatial_engine.local_xy_to_georeferenced(pred_x, pred_y)
            future_waypoints.append({
                "time_offset_sec": t,
                "x_m": round(pred_x, 2),
                "y_m": round(pred_y, 2),
                "distance_m": round(math.hypot(pred_x, pred_y), 2),
                "latitude": geo_pt["latitude"],
                "longitude": geo_pt["longitude"],
                "mgrs_grid": geo_pt.get("mgrs_8digit", "43R FU 8785 9912"),
                "mgrs_8digit": geo_pt.get("mgrs_8digit", "43R FU 8785 9912")
            })

        # 2. Calculate Estimated Time to Breach (ETB) & Predicted Point of Infiltration (PPI)
        # Fence is along Y = self.fence_y_m
        dist_to_fence = self.fence_y_m - y_m
        approaching_fence = vy_mps > 0.05 and dist_to_fence > 0

        etb_sec: Optional[float] = None
        ppi_info: Optional[Dict[str, Any]] = None
        urgency: str = "NORMAL"

        if approaching_fence:
            etb_sec = round(dist_to_fence / vy_mps, 1)
            # Predicted X at the fence line
            ppi_x = x_m + vx_mps * (etb_sec)
            ppi_y = self.fence_y_m
            geo_ppi = geospatial_engine.local_xy_to_georeferenced(ppi_x, ppi_y)

            if etb_sec <= 30.0:
                urgency = "CRITICAL_IMMINENT_BREACH"
            elif etb_sec <= 60.0:
                urgency = "HIGH_APPROACH_ALERT"
            else:
                urgency = "MODERATE_INTERCEPT_ZONE"

            ppi_info = {
                "x_m": round(ppi_x, 2),
                "y_m": round(ppi_y, 2),
                "latitude": geo_ppi["latitude"],
                "longitude": geo_ppi["longitude"],
                "mgrs_grid": geo_ppi.get("mgrs_8digit", "43R FU 8785 9912"),
                "mgrs_8digit": geo_ppi.get("mgrs_8digit", "43R FU 8785 9912"),
                "utm_easting": geo_ppi["utm_easting"],
                "utm_northing": geo_ppi["utm_northing"],
                "defense_sector": "ZONE_C_RESTRICTED_FENCE"
            }
        else:
            if y_m >= self.fence_y_m:
                urgency = "INSIDE_RESTRICTED_FENCE"
                etb_sec = 0.0
            else:
                urgency = "PARALLEL_OR_RECEDING"

        result = {
            "target_id": target_id,
            "calculated_at": now,
            "current_state": {
                "x_m": round(x_m, 2),
                "y_m": round(y_m, 2),
                "speed_mps": round(current_speed, 2),
                "heading_deg": round(current_heading_deg, 1),
                "distance_to_fence_m": round(max(0.0, dist_to_fence), 2)
            },
            "estimated_time_to_breach_sec": etb_sec,
            "threat_urgency": urgency,
            "predicted_point_of_infiltration": ppi_info,
            "projected_waypoints": future_waypoints
        }

        self.predictions_cache[target_id] = result
        return result

    async def broadcast_prediction(self, prediction: Dict[str, Any]) -> None:
        """Emits real-time ETB trajectory prediction over WebSocket."""
        await ws_manager.broadcast({
            "type": "ETB_TRAJECTORY_PREDICTION",
            "prediction": prediction
        })

    def get_prediction(self, target_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves cached kinematics prediction for a target."""
        return self.predictions_cache.get(target_id)

# Global singleton
kinematics_predictor = KinematicsPredictor()
