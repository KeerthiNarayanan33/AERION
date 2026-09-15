import pytest
import numpy as np
import cv2
import base64
from fastapi.testclient import TestClient

from backend.main import app
from backend.database.database import init_db
from backend.ai.anpr_engine import ANPREngine, anpr_engine
from backend.events.scenario_runner import scenario_runner
from backend.uav.uav_controller import uav_controller, UAVState

@pytest.fixture(scope="module", autouse=True)
def setup_test_environment():
    init_db()

client = TestClient(app)

# ============================================================================
# 1. ANPR ENGINE UNIT TESTS
# ============================================================================

def test_anpr_candidate_vehicle_filtering():
    engine = ANPREngine()

    # Persons, backpacks, animals should NEVER trigger ANPR
    assert engine.is_candidate_vehicle("person", (10, 10, 200, 300)) is False
    assert engine.is_candidate_vehicle("backpack", (10, 10, 200, 300)) is False

    # Vehicles with small bounding box (< 3200 px) should be rejected
    assert engine.is_candidate_vehicle("car", (10, 10, 40, 40)) is False  # 30x30 = 900 px

    # Vehicles with sufficient resolution should qualify
    assert engine.is_candidate_vehicle("car", (100, 100, 300, 250)) is True  # 200x150 = 30000 px
    assert engine.is_candidate_vehicle("truck", (50, 50, 250, 200)) is True
    assert engine.is_candidate_vehicle("bus", (50, 50, 350, 300)) is True

def test_anpr_plate_not_readable_fallback():
    engine = ANPREngine()

    # Completely blank or pure black image must strictly return PLATE_NOT_READABLE without hallucination
    blank_plate = np.zeros((40, 120, 3), dtype=np.uint8)
    plate_text, conf, is_readable = engine.recognize_plate(blank_plate)
    assert plate_text == "PLATE_NOT_READABLE"
    assert is_readable is False
    assert conf == 0.0

def test_anpr_plate_recognition_structured():
    engine = ANPREngine()

    # Create synthetic test plate with high contrast characters
    plate_img = np.ones((60, 200, 3), dtype=np.uint8) * 240
    # Draw dark character blocks resembling license plate text
    for i in range(8):
        x = 20 + i * 20
        cv2.rectangle(plate_img, (x, 15), (x + 12, 45), (20, 20, 20), -1)

    plate_text, conf, is_readable = engine.recognize_plate(plate_img)
    assert is_readable is True
    assert conf >= 0.70
    assert plate_text != "PLATE_NOT_READABLE"
    assert len(plate_text.split()) >= 3  # e.g. "DL 01 AB 1234"

def test_anpr_process_vehicle_cycle():
    engine = ANPREngine()

    # Create synthetic vehicle frame (480x640)
    frame = np.ones((480, 640, 3), dtype=np.uint8) * 180
    # Draw vehicle body
    cv2.rectangle(frame, (150, 120), (450, 380), (70, 70, 70), -1)
    # Draw license plate in lower central region
    cv2.rectangle(frame, (250, 300), (350, 340), (240, 240, 240), -1)
    for i in range(7):
        cx = 260 + i * 12
        cv2.rectangle(frame, (cx, 310), (cx + 8, 330), (10, 10, 10), -1)

    result = engine.process_vehicle(
        frame=frame,
        bbox=(150, 120, 450, 380),
        vehicle_track_id=88,
        camera_id="CAM_01"
    )

    assert result["vehicle_track_id"] == 88
    assert result["camera_id"] == "CAM_01"
    assert "plate_text" in result
    assert result["snapshot_path"] is not None

# ============================================================================
# 2. ANPR REST API TESTS
# ============================================================================

def test_anpr_records_api():
    response = client.get("/api/anpr/records")
    assert response.status_code == 200
    data = response.json()
    assert "total" in data
    assert "records" in data
    assert isinstance(data["records"], list)

def test_anpr_stats_api():
    response = client.get("/api/anpr/stats")
    assert response.status_code == 200
    data = response.json()
    assert "total_scanned" in data
    assert "readable_plates" in data
    assert "unreadable_plates" in data
    assert "recognition_rate_percent" in data

def test_anpr_detect_api():
    # Test on-demand detection endpoint with synthetic frame
    dummy_frame = np.ones((480, 640, 3), dtype=np.uint8) * 120
    # Draw simulated vehicle / plate bounding area
    cv2.rectangle(dummy_frame, (100, 100), (350, 300), (40, 40, 40), -1)
    cv2.rectangle(dummy_frame, (160, 240), (280, 275), (255, 255, 255), -1)
    cv2.putText(dummy_frame, "DL 01 AB 1234", (165, 265), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 0), 1)

    _, buf = cv2.imencode('.jpg', dummy_frame)
    b64_str = base64.b64encode(buf).decode('utf-8')

    response = client.post("/api/anpr/detect", json={
        "camera_id": "CAM_01",
        "track_id": 99,
        "class_name": "car",
        "bbox": [100, 100, 350, 300],
        "image_base64": b64_str
    })
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "SUCCESS"
    assert "result" in data
    assert "plate_text" in data["result"]

# ============================================================================
# 3. SIH DEMONSTRATION SCENARIOS TESTS
# ============================================================================

def test_scenario_1_normal_patrol():
    res = client.post("/api/system/scenario/1")
    assert res.status_code == 200
    data = res.json()
    assert data["scenario"] == 1
    assert data["status"] == "ACTIVE"

def test_scenario_2_restricted_fence_breach():
    res = client.post("/api/system/scenario/2")
    assert res.status_code == 200
    data = res.json()
    assert data["scenario"] == 2
    assert data["status"] == "ALARM_TRIGGERED"
    assert "event_id" in data

def test_scenario_3_vehicle_and_anpr():
    res = client.post("/api/system/scenario/3")
    assert res.status_code == 200
    data = res.json()
    assert data["scenario"] == 3
    assert data["status"] == "ALARM_TRIGGERED"
    assert "event_id" in data

def test_scenario_4_camera_failure_surveillance_gap():
    res = client.post("/api/system/scenario/4")
    assert res.status_code == 200
    data = res.json()
    assert data["scenario"] == 4
    assert data["status"] == "SURVEILLANCE_GAP_DETECTED"
    assert "event_id" in data

def test_scenario_5_uav_recon_verification():
    res = client.post("/api/system/scenario/5")
    assert res.status_code == 200
    data = res.json()
    assert data["scenario"] == 5
    assert data["status"] == "UAV_DISPATCHED"
    assert "telemetry" in data
    assert data["telemetry"]["is_airborne"] is True

def test_scenario_reset():
    res = client.post("/api/system/scenario/reset")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "CLEAN"
    assert uav_controller.state in (UAVState.RETURNING, UAVState.STANDBY)

# ============================================================================
# 4. MOBILE IP CAMERA CONNECTION TEST
# ============================================================================

def test_camera_connection_test_api():
    # Unreachable host should return reachable=False gracefully without crash
    res = client.post("/api/cameras/CAM_02/test-connection", json={
        "source": "http://192.0.2.1:8080/nonexistent"
    })
    assert res.status_code == 200
    data = res.json()
    assert data["reachable"] is False
    assert "error" in data

# ============================================================================
# 5. ENHANCED ANPR EASYOCR & SYNTAX DISAMBIGUATION TESTS
# ============================================================================

def test_anpr_syntax_disambiguation_rules():
    engine = ANPREngine()

    # Digits disambiguated from letter O, I
    plate, conf, valid = engine.clean_and_disambiguate_plate("DL O1 AB I234")
    assert valid is True
    assert plate == "DL 01 AB 1234"

    # Bharat Series format
    plate_bh, conf_bh, valid_bh = engine.clean_and_disambiguate_plate("22BH1234AA")
    assert valid_bh is True
    assert plate_bh == "22 BH 1234 AA"

    # Extraneous "IND" watermark prefix stripped
    plate_ind, conf_ind, valid_ind = engine.clean_and_disambiguate_plate("IND MH12DE1433")
    assert valid_ind is True
    assert plate_ind == "MH 12 DE 1433"

def test_anpr_easyocr_rendered_plate():
    engine = ANPREngine()

    # Render a high-contrast standard Indian license plate: "MH 12 DE 1433"
    plate_img = np.ones((70, 260, 3), dtype=np.uint8) * 250
    cv2.putText(plate_img, "MH 12 DE 1433", (12, 48), cv2.FONT_HERSHEY_SIMPLEX, 0.95, (10, 10, 10), 2)

    plate_text, conf, is_readable = engine.recognize_plate(plate_img)
    assert is_readable is True
    assert conf >= 0.75
    assert "MH 12" in plate_text or "1433" in plate_text

# ============================================================================
# 6. RESTRICTED ZONE ALARM ESCALATION TESTS
# ============================================================================

def test_restricted_zone_escalation_security_alert():
    from backend.events.event_engine import event_engine
    from backend.zones.state_machine import IntrusionState
    from backend.events.event_types import EventSeverity

    # 1. Step in Warning Zone
    rec1 = event_engine.process_target_state(
        target_id="CAM_01_TRK_TEST_99",
        object_class="person",
        intrusion_state=IntrusionState.WARNING,
        zone_id="ZONE_B",
        zone_name="Warning Approach Sector",
        zone_type="WARNING",
        coordinates=(0.50, 0.50),
        confidence=0.95,
        camera_id="CAM_01"
    )
    assert rec1 is not None

    # 2. Step into Restricted Zone C (Escalation to CRITICAL)
    rec2 = event_engine.process_target_state(
        target_id="CAM_01_TRK_TEST_99",
        object_class="person",
        intrusion_state=IntrusionState.RESTRICTED_ENTRY,
        zone_id="ZONE_C",
        zone_name="Restricted Border Fence",
        zone_type="RESTRICTED",
        coordinates=(0.80, 0.50),
        confidence=0.98,
        camera_id="CAM_01"
    )
    assert rec2 is not None
    assert rec2.peak_severity == EventSeverity.CRITICAL

def test_zone_manager_restricted_evaluation():
    from backend.zones.zone_manager import zone_manager

    # Point in ZONE_C (norm_x = 0.80, norm_y = 0.50)
    eval_res = zone_manager.evaluate_camera_track(
        track_id=101,
        center_px=(512, 240),
        frame_shape=(480, 640),
        velocity_px=(0.0, 0.0),
        object_class="person",
        camera_id="CAM_01"
    )
    assert eval_res["zone_id"] == "ZONE_C"
    assert eval_res["state"] in ("RESTRICTED_ENTRY", "ACTIVE_EVENT")

