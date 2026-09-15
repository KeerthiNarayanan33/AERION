import os
import psutil
import json
import subprocess
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from backend.config import get_settings
from backend.database.database import get_db
from backend.database.models import SystemHealthModel, SettingModel
from backend.websocket.manager import ws_manager

router = APIRouter(prefix="/api/system", tags=["System"])
settings = get_settings()

class SettingUpdate(BaseModel):
    value: str

def get_gpu_metrics() -> Dict[str, Any]:
    """Inspects NVIDIA GPU if available via nvidia-smi."""
    try:
        cmd = ["nvidia-smi", "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu", "--format=csv,noheader,nounits"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
        if result.returncode == 0 and result.stdout.strip():
            parts = [p.strip() for p in result.stdout.strip().split(",")]
            return {
                "available": True,
                "name": parts[0],
                "gpu_utilization_percent": float(parts[1]),
                "memory_used_mb": float(parts[2]),
                "memory_total_mb": float(parts[3]),
                "temperature_c": float(parts[4])
            }
    except Exception:
        pass
    return {"available": False, "name": "CPU Fallback", "gpu_utilization_percent": 0.0, "memory_used_mb": 0.0, "memory_total_mb": 0.0}

@router.get("/health")
@router.get("/status")
def get_system_health(db: Session = Depends(get_db)):
    """Returns comprehensive system health for all surveillance subsystems."""
    records = db.query(SystemHealthModel).all()
    components: Dict[str, Any] = {}
    for r in records:
        components[r.component_name] = {
            "status": r.status,
            "last_checked": r.last_checked.isoformat() if r.last_checked else None,
            "metadata": json.loads(r.metrics_json) if r.metrics_json else {}
        }

    cpu_percent = psutil.cpu_percent(interval=0.1)
    ram = psutil.virtual_memory()
    gpu = get_gpu_metrics()

    return {
        "status": "HEALTHY",
        "system_mode": settings.SYSTEM_MODE,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "host_metrics": {
            "cpu_percent": cpu_percent,
            "ram_percent": ram.percent,
            "ram_used_gb": round((ram.total - ram.available) / (1024**3), 2),
            "ram_total_gb": round(ram.total / (1024**3), 2),
            "gpu": gpu
        },
        "components": components
    }

@router.get("/metrics")
def get_telemetry_metrics():
    """Real-time performance telemetry for command dashboard."""
    cpu_percent = psutil.cpu_percent(interval=None)
    ram = psutil.virtual_memory()
    gpu = get_gpu_metrics()

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "cpu_percent": cpu_percent,
        "ram_percent": ram.percent,
        "gpu": gpu,
        "target_ai_fps": settings.AI_INFERENCE_FPS,
        "camera_target_fps": settings.CAMERA_FPS,
        "system_mode": settings.SYSTEM_MODE
    }

@router.get("/settings")
def get_all_settings(db: Session = Depends(get_db)):
    """Retrieves all configuration settings stored in database."""
    items = db.query(SettingModel).all()
    return [{"key": i.key, "value": i.value, "description": i.description} for i in items]

@router.put("/settings/{key}")
async def update_setting(key: str, update: SettingUpdate, db: Session = Depends(get_db)):
    """Updates a runtime configuration setting and notifies WebSocket subscribers."""
    setting = db.query(SettingModel).filter(SettingModel.key == key).first()
    if not setting:
        raise HTTPException(status_code=404, detail=f"Setting key '{key}' not found")

    setting.value = update.value
    db.commit()

    # Broadcast setting change event
    await ws_manager.broadcast({
        "type": "SETTING_UPDATED",
        "key": key,
        "value": update.value,
        "timestamp": datetime.now(timezone.utc).isoformat()
    })

    return {"message": f"Setting {key} updated to {update.value}", "key": key, "value": update.value}

class FaultInjectionPayload(BaseModel):
    action: str = "FAIL"  # FAIL, RECOVER, STATUS
    reason: Optional[str] = "Simulated hardware link severance"

@router.post("/fault/{sensor_id}")
def inject_or_recover_sensor_fault(sensor_id: str, payload: FaultInjectionPayload):
    """
    Simulates hardware disconnect or link loss on a sensor, testing graceful degradation and auto-recovery.
    """
    from backend.camera.fault_recovery import sensor_watchdog
    return sensor_watchdog.inject_fault(sensor_id, action=payload.action, reason=payload.reason or "Evaluator injection")

@router.get("/fault/status")
def get_fault_recovery_status():
    """Returns watchdog status and telemetry for all monitored sensors."""
    from backend.camera.fault_recovery import sensor_watchdog
    return sensor_watchdog.get_all_status()
