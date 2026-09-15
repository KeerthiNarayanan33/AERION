import base64
import cv2
import numpy as np
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy.orm import Session
from pydantic import BaseModel

from backend.database.database import get_db
from backend.database.models import ANPRResultModel
from backend.ai.anpr_engine import anpr_engine
from backend.camera.camera_manager import camera_manager

router = APIRouter(prefix="/api/anpr", tags=["ANPR / Number Plate Recognition"])

class ManualDetectRequest(BaseModel):
    camera_id: str = "CAM_01"
    track_id: int = 101
    class_name: str = "car"
    # Optional bounding box in pixels: [x1, y1, x2, y2]
    bbox: Optional[List[int]] = None
    # Optional base64 encoded image
    image_base64: Optional[str] = None

@router.get("/records")
def get_anpr_records(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    camera_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Retrieves paginated list of vehicle license plate recognition records."""
    query = db.query(ANPRResultModel)
    if camera_id:
        query = query.filter(ANPRResultModel.camera_id == camera_id)

    total = query.count()
    records = query.order_by(ANPRResultModel.timestamp.desc()).offset(offset).limit(limit).all()

    items = []
    for r in records:
        items.append({
            "id": r.id,
            "event_id": r.event_id,
            "vehicle_track_id": r.vehicle_track_id,
            "camera_id": r.camera_id,
            "plate_text": r.plate_text,
            "confidence": r.confidence,
            "is_readable": r.plate_text != "PLATE_NOT_READABLE",
            "snapshot_path": r.snapshot_path,
            "timestamp": r.timestamp.isoformat() if r.timestamp else None
        })

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "records": items
    }

@router.get("/stats")
def get_anpr_stats(db: Session = Depends(get_db)):
    """Returns operational ANPR intelligence metrics."""
    total = db.query(ANPRResultModel).count()
    unreadable = db.query(ANPRResultModel).filter(ANPRResultModel.plate_text == "PLATE_NOT_READABLE").count()
    readable = total - unreadable

    return {
        "total_scanned": total,
        "readable_plates": readable,
        "unreadable_plates": unreadable,
        "recognition_rate_percent": round((readable / total * 100.0), 1) if total > 0 else 0.0
    }

@router.post("/detect")
def trigger_anpr_detection(payload: ManualDetectRequest):
    """
    On-demand ANPR trigger.
    Either inspects uploaded base64 image or captures active frame from camera.
    """
    frame = None

    if payload.image_base64:
        try:
            raw_bytes = base64.b64decode(payload.image_base64)
            np_arr = np.frombuffer(raw_bytes, np.uint8)
            frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid base64 image: {e}")
    else:
        # Grab active frame from camera
        cam = camera_manager.get_camera(payload.camera_id)
        if not cam:
            raise HTTPException(status_code=404, detail=f"Camera {payload.camera_id} not found")
        frame = cam.get_latest_frame()

    if frame is None or frame.size == 0:
        raise HTTPException(status_code=503, detail=f"No video frame available for {payload.camera_id}")

    h, w = frame.shape[:2]
    # Default bounding box: center vehicle region if none supplied
    bbox = payload.bbox or [int(w * 0.2), int(h * 0.3), int(w * 0.8), int(h * 0.85)]

    result = anpr_engine.process_vehicle(
        frame=frame,
        bbox=tuple(bbox),
        vehicle_track_id=payload.track_id,
        camera_id=payload.camera_id
    )

    return {
        "status": "SUCCESS",
        "result": result
    }
