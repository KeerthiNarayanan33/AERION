"""
SENTINEL-AI: Geospatial & Tactical Grid REST Routes
Exposes Georeferenced Anchor, Coordinate Transformations, and QRT Mission Dispatch orders.
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List

from backend.geospatial.coordinates import geospatial_engine
from backend.radar.radar_driver import radar_driver

router = APIRouter(prefix="/api/geo", tags=["Geospatial & Tactical Grid"])

class TransformRequest(BaseModel):
    mode: str = Field(default="xy", description="'xy', 'polar', or 'camera_pixel'")
    x_east_m: Optional[float] = None
    y_north_m: Optional[float] = None
    range_m: Optional[float] = None
    azimuth_deg: Optional[float] = None
    norm_u: Optional[float] = None
    norm_v: Optional[float] = None

class QRTDispatchRequest(BaseModel):
    event_id: str = "EVT_BREACH_ZONE_C"
    target_id: str = "TGT_001"
    classification: str = "person"
    severity: str = "CRITICAL"
    local_x_m: float = 2.4
    local_y_m: float = 4.8
    speed_mps: float = 1.6
    threat_zone: str = "ZONE_C"
    operator_callsign: str = "WATCH_COMMANDER_01"

@router.get("/anchor")
def get_base_anchor() -> Dict[str, Any]:
    """Returns the geodetic anchor datum of the Command Hub Forward Operating Base."""
    return geospatial_engine.get_anchor_info()

@router.post("/transform")
def transform_coordinates(req: TransformRequest) -> Dict[str, Any]:
    """
    Transforms sensor coordinates into WGS-84 Lat/Lon, UTM Zone 43N, and MGRS 8-digit military grid.
    """
    if req.mode == "xy":
        if req.x_east_m is None or req.y_north_m is None:
            raise HTTPException(status_code=400, detail="x_east_m and y_north_m are required for xy mode")
        return geospatial_engine.local_xy_to_georeferenced(req.x_east_m, req.y_north_m)
    elif req.mode == "polar":
        if req.range_m is None or req.azimuth_deg is None:
            raise HTTPException(status_code=400, detail="range_m and azimuth_deg are required for polar mode")
        return geospatial_engine.radar_polar_to_georeferenced(req.range_m, req.azimuth_deg)
    elif req.mode == "camera_pixel":
        if req.norm_u is None or req.norm_v is None:
            raise HTTPException(status_code=400, detail="norm_u and norm_v are required for camera_pixel mode")
        return geospatial_engine.camera_pixel_to_georeferenced(req.norm_u, req.norm_v)
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported mode: {req.mode}")

@router.get("/targets")
def get_georeferenced_targets() -> Dict[str, Any]:
    """
    Returns all active radar targets annotated with live WGS-84, UTM, and MGRS military grid coordinates.
    """
    raw_targets = radar_driver.get_active_targets()
    geo_targets = []
    
    for t in raw_targets:
        geo = geospatial_engine.local_xy_to_georeferenced(t["x"], t["y"])
        geo_targets.append({
            "target_id": t["target_id"],
            "x": t["x"],
            "y": t["y"],
            "speed": t["speed"],
            "distance": t["distance"],
            "bearing_deg": geo["bearing_deg"],
            "latitude": geo["latitude"],
            "longitude": geo["longitude"],
            "latitude_dms": geo["latitude_dms"],
            "longitude_dms": geo["longitude_dms"],
            "utm": f"{geo['utm_zone']} {geo['utm_easting']}E {geo['utm_northing']}N",
            "mgrs_8digit": geo["mgrs_8digit"]
        })
    
    return {
        "status": "HEALTHY",
        "anchor": geospatial_engine.get_anchor_info(),
        "total_targets": len(geo_targets),
        "targets": geo_targets
    }

@router.post("/qrt-dispatch")
def generate_qrt_mission_dispatch(req: QRTDispatchRequest) -> Dict[str, Any]:
    """
    Generates a formalized Quick Reaction Team (QRT) Tactical Mission Dispatch Order
    with target MGRS grid, azimuth bearing, and intercept parameters.
    """
    order = geospatial_engine.generate_qrt_dispatch_order(
        event_id=req.event_id,
        target_id=req.target_id,
        classification=req.classification,
        severity=req.severity,
        local_x_m=req.local_x_m,
        local_y_m=req.local_y_m,
        speed_mps=req.speed_mps,
        threat_zone=req.threat_zone,
        operator_callsign=req.operator_callsign
    )
    return order
