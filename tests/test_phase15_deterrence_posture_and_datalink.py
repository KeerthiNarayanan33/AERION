"""
SENTINEL-AI: Phase 15 Automated Test Suite
Validates:
1. Multi-Stage Non-Lethal Deterrence Escalation Matrix (Sections 22 & 75)
2. Intruder Posture & Carriage Anomaly Classifier (Sections 16 & 27)
3. Tactical Data Link & Low-Bandwidth Radio Sync (STANAG 4586) (Sections 50 & 60)
4. Master SIH 2026 Evaluator Compliance Audit (Sections 72 & 75)
"""

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.events.deterrence import deterrence_matrix_manager, STAGES
from backend.ai.posture_classifier import posture_classifier
from backend.network.tactical_datalink import tactical_datalink_encoder
from backend.system.sih_compliance import sih_compliance_auditor

client = TestClient(app)


# =========================================================================
# 1. NON-LETHAL DETERRENCE ESCALATION MATRIX (Sections 22 & 75)
# =========================================================================

@pytest.mark.anyio
async def test_deterrence_matrix_lifecycle():
    """Validates 4-stage graduated deterrence escalation, ROE compliance states, and reset."""
    # Reset to baseline
    reset_res = await deterrence_matrix_manager.reset_deterrence()
    assert reset_res["status"] == "RESET_COMPLETED"
    assert reset_res["current_stage"] == 0
    assert reset_res["compliance_status"] == "STANDBY"

    state = deterrence_matrix_manager.get_state()
    assert state["current_stage"] == 0
    assert state["stage_info"] is None
    assert len(state["all_stages"]) == 4

    # Stage 1: Optical Strobe (20 Hz)
    stg1 = await deterrence_matrix_manager.escalate_stage(event_id="EVT_01", target_id="TRK_01", zone_id="ZONE_C")
    assert stg1["current_stage"] == 1
    assert stg1["stage_info"]["code"] == "STAGE_1_OPTICAL_STROBE"
    assert stg1["stage_info"]["output_type"] == "OPTICAL_DAZZLER"
    assert stg1["compliance_status"] == "MONITORING_RESPONSE"

    # Stage 2: LRAD Directed Voice Warning (Hindi, Punjabi, English)
    stg2 = await deterrence_matrix_manager.escalate_stage(event_id="EVT_01", target_id="TRK_01", zone_id="ZONE_C")
    assert stg2["current_stage"] == 2
    assert stg2["stage_info"]["code"] == "STAGE_2_DIRECTIONAL_VOICE"
    assert "audio_scripts" in stg2["stage_info"]
    assert "hindi" in stg2["stage_info"]["audio_scripts"]
    assert "punjabi" in stg2["stage_info"]["audio_scripts"]
    assert "english" in stg2["stage_info"]["audio_scripts"]
    assert stg2["stage_info"]["decibels"] == 95

    # Stage 3: 115 dB Acoustic Dispersion Siren
    stg3 = await deterrence_matrix_manager.escalate_stage(event_id="EVT_01", target_id="TRK_01", zone_id="ZONE_C")
    assert stg3["current_stage"] == 3
    assert stg3["stage_info"]["code"] == "STAGE_3_ACOUSTIC_DISPERSION"
    assert stg3["stage_info"]["decibels"] == 115
    assert stg3["compliance_status"] == "NON_COMPLIANT_ESCALATION"

    # Stage 4: Tactical QRT Ground Intercept Directive
    stg4 = await deterrence_matrix_manager.escalate_stage(event_id="EVT_01", target_id="TRK_01", zone_id="ZONE_C")
    assert stg4["current_stage"] == 4
    assert stg4["stage_info"]["code"] == "STAGE_4_QRT_INTERCEPT"
    assert stg4["compliance_status"] == "QRT_GROUND_INTERCEPT_AUTHORIZED"

    # Stage cap check: should not escalate beyond stage 4
    stg5 = await deterrence_matrix_manager.escalate_stage(event_id="EVT_01", target_id="TRK_01", zone_id="ZONE_C")
    assert stg5["current_stage"] == 4

    # Reset
    await deterrence_matrix_manager.reset_deterrence()
    assert deterrence_matrix_manager.current_stage == 0


def test_deterrence_routes_api():
    """Validates REST endpoints for deterrence escalation and state retrieval."""
    # 1. State endpoint
    res = client.get("/api/deterrence/state")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "HEALTHY"
    assert "all_stages" in data

    # 2. Escalate endpoint
    res_esc = client.post("/api/deterrence/escalate", json={
        "event_id": "EVT_TEST_101",
        "target_id": "TARGET_ALPHA",
        "zone_id": "ZONE_C",
        "operator": "OFFICER_TEST"
    })
    assert res_esc.status_code == 200
    data_esc = res_esc.json()
    assert data_esc["status"] == "STAGE_ACTIVATED"
    assert data_esc["current_stage"] >= 1

    # 3. Reset endpoint
    res_reset = client.post("/api/deterrence/reset")
    assert res_reset.status_code == 200
    data_reset = res_reset.json()
    assert data_reset["status"] == "RESET_COMPLETED"
    assert data_reset["current_stage"] == 0


# =========================================================================
# 2. INTRUDER POSTURE & CARRIAGE ANOMALY CLASSIFIER (Sections 16 & 27)
# =========================================================================

def test_posture_classifier_geometry_and_rules():
    """Validates aspect-ratio based posture determination and carriage assessment."""
    # Case A: Prone crawling (Width=0.45, Height=0.15 -> AR=3.0 >= 1.35)
    crawl_bbox = [0.10, 0.50, 0.55, 0.65]
    crawl = posture_classifier.classify_target(
        target_id="TRK_CRAWL_01",
        bbox=crawl_bbox,
        speed_mps=0.4,
        zone_id="ZONE_C",
        has_equipment_load=True
    )
    assert crawl["posture"] == "PRONE_CRAWLING"
    assert crawl["aspect_ratio"] >= 1.35
    assert crawl["threat_level"] == "CRITICAL"
    assert crawl["is_stealth_tactic"] is True
    assert crawl["carriage_status"] == "HEAVY_LOAD_EQUIPMENT_DETECTED"

    # Case B: Crouching / loitering (Width=0.30, Height=0.32 -> AR=0.937)
    crouch_bbox = [0.10, 0.40, 0.40, 0.72]
    crouch = posture_classifier.classify_target(
        target_id="TRK_CROUCH_01",
        bbox=crouch_bbox,
        speed_mps=0.8,
        zone_id="ZONE_B"
    )
    assert crouch["posture"] == "CROUCHING_CONCEALMENT"
    assert 0.70 <= crouch["aspect_ratio"] < 1.35
    assert crouch["threat_level"] == "HIGH"
    assert crouch["is_stealth_tactic"] is False
    assert crouch["carriage_status"] == "STANDARD_PROFILE"

    # Case C: Upright walking (Width=0.12, Height=0.45 -> AR=0.267)
    walk_bbox = [0.20, 0.20, 0.32, 0.65]
    walk = posture_classifier.classify_target(
        target_id="TRK_WALK_01",
        bbox=walk_bbox,
        speed_mps=1.1,
        zone_id="ZONE_A"
    )
    assert walk["posture"] == "UPRIGHT_WALKING"
    assert walk["aspect_ratio"] < 0.70

    # Case D: Upright running (Speed > 2.0 m/s)
    run = posture_classifier.classify_target(
        target_id="TRK_RUN_01",
        bbox=walk_bbox,
        speed_mps=3.4,
        zone_id="ZONE_B"
    )
    assert run["posture"] == "UPRIGHT_RUNNING"


@pytest.mark.anyio
async def test_posture_simulate_crawl_and_api():
    """Validates prone crawl simulation and posture query endpoints."""
    # 1. Simulate crawling
    sim_res = await posture_classifier.simulate_crawling_intruder()
    assert sim_res["posture"] == "PRONE_CRAWLING"
    assert sim_res["is_stealth_tactic"] is True

    # 2. Query active posture classifications
    active = posture_classifier.get_active()
    assert active["status"] == "HEALTHY"
    assert active["total_crawling_alerts"] >= 1
    assert len(active["classifications"]) >= 1

    # 3. Test REST endpoints
    res_active = client.get("/api/ai/posture/active")
    assert res_active.status_code == 200
    assert res_active.json()["status"] == "HEALTHY"

    res_sim = client.post("/api/ai/posture/simulate-crawl")
    assert res_sim.status_code == 200
    assert res_sim.json()["posture"] == "PRONE_CRAWLING"

    # 4. Custom classify endpoint
    res_class = client.post("/api/ai/posture/classify", json={
        "target_id": "TRK_API_01",
        "bbox": [0.1, 0.1, 0.6, 0.25], # AR = 0.5/0.15 = 3.33
        "speed_mps": 0.2,
        "zone_id": "ZONE_C",
        "has_equipment_load": False
    })
    assert res_class.status_code == 200
    assert res_class.json()["posture"] == "PRONE_CRAWLING"


# =========================================================================
# 3. TACTICAL DATA LINK & STANAG 4586 PACKET ENCODER (Sections 50 & 60)
# =========================================================================

def test_tactical_datalink_frame_specs():
    """Validates STANAG 4586 binary encoding, < 180 byte limit, and HMAC checksum."""
    frame = tactical_datalink_encoder.generate_compact_frame()
    assert frame["status"] == "PACKET_COMPILED"
    assert "STANAG 4586" in frame["protocol"]
    
    # Critical spec: packet size strictly under 180 bytes for HF tactical radios
    assert frame["packet_size_bytes"] < 180
    assert frame["packet_size_bytes"] >= 35

    # Bandwidth saving vs standard REST JSON must be >= 95%
    assert frame["bandwidth_reduction_pct"] >= 95.0

    # Airtime over 9.6 kbps tactical radio must be < 150 ms
    assert frame["tactical_radio_airtime_ms"] < 150.0

    # Base64 payload and HMAC checksum verification
    assert len(frame["binary_base64_payload"]) > 20
    assert len(frame["hmac_sha256_checksum"]) > 8


def test_tactical_datalink_routes_api():
    """Validates REST endpoints for low-bandwidth tactical data link."""
    # 1. Compile packet
    res_pkt = client.get("/api/datalink/packet")
    assert res_pkt.status_code == 200
    pkt = res_pkt.json()
    assert pkt["status"] == "PACKET_COMPILED"
    assert pkt["packet_size_bytes"] < 180

    # 2. Cumulative stats
    res_stats = client.get("/api/datalink/stats")
    assert res_stats.status_code == 200
    stats = res_stats.json()
    assert stats["status"] == "ONLINE"
    assert stats["packets_transmitted"] >= 1
    assert stats["total_bytes_saved_kb"] > 0

    # 3. Transmit packet to HQ
    res_tx = client.post("/api/datalink/transmit")
    assert res_tx.status_code == 200
    tx_data = res_tx.json()
    assert tx_data["status"] == "TRANSMITTED_TO_HQ"
    assert "frame" in tx_data
    assert "cumulative_stats" in tx_data


# =========================================================================
# 4. MASTER SIH 2026 EVALUATOR COMPLIANCE AUDIT (Sections 72 & 75)
# =========================================================================

def test_sih_2026_master_compliance_audit():
    """
    Executes autonomous self-test of all 12 core value propositions (Section 75)
    and verifies zero cloud API dependencies / architectural integrity (Section 72).
    """
    audit = sih_compliance_auditor.run_compliance_audit()
    assert audit["status"] == "AUDIT_COMPLETE"
    assert audit["compliance_score_percentage"] == 100.0
    assert audit["compliance_status"] == "100% SPECIFICATION COMPLIANT"

    checklist = audit["checklist"]
    assert len(checklist) == 12, "Section 75 mandates exactly 12 core value proposition pillars"

    # Verify all 12 pillars are marked PASSED
    for pillar in checklist:
        assert pillar["status"] == "PASSED", f"Pillar {pillar['id']} ({pillar['pillar']}) did not pass"

    # Specific pillar verifications
    pillars_by_id = {p["id"]: p for p in checklist}
    assert "Radar-First" in pillars_by_id[1]["pillar"]
    assert "AI-Based" in pillars_by_id[2]["pillar"]
    assert "Multi-Object Tracking" in pillars_by_id[3]["pillar"]
    assert "Restricted-Zone" in pillars_by_id[4]["pillar"]
    assert "Multi-Sensor Fusion" in pillars_by_id[5]["pillar"]
    assert "Evidence Recording" in pillars_by_id[6]["pillar"]
    assert "14-Day" in pillars_by_id[7]["pillar"]
    assert "Health Monitoring" in pillars_by_id[8]["pillar"]
    assert "Surveillance-Gap" in pillars_by_id[9]["pillar"]
    assert "UAV Verification" in pillars_by_id[10]["pillar"]
    assert "Command Dashboard" in pillars_by_id[11]["pillar"]
    assert "Computational Optimization" in pillars_by_id[12]["pillar"]

    # Section 72 Architectural Integrity Verification
    arch = audit["architectural_integrity"]
    assert arch["offline_first_guarantee"] is True
    assert arch["zero_cloud_api_dependencies"] is True
    assert arch["hardcoded_secrets_count"] == 0
    assert arch["graceful_sensor_degradation"] is True


def test_sih_compliance_route_api():
    """Validates the evaluator audit endpoint."""
    res = client.get("/api/system/sih-compliance/audit")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "AUDIT_COMPLETE"
    assert data["compliance_score_percentage"] == 100.0
    assert len(data["checklist"]) == 12
