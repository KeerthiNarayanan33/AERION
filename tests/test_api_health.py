import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.database.database import init_db

@pytest.fixture(scope="module", autouse=True)
def setup_test_db():
    init_db()

client = TestClient(app)

def test_root_serves_html():
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    assert "AERION" in response.text

def test_system_health_endpoint():
    response = client.get("/api/system/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "HEALTHY"
    assert "host_metrics" in data
    assert "components" in data
    assert "AI_ENGINE" in data["components"]
    assert "LD2450" in data["components"]

def test_cameras_listing():
    response = client.get("/api/cameras")
    assert response.status_code == 200
    cams = response.json()
    assert len(cams) >= 3
    cam_ids = [c["id"] for c in cams]
    assert "CAM_01" in cam_ids
    assert "CAM_02" in cam_ids
    assert "UAV_01" in cam_ids

def test_zones_listing():
    response = client.get("/api/zones")
    assert response.status_code == 200
    zones = response.json()
    assert len(zones) >= 3
    zone_ids = [z["id"] for z in zones]
    assert "ZONE_A" in zone_ids
    assert "ZONE_B" in zone_ids
    assert "ZONE_C" in zone_ids

def test_radar_status():
    response = client.get("/api/radar/status")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "RADAR_01"
    assert data["model"] == "LD2450"

def test_radar_ingest():
    payload = {
        "sensor_id": "RADAR_01",
        "targets": [
            {
                "id": 1,
                "x": 120.0,
                "y": 450.0,
                "speed_x": 15.0,
                "speed_y": -5.0
            }
        ]
    }
    response = client.post("/api/radar/ingest", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ACK"
    assert data["targets_processed"] == 1

def test_events_pagination():
    response = client.get("/api/events")
    assert response.status_code == 200
    data = response.json()
    assert "events" in data
    assert "total" in data
