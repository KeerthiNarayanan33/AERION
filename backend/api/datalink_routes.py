"""
SENTINEL-AI: Tactical Data Link REST Routes
Exposes STANAG 4586 Binary Frame Inspection, Radio Airtime Metrics, and Transmission.
"""

from fastapi import APIRouter
from typing import Dict, Any

from backend.network.tactical_datalink import tactical_datalink_encoder

router = APIRouter(prefix="/api/datalink", tags=["Tactical Data Link (STANAG 4586)"])

@router.get("/packet")
def get_current_packet() -> Dict[str, Any]:
    """Generates and returns the latest compact binary tactical data link frame."""
    return tactical_datalink_encoder.generate_compact_frame()

@router.get("/stats")
def get_datalink_stats() -> Dict[str, Any]:
    """Returns radio bandwidth savings and cumulative packets transmitted."""
    return tactical_datalink_encoder.get_stats()

@router.post("/transmit")
def transmit_tactical_packet() -> Dict[str, Any]:
    """Transmits packet over simulated low-bandwidth tactical radio link to HQ."""
    return tactical_datalink_encoder.transmit_packet()
