from typing import Optional, Dict, Any, List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.events.incident_service import incident_service

router = APIRouter(prefix="/api/incidents", tags=["Security Incidents"])

class TriggerIncidentPayload(BaseModel):
    camera_id: str = "CAM_01"
    zone_id: Optional[str] = "ZONE_B"
    identity: str = "UNKNOWN"
    confidence: float = 0.92
    authorization: str = "UNAUTHORIZED"

class ResolveIncidentPayload(BaseModel):
    operator: str = "Chief Watch Officer"

@router.get("")
def list_incidents(limit: int = 20):
    """Lists recent security incidents."""
    return {
        "count": len(incident_service.list_incidents(limit)),
        "incidents": incident_service.list_incidents(limit)
    }

@router.get("/active")
def get_active_incident():
    """Returns currently active unresolved incident."""
    inc = incident_service.get_active_incident()
    return {"active_incident": inc}

@router.post("/trigger")
def trigger_unauthorized_incident(payload: TriggerIncidentPayload):
    """Triggers an unauthorized intrusion incident and dispatches drone."""
    inc = incident_service.process_unauthorized_detection(
        camera_id=payload.camera_id,
        zone_id=payload.zone_id,
        track_id=1,
        identity=payload.identity,
        confidence=payload.confidence,
        authorization=payload.authorization
    )
    return {"status": "SUCCESS", "incident": inc}

@router.post("/{incident_id}/resolve")
def resolve_incident(incident_id: str, payload: ResolveIncidentPayload):
    """Resolves an incident and commands drone return home."""
    res = incident_service.resolve_incident(incident_id, operator=payload.operator)
    return res
