import json
import base64
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
import numpy as np
import cv2

from backend.ai.identity_service import identity_service
from backend.websocket.manager import ws_manager
from backend.logger import logger

router = APIRouter(prefix="/api/identity", tags=["Person Identification & Authorization"])

class PersonRegisterPayload(BaseModel):
    person_id: str
    name: str
    allowed_zones: List[str] = ["ZONE_A", "ZONE_B"]
    image_base64: Optional[str] = None

class SimulateIdentityPayload(BaseModel):
    camera_id: str = "CAM_01"
    identity: str = "Keerthi"
    confidence: float = 0.96
    authorization: str = "AUTHORIZED"  # AUTHORIZED, UNAUTHORIZED, NOT_AUTHORIZED_FOR_ZONE, UNVERIFIED
    duration: float = 30.0

@router.get("/persons")
def list_registered_persons():
    """Returns all enrolled authorized persons."""
    return {
        "count": len(identity_service.list_persons()),
        "persons": identity_service.list_persons()
    }

@router.post("/persons")
def register_person(payload: PersonRegisterPayload):
    """Enrolls a new authorized person in the registry."""
    image_np = None
    if payload.image_base64:
        try:
            raw_data = base64.b64decode(payload.image_base64.split(",")[-1])
            nparr = np.frombuffer(raw_data, np.uint8)
            image_np = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        except Exception as e:
            logger.warning(f"[IDENTITY] Failed to decode base64 image: {e}")

    # If no image provided, generate synthetic reference portrait for testing
    if image_np is None:
        image_np = np.full((128, 128, 3), 180, dtype=np.uint8)
        cv2.putText(image_np, payload.name[:2].upper(), (32, 75), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (20, 20, 20), 3)

    success = identity_service.enroll_person(
        person_id=payload.person_id,
        name=payload.name,
        allowed_zones=payload.allowed_zones,
        image=image_np
    )

    if not success:
        raise HTTPException(status_code=400, detail="Failed to enroll person.")

    return {
        "status": "SUCCESS",
        "message": f"Successfully enrolled {payload.name} ({payload.person_id})",
        "person_id": payload.person_id,
        "allowed_zones": payload.allowed_zones
    }

@router.delete("/persons/{person_id}")
def delete_person(person_id: str):
    """Deletes an authorized person from registry."""
    success = identity_service.delete_person(person_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Person '{person_id}' not found.")
    return {"status": "SUCCESS", "message": f"Person '{person_id}' removed from registry."}

@router.get("/latest/{camera_id}")
def get_latest_identity(camera_id: str):
    """Returns latest identity result for a given camera."""
    return identity_service.get_latest_result(camera_id)

@router.get("/status")
def get_identity_status():
    """Returns status and latest results across all cameras."""
    cams = ["CAM_01", "CAM_02", "UAV_01"]
    return {
        "enrolled_count": len(identity_service.list_persons()),
        "threshold": getattr(identity_service, "_threshold", 0.85),
        "results": {cid: identity_service.get_latest_result(cid) for cid in cams}
    }

@router.post("/simulate")
async def simulate_identity_trigger(payload: SimulateIdentityPayload):
    """
    Injects a simulated identity result for testing and SIH live demonstration scenarios.
    """
    identity_service.simulate_identity(
        camera_id=payload.camera_id,
        identity=payload.identity,
        confidence=payload.confidence,
        authorization=payload.authorization,
        duration=payload.duration
    )

    res = identity_service.get_latest_result(payload.camera_id)

    # Broadcast identity update immediately over WebSocket
    await ws_manager.broadcast({
        "type": "IDENTITY_UPDATE",
        "camera_id": payload.camera_id,
        "identity": res["identity"],
        "confidence": res["confidence"],
        "authorization": res["authorization"],
        "zone_id": res.get("zone_id", "ZONE_B"),
        "timestamp": res.get("timestamp")
    })

    return {
        "status": "SIMULATION_ACTIVE",
        "camera_id": payload.camera_id,
        "result": res
    }

@router.post("/simulate/clear")
def clear_identity_simulation(camera_id: Optional[str] = None):
    """Clears simulation override for a camera or all cameras."""
    identity_service.clear_simulation(camera_id)
    return {"status": "CLEARED"}
