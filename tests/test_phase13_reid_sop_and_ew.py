import pytest
from fastapi.testclient import TestClient
import numpy as np

from backend.main import app
from backend.ai.reid_handover import reid_engine
from backend.radar.rf_integrity import rf_integrity_monitor

client = TestClient(app)

def test_reid_feature_extraction_and_similarity():
    """Validates color appearance descriptor extraction and cosine similarity matching."""
    # Test synthetic fallback feature
    feat1 = reid_engine.extract_appearance_feature(None)
    assert len(feat1) == 32
    # L2 norm check
    norm = sum(x * x for x in feat1)
    assert 0.95 <= norm <= 1.05

    # Test identical vectors have similarity 1.0
    sim_self = reid_engine.compute_similarity(feat1, feat1)
    assert pytest.approx(sim_self, abs=1e-3) == 1.0

    # Test orthogonal/dissimilar vectors
    feat_zeros = [0.0] * 32
    feat_zeros[0] = 1.0
    feat_other = [0.0] * 32
    feat_other[10] = 1.0
    assert reid_engine.compute_similarity(feat_zeros, feat_other) == 0.0

def test_cross_camera_handover_lifecycle():
    """Validates target departure registration, candidate tracking, and cross-camera matching."""
    # 1. Register departure from CAM_01 heading East
    feat_person = [0.1] * 32
    feat_person[2] = 0.9
    dep_rec = reid_engine.register_departing_target(
        camera_id="CAM_01",
        track_id=12,
        object_class="person",
        bbox=[0.86, 0.2, 0.95, 0.8],
        feature=feat_person
    )
    assert dep_rec["exit_direction"] == "EAST"
    assert dep_rec["global_id"].startswith("GLOBAL_TARGET_")

    # Check active pool
    status = reid_engine.get_status()
    assert status["active_handover_candidates"] >= 1

    # 2. Attempt arrival on CAM_02 with matching appearance
    arrival_feat = [x + 0.01 for x in feat_person]
    handover = reid_engine.attempt_handover(
        entering_camera_id="CAM_02",
        track_id=1,
        object_class="person",
        feature=arrival_feat
    )
    assert handover is not None
    assert handover["status"] == "CONFIRMED"
    assert handover["from_camera"] == "CAM_01"
    assert handover["to_camera"] == "CAM_02"
    assert handover["similarity_score"] >= 0.74
    assert handover["global_id"] == dep_rec["global_id"]

def test_reid_api_endpoints():
    """Validates REST endpoints for Cross-Camera ReID inspection and simulation."""
    # Active status
    res = client.get("/api/ai/handover/active")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "HEALTHY"
    assert "active_handover_candidates" in data

    # Simulate handover
    sim_res = client.post("/api/ai/handover/simulate", json={
        "from_camera": "CAM_01",
        "to_camera": "CAM_02",
        "track_id": 5,
        "object_class": "person"
    })
    assert sim_res.status_code == 200
    sim_data = sim_res.json()
    assert "handover" in sim_data
    assert sim_data["handover"]["status"] == "CONFIRMED"
    assert sim_data["handover"]["to_camera"] == "CAM_02"

def test_defensive_rf_integrity_and_jamming():
    """Validates Electronic Warfare RF Jamming detection and reset cycle."""
    # Nominal baseline
    baseline = client.get("/api/radar/rf-integrity").json()
    assert baseline["status"] == "HEALTHY"
    assert baseline["ew_state"] in ["NORMAL", "SIGNAL_DEGRADATION"]

    # Trigger simulated RF Jamming attack
    jam_res = client.post("/api/radar/simulate-jamming")
    assert jam_res.status_code == 200
    jam_data = jam_res.json()["telemetry"]
    assert jam_data["ew_state"] == "ACTIVE_RF_JAMMING"
    assert jam_data["countermeasure_active"] is True
    assert jam_data["packet_loss_rate"] >= 0.50

    # Reset RF spectrum
    reset_res = client.post("/api/radar/reset-rf")
    assert reset_res.status_code == 200
    reset_data = reset_res.json()["telemetry"]
    assert reset_data["ew_state"] == "NORMAL"
    assert reset_data["countermeasure_active"] is False

def test_sop_command_matrix_workflow():
    """Validates 6-step CAPF/BSF SOP checklist retrieval and step execution."""
    # Create test event
    ev_res = client.post("/api/events", json={
        "event_type": "ZONE_INTRUSION",
        "severity": "CRITICAL",
        "camera_id": "CAM_01",
        "zone_id": "ZONE_C",
        "object_id": "88",
        "object_class": "person",
        "confidence": 0.95,
        "description": "SOP Test Intrusion",
        "is_simulated": True
    })
    assert ev_res.status_code == 200
    ev_data = ev_res.json()
    event_id = ev_data.get("event_id") or ev_data.get("id")

    # 1. Fetch initial SOP
    sop_res = client.get(f"/api/events/{event_id}/sop")
    assert sop_res.status_code == 200
    sop_data = sop_res.json()
    assert sop_data["total_steps"] == 6
    assert sop_data["completed_steps"] == 0
    assert sop_data["progress_percentage"] == 0.0
    assert sop_data["next_recommended_step"] == "STEP_VISUAL_VERIFY"

    # 2. Execute Step 1: Visual Verify
    step1_res = client.post(
        f"/api/events/{event_id}/sop/STEP_VISUAL_VERIFY/execute",
        params={"operator_name": "Inspector Singh"}
    )
    assert step1_res.status_code == 200
    s1_data = step1_res.json()["sop"]
    assert s1_data["completed_steps"] == 1
    step1 = next(s for s in s1_data["steps"] if s["step_id"] == "STEP_VISUAL_VERIFY")
    assert step1["status"] == "COMPLETED"

    # 3. Execute Step 3: UAV Recon Sortie
    step3_res = client.post(
        f"/api/events/{event_id}/sop/STEP_UAV_SORTIE/execute",
        params={"operator_name": "Inspector Singh"}
    )
    assert step3_res.status_code == 200
    s3_data = step3_res.json()["sop"]
    assert s3_data["completed_steps"] == 2

    # 4. Invalid step rejection
    bad_res = client.post(f"/api/events/{event_id}/sop/NON_EXISTENT_STEP/execute")
    assert bad_res.status_code == 400

def test_executive_shift_intelligence_report():
    """Validates Shift Intelligence Report JSON and printable HTML output."""
    # JSON API
    json_res = client.get("/api/analytics/shift-report")
    assert json_res.status_code == 200
    report = json_res.json()
    assert "shift_id" in report
    assert "summary_kpis" in report
    assert "sensor_telemetry_uptimes" in report
    assert report["summary_kpis"]["total_security_events"] >= 0

    # HTML Printable Document
    html_res = client.get("/api/analytics/shift-report/html")
    assert html_res.status_code == 200
    assert "text/html" in html_res.headers["content-type"]
    html = html_res.text
    assert "SENTINEL-AI EXECUTIVE SHIFT INTELLIGENCE BRIEFING" in html
    assert "MULTI-SENSOR TELEMETRY" in html
    assert "window.print()" in html
