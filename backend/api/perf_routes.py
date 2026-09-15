"""
SENTINEL-AI Performance & Hardware Acceleration API Routes (Sections 15, 60, & 61).
Provides endpoints for monitoring end-to-end latency decomposition,
controlling the Adaptive Inference FPS Governor, and querying hardware accelerator status.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

from backend.ai.fps_governor import fps_governor, GovernorMode
from backend.ai.hw_accelerator import hw_accelerator
from backend.logger import logger

router = APIRouter(prefix="/api/perf", tags=["Performance & Hardware Acceleration"])


class GovernorModeRequest(BaseModel):
    mode: str = Field(..., description="Target mode: AUTO_ADAPTIVE, ECO_IDLE, BALANCED, BURST_MAX")


class SimulateLoadRequest(BaseModel):
    duration_seconds: float = Field(10.0, ge=1.0, le=60.0, description="Duration in seconds to simulate threat load")


class PrecisionRequest(BaseModel):
    precision: str = Field(..., description="Target quantization precision: FP32, FP16, INT8")


@router.get("/status", summary="Get comprehensive performance & hardware status")
async def get_performance_status() -> Dict[str, Any]:
    """
    Returns live telemetry for:
    1. Adaptive FPS Governor (mode, target FPS, power savings %, frame drop stats)
    2. End-to-end Latency Budget Breakdown (capture, inference, tracking, network ms, and <100ms headroom)
    3. Hardware Execution Provider and Precision Profile
    """
    gov_status = fps_governor.get_status()
    hw_status = hw_accelerator.get_status()
    return {
        "status": "OPERATIONAL",
        "governor": gov_status,
        "hardware": hw_status,
        "latency_compliance": hw_status["latency"]["status"],
        "total_latency_ms": hw_status["latency"]["total_e2e_ms"],
        "power_saved_pct": gov_status["power_saved_pct"]
    }


@router.post("/governor", summary="Configure inference FPS governor mode")
async def set_governor_mode(req: GovernorModeRequest) -> Dict[str, Any]:
    """Updates governor mode (AUTO_ADAPTIVE, ECO_IDLE, BALANCED, BURST_MAX)."""
    mode_str = req.mode.upper()
    valid_modes = [m.value for m in GovernorMode]
    if mode_str not in valid_modes:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid governor mode '{req.mode}'. Valid modes: {valid_modes}"
        )
    new_mode = fps_governor.set_mode(mode_str)
    return {
        "message": f"Governor mode updated to {new_mode.value}",
        "governor": fps_governor.get_status()
    }


@router.post("/simulate-load", summary="Simulate threat load to test burst ramp-up")
async def simulate_threat_load(req: SimulateLoadRequest = SimulateLoadRequest()) -> Dict[str, Any]:
    """
    Forces governor into BURST_MAX (25-30 FPS) for demo/testing duration,
    verifying autonomous threat burst transition in < 20 ms.
    """
    fps_governor.simulate_threat_load(duration_seconds=req.duration_seconds)
    return {
        "message": f"Simulated threat load active for {req.duration_seconds}s. Target FPS ramped to 30 FPS.",
        "governor": fps_governor.get_status()
    }


@router.post("/precision", summary="Select quantization precision tier")
async def set_precision(req: PrecisionRequest) -> Dict[str, Any]:
    """Selects FP32, FP16, or INT8 quantization tier."""
    prec = req.precision.upper()
    if prec not in ("FP32", "FP16", "INT8"):
        raise HTTPException(
            status_code=400,
            detail="Invalid precision. Must be one of: FP32, FP16, INT8"
        )
    active = hw_accelerator.set_precision(prec)
    return {
        "message": f"Active quantization precision set to {active}",
        "hardware": hw_accelerator.get_status()
    }
