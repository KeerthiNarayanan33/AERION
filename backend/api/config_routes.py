from typing import Optional, Dict, Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.config import get_settings, update_runtime_settings
from backend.websocket.manager import ws_manager
from backend.logger import logger

router = APIRouter(prefix="/api/config", tags=["Configuration"])

class RuntimeConfigUpdate(BaseModel):
    AI_INFERENCE_FPS: Optional[int] = Field(None, ge=5, le=30, description="Target AI inference FPS")
    DETECTION_CONFIDENCE: Optional[float] = Field(None, ge=0.15, le=0.95, description="YOLO detection confidence threshold")
    EVENT_COOLDOWN_SECONDS: Optional[float] = Field(None, ge=1.0, le=30.0, description="Zone hysteresis deduplication window")
    LOITERING_THRESHOLD_SECONDS: Optional[float] = Field(None, ge=3.0, le=60.0, description="Time inside warning zone before loitering alarm")
    PRE_EVENT_SECONDS: Optional[int] = Field(None, ge=2, le=15, description="Rolling pre-event buffer clip length")
    POST_EVENT_SECONDS: Optional[int] = Field(None, ge=3, le=30, description="Post-event video recording duration")
    FUSION_PROJECTION_GATE: Optional[float] = Field(None, ge=0.05, le=0.60, description="Max spatial distance for radar-camera match")
    UAV_RTB_BATTERY_PERCENT: Optional[int] = Field(None, ge=10, le=35, description="Low battery threshold triggering RTB")
    PRIVACY_BLUR_ENABLED: Optional[bool] = Field(None, description="Gaussian privacy blurring on civilian faces/bodies")
    THREAT_SCORING_ENABLED: Optional[bool] = Field(None, description="Direction-of-approach velocity threat index scoring")
    AUDIO_ALERTS_ENABLED: Optional[bool] = Field(None, description="Web Audio API acoustic siren alarm")

@router.get("")
def get_runtime_configuration() -> Dict[str, Any]:
    """Retrieves current operational settings and tunable parameter ranges."""
    s = get_settings()
    return {
        "status": "SUCCESS",
        "settings": {
            "AI_INFERENCE_FPS": s.AI_INFERENCE_FPS,
            "DETECTION_CONFIDENCE": s.DETECTION_CONFIDENCE,
            "EVENT_COOLDOWN_SECONDS": s.EVENT_COOLDOWN_SECONDS,
            "LOITERING_THRESHOLD_SECONDS": s.LOITERING_THRESHOLD_SECONDS,
            "PRE_EVENT_SECONDS": s.PRE_EVENT_SECONDS,
            "POST_EVENT_SECONDS": s.POST_EVENT_SECONDS,
            "FUSION_PROJECTION_GATE": s.FUSION_PROJECTION_GATE,
            "UAV_RTB_BATTERY_PERCENT": s.UAV_RTB_BATTERY_PERCENT,
            "PRIVACY_BLUR_ENABLED": s.PRIVACY_BLUR_ENABLED,
            "THREAT_SCORING_ENABLED": s.THREAT_SCORING_ENABLED,
            "AUDIO_ALERTS_ENABLED": s.AUDIO_ALERTS_ENABLED,
            "RETENTION_DAYS": s.RETENTION_DAYS,
            "SYSTEM_MODE": s.SYSTEM_MODE
        },
        "limits": {
            "AI_INFERENCE_FPS": {"min": 5, "max": 30, "step": 1},
            "DETECTION_CONFIDENCE": {"min": 0.15, "max": 0.95, "step": 0.05},
            "EVENT_COOLDOWN_SECONDS": {"min": 1.0, "max": 20.0, "step": 0.5},
            "LOITERING_THRESHOLD_SECONDS": {"min": 3.0, "max": 60.0, "step": 1.0},
            "PRE_EVENT_SECONDS": {"min": 2, "max": 15, "step": 1},
            "POST_EVENT_SECONDS": {"min": 3, "max": 30, "step": 1},
            "FUSION_PROJECTION_GATE": {"min": 0.05, "max": 0.60, "step": 0.02},
            "UAV_RTB_BATTERY_PERCENT": {"min": 10, "max": 35, "step": 5}
        }
    }

@router.put("")
def update_runtime_configuration(payload: RuntimeConfigUpdate) -> Dict[str, Any]:
    """Dynamically applies configuration updates to active in-memory singletons."""
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No valid configuration parameters provided.")

    new_settings = update_runtime_settings(updates)
    logger.info(f"[CONFIG] Runtime configuration updated: {updates}")

    ws_manager.broadcast_sync({
        "type": "CONFIG_UPDATED",
        "updates": updates
    })

    return {
        "status": "SUCCESS",
        "message": f"Updated {len(updates)} parameter(s) dynamically.",
        "updates": updates,
        "current_settings": {
            "AI_INFERENCE_FPS": new_settings.AI_INFERENCE_FPS,
            "DETECTION_CONFIDENCE": new_settings.DETECTION_CONFIDENCE,
            "EVENT_COOLDOWN_SECONDS": new_settings.EVENT_COOLDOWN_SECONDS,
            "LOITERING_THRESHOLD_SECONDS": new_settings.LOITERING_THRESHOLD_SECONDS,
            "PRE_EVENT_SECONDS": new_settings.PRE_EVENT_SECONDS,
            "POST_EVENT_SECONDS": new_settings.POST_EVENT_SECONDS,
            "PRIVACY_BLUR_ENABLED": new_settings.PRIVACY_BLUR_ENABLED,
            "AUDIO_ALERTS_ENABLED": new_settings.AUDIO_ALERTS_ENABLED
        }
    }

@router.post("/reset")
def reset_default_configuration() -> Dict[str, Any]:
    """Restores factory default surveillance parameters."""
    defaults = {
        "AI_INFERENCE_FPS": 15,
        "DETECTION_CONFIDENCE": 0.50,
        "EVENT_COOLDOWN_SECONDS": 10.0,
        "LOITERING_THRESHOLD_SECONDS": 8.0,
        "PRE_EVENT_SECONDS": 10,
        "POST_EVENT_SECONDS": 15,
        "FUSION_PROJECTION_GATE": 0.28,
        "UAV_RTB_BATTERY_PERCENT": 15,
        "PRIVACY_BLUR_ENABLED": False,
        "THREAT_SCORING_ENABLED": True,
        "AUDIO_ALERTS_ENABLED": True
    }
    update_runtime_settings(defaults)
    logger.info("[CONFIG] Surveillance parameters reset to factory defaults.")

    ws_manager.broadcast_sync({
        "type": "CONFIG_RESET",
        "defaults": defaults
    })

    return {
        "status": "SUCCESS",
        "message": "Configuration restored to factory defaults.",
        "defaults": defaults
    }
