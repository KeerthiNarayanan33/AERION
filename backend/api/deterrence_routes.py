"""
SENTINEL-AI: Non-Lethal Deterrence REST Routes
Exposes Deterrence Ladder Status, Stage Escalation, and Standby Reset.
"""

from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional

from backend.events.deterrence import deterrence_matrix_manager

router = APIRouter(prefix="/api/deterrence", tags=["Non-Lethal Deterrence Matrix"])

class EscalateRequest(BaseModel):
    event_id: str = Field(default="EVT_BREACH_ZONE_C", description="Incident event ID")
    target_id: str = Field(default="GLOBAL_TARGET_001", description="Intruder target ID")
    zone_id: str = Field(default="ZONE_C", description="Breached sector ID")
    operator: str = Field(default="COMMAND_WATCH_01", description="Authorizing officer")

@router.get("/state")
def get_deterrence_state() -> Dict[str, Any]:
    """Returns current graduated deterrence stage, compliance state, and action history."""
    return deterrence_matrix_manager.get_state()

@router.post("/escalate")
async def escalate_deterrence_stage(req: Optional[EscalateRequest] = None) -> Dict[str, Any]:
    """
    Escalates deterrence to next stage:
    Stage 1: 20Hz Strobe -> Stage 2: LRAD Multilingual Warning -> Stage 3: 115dB Siren -> Stage 4: QRT Intercept.
    """
    event_id = req.event_id if req else "EVT_BREACH_ZONE_C"
    target_id = req.target_id if req else "GLOBAL_TARGET_001"
    zone_id = req.zone_id if req else "ZONE_C"
    operator = req.operator if req else "COMMAND_WATCH_01"
    
    return await deterrence_matrix_manager.escalate_stage(
        event_id=event_id, target_id=target_id, zone_id=zone_id, operator=operator
    )

@router.post("/reset")
async def reset_deterrence() -> Dict[str, Any]:
    """Resets deterrence to baseline standby state."""
    return await deterrence_matrix_manager.reset_deterrence()
