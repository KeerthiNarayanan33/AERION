"""
SENTINEL-AI: Multi-Sensor EKF Fusion & Slew-to-Cue API Routes
Sections 10, 20, 21, 32, & 47: Extended Kalman Filter tracks, covariance ellipses,
and automated radar-directed PTZ optical boresight slewing.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

from backend.fusion.ekf_tracker import ekf_fusion_tracker
from backend.fusion.slew_director import slew_to_cue_director

router = APIRouter(prefix="/api/fusion", tags=["Sensor Fusion & PTZ"])

class RadarObservationRequest(BaseModel):
    radar_id: int = Field(default=101, description="Radar target ID")
    x_m: float = Field(default=-0.8, description="Lateral X coordinate in meters")
    y_m: float = Field(default=3.5, description="Depth Y coordinate in meters")
    speed_mps: float = Field(default=-1.2, description="Radial speed in m/s")
    distance_m: float = Field(default=3.59, description="Total distance in meters")

class SlewToCueRequest(BaseModel):
    target_id: str = Field(default="TRK_RADAR_01", description="Target identifier to cue")
    x_m: float = Field(default=-1.5, description="Target X coordinate")
    y_m: float = Field(default=4.2, description="Target Y coordinate")
    z_m: float = Field(default=1.2, description="Target height AGL in meters")

@router.get("/ekf-tracks")
def get_ekf_tracks():
    """Returns active Extended Kalman Filter multi-sensor tracks with 95% error ellipses."""
    return {
        "status": "TRACKS_AVAILABLE",
        "total_active_tracks": len(ekf_fusion_tracker.get_tracks()),
        "tracks": ekf_fusion_tracker.get_tracks()
    }

@router.post("/fuse-observation")
def fuse_radar_observation(payload: RadarObservationRequest):
    """Ingests and fuses a radar observation into the EKF multi-target tracker."""
    return ekf_fusion_tracker.process_radar_target(
        radar_id=payload.radar_id,
        x_m=payload.x_m,
        y_m=payload.y_m,
        speed_mps=payload.speed_mps,
        distance_m=payload.distance_m
    )

@router.post("/slew-to-cue")
async def execute_slew_to_cue(payload: SlewToCueRequest):
    """Directs PTZ camera gimbal to slew boresight onto target coordinates."""
    return await slew_to_cue_director.execute_slew_to_cue(
        target_id=payload.target_id,
        x_m=payload.x_m,
        y_m=payload.y_m,
        z_m=payload.z_m
    )

@router.get("/ptz-status")
def get_ptz_status():
    """Returns current PTZ gimbal angles, zoom factor, and tracking lock."""
    return slew_to_cue_director.get_status()

@router.post("/reset")
async def reset_fusion_and_ptz():
    """Resets EKF tracks and re-centers PTZ boresight."""
    ekf_fusion_tracker.reset()
    await slew_to_cue_director.reset_boresight()
    return {"status": "FUSION_AND_PTZ_RESET"}
