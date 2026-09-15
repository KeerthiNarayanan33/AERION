"""
SENTINEL-AI: Counter-UAS (C-UAS) API Routes
Sections 38, 55, & 64: Sky shield status, rogue drone simulation, and jamming countermeasures.
"""

from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import Optional

from backend.radar.counter_uas import counter_uas_manager

router = APIRouter(prefix="/api/cuas", tags=["Counter-UAS"])

class SimulateThreatRequest(BaseModel):
    callsign: str = Field(default="HOSTILE_HEXA_09", description="Simulated drone callsign")
    altitude_m: float = Field(default=48.5, description="Altitude AGL in meters")
    payload_type: str = Field(default="SUSPECTED_CONTRABAND_CONTAINER", description="Identified payload profile")

class EscalateRequest(BaseModel):
    operator: str = Field(default="AIR_DEFENSE_WATCH_01", description="Watch operator ID")

@router.get("/status")
def get_cuas_status():
    """Returns Counter-UAS sky shield status, RF jammer states, and active rogue drone threats."""
    return counter_uas_manager.get_status()

@router.post("/simulate-threat")
async def simulate_threat(payload: Optional[SimulateThreatRequest] = None):
    """Simulates detection of an incoming unauthorized contraband drone."""
    callsign = payload.callsign if payload else "HOSTILE_HEXA_09"
    altitude_m = payload.altitude_m if payload else 48.5
    payload_type = payload.payload_type if payload else "SUSPECTED_CONTRABAND_CONTAINER"

    return await counter_uas_manager.simulate_rogue_drone(
        callsign=callsign,
        altitude_m=altitude_m,
        payload_type=payload_type
    )

@router.post("/escalate")
async def escalate_countermeasure(payload: Optional[EscalateRequest] = None):
    """Escalates countermeasure to next operational stage (Jam -> Spoof -> Net Intercept)."""
    operator = payload.operator if payload else "AIR_DEFENSE_WATCH_01"
    return await counter_uas_manager.escalate_countermeasure(operator=operator)

@router.post("/neutralize")
async def neutralize_threat():
    """Confirms rogue drone neutralized / brought down and logs capture."""
    return await counter_uas_manager.neutralize_threat()

@router.post("/reset")
async def reset_cuas():
    """Resets Counter-UAS system back to standby."""
    return await counter_uas_manager.reset_sky_shield()
