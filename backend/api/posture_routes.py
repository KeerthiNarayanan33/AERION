"""
SENTINEL-AI: Intruder Posture & Carriage REST Routes
Exposes Posture Classifications (Prone Crawling, Crouching, Upright) and Crawl Simulation.
"""

from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional

from backend.ai.posture_classifier import posture_classifier

router = APIRouter(prefix="/api/ai/posture", tags=["Intruder Posture & Carriage Classifier"])

class ClassifyRequest(BaseModel):
    target_id: str = "TGT_001"
    bbox: List[float] = Field(default=[0.2, 0.4, 0.5, 0.8], description="[x1, y1, x2, y2]")
    speed_mps: float = 1.2
    zone_id: str = "ZONE_C"
    has_equipment_load: bool = False

@router.get("/active")
def get_active_postures() -> Dict[str, Any]:
    """Returns active target posture classifications and crawl alert statistics."""
    return posture_classifier.get_active()

@router.post("/classify")
def classify_target_posture(req: ClassifyRequest) -> Dict[str, Any]:
    """Classifies posture for an arbitrary target bounding box."""
    return posture_classifier.classify_target(
        target_id=req.target_id,
        bbox=req.bbox,
        speed_mps=req.speed_mps,
        zone_id=req.zone_id,
        has_equipment_load=req.has_equipment_load
    )

@router.post("/simulate-crawl")
async def simulate_crawling_intruder() -> Dict[str, Any]:
    """
    1-click Evaluator Trigger: Simulates a prone-crawling intruder attempting
    to crawl under the perimeter fence wire in ZONE_C.
    """
    return await posture_classifier.simulate_crawling_intruder()
