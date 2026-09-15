import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.camera.uav_camera import UAVCamera
from backend.zones.zone_manager import zone_manager
from backend.zones.state_machine import IntrusionState
from backend.database.database import SessionLocal
from backend.database.models import ZoneModel

@pytest.fixture
def client():
    return TestClient(app)

def test_uav_camera_generation():
    """Verify UAVCamera generates valid tactical aerial frames and JPEG stream."""
    cam = UAVCamera(camera_id="UAV_TEST", name="Test UAV Camera", source="")
    frame = cam._generate_aerial_recon_frame()
    assert frame is not None
    assert frame.shape == (540, 960, 3)
    
    # Test JPEG generation
    cam._update_telemetry(frame, capture_latency_ms=10.0)
    cam.status = "ONLINE"
    jpeg = cam.get_jpeg()
    assert jpeg is not None
    assert len(jpeg) > 1000
    assert jpeg.startswith(b'\xff\xd8')  # JPEG magic bytes

def test_zone_name_rename_api(client):
    """Verify PATCH /api/zones/{zone_id}/name updates zone name."""
    res = client.patch("/api/zones/ZONE_B/name", json={"name": "Sector Bravo - Tactical Warning"})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "SUCCESS"
    assert data["zone"]["name"] == "Sector Bravo - Tactical Warning"
    
    # Fetch from GET to confirm DB persistence
    get_res = client.get("/api/zones/ZONE_B")
    assert get_res.status_code == 200
    assert get_res.json()["name"] == "Sector Bravo - Tactical Warning"

def test_authorized_alarm_suppressed_in_restricted_zone():
    """Verify that when is_authorized=True, critical alarms and transitions are suppressed."""
    # Test evaluate_camera_track with authorized person
    res = zone_manager.evaluate_camera_track(
        track_id=101,
        center_px=(320, 240),
        frame_shape=(480, 640),
        velocity_px=(0.0, 0.0),
        object_class="person",
        camera_id="CAM_01",
        is_authorized=True,
        identity="Dr. John Doe (Authorized Director)"
    )
    # Target should have transition suppressed (record is None) because subject is authorized
    assert res["transition"] is None

def test_drone_control_endpoints(client):
    """Verify dispatch, start-scan, return-home, abort, and verify-rotor endpoints."""
    # 1. Rotor verification
    rotor_res = client.post("/api/uav/verify-rotor", json={"duration_sec": 1.0, "throttle": 15})
    assert rotor_res.status_code == 200
    assert rotor_res.json()["action"] == "ROTOR_BLADE_VERIFICATION"

    # 2. Dispatch
    disp_res = client.post("/api/uav/dispatch", json={"zone_id": "ZONE_B", "reason": "Test sortie"})
    assert disp_res.status_code == 200
    assert "telemetry" in disp_res.json()

    # 3. Start Scan
    scan_res = client.post("/api/uav/start-scan")
    assert scan_res.status_code == 200
    assert "telemetry" in scan_res.json()

    # 4. Return Home
    rth_res = client.post("/api/uav/return-home", json={"reason": "Test RTH"})
    assert rth_res.status_code == 200
    assert "telemetry" in rth_res.json()

    # 5. Abort
    abort_res = client.post("/api/uav/abort", json={"reason": "Test Abort"})
    assert abort_res.status_code == 200
    assert "telemetry" in abort_res.json()

def test_site_location_api(client):
    """Verify site configuration read and write."""
    payload = {
        "site_id": "SITE-001",
        "site_name": "SIH Tactical Command Post",
        "country": "India",
        "city": "Amritsar",
        "state": "Punjab",
        "latitude": 31.624000,
        "longitude": 74.872300,
        "description": "Perimeter defense surveillance site"
    }
    save_res = client.post("/api/site", json=payload)
    assert save_res.status_code == 200
    
    get_res = client.get("/api/site")
    assert get_res.status_code == 200
    site = get_res.json()["site"]
    assert site["site_name"] == "SIH Tactical Command Post"
    assert site["latitude"] == 31.624000
    assert site["longitude"] == 74.872300
