"""
SENTINEL-AI Electronic Warfare & Ground Sensor API Routes (Sections 62, 64, 65, 66, 67, & 70).
Provides endpoints for RF Jamming Triangulation, Piezo Geophone Ingestion,
Thermal Radiance Cross-Spectral Verification, and Military SITREP Generation.
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

from backend.radar.jamming_triangulator import jamming_triangulator
from backend.events.ground_sensors import ground_sensor_manager
from backend.ai.thermal_verifier import thermal_verifier
from backend.analytics.sitrep_generator import sitrep_generator
from backend.logger import logger

router = APIRouter(prefix="/api/ew-sensors", tags=["Electronic Warfare & Ground Sensors"])


class TriangulateRequest(BaseModel):
    true_emitter_x: float = Field(-4.5, description="True Cartesian X coordinate of emitter in meters")
    true_emitter_y: float = Field(28.0, description="True Cartesian Y coordinate of emitter in meters")
    noise_std_deg: float = Field(1.2, ge=0.0, le=10.0, description="Sensor angle noise in degrees")


class SeismicTriggerRequest(BaseModel):
    node_id: str = Field("GEO_02", description="Geophone / acoustic sensor node ID (e.g., GEO_01, GEO_02, GEO_03, MIC_01)")
    cadence_hz: float = Field(0.8, ge=0.1, le=200.0, description="Measured ground vibration cadence in Hz")
    energy: float = Field(0.78, ge=0.0, le=1.0, description="Normalized signal energy [0.0 - 1.0]")
    audio_db: Optional[float] = Field(None, ge=30.0, le=160.0, description="Optional peak acoustic sound pressure in dB")


class ThermalCheckRequest(BaseModel):
    track_id: str = Field("CAM_01_TRK_01", description="Camera or radar track identifier")
    class_name: str = Field("person", description="Detected visual object class (person, animal, car)")
    bbox_aspect_ratio: float = Field(2.4, ge=0.1, le=10.0, description="Bounding box height-to-width ratio")
    apparent_temp_c: Optional[float] = Field(None, ge=-20.0, le=200.0, description="Radiometric temperature in Celsius")


@router.get("/status", summary="Get multi-domain EW, seismic, and thermal sensor status")
async def get_ew_sensors_status() -> Dict[str, Any]:
    """Provides consolidated operational status across EW, ground, and thermal sensors."""
    return {
        "status": "OPERATIONAL",
        "direction_finding_array": jamming_triangulator.get_status(),
        "ground_sensors": ground_sensor_manager.get_status(),
        "thermal_verifier": thermal_verifier.get_metrics()
    }


@router.post("/triangulate", summary="Triangulate hostile RF/GPS jammer using AoA least-squares")
async def triangulate_jammer(req: TriangulateRequest = TriangulateRequest()) -> Dict[str, Any]:
    """Executes multi-station bearing intersection and converts to 8-digit MGRS military grid."""
    result = jamming_triangulator.triangulate(
        true_emitter_x=req.true_emitter_x,
        true_emitter_y=req.true_emitter_y,
        noise_std_deg=req.noise_std_deg
    )
    return {
        "message": "Hostile EW Jammer localized via 3-station AoA least-squares intersection.",
        "triangulation": result
    }


@router.post("/seismic-trigger", summary="Ingest boundary geophone or acoustic sensor event")
async def ingest_seismic_trigger(req: SeismicTriggerRequest) -> Dict[str, Any]:
    """Classifies seismic frequency cadences (crawling, footsteps, vehicle, fence cutting)."""
    result = ground_sensor_manager.record_seismic_trigger(
        node_id=req.node_id,
        cadence_hz=req.cadence_hz,
        energy=req.energy,
        audio_db=req.audio_db
    )
    return {
        "message": f"Seismic event recorded: {result['classification']}",
        "event": result
    }


@router.post("/thermal-check", summary="Perform cross-spectral FLIR LWIR thermal verification")
async def verify_thermal_radiance(req: ThermalCheckRequest) -> Dict[str, Any]:
    """Validates human biological thermal envelope (34-38°C) to filter false alarms."""
    result = thermal_verifier.verify_target(
        track_id=req.track_id,
        class_name=req.class_name,
        bbox_aspect_ratio=req.bbox_aspect_ratio,
        apparent_temp_c=req.apparent_temp_c
    )
    return {
        "message": f"Thermal verification decision: {result['decision']}",
        "verification": result
    }


@router.get("/sitrep", summary="Generate official CAPF / BSF Form-IV Tactical SITREP")
async def get_tactical_sitrep(incident_id: Optional[str] = None) -> Dict[str, Any]:
    """Generates official military Form-IV incident report with HMAC-SHA256 digital seal."""
    return sitrep_generator.compile_sitrep(incident_id=incident_id)


@router.get("/sitrep/html", response_class=HTMLResponse, summary="Download / View print-ready military SITREP")
async def get_tactical_sitrep_html(incident_id: Optional[str] = None):
    """Renders print-ready military Form-IV dossier in high-contrast command formatting."""
    sitrep_data = sitrep_generator.compile_sitrep(incident_id=incident_id)
    html_content = sitrep_generator.generate_html_report(sitrep_data)
    return HTMLResponse(content=html_content)
