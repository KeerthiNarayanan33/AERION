import pytest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient

from backend.main import app
from backend.database.database import init_db, SessionLocal
from backend.database.models import EventModel, ANPRResultModel
from backend.camera.fault_recovery import sensor_watchdog

@pytest.fixture(scope="module", autouse=True)
def setup_test_environment():
    init_db()

client = TestClient(app)

# ============================================================================
# 1. MULTI-PARAMETER EVENT SEARCH & FILTERING (SECTION 38)
# ============================================================================

def test_multi_filter_events_by_class_and_type():
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        e1 = EventModel(
            id=f"EVT_TEST_FILTER_1_{int(now.timestamp())}",
            event_type="ZONE_INTRUSION",
            severity="MEDIUM",
            object_id="TRK_FILTER_PERSON",
            object_class="person",
            confidence=0.92,
            status="ACTIVE",
            start_time=now,
            description="Person walking near warning boundary",
            is_simulated=True
        )
        e2 = EventModel(
            id=f"EVT_TEST_FILTER_2_{int(now.timestamp())}",
            event_type="RESTRICTED_BREACH",
            severity="CRITICAL",
            object_id="TRK_FILTER_TRUCK",
            object_class="truck",
            confidence=0.96,
            status="RESOLVED",
            start_time=now - timedelta(minutes=5),
            description="Heavy truck breaching restricted perimeter gate",
            is_simulated=True
        )
        db.add_all([e1, e2])
        db.commit()

        # 1. Filter by object_class='truck'
        res_truck = client.get("/api/events?object_class=truck")
        assert res_truck.status_code == 200
        data_truck = res_truck.json()
        assert any(e["id"] == e2.id for e in data_truck["events"])
        assert not any(e["id"] == e1.id for e in data_truck["events"])

        # 2. Filter by event_type='RESTRICTED_BREACH'
        res_type = client.get("/api/events?event_type=RESTRICTED_BREACH")
        assert res_type.status_code == 200
        data_type = res_type.json()
        assert any(e["id"] == e2.id for e in data_type["events"])

        # 3. Filter by severity='CRITICAL'
        res_sev = client.get("/api/events?severity=CRITICAL")
        assert res_sev.status_code == 200
        data_sev = res_sev.json()
        assert all(e["severity"] == "CRITICAL" for e in data_sev["events"])

        # 4. Filter by status='RESOLVED'
        res_stat = client.get("/api/events?status=RESOLVED")
        assert res_stat.status_code == 200
        data_stat = res_stat.json()
        assert any(e["id"] == e2.id for e in data_stat["events"])

    finally:
        db.close()

def test_multi_filter_events_by_search_keyword():
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        unique_kw = f"ALPHA_BRAVO_{int(now.timestamp())}"
        e = EventModel(
            id=f"EVT_SEARCH_{int(now.timestamp())}",
            event_type="ZONE_INTRUSION",
            severity="HIGH",
            object_id=f"TARGET_{unique_kw}",
            object_class="motorcycle",
            confidence=0.88,
            status="ACTIVE",
            start_time=now,
            description=f"Patrol alert containing unique tag {unique_kw} in sector",
            is_simulated=True
        )
        db.add(e)
        db.commit()

        # Keyword search
        res = client.get(f"/api/events?search={unique_kw}")
        assert res.status_code == 200
        data = res.json()
        assert len(data["events"]) >= 1
        assert data["events"][0]["id"] == e.id
    finally:
        db.close()

def test_multi_filter_events_date_range():
    now = datetime.now(timezone.utc)
    start_str = (now - timedelta(days=1)).isoformat()
    end_str = (now + timedelta(days=1)).isoformat()

    res = client.get(f"/api/events?start_date={start_str}&end_date={end_str}")
    assert res.status_code == 200
    data = res.json()
    assert "events" in data
    assert isinstance(data["events"], list)

# ============================================================================
# 2. AUTOMATED FORENSIC INCIDENT DOSSIER GENERATOR (SECTION 39)
# ============================================================================

def test_generate_incident_dossier_html():
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        evt_id = f"EVT_DOSSIER_{int(now.timestamp())}"
        e = EventModel(
            id=evt_id,
            event_type="RESTRICTED_BREACH",
            severity="CRITICAL",
            camera_id="CAM_01",
            radar_id="RADAR_01",
            zone_id="ZONE_C",
            object_id="TRK_DOSSIER_TARGET",
            object_class="person",
            confidence=0.97,
            status="ACTIVE",
            start_time=now,
            description="Perimeter fence breach verified with LD2450 radar range-angle corroboration.",
            is_simulated=True
        )
        db.add(e)

        # Attach ANPR record
        anpr = ANPRResultModel(
            event_id=evt_id,
            vehicle_track_id=999,
            camera_id="CAM_01",
            plate_text="DL 01 AB 9999",
            confidence=0.96,
            timestamp=now
        )
        db.add(anpr)
        db.commit()

        # Request Dossier
        res = client.get(f"/api/events/{evt_id}/dossier")
        assert res.status_code == 200
        assert "text/html" in res.headers["content-type"]
        html = res.text

        # Verify Key Official Sections
        assert "CENTRAL ARMED POLICE FORCES" in html
        assert "INCIDENT DOSSIER" in html
        assert evt_id in html
        assert "CRYPTOGRAPHIC EVIDENCE HASH" in html
        assert "DL 01 AB 9999" in html
        assert "T - 10s" in html
        assert "CHAIN OF CUSTODY" in html
        assert "window.print()" in html

    finally:
        db.close()

def test_dossier_not_found_returns_404():
    res = client.get("/api/events/EVT_NON_EXISTENT_99999/dossier")
    assert res.status_code == 404
    assert "not found" in res.json()["detail"].lower()

# ============================================================================
# 3. SENSOR FAULT RECOVERY & RECONNECTION WATCHDOG (SECTION 49)
# ============================================================================

def test_sensor_fault_injection_and_recovery():
    # 1. Inject fault into CAM_02
    res_fail = client.post("/api/system/fault/CAM_02", json={
        "action": "FAIL",
        "reason": "Evaluator cut camera ethernet cable"
    })
    assert res_fail.status_code == 200
    data_fail = res_fail.json()
    assert data_fail["status"] == "OFFLINE"
    assert data_fail["fault_injected"] is True
    assert data_fail["fallback_mode"] == "RADAR_PRIMARY_FALLBACK"

    # 2. Inspect fault watchdog status
    res_status = client.get("/api/system/fault/status")
    assert res_status.status_code == 200
    data_status = res_status.json()
    assert data_status["active_faults_count"] >= 1
    assert "CAM_02" in data_status["sensors"]
    assert data_status["sensors"]["CAM_02"]["fault_injected"] is True

    # 3. Clear fault & recover CAM_02
    res_recover = client.post("/api/system/fault/CAM_02", json={
        "action": "RECOVER"
    })
    assert res_recover.status_code == 200
    data_rec = res_recover.json()
    assert data_rec["action"] == "RECOVER"
    assert data_rec["fault_injected"] is False

    # 4. Check status again
    res_status_after = client.get("/api/system/fault/status")
    assert res_status_after.status_code == 200
    assert res_status_after.json()["sensors"]["CAM_02"]["fault_injected"] is False

def test_watchdog_singleton_methods():
    status = sensor_watchdog.get_sensor_status("CAM_01")
    assert "sensor_id" in status
    assert status["sensor_id"] == "CAM_01"
    assert "reconnect_attempts" in status

    all_status = sensor_watchdog.get_all_status()
    assert "sensors" in all_status
    assert "CAM_01" in all_status["sensors"]
    assert "RADAR_01" in all_status["sensors"]
