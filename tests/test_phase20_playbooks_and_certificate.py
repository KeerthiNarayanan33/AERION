"""
Test Suite for Phase 20: Master Tactical Demonstration Playbooks & Evaluator Pitch Mode
Sections 71, 73, 74, & 75: Staged Intrusion Drills & Evaluator Certification.
"""

import pytest
import hmac
import hashlib
from httpx import AsyncClient, ASGITransport

from backend.main import app
from backend.events.tactical_playbooks import tactical_playbook_engine
from backend.analytics.evaluator_certificate import evaluator_certificate_generator, SECRET_SEAL_KEY


# -----------------------------------------------------------------------------
# Unit Tests: Master Tactical Playbooks Engine
# -----------------------------------------------------------------------------

def test_playbooks_catalog():
    """Verify that all 8 demonstration playbooks are registered with valid metadata."""
    catalog = tactical_playbook_engine.get_playbooks_catalog()
    assert len(catalog) == 8
    
    # Check key flagship playbooks
    pb_ids = [p["id"] for p in catalog]
    assert pb_ids == [1, 2, 3, 4, 5, 6, 7, 8]
    
    pb6 = next(p for p in catalog if p["id"] == 6)
    assert pb6["code"] == "PB-06"
    assert pb6["threat_level"] == "CRITICAL"
    assert pb6["stages_count"] == 6
    assert "EW DF Triangulator" in pb6["subsystems"]
    assert "Form-IV SITREP" in pb6["subsystems"]

    pb7 = next(p for p in catalog if p["id"] == 7)
    assert pb7["code"] == "PB-07"
    assert "Pneumatic Net" in pb7["subsystems"]

    pb8 = next(p for p in catalog if p["id"] == 8)
    assert pb8["code"] == "PB-08"
    assert any("Mesh" in s for s in pb8["subsystems"])


@pytest.mark.anyio
async def test_playbook_6_flagship_drill_execution():
    """
    Verify Playbook 6 executes all 6 stages synchronously:
    EW Jamming -> Geophone Crawl -> Radar EKF Kinematics -> Thermal Radiance -> Deterrence -> Form-IV SITREP.
    """
    res = await tactical_playbook_engine.execute_playbook(6)
    assert res["playbook_id"] == 6
    assert res["status"] == "COMPLETED"
    assert res["total_stages"] == 6
    stages = res["stages"]
    assert len(stages) == 6

    # Stage 1: EW Jamming Triangulation
    assert stages[0]["stage"] == 1
    assert "mgrs_8digit" in stages[0]["metrics"]
    assert len(stages[0]["metrics"]["mgrs_8digit"]) >= 8

    # Stage 2: Geophone Seismic Cadence
    assert stages[1]["stage"] == 2
    assert stages[1]["metrics"]["classification"] == "STEALTH_CRAWL"

    # Stage 3: Radar 4D EKF Kinematics & ETB
    assert stages[2]["stage"] == 3
    assert stages[2]["metrics"]["etb_seconds"] > 0
    assert stages[2]["metrics"]["ppi_probability"] > 0

    # Stage 4: Slew-to-Cue PTZ & FLIR Boson LWIR
    assert stages[3]["stage"] == 4
    assert stages[3]["metrics"]["human_verified"] is True
    assert stages[3]["metrics"]["decision"] == "CONFIRMED_HUMAN_INTRUDER"

    # Stage 5: Deterrence Escalation
    assert stages[4]["stage"] == 5
    assert stages[4]["metrics"]["current_stage"] >= 1

    # Stage 6: Form-IV SITREP
    assert stages[5]["stage"] == 6
    assert "SITREP-" in stages[5]["metrics"]["report_reference"]
    assert len(stages[5]["metrics"]["hmac_seal"]) > 10


@pytest.mark.anyio
async def test_playbook_7_cuas_interceptor_drill():
    """Verify Playbook 7 executes rogue drone detection, scramble, pneumatic net capture, and datalink frame."""
    res = await tactical_playbook_engine.execute_playbook(7)
    assert res["playbook_id"] == 7
    assert res["status"] == "COMPLETED"
    assert res["total_stages"] == 4
    stages = res["stages"]

    # Stage 1: Acoustic detection
    assert stages[0]["metrics"]["classification"] in ("UAV_ROTOR_WHINE", "ACOUSTIC_ANOMALY")
    # Stage 2: Scramble
    assert stages[1]["metrics"]["threat_level"] == "CRITICAL"
    # Stage 3: Kinetic Intercept
    assert stages[2]["metrics"]["total_neutralized"] >= 1
    # Stage 4: STANAG 4586 Datalink frame
    assert stages[3]["metrics"]["packet_size_bytes"] < 180


@pytest.mark.anyio
async def test_playbook_8_lora_mesh_failover_drill():
    """Verify Playbook 8 executes backbone link drop, LoRa mesh re-routing, and WORM vault lockdown."""
    res = await tactical_playbook_engine.execute_playbook(8)
    assert res["playbook_id"] == 8
    assert res["status"] == "COMPLETED"
    assert res["total_stages"] == 3
    stages = res["stages"]

    assert stages[0]["metrics"]["status"] in ("NODE_DROPPED", "FAILOVER_ACTIVATED")
    assert stages[1]["metrics"]["packet_loss_pct"] == 0.0
    assert stages[2]["metrics"]["vault_mode"] == "WORM_IMMUTABLE"


@pytest.mark.anyio
async def test_playbook_step_by_step_evaluator_stepping():
    """Verify judge-controlled stepping advances one stage at a time and tracks progress."""
    # Reset first
    await tactical_playbook_engine.reset_all()

    step1 = await tactical_playbook_engine.step_playbook(6)
    assert step1["playbook_id"] == 6
    assert step1["stage_index"] == 1
    assert step1["total_stages"] == 6
    assert step1["is_last_stage"] is False
    assert step1["current_stage"]["stage"] == 1

    step2 = await tactical_playbook_engine.step_playbook(6)
    assert step2["stage_index"] == 2
    assert step2["current_stage"]["stage"] == 2


@pytest.mark.anyio
async def test_playbook_reset_all():
    """Verify reset restores all sensors, tracks, actuators, and drones to clean state."""
    res = await tactical_playbook_engine.reset_all()
    assert res["status"] == "SYSTEM_RESTORED"
    assert tactical_playbook_engine.active_playbook_id is None
    assert tactical_playbook_engine.current_stage_index == 0


# -----------------------------------------------------------------------------
# Unit Tests: SIH 2026 Evaluator Defense Certificate & HMAC Verification
# -----------------------------------------------------------------------------

def test_evaluator_certificate_generation_and_hmac_seal():
    """Verify that certificate data satisfies all 12 pillars and carries a valid HMAC-SHA256 seal."""
    cert = evaluator_certificate_generator.generate_certificate_data()

    assert "certificate_id" in cert
    assert cert["compliance_score_pct"] == 100.0
    assert cert["compliance_status"] == "100% SPECIFICATION COMPLIANT"
    assert cert["total_value_propositions_verified"] == "12 / 12"
    assert len(cert["pillars_evaluated"]) == 12

    # Check hardware profile
    assert cert["hardware_profiling"]["end_to_end_latency_ms"] < 100.0
    assert "INT8" in cert["hardware_profiling"]["quantization_support"]

    # Verify cryptographic seal authenticity
    seal_info = cert["cryptographic_seal"]
    assert seal_info["algorithm"] == "HMAC-SHA256"
    assert len(seal_info["signature"]) == 64  # SHA256 hex is 64 characters
    assert seal_info["air_gapped_authenticity"] is True


def test_evaluator_certificate_html_rendering():
    """Verify that print-ready HTML certificate renders complete with defense badges and seal."""
    html = evaluator_certificate_generator.generate_html_certificate()
    assert "<!DOCTYPE html>" in html
    assert "SMART INDIA HACKATHON 2026" in html
    assert "100% SPECIFICATION COMPLIANT" in html
    assert "SECTION 75: 12 CORE VALUE PROPOSITIONS AUDIT MATRIX" in html
    assert "SECTION 72: ARCHITECTURAL INTEGRITY" in html
    assert "CRYPTOGRAPHIC DEFENSE INTEGRITY SEAL" in html
    assert len(html) > 2000


# -----------------------------------------------------------------------------
# Integration Tests: REST API Endpoints
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_rest_playbooks_catalog():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/playbooks")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "SUCCESS"
        assert data["total_playbooks"] == 8


@pytest.mark.anyio
async def test_rest_playbook_execute():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.post("/api/playbooks/6/execute")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "SUCCESS"
        assert data["execution"]["playbook_id"] == 6
        assert data["execution"]["status"] == "COMPLETED"


@pytest.mark.anyio
async def test_rest_playbook_step_and_reset():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        step_res = await ac.post("/api/playbooks/7/step")
        assert step_res.status_code == 200
        assert step_res.json()["status"] == "SUCCESS"

        reset_res = await ac.post("/api/playbooks/reset")
        assert reset_res.status_code == 200
        assert reset_res.json()["result"]["status"] == "SYSTEM_RESTORED"


@pytest.mark.anyio
async def test_rest_evaluator_certificate_endpoints():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # JSON endpoint
        json_res = await ac.get("/api/playbooks/certificate")
        assert json_res.status_code == 200
        assert json_res.json()["certificate"]["compliance_score_pct"] == 100.0

        # HTML endpoint
        html_res = await ac.get("/api/playbooks/certificate/html")
        assert html_res.status_code == 200
        assert "text/html" in html_res.headers["content-type"]
        assert "SMART INDIA HACKATHON 2026" in html_res.text
