from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

from backend.ai.reid_handover import reid_engine
from backend.websocket.manager import ws_manager

router = APIRouter(prefix="/api/ai/handover", tags=["Cross-Camera ReID & Handover"])

class HandoverSimulatePayload(BaseModel):
    from_camera: str = "CAM_01"
    to_camera: str = "CAM_02"
    track_id: int = 4
    object_class: str = "person"

@router.get("/active")
def get_active_handover_status():
    """
    Returns active cross-camera handover candidate pool and persistent identity records (Sections 56 & 65).
    """
    return reid_engine.get_status()

@router.post("/simulate")
async def simulate_cross_camera_handover(payload: Optional[HandoverSimulatePayload] = None):
    """
    Simulates a cross-camera target transition (e.g. CAM_01 -> CAM_02)
    and broadcasts a live CROSS_CAMERA_HANDOVER telemetry alert.
    """
    p = payload or HandoverSimulatePayload()
    handover = reid_engine.simulate_handover(
        from_cam=p.from_camera,
        to_cam=p.to_camera,
        track_id=p.track_id,
        object_class=p.object_class
    )

    await ws_manager.broadcast({
        "type": "CROSS_CAMERA_HANDOVER",
        "handover": handover
    })

    return {
        "message": "Cross-camera handover sequence executed and broadcasted",
        "handover": handover
    }
