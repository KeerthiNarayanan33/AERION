"""
SENTINEL-AI: Multi-UAV Swarm Coordination API Routes
Sections 33, 52, & 63: Swarm status, search sweeps, and autonomous low-battery relief handover.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

from backend.uav.swarm_manager import swarm_mission_manager

router = APIRouter(prefix="/api/swarm", tags=["UAV Swarm"])

class SwarmDispatchRequest(BaseModel):
    pattern: str = Field(default="CREEPING_LINE_SEARCH", description="CREEPING_LINE_SEARCH, EXPANDING_SQUARE, PERIMETER_PATROL")
    zone_id: str = Field(default="ZONE_C", description="Target perimeter zone")
    formation: str = Field(default="VEE_FORMATION", description="VEE_FORMATION, ECHELON_RIGHT, LINE_ABREAST, INDEPENDENT_DISPERSED")

class SwarmHandoverRequest(BaseModel):
    retiring_drone_id: str = Field(default="UAV_01", description="Retiring drone ID")
    relief_drone_id: str = Field(default="UAV_02", description="Relief drone acquiring lock")

class SwarmRecallRequest(BaseModel):
    reason: str = Field(default="Operator command", description="Recall reason")

@router.get("/status")
def get_swarm_status():
    """Returns telemetry for all swarm units, flight formations, and active missions."""
    return swarm_mission_manager.get_status()

@router.post("/dispatch")
async def dispatch_swarm(payload: SwarmDispatchRequest):
    """Dispatches the multi-UAV swarm in coordinated search formation."""
    return await swarm_mission_manager.dispatch_swarm(
        pattern=payload.pattern,
        zone_id=payload.zone_id,
        formation=payload.formation
    )

@router.post("/handover")
async def execute_relief_handover(payload: SwarmHandoverRequest):
    """Executes target lock handover from low-battery drone to relief drone."""
    try:
        return await swarm_mission_manager.execute_relief_handover(
            retiring_drone_id=payload.retiring_drone_id,
            relief_drone_id=payload.relief_drone_id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/recall")
async def recall_swarm(payload: Optional[SwarmRecallRequest] = None):
    """Recalls all swarm drones back to base dock."""
    reason = payload.reason if payload else "Operator command"
    return await swarm_mission_manager.recall_swarm(reason=reason)
