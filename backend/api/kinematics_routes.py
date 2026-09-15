"""
SENTINEL-AI: Kinematics & ETB Prediction API Routes
Sections 27, 47, & 63: Trajectory forecasting, Predicted Point of Infiltration (PPI),
and Estimated Time to Breach (ETB).
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

from backend.ai.kinematics_predictor import kinematics_predictor

router = APIRouter(prefix="/api/kinematics", tags=["Kinematics & ETB"])

class SimulateTrajectoryRequest(BaseModel):
    target_id: str = Field(default="INTRUDER_VEC_01", description="Target identifier")
    x_m: float = Field(default=-1.2, description="Current X coordinate (lateral)")
    y_m: float = Field(default=2.2, description="Current Y coordinate (depth, approaching fence at Y=5.0)")
    vx_mps: float = Field(default=0.15, description="Lateral velocity m/s")
    vy_mps: float = Field(default=0.85, description="Approach velocity m/s towards fence")
    turn_rate_dps: float = Field(default=0.0, description="Turn rate in degrees/sec")

@router.get("/prediction/{target_id}")
def get_prediction(target_id: str):
    """Returns the forecasted trajectory, ETB, and PPI for a target."""
    pred = kinematics_predictor.get_prediction(target_id)
    if not pred:
        # Generate default prediction
        pred = kinematics_predictor.predict_trajectory(
            target_id=target_id,
            x_m=-0.5,
            y_m=2.0,
            vx_mps=0.1,
            vy_mps=0.75
        )
    return pred

@router.post("/simulate-trajectory")
async def simulate_trajectory(payload: Optional[SimulateTrajectoryRequest] = None):
    """Simulates an approaching target, calculates ETB & PPI, and broadcasts alert."""
    req = payload if payload else SimulateTrajectoryRequest()
    pred = kinematics_predictor.predict_trajectory(
        target_id=req.target_id,
        x_m=req.x_m,
        y_m=req.y_m,
        vx_mps=req.vx_mps,
        vy_mps=req.vy_mps,
        turn_rate_dps=req.turn_rate_dps
    )
    await kinematics_predictor.broadcast_prediction(pred)
    return pred
