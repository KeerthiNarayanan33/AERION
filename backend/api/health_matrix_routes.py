"""
SENTINEL-AI: Multi-Sensor Health Matrix & Failover API Routes
Sections 28, 29, & 49: Sensor telemetry, SNR, jitter, and dynamic degraded mode failover.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

from backend.system.health_matrix import sensor_health_matrix

router = APIRouter(prefix="/api/health", tags=["Sensor Health Matrix"])

class FailoverTriggerRequest(BaseModel):
    mode_id: str = Field(default="FOG_SMOKE_DEGRADED", description="BALANCED_FUSION, FOG_SMOKE_DEGRADED, EW_RADAR_JAMMED, OPTICAL_FAILOVER")
    reason: str = Field(default="Evaluator demonstration failover", description="Diagnostic cause description")

@router.get("/matrix")
def get_sensor_health_matrix():
    """Returns live telemetry, SNR, MTBF, and degraded mode weights across all sensors."""
    return sensor_health_matrix.get_matrix_status()

@router.post("/trigger-failover")
async def trigger_sensor_failover(payload: Optional[FailoverTriggerRequest] = None):
    """Triggers autonomous sensor failover and re-balances detection weighting."""
    mode = payload.mode_id if payload else "FOG_SMOKE_DEGRADED"
    reason = payload.reason if payload else "Evaluator demonstration failover"
    try:
        return await sensor_health_matrix.trigger_failover(mode_id=mode, reason=reason)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/reset-matrix")
async def reset_sensor_matrix():
    """Restores all sensors back to nominal balanced fusion mode."""
    return await sensor_health_matrix.reset_matrix()
