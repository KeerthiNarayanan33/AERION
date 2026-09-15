import math
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from backend.database.database import get_db
from backend.database.models import RadarSensorModel
from backend.websocket.manager import ws_manager
from backend.radar.radar_driver import radar_driver, RadarTarget
from backend.fusion.fusion_engine import fusion_engine

router = APIRouter(prefix="/api/radar", tags=["Radar"])

class RawTarget(BaseModel):
    id: int
    x: float  # cm or m relative to radar
    y: float
    speed_x: Optional[float] = None
    speed_y: Optional[float] = None
    speed: Optional[float] = None
    resolution: Optional[float] = 0.1

class RadarIngestPacket(BaseModel):
    sensor_id: str = "RADAR_01"
    timestamp: Optional[float] = None
    targets: List[RawTarget] = Field(default_factory=list)

class SimulateTargetPayload(BaseModel):
    target_id: int = 1
    x: float = 0.5  # meters
    y: float = 4.0  # meters
    speed: float = -1.2  # m/s

@router.get("/status")
def get_radar_status(db: Session = Depends(get_db)):
    """Retrieves LD2450 radar sensor hardware status."""
    sensor = db.query(RadarSensorModel).filter(RadarSensorModel.id == "RADAR_01").first()
    active_targets = radar_driver.get_active_targets()

    return {
        "id": sensor.id if sensor else "RADAR_01",
        "name": sensor.name if sensor else "LD2450 mmWave Radar",
        "model": sensor.model if sensor else "LD2450",
        "status": radar_driver.status,
        "connection_type": sensor.connection_type if sensor else "WIFI",
        "ip_address": sensor.ip_address if sensor else "10.146.49.X",
        "port": sensor.port if sensor else 8080,
        "last_heartbeat": datetime.fromtimestamp(radar_driver.last_heartbeat, tz=timezone.utc).isoformat(),
        "active_targets_count": len(active_targets)
    }

@router.get("/targets")
def get_current_targets():
    """Returns current active targets detected by the LD2450 radar."""
    targets = radar_driver.get_active_targets()
    return {
        "sensor_id": radar_driver.sensor_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "targets": [t.to_dict() for t in targets]
    }

@router.get("/fused-targets")
def get_fused_targets():
    """Returns real-time cross-validated tracks produced by the Sensor Fusion Engine."""
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "fused_tracks": fusion_engine.get_latest_fused_tracks()
    }

@router.post("/ingest")
async def ingest_radar_data(packet: RadarIngestPacket, db: Session = Depends(get_db)):
    """
    Ingestion endpoint for ESP32 Wi-Fi packets.
    Parses raw radar coordinates and executes sensor fusion with active optical camera tracks.
    """
    now = datetime.now(timezone.utc)

    # 1. Parse targets using Radar Driver
    raw_dicts = [t.model_dump() for t in packet.targets]
    radar_targets = radar_driver.parse_esp32_json(raw_dicts)

    # 2. Update DB sensor heartbeat
    sensor = db.query(RadarSensorModel).filter(RadarSensorModel.id == packet.sensor_id).first()
    if sensor:
        sensor.last_heartbeat = now
        sensor.status = "ONLINE"
        db.commit()

    # 3. Retrieve Camera tracks for Multi-Sensor Fusion
    camera_tracks = []
    cam_status = "ONLINE"
    try:
        from backend.ai.inference_manager import inference_manager
        from backend.camera.camera_manager import camera_manager
        cam_inst = camera_manager.get_camera("CAM_01")
        if cam_inst:
            cam_status = cam_inst.status
        active_t = inference_manager.get_latest_tracks("CAM_01")
        for t in active_t:
            norm_x, norm_y = t.center
            camera_tracks.append({
                "track_id": f"CAM_{t.track_id}",
                "class_name": t.class_name,
                "confidence": t.confidence,
                "norm_x": norm_x / 640.0,
                "norm_y": norm_y / 480.0,
                "zone_id": getattr(t, "zone_id", "ZONE_B")
            })
    except Exception as cam_err:
        logger.debug(f"[RADAR_FUSION] Camera track retrieval bypass: {cam_err}")
        camera_tracks = []

    # 4. Run Multi-Sensor Fusion
    fused = fusion_engine.fuse_frame(camera_tracks, radar_targets, camera_status=cam_status)

    # 5. Broadcast real-time telemetry over WebSocket
    targets_data = [t.to_dict() for t in radar_targets]
    await ws_manager.broadcast({
        "type": "RADAR_TARGETS_UPDATE",
        "sensor_id": packet.sensor_id,
        "targets": targets_data,
        "timestamp": now.isoformat()
    })

    if fused:
        await ws_manager.broadcast({
            "type": "FUSED_TRACKS_UPDATE",
            "fused_tracks": [f.to_dict() for f in fused],
            "timestamp": now.isoformat()
        })

    return {
        "status": "ACK",
        "targets_processed": len(radar_targets),
        "fused_tracks_count": len(fused)
    }

@router.post("/simulate-target")
async def simulate_radar_target(payload: SimulateTargetPayload):
    """Injects a simulated radar target on demand for SIH demonstrations."""
    target = radar_driver.inject_single_target(
        target_id=payload.target_id,
        x=payload.x,
        y=payload.y,
        speed=payload.speed
    )

    now = datetime.now(timezone.utc)
    await ws_manager.broadcast({
        "type": "RADAR_TARGETS_UPDATE",
        "sensor_id": "RADAR_01",
        "targets": [target.to_dict()],
        "is_simulated": True,
        "timestamp": now.isoformat()
    })

    return {
        "message": "Simulated radar target injected",
        "target": target.to_dict()
    }

@router.get("/rf-integrity")
def get_rf_integrity_status():
    """
    Returns real-time Defensive Electronic Warfare (EW) & RF Jamming spectrum telemetry (Sections 61 & 62).
    """
    from backend.radar.rf_integrity import rf_integrity_monitor
    return rf_integrity_monitor.get_telemetry()

@router.post("/simulate-jamming")
async def simulate_rf_jamming_attack():
    """
    Triggers active RF barrage jamming on radar telemetry and broadcasts EW_JAMMING_ALERT over WebSocket.
    """
    from backend.radar.rf_integrity import rf_integrity_monitor
    telemetry = rf_integrity_monitor.simulate_jamming(severity="HIGH", duration_seconds=25.0)

    await ws_manager.broadcast({
        "type": "RF_JAMMING_ALERT",
        "telemetry": telemetry
    })

    return {
        "message": "Active RF Jamming Anomaly triggered and broadcasted",
        "telemetry": telemetry
    }

@router.post("/reset-rf")
async def reset_rf_spectrum():
    """
    Restores clean RF spectrum baseline after an electronic warfare simulation.
    """
    from backend.radar.rf_integrity import rf_integrity_monitor
    telemetry = rf_integrity_monitor.reset()

    await ws_manager.broadcast({
        "type": "RF_INTEGRITY_UPDATE",
        "telemetry": telemetry
    })

    return {
        "message": "RF spectrum restored to nominal clean state",
        "telemetry": telemetry
    }

