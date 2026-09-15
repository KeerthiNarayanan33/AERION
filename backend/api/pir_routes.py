from typing import Optional
from fastapi import APIRouter
from pydantic import BaseModel

from backend.events.pir_service import pir_service

router = APIRouter(prefix="/api/pir", tags=["PIR Sensor"])

class PIRTriggerPayload(BaseModel):
    source: Optional[str] = "SIMULATION"

@router.get("/status")
def get_pir_status():
    """Returns status of the single PIR-001 sensor."""
    return pir_service.get_status()

@router.post("/trigger")
def trigger_pir_motion(payload: Optional[PIRTriggerPayload] = None):
    """Triggers a PIR motion event."""
    src = payload.source if payload else "SIMULATION"
    return pir_service.trigger_motion(source=src)

@router.post("/mode")
def set_pir_mode(mode: str):
    """Sets PIR operational mode (LIVE or SIMULATION)."""
    pir_service.set_mode(mode)
    return {"status": "SUCCESS", "mode": pir_service.mode}
