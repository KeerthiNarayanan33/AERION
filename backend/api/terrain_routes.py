"""
SENTINEL-AI: Terrain Elevation & Line-of-Sight (LOS) REST Routes
Exposes DEM Transects, Radar Shadow Pocket Analysis, and UAV Clearance Calculations.
"""

from fastapi import APIRouter, Query
from typing import Dict, Any

from backend.radar.terrain_los import terrain_los_analyzer

router = APIRouter(prefix="/api/terrain", tags=["Terrain Elevation & Line-of-Sight (LOS)"])

@router.get("/profile")
def get_terrain_elevation_profile() -> Dict[str, Any]:
    """
    Returns the border perimeter DEM transect, mast ray-casting visibility,
    and terrain shadow pocket boundaries.
    """
    return terrain_los_analyzer.compute_los_profile()

@router.get("/uav-los")
def get_uav_los_solution(altitude_m: float = Query(default=25.0, ge=5.0, le=100.0)) -> Dict[str, Any]:
    """
    Returns the UAV aerial look-down angle and clearance solution
    required to eliminate terrain shadow dead zones.
    """
    return terrain_los_analyzer.compute_uav_clearance_solution(uav_altitude_m=altitude_m)
