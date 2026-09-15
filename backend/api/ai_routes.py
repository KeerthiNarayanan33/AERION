from typing import Optional, List
from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel
import cv2
import numpy as np

from backend.ai.inference_manager import inference_manager
from backend.config import get_settings

router = APIRouter(prefix="/api/ai", tags=["AI Inference"])
settings = get_settings()

class AIConfigUpdate(BaseModel):
    confidence_threshold: Optional[float] = None
    inference_fps: Optional[int] = None

@router.get("/status")
def get_ai_status():
    """Retrieves operational status, hardware acceleration, and inference telemetry."""
    metrics = inference_manager.get_metrics()
    detector = inference_manager._detector
    supported_classes = detector.get_supported_classes() if detector else []

    return {
        "status": "READY" if metrics["is_ready"] else "WARMING_UP",
        "metrics": metrics,
        "supported_classes": supported_classes
    }

@router.get("/detections/{camera_id}")
def get_camera_detections(camera_id: str = "CAM_01"):
    """Retrieves the latest AI object detections for a camera."""
    result = inference_manager.get_latest_detections(camera_id)
    if not result:
        return {
            "camera_id": camera_id,
            "count": 0,
            "detections": [],
            "inference_time_ms": 0.0,
            "timestamp": None
        }

    return {
        "camera_id": camera_id,
        "count": result.count,
        "person_count": result.person_count,
        "vehicle_count": result.vehicle_count,
        "inference_time_ms": result.inference_time_ms,
        "device": result.device,
        "timestamp": result.timestamp,
        "detections": [d.model_dump() for d in result.detections]
    }

@router.get("/tracks/{camera_id}")
def get_camera_tracks(camera_id: str = "CAM_01"):
    """Retrieves active tracked objects with trajectory history for a camera."""
    tracks = inference_manager.get_latest_tracks(camera_id)
    return {
        "camera_id": camera_id,
        "count": len(tracks),
        "tracks": [t.model_dump() for t in tracks]
    }


@router.post("/detect")
async def detect_uploaded_image(file: UploadFile = File(...)):
    """Runs on-demand inference on an uploaded image file."""
    contents = await file.read()
    nparr = np.frombuffer(contents, np.uint8)
    image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    if image is None:
        raise HTTPException(status_code=400, detail="Invalid image file")

    detector = inference_manager._detector
    if not detector or not detector.is_ready():
        raise HTTPException(status_code=503, detail="AI model is still warming up")

    result = detector.detect(image)
    return {
        "count": result.count,
        "person_count": result.person_count,
        "vehicle_count": result.vehicle_count,
        "inference_time_ms": result.inference_time_ms,
        "detections": [d.model_dump() for d in result.detections]
    }
