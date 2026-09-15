import json
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from datetime import datetime, timezone

from backend.database.database import get_db
from backend.database.models import ZoneModel
from backend.websocket.manager import ws_manager
from backend.zones.zone_manager import zone_manager

router = APIRouter(prefix="/api/zones", tags=["Zones"])

class ZoneCreateOrUpdate(BaseModel):
    id: str
    name: str
    zone_type: str = "NORMAL"  # NORMAL, WARNING, RESTRICTED
    zone_subtype: str = "PUBLIC"  # PUBLIC, STAFF_ONLY, RESTRICTED, CRITICAL, NO_ENTRY
    security_level: str = "LOW"  # LOW, MEDIUM, HIGH, CRITICAL
    priority: int = Field(3, ge=1, le=5)
    status: str = "ACTIVE"  # ACTIVE, INACTIVE
    coordinates: List[List[float]] = Field(..., description="Polygon points [[x1, y1], [x2, y2], ...]")
    color: Optional[str] = None
    description: Optional[str] = None
    # Geo coordinates
    center_lat: Optional[float] = None
    center_lon: Optional[float] = None
    radius_m: Optional[float] = None
    geo_coords_json: Optional[str] = None
    # Sensor assignments
    authorized_persons: List[str] = []
    assigned_cameras: List[str] = []
    assigned_radar: List[str] = []
    assigned_uav: List[str] = []

class ZoneGpsUpdate(BaseModel):
    center_lat: float
    center_lon: float
    radius_m: Optional[float] = 25.0

class ZoneNameUpdate(BaseModel):
    name: str

class EvaluatePointPayload(BaseModel):
    x: float
    y: float
    vx: float = 0.0
    vy: float = 0.0
    object_id: str = "TARGET_SIM"
    object_class: str = "person"

def _zone_to_dict(z: ZoneModel) -> dict:
    coords = []
    try:
        coords = json.loads(z.coordinates_json)
    except Exception:
        pass

    def _parse_json_list(s):
        try:
            return json.loads(s) if s else []
        except Exception:
            return []

    return {
        "id": z.id,
        "name": z.name,
        "zone_type": z.zone_type,
        "zone_subtype": getattr(z, "zone_subtype", "PUBLIC") or "PUBLIC",
        "security_level": getattr(z, "security_level", "LOW") or "LOW",
        "priority": getattr(z, "priority", 3) or 3,
        "status": getattr(z, "status", "ACTIVE") or "ACTIVE",
        "coordinates": coords,
        "color": z.color,
        "description": z.description,
        "center_lat": getattr(z, "center_lat", None),
        "center_lon": getattr(z, "center_lon", None),
        "radius_m": getattr(z, "radius_m", None),
        "geo_coords_json": getattr(z, "geo_coords_json", None),
        "authorized_persons": _parse_json_list(getattr(z, "authorized_persons_json", "[]")),
        "assigned_cameras": _parse_json_list(getattr(z, "assigned_cameras_json", "[]")),
        "assigned_radar": _parse_json_list(getattr(z, "assigned_radar_json", "[]")),
        "assigned_uav": _parse_json_list(getattr(z, "assigned_uav_json", "[]")),
        "created_at": z.created_at.isoformat() if z.created_at else None,
    }

@router.get("")
def list_zones(db: Session = Depends(get_db)):
    """Retrieves all defined surveillance zones with polygon coordinates and sensor assignments."""
    zones = db.query(ZoneModel).order_by(ZoneModel.id).all()
    return [_zone_to_dict(z) for z in zones]

@router.get("/status")
def get_zones_status():
    """Retrieves real-time intrusion states and tracked targets across all zones."""
    return {
        "active_targets": zone_manager.get_all_target_states(),
        "total_zones": len(zone_manager.get_zones())
    }

@router.get("/{zone_id}")
def get_zone(zone_id: str, db: Session = Depends(get_db)):
    z = db.query(ZoneModel).filter(ZoneModel.id == zone_id).first()
    if not z:
        raise HTTPException(status_code=404, detail=f"Zone '{zone_id}' not found.")
    return _zone_to_dict(z)

@router.post("")
async def save_zone(payload: ZoneCreateOrUpdate, db: Session = Depends(get_db)):
    """Creates or updates a polygonal surveillance zone with sensor assignments."""
    zone = db.query(ZoneModel).filter(ZoneModel.id == payload.id).first()
    coords_json = json.dumps(payload.coordinates)

    color = payload.color
    if not color:
        type_upper = payload.zone_type.upper()
        if type_upper == "RESTRICTED":
            color = "#ff1744"
        elif type_upper == "WARNING":
            color = "#ffab00"
        else:
            color = "#00e676"

    now = datetime.now(timezone.utc)

    if zone:
        zone.name = payload.name
        zone.zone_type = payload.zone_type.upper()
        zone.coordinates_json = coords_json
        zone.color = color
        zone.description = payload.description
        # New fields (may not exist on old rows — safe assignment)
        try:
            zone.zone_subtype = payload.zone_subtype
            zone.security_level = payload.security_level.upper()
            zone.priority = payload.priority
            zone.status = payload.status.upper()
            zone.center_lat = payload.center_lat
            zone.center_lon = payload.center_lon
            zone.radius_m = payload.radius_m
            zone.geo_coords_json = payload.geo_coords_json
            zone.authorized_persons_json = json.dumps(payload.authorized_persons)
            zone.assigned_cameras_json = json.dumps(payload.assigned_cameras)
            zone.assigned_radar_json = json.dumps(payload.assigned_radar)
            zone.assigned_uav_json = json.dumps(payload.assigned_uav)
            zone.updated_at = now
        except Exception:
            pass
    else:
        zone = ZoneModel(
            id=payload.id,
            name=payload.name,
            zone_type=payload.zone_type.upper(),
            zone_subtype=payload.zone_subtype,
            security_level=payload.security_level.upper(),
            priority=payload.priority,
            status=payload.status.upper(),
            coordinates_json=coords_json,
            color=color,
            description=payload.description,
            center_lat=payload.center_lat,
            center_lon=payload.center_lon,
            radius_m=payload.radius_m,
            geo_coords_json=payload.geo_coords_json,
            authorized_persons_json=json.dumps(payload.authorized_persons),
            assigned_cameras_json=json.dumps(payload.assigned_cameras),
            assigned_radar_json=json.dumps(payload.assigned_radar),
            assigned_uav_json=json.dumps(payload.assigned_uav),
        )
        db.add(zone)

    db.commit()
    zone_manager.refresh_zones()

    await ws_manager.broadcast({
        "type": "ZONE_UPDATED",
        "zone": _zone_to_dict(zone)
    })

    return {"message": "Zone saved successfully", "zone": _zone_to_dict(zone)}

@router.post("/{zone_id}/gps")
@router.put("/{zone_id}/gps")
async def update_zone_gps(zone_id: str, payload: ZoneGpsUpdate, db: Session = Depends(get_db)):
    """Updates the GPS latitude, longitude, and coverage radius for a surveillance zone."""
    zone = db.query(ZoneModel).filter(ZoneModel.id == zone_id).first()
    now = datetime.now(timezone.utc)

    if not zone:
        # Create zone record if missing
        default_coords = [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]]
        zone = ZoneModel(
            id=zone_id,
            name=f"Sector {zone_id}",
            zone_type="RESTRICTED" if zone_id == "ZONE_C" else ("WARNING" if zone_id == "ZONE_B" else "NORMAL"),
            coordinates_json=json.dumps(default_coords),
            center_lat=payload.center_lat,
            center_lon=payload.center_lon,
            radius_m=payload.radius_m or 25.0,
            created_at=now,
            updated_at=now
        )
        db.add(zone)
    else:
        zone.center_lat = payload.center_lat
        zone.center_lon = payload.center_lon
        zone.radius_m = payload.radius_m or 25.0
        zone.updated_at = now

    db.commit()
    zone_manager.refresh_zones()

    zone_dict = _zone_to_dict(zone)
    await ws_manager.broadcast({
        "type": "ZONE_UPDATED",
        "zone": zone_dict
    })

    return {
        "status": "SUCCESS",
        "message": f"GPS coordinates for {zone_id} saved successfully ({payload.center_lat}, {payload.center_lon}).",
        "zone": zone_dict
    }

@router.patch("/{zone_id}/name")
@router.put("/{zone_id}/name")
async def update_zone_name(zone_id: str, payload: ZoneNameUpdate, db: Session = Depends(get_db)):
    """Renames an existing surveillance zone and broadcasts updates to UI and AI subsystems."""
    new_name = payload.name.strip()
    if not new_name:
        raise HTTPException(status_code=400, detail="Zone name cannot be empty.")

    zone = db.query(ZoneModel).filter(ZoneModel.id == zone_id).first()
    now = datetime.now(timezone.utc)

    if not zone:
        default_coords = [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]]
        zone = ZoneModel(
            id=zone_id,
            name=new_name,
            zone_type="RESTRICTED" if zone_id == "ZONE_C" else ("WARNING" if zone_id == "ZONE_B" else "NORMAL"),
            coordinates_json=json.dumps(default_coords),
            created_at=now,
            updated_at=now
        )
        db.add(zone)
    else:
        zone.name = new_name
        zone.updated_at = now

    db.commit()
    zone_manager.refresh_zones()

    zone_dict = _zone_to_dict(zone)
    await ws_manager.broadcast({
        "type": "ZONE_UPDATED",
        "zone": zone_dict
    })

    return {
        "status": "SUCCESS",
        "message": f"Zone '{zone_id}' name updated to '{new_name}'.",
        "zone": zone_dict
    }

@router.post("/evaluate")
def evaluate_point(payload: EvaluatePointPayload):
    """Evaluates a coordinate against the real-time intrusion state machine."""
    state, record = zone_manager.evaluate_point(
        point=(payload.x, payload.y),
        velocity=(payload.vx, payload.vy),
        object_id=payload.object_id,
        object_class=payload.object_class
    )
    return {
        "object_id": payload.object_id,
        "current_state": state.value,
        "transition": record.model_dump() if record else None
    }

@router.delete("/{zone_id}")
async def delete_zone(zone_id: str, db: Session = Depends(get_db)):
    """Deletes a surveillance zone."""
    zone = db.query(ZoneModel).filter(ZoneModel.id == zone_id).first()
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")
    db.delete(zone)
    db.commit()
    zone_manager.refresh_zones()

    await ws_manager.broadcast({
        "type": "ZONE_DELETED",
        "zone_id": zone_id
    })
    return {"message": "Zone deleted successfully", "zone_id": zone_id}
