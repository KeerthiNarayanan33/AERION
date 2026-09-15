"""
SENTINEL-AI: Forensic Timeline Incident Replay API Routes
Sections 26, 47, & 66: Timeline range, time-travel historical state query, and forensic blackbox dossier.
"""

from fastapi import APIRouter, Query
from backend.events.timeline_replay import timeline_replay_engine

router = APIRouter(prefix="/api/replay", tags=["Timeline Replay"])

@router.get("/timeline")
def get_timeline():
    """Returns timeline bounds, duration, and incident markers for scrubbing."""
    return timeline_replay_engine.get_timeline_range()

@router.get("/state")
def get_state_at(epoch_sec: int = Query(..., description="Unix epoch timestamp in seconds")):
    """Fetches full historical multi-sensor state at the specified second."""
    return timeline_replay_engine.get_state_at_timestamp(epoch_sec)

@router.get("/dossier")
def get_blackbox_dossier(incident_id: str = Query(default="EVT_INCIDENT_01")):
    """Generates court-admissible forensic dossier with SHA-256 integrity seal."""
    return timeline_replay_engine.generate_forensic_blackbox_dossier(incident_id=incident_id)
