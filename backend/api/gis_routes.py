"""
SENTINEL-AI: Tactical GIS Vector Mapping API Routes
Sections 37, 51, & 67: Offline GeoJSON vector layers, MGRS tactical grid, and sensor FOV cones.
"""

from fastapi import APIRouter
from backend.geospatial.gis_engine import tactical_gis_engine

router = APIRouter(prefix="/api/gis", tags=["Tactical GIS"])

@router.get("/vector-layers")
def get_vector_layers():
    """Returns complete offline tactical vector map layers as standard GeoJSON."""
    return tactical_gis_engine.get_tactical_vector_layers()
