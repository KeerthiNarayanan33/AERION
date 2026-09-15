"""
Test Suite for Phase 18: Performance Optimization & Hardware Acceleration (Sections 15, 60, & 61).
Verifies:
1. Adaptive FPS Governor states (Auto-Adaptive, Eco-Idle 6 FPS, Burst-Max 30 FPS).
2. End-to-end Latency Budget Decomposition (< 100ms Section 61 requirement).
3. Hardware compute accelerator detection and quantization tier profiles.
4. FastAPI performance telemetry and governor control REST endpoints.
"""

import pytest
from httpx import AsyncClient, ASGITransport

from backend.main import app
from backend.ai.fps_governor import fps_governor, GovernorMode
from backend.ai.hw_accelerator import hw_accelerator
from backend.ai.inference_manager import inference_manager


# -----------------------------------------------------------------------------
# Unit Tests: Adaptive FPS Governor
# -----------------------------------------------------------------------------

def test_fps_governor_modes():
    """Verify governor respects ECO_IDLE, BALANCED, and BURST_MAX presets."""
    fps_governor.set_mode(GovernorMode.ECO_IDLE)
    assert fps_governor.mode == GovernorMode.ECO_IDLE
    assert fps_governor.get_target_fps() == 6.0

    fps_governor.set_mode(GovernorMode.BALANCED)
    assert fps_governor.mode == GovernorMode.BALANCED
    assert fps_governor.get_target_fps() == 15.0

    fps_governor.set_mode(GovernorMode.BURST_MAX)
    assert fps_governor.mode == GovernorMode.BURST_MAX
    assert fps_governor.get_target_fps() == 30.0


def test_fps_governor_auto_adaptive_threat_burst():
    """Verify AUTO_ADAPTIVE switches between 6 FPS (quiet) and 30 FPS (threat detected)."""
    fps_governor.set_mode(GovernorMode.AUTO_ADAPTIVE)
    # Clear any old threat times
    fps_governor._last_threat_time = 0.0
    fps_governor._simulated_load_until = 0.0

    # In calm state: 6.0 FPS
    target = fps_governor.get_target_fps(active_threats_present=False)
    assert target == 6.0

    # Threat arrives (radar contact or perimeter breach)
    target_burst = fps_governor.get_target_fps(active_threats_present=True)
    assert target_burst == 30.0

    status = fps_governor.get_status()
    assert status["is_bursting"] is True
    assert status["power_usage_pct"] == 100.0


def test_fps_governor_power_savings_calculation():
    """Verify power savings telemetry calculation at eco idle (6 FPS = ~80% savings)."""
    fps_governor.set_mode(GovernorMode.ECO_IDLE)
    fps_governor.get_target_fps()
    status = fps_governor.get_status()
    assert status["power_saved_pct"] == 80.0
    assert status["queue_lag_ms"] == 0.0


# -----------------------------------------------------------------------------
# Unit Tests: Hardware Accelerator & Latency Budget
# -----------------------------------------------------------------------------

def test_hardware_accelerator_detection():
    """Verify hardware accelerator probes compute provider and CPU cores."""
    status = hw_accelerator.get_status()
    assert "device_name" in status
    assert "compute_provider" in status
    assert status["cpu_cores"] >= 1
    assert "quantization_profiles" in status
    assert "FP32" in status["quantization_profiles"]
    assert "FP16" in status["quantization_profiles"]
    assert "INT8" in status["quantization_profiles"]


def test_latency_budget_decomposition_under_100ms():
    """Verify Section 61 budget: Total E2E Latency must remain strictly < 100 ms."""
    hw_accelerator.update_stage_latencies(
        capture_ms=14.0,
        inference_ms=28.0,
        tracking_ms=2.0,
        network_ms=3.0
    )
    decomp = hw_accelerator.get_latency_decomposition()
    assert decomp["status"] == "WITHIN_BUDGET"
    assert decomp["total_e2e_ms"] < 100.0
    assert decomp["headroom_ms"] > 0.0
    assert 0.1 <= decomp["stages_ms"]["capture"] <= 50.0
    assert 0.1 <= decomp["stages_ms"]["inference"] <= 80.0
    assert 0.1 <= decomp["stages_ms"]["tracking"] <= 20.0
    assert 0.1 <= decomp["stages_ms"]["network"] <= 20.0


def test_quantization_tier_switching():
    """Verify selecting FP16 and INT8 profiles."""
    hw_accelerator.set_precision("INT8")
    assert hw_accelerator.current_precision == "INT8"
    assert hw_accelerator.latency_inference_ms == 14.8

    hw_accelerator.set_precision("FP16")
    assert hw_accelerator.current_precision == "FP16"


def test_inference_manager_metrics_integration():
    """Verify InferenceManager exposes governor and hardware status in metrics."""
    metrics = inference_manager.get_metrics()
    assert "governor" in metrics
    assert "hardware" in metrics
    assert "current_target_fps" in metrics["governor"]
    assert "latency" in metrics["hardware"]


# -----------------------------------------------------------------------------
# Integration Tests: REST API Endpoints
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_api_perf_status_endpoint():
    """Verify GET /api/perf/status returns complete telemetry payload."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/perf/status")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "OPERATIONAL"
        assert "governor" in data
        assert "hardware" in data
        assert data["latency_compliance"] == "WITHIN_BUDGET"
        assert data["total_latency_ms"] < 100.0


@pytest.mark.anyio
async def test_api_perf_governor_mode_endpoint():
    """Verify POST /api/perf/governor sets mode and returns updated status."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.post("/api/perf/governor", json={"mode": "BALANCED"})
        assert res.status_code == 200
        data = res.json()
        assert data["governor"]["mode"] == "BALANCED"
        assert data["governor"]["current_target_fps"] == 15.0

        # Invalid mode returns 400
        res_bad = await ac.post("/api/perf/governor", json={"mode": "INVALID_MODE"})
        assert res_bad.status_code == 400


@pytest.mark.anyio
async def test_api_perf_simulate_load_endpoint():
    """Verify POST /api/perf/simulate-load ramps up target FPS to 30."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.post("/api/perf/simulate-load", json={"duration_seconds": 5.0})
        assert res.status_code == 200
        data = res.json()
        assert data["governor"]["is_bursting"] is True
        assert data["governor"]["current_target_fps"] == 30.0


@pytest.mark.anyio
async def test_api_perf_precision_endpoint():
    """Verify POST /api/perf/precision switches precision."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.post("/api/perf/precision", json={"precision": "INT8"})
        assert res.status_code == 200
        data = res.json()
        assert data["hardware"]["current_precision"] == "INT8"
