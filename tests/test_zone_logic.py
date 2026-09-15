import time
import pytest
from fastapi.testclient import TestClient

from backend.zones.zone_logic import (
    is_point_in_polygon,
    distance_to_polygon,
    is_vector_approaching_polygon
)
from backend.zones.state_machine import (
    IntrusionState,
    ZoneInfo,
    TargetStateMachine
)
from backend.zones.zone_manager import zone_manager
from backend.main import app
from backend.database.database import init_db

@pytest.fixture(scope="module", autouse=True)
def setup_zones_test():
    init_db()
    zone_manager.initialize()

client = TestClient(app)

def test_point_in_polygon_ray_casting():
    # 10x10 square: (0,0) to (10,10)
    square = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]

    assert is_point_in_polygon((5.0, 5.0), square) is True     # Inside
    assert is_point_in_polygon((15.0, 5.0), square) is False   # Outside right
    assert is_point_in_polygon((-5.0, 5.0), square) is False   # Outside left
    assert is_point_in_polygon((5.0, 15.0), square) is False   # Outside top
    assert is_point_in_polygon((5.0, -5.0), square) is False   # Outside bottom

    # Concave L-shaped polygon
    l_shape = [
        (0.0, 0.0), (10.0, 0.0), (10.0, 5.0),
        (5.0, 5.0), (5.0, 10.0), (0.0, 10.0)
    ]
    assert is_point_in_polygon((2.0, 2.0), l_shape) is True    # Inside lower left
    assert is_point_in_polygon((2.0, 8.0), l_shape) is True    # Inside upper left
    assert is_point_in_polygon((8.0, 2.0), l_shape) is True    # Inside lower right
    assert is_point_in_polygon((8.0, 8.0), l_shape) is False   # In cutout area!

def test_distance_to_polygon():
    square = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]

    # Point inside should be 0.0
    assert distance_to_polygon((5.0, 5.0), square) == 0.0

    # Point directly right of edge (10, 5) at (13, 5) -> distance is 3.0
    assert pytest.approx(distance_to_polygon((13.0, 5.0), square), 0.01) == 3.0

    # Point diagonally from corner (10, 10) at (13, 14) -> distance is hypot(3, 4) = 5.0
    assert pytest.approx(distance_to_polygon((13.0, 14.0), square), 0.01) == 5.0

def test_is_vector_approaching_polygon():
    # Unit box (0.5, 0.5) to (1.0, 1.0)
    box = [(0.5, 0.5), (1.0, 0.5), (1.0, 1.0), (0.5, 1.0)]

    # Position at (0.45, 0.75), distance = 0.05 (within default threshold 0.08)
    pos = (0.45, 0.75)

    # Moving right towards the box (+vx)
    assert is_vector_approaching_polygon(pos, velocity=(0.5, 0.0), polygon=box, threshold=0.08) is True

    # Moving left away from the box (-vx)
    assert is_vector_approaching_polygon(pos, velocity=(-0.5, 0.0), polygon=box, threshold=0.08) is False

def test_state_machine_lifecycle_transitions():
    warning_zone = ZoneInfo(
        id="WARN_1",
        name="Warning Perimeter",
        zone_type="WARNING",
        coordinates=[(0.3, 0.0), (0.6, 0.0), (0.6, 1.0), (0.3, 1.0)],
        color="#ffab00"
    )
    restricted_zone = ZoneInfo(
        id="RESTRICT_1",
        name="Restricted Fence",
        zone_type="RESTRICTED",
        coordinates=[(0.6, 0.0), (1.0, 0.0), (1.0, 1.0), (0.6, 1.0)],
        color="#ff1744"
    )
    zones = [warning_zone, restricted_zone]

    sm = TargetStateMachine("INTRUDER_01", "person")
    assert sm.current_state == IntrusionState.NORMAL

    # Step 1: Intruder starts far out at (0.1, 0.5)
    state, rec = sm.evaluate((0.1, 0.5), (0.0, 0.0), zones)
    assert state == IntrusionState.NORMAL

    # Step 2: Approaching warning zone at (0.25, 0.5) moving east (+vx = 0.5)
    state, rec = sm.evaluate((0.25, 0.5), (0.5, 0.0), zones, approach_threshold=0.08)
    assert state == IntrusionState.APPROACHING
    assert rec is not None
    assert rec.current_state == IntrusionState.APPROACHING

    # Step 3: Enters Warning Zone at (0.4, 0.5)
    state, rec = sm.evaluate((0.4, 0.5), (0.5, 0.0), zones)
    assert state == IntrusionState.WARNING
    assert sm.current_zone_id == "WARN_1"

    # Step 4: Breaches Restricted Zone at (0.7, 0.5) -> First breach is RESTRICTED_ENTRY!
    state, rec = sm.evaluate((0.7, 0.5), (0.5, 0.0), zones)
    assert state == IntrusionState.RESTRICTED_ENTRY
    assert rec.current_state == IntrusionState.RESTRICTED_ENTRY
    assert sm.current_zone_id == "RESTRICT_1"

    # Step 5: Remains in Restricted Zone -> ACTIVE_EVENT!
    state, rec = sm.evaluate((0.75, 0.5), (0.2, 0.0), zones)
    assert state == IntrusionState.ACTIVE_EVENT

    # Step 6: Intruder retreats outside all zones -> RESOLVED!
    state, rec = sm.evaluate((0.05, 0.5), (-0.5, 0.0), zones)
    assert state == IntrusionState.RESOLVED
    assert rec.current_state == IntrusionState.RESOLVED

def test_zone_manager_evaluate_camera_track():
    # Evaluate a pixel coordinate on 640x480 frame
    # (x=500, y=240) -> normalized x = 500/640 = 0.78 (inside ZONE_C which is 0.65 to 0.95)
    res = zone_manager.evaluate_camera_track(
        track_id=1,
        center_px=(500, 240),
        frame_shape=(480, 640),
        velocity_px=(10.0, 0.0),
        object_class="person",
        camera_id="CAM_01"
    )
    assert res["state"] in ("RESTRICTED_ENTRY", "ACTIVE_EVENT")
    assert res["zone_id"] == "ZONE_C"

def test_api_zones_endpoints():
    # 1. GET /api/zones
    res = client.get("/api/zones")
    assert res.status_code == 200
    zones = res.json()
    assert len(zones) >= 3
    zone_ids = [z["id"] for z in zones]
    assert "ZONE_A" in zone_ids
    assert "ZONE_B" in zone_ids
    assert "ZONE_C" in zone_ids

    # 2. GET /api/zones/status
    res_status = client.get("/api/zones/status")
    assert res_status.status_code == 200
    data = res_status.json()
    assert "active_targets" in data
    assert "total_zones" in data
    assert data["total_zones"] >= 3

    # 3. POST /api/zones/evaluate
    eval_payload = {
        "x": 0.8,
        "y": 0.5,
        "vx": 0.1,
        "vy": 0.0,
        "object_id": "TEST_AGENT_01",
        "object_class": "person"
    }
    res_eval = client.post("/api/zones/evaluate", json=eval_payload)
    assert res_eval.status_code == 200
    eval_data = res_eval.json()
    assert eval_data["object_id"] == "TEST_AGENT_01"
    assert eval_data["current_state"] in ("RESTRICTED_ENTRY", "ACTIVE_EVENT")

    # 4. POST /api/zones (create custom zone)
    new_zone = {
        "id": "ZONE_TEST_CUSTOM",
        "name": "Custom Test Zone",
        "zone_type": "WARNING",
        "coordinates": [[0.01, 0.01], [0.09, 0.01], [0.09, 0.09], [0.01, 0.09]],
        "color": "#ffab00",
        "description": "Test created zone"
    }
    res_create = client.post("/api/zones", json=new_zone)
    assert res_create.status_code == 200

    # Verify created
    res_list = client.get("/api/zones")
    assert any(z["id"] == "ZONE_TEST_CUSTOM" for z in res_list.json())

    # 5. DELETE /api/zones/{zone_id}
    res_del = client.delete("/api/zones/ZONE_TEST_CUSTOM")
    assert res_del.status_code == 200

    # Verify deleted
    res_list_after = client.get("/api/zones")
    assert not any(z["id"] == "ZONE_TEST_CUSTOM" for z in res_list_after.json())
