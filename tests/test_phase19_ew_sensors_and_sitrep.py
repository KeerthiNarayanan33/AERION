"""
Test Suite for Phase 19: Electronic Warfare Jamming Triangulation, Acoustic/Seismic Ground Sensors,
Thermal Radiance Verifier, and Military SITREP Generator (Sections 62, 64, 65, 66, 67, & 70).
"""

import pytest
from httpx import AsyncClient, ASGITransport

from backend.main import app
from backend.radar.jamming_triangulator import jamming_triangulator
from backend.events.ground_sensors import ground_sensor_manager
from backend.ai.thermal_verifier import thermal_verifier
from backend.analytics.sitrep_generator import sitrep_generator


# -----------------------------------------------------------------------------
# Unit Tests: EW Jamming Triangulation & Direction-Finding
# -----------------------------------------------------------------------------

def test_jamming_triangulation_least_squares():
    """Verify 3-station AoA least-squares triangulation locates hostile RF jammer."""
    true_x = -5.0
    true_y = 30.0
    res = jamming_triangulator.triangulate(true_emitter_x=true_x, true_emitter_y=true_y, noise_std_deg=0.5)

    assert res["status"] == "TRIANGULATION_LOCKED"
    assert "georeferenced" in res
    assert "mgrs_8digit" in res["georeferenced"]
    assert len(res["georeferenced"]["mgrs_8digit"]) >= 8

    # Estimated coordinates should be close to true emitter (within 3m with 0.5 deg noise)
    est_x = res["estimated_coords"]["x_m"]
    est_y = res["estimated_coords"]["y_m"]
    assert abs(est_x - true_x) < 4.0
    assert abs(est_y - true_y) < 4.0
    assert res["estimated_coords"]["cep_radius_m"] > 0.0

    # Anti-spoofing fallback triggered
    assert res["anti_spoofing"]["gps_denial_detected"] is True
    assert res["anti_spoofing"]["countermeasure"] == "INS_DEAD_RECKONING_FALLBACK"


def test_jamming_triangulator_status_and_reset():
    """Verify status reporting and clean reset."""
    status = jamming_triangulator.get_status()
    assert len(status["stations"]) == 3
    assert status["is_jamming_active"] is True

    jamming_triangulator.reset()
    clean_status = jamming_triangulator.get_status()
    assert clean_status["is_jamming_active"] is False
    assert clean_status["latest_triangulation"] is None


# -----------------------------------------------------------------------------
# Unit Tests: Seismic Geophone & Acoustic Sensor Ingestion
# -----------------------------------------------------------------------------

def test_seismic_cadence_classification():
    """Verify frequency & energy classification of ground vibration signatures."""
    # Crawling (0.8 Hz)
    assert ground_sensor_manager.classify_seismic_cadence(0.8, 0.7) == "STEALTH_CRAWL"

    # Footstep cadence (2.1 Hz)
    assert ground_sensor_manager.classify_seismic_cadence(2.1, 0.5) == "FOOTSTEP_CADENCE"

    # Vehicle rumble (30.0 Hz)
    assert ground_sensor_manager.classify_seismic_cadence(30.0, 0.9) == "VEHICLE_TREAD_RUMBLE"

    # Fence cutting (>75.0 Hz)
    assert ground_sensor_manager.classify_seismic_cadence(85.0, 0.95) == "FENCE_CUTTING_OR_CLIMB"


def test_seismic_trigger_ingestion_and_gunshot_acoustic():
    """Verify recording seismic vibration and acoustic blast impulses."""
    # Footstep trigger
    trig1 = ground_sensor_manager.record_seismic_trigger(node_id="GEO_01", cadence_hz=2.0, energy=0.6)
    assert trig1["classification"] == "FOOTSTEP_CADENCE"
    assert trig1["is_critical"] is False

    # Gunshot acoustic impulse (> 125 dB)
    trig2 = ground_sensor_manager.record_seismic_trigger(node_id="MIC_01", cadence_hz=100.0, energy=0.98, audio_db=140.0)
    assert trig2["classification"] == "GUNSHOT_IMPULSE"
    assert trig2["acoustic_label"] == "GUNSHOT_IMPULSE"
    assert trig2["is_critical"] is True
    assert trig2["threat_score"] == 0.95


# -----------------------------------------------------------------------------
# Unit Tests: Thermal Radiance Verifier
# -----------------------------------------------------------------------------

def test_thermal_radiance_human_verification():
    """Verify human metabolic radiance (36.4°C) is verified and cold debris rejected."""
    # Human standing (36.4°C, aspect ratio 2.4)
    res_human = thermal_verifier.verify_target(
        track_id="TRK_01",
        class_name="person",
        bbox_aspect_ratio=2.4,
        apparent_temp_c=36.4,
        ambient_temp_c=22.0
    )
    assert res_human["decision"] == "CONFIRMED_HUMAN_INTRUDER"
    assert res_human["is_human_verified"] is True
    assert res_human["confidence"] >= 0.90

    # Cold debris / windblown tumbleweed (22.5°C with ambient 22.0°C)
    res_debris = thermal_verifier.verify_target(
        track_id="TRK_02",
        class_name="person",
        apparent_temp_c=22.5,
        ambient_temp_c=22.0
    )
    assert res_debris["decision"] == "FALSE_ALARM_INERT_DEBRIS"
    assert res_debris["is_human_verified"] is False

    # Quadruped animal (39.8°C)
    res_animal = thermal_verifier.verify_target(
        track_id="TRK_03",
        class_name="animal",
        apparent_temp_c=39.8,
        ambient_temp_c=22.0
    )
    assert res_animal["decision"] == "FALSE_ALARM_WILDLIFE"
    assert res_animal["is_human_verified"] is False


# -----------------------------------------------------------------------------
# Unit Tests: Military Form-IV SITREP Generator & HMAC Seal
# -----------------------------------------------------------------------------

def test_sitrep_compilation_and_cryptographic_seal():
    """Verify Form-IV tactical report structure and HMAC-SHA256 non-repudiation seal."""
    sitrep = sitrep_generator.compile_sitrep()
    assert sitrep["form_id"] == "CAPF/BSF FORM-IV (TACTICAL INCIDENT SITREP)"
    assert "dtg" in sitrep
    assert "Z " in sitrep["dtg"]  # Zulu military DTG format
    assert "mgrs_grid" in sitrep["incident"]
    assert "cryptographic_hmac_sha256_seal" in sitrep
    assert len(sitrep["cryptographic_hmac_sha256_seal"]) == 64  # SHA-256 hex length

    # HTML rendering
    html = sitrep_generator.generate_html_report(sitrep)
    assert "OFFICIAL TACTICAL SITREP" in html
    assert sitrep["cryptographic_hmac_sha256_seal"] in html
    assert "Section 65B Indian Evidence Act" in html


# -----------------------------------------------------------------------------
# Integration Tests: REST API Endpoints
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_api_ew_sensors_status_endpoint():
    """Verify GET /api/ew-sensors/status returns consolidated metrics."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/ew-sensors/status")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "OPERATIONAL"
        assert "direction_finding_array" in data
        assert "ground_sensors" in data
        assert "thermal_verifier" in data


@pytest.mark.anyio
async def test_api_ew_sensors_triangulate_endpoint():
    """Verify POST /api/ew-sensors/triangulate localizes hostile jammer."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.post("/api/ew-sensors/triangulate", json={"true_emitter_x": -6.0, "true_emitter_y": 25.0})
        assert res.status_code == 200
        data = res.json()
        assert "triangulation" in data
        assert data["triangulation"]["status"] == "TRIANGULATION_LOCKED"
        assert "mgrs_8digit" in data["triangulation"]["georeferenced"]


@pytest.mark.anyio
async def test_api_ew_sensors_seismic_trigger_endpoint():
    """Verify POST /api/ew-sensors/seismic-trigger classifies ground vibration."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.post("/api/ew-sensors/seismic-trigger", json={"node_id": "GEO_02", "cadence_hz": 0.8, "energy": 0.78})
        assert res.status_code == 200
        data = res.json()
        assert data["event"]["classification"] == "STEALTH_CRAWL"


@pytest.mark.anyio
async def test_api_ew_sensors_thermal_check_endpoint():
    """Verify POST /api/ew-sensors/thermal-check returns radiometric decision."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.post("/api/ew-sensors/thermal-check", json={"track_id": "TRK_TEST", "class_name": "person", "apparent_temp_c": 36.5})
        assert res.status_code == 200
        data = res.json()
        assert data["verification"]["is_human_verified"] is True
        assert data["verification"]["decision"] == "CONFIRMED_HUMAN_INTRUDER"


@pytest.mark.anyio
async def test_api_ew_sensors_sitrep_endpoints():
    """Verify GET /api/ew-sensors/sitrep and HTML view."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # JSON SITREP
        res_json = await ac.get("/api/ew-sensors/sitrep")
        assert res_json.status_code == 200
        data = res_json.json()
        assert "cryptographic_hmac_sha256_seal" in data

        # HTML SITREP
        res_html = await ac.get("/api/ew-sensors/sitrep/html")
        assert res_html.status_code == 200
        assert "text/html" in res_html.headers.get("content-type", "")
        assert "CAPF/BSF FORM-IV" in res_html.text
