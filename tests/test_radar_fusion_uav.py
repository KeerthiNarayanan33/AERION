import pytest
import math
import time
from fastapi.testclient import TestClient

from backend.main import app
from backend.database.database import init_db
from backend.radar.radar_driver import LD2450RadarDriver, RadarTarget
from backend.fusion.fusion_engine import RadarCameraFusionEngine, FusedTrack
from backend.uav.uav_controller import UAVMissionController, UAVState

@pytest.fixture(scope="module", autouse=True)
def setup_test_environment():
    init_db()

client = TestClient(app)

# ============================================================================
# 1. LD2450 RADAR DRIVER TESTS
# ============================================================================

def test_radar_driver_polar_coordinates():
    driver = LD2450RadarDriver(sensor_id="RADAR_TEST")
    # Target at X=3m, Y=4m -> Distance = 5m, Angle = ~36.87 deg
    dist, angle = driver.cartesian_to_polar(3.0, 4.0)
    assert round(dist, 2) == 5.0
    assert round(angle, 1) == 36.9

def test_radar_driver_esp32_json_parsing():
    driver = LD2450RadarDriver(sensor_id="RADAR_TEST")
    raw_esp32_data = [
        {"id": 1, "x": 120, "y": 350, "speed": -150, "resolution": 0.1},
        {"id": 2, "x": -80, "y": 200, "speed": 5, "resolution": 0.1}
    ]
    targets = driver.parse_esp32_json(raw_esp32_data)
    assert len(targets) == 2

    # Target 1: 120cm -> 1.2m, 350cm -> 3.5m, speed -150 cm/s -> -1.5m/s
    t1 = targets[0]
    assert t1.target_id == 1
    assert t1.x == 1.2
    assert t1.y == 3.5
    assert t1.speed == -1.5
    assert t1.distance > 0

def test_radar_driver_uart_packet_decoder():
    driver = LD2450RadarDriver(sensor_id="RADAR_TEST")

    # Construct standard LD2450 frame (30 bytes)
    # Header: 0xAA 0xFF 0x03 0x00
    # Target 1: X=100 (0x0064), Y=300 (0x012C), Speed=-20 (0x8014), Resolution=15 (0x000F)
    # Target 2: zeros (no target)
    # Target 3: zeros (no target)
    # Tail: 0x55 0xCC (at bytes 28..30)
    pkt = bytearray(30)
    pkt[0:4] = bytes([0xAA, 0xFF, 0x03, 0x00])

    # Target 1
    x_val = 100
    y_val = 300
    speed_sign = 0x8000 | 20 # negative speed 20 cm/s
    pkt[4:6] = x_val.to_bytes(2, 'little')
    pkt[6:8] = y_val.to_bytes(2, 'little')
    pkt[8:10] = speed_sign.to_bytes(2, 'little')
    pkt[10:12] = (15).to_bytes(2, 'little')

    # Tail
    pkt[28:30] = bytes([0x55, 0xCC])

    targets = driver.parse_uart_packet(bytes(pkt))
    assert len(targets) == 1
    assert targets[0].target_id == 1
    assert targets[0].x == 1.0
    assert targets[0].y == 3.0
    assert targets[0].speed == -0.2

def test_radar_driver_inject_target():
    driver = LD2450RadarDriver(sensor_id="RADAR_TEST")
    target = driver.inject_single_target(target_id=1, x=0.5, y=4.0, speed=-1.2)
    assert target.target_id == 1
    assert target.x == 0.5
    assert target.y == 4.0
    assert target.speed == -1.2
    assert len(driver.get_active_targets()) == 1

# ============================================================================
# 2. SENSOR FUSION ENGINE TESTS
# ============================================================================

def test_fusion_projection_to_camera_viewport():
    engine = RadarCameraFusionEngine(camera_hfov_deg=70.0, radar_max_range_m=8.0)

    # Center target: X=0, Y=4m -> u should be 0.5 (center)
    u, v = engine.project_radar_to_camera(x_m=0.0, y_m=4.0)
    assert round(u, 2) == 0.5
    assert 0.0 <= v <= 1.0

    # Right target: X=1.5m -> u > 0.5
    u_right, _ = engine.project_radar_to_camera(x_m=1.5, y_m=4.0)
    assert u_right > 0.5

    # Left target: X=-1.5m -> u < 0.5
    u_left, _ = engine.project_radar_to_camera(x_m=-1.5, y_m=4.0)
    assert u_left < 0.5

def test_fusion_cross_sensor_confirmation():
    engine = RadarCameraFusionEngine()

    # Radar target at (0.0, 4.0) -> projects to u=0.5, v ~0.625
    radar_targets = [
        RadarTarget(target_id=1, x=0.0, y=4.0, speed=-1.0, distance=4.0, angle_deg=0.0)
    ]

    # Camera track at center (norm_x=0.5, norm_y=0.62)
    camera_tracks = [
        {
            "track_id": "CAM_TRK_01",
            "class_name": "person",
            "confidence": 0.88,
            "norm_x": 0.5,
            "norm_y": 0.62,
            "zone_id": "ZONE_B"
        }
    ]

    fused = engine.fuse_frame(camera_tracks, radar_targets, camera_status="ONLINE")
    assert len(fused) == 1
    f = fused[0]
    assert f.is_cross_confirmed is True
    assert f.fusion_status == "CONFIRMED"
    assert f.camera_track_id == "CAM_TRK_01"
    assert f.radar_target_id == 1
    # Fused confidence boosted: 0.6*0.88 + 0.4*0.90 + 0.12 = 0.528 + 0.36 + 0.12 = ~0.99
    assert f.confidence >= 0.95

def test_fusion_unconfirmed_radar_blindspot():
    engine = RadarCameraFusionEngine()

    # Radar detects target but camera tracks are empty (camera offline / obscured)
    radar_targets = [
        RadarTarget(target_id=2, x=0.5, y=3.0, speed=-1.5, distance=3.04, angle_deg=9.5)
    ]
    camera_tracks = []

    fused = engine.fuse_frame(camera_tracks, radar_targets, camera_status="OFFLINE")
    assert len(fused) == 1
    f = fused[0]
    assert f.is_cross_confirmed is False
    assert f.fusion_status == "UNCONFIRMED_RADAR_ONLY"
    assert f.radar_target_id == 2
    assert f.camera_track_id is None

# ============================================================================
# 3. UAV CONTROLLER TESTS
# ============================================================================

def test_uav_controller_lifecycle():
    controller = UAVMissionController("UAV_TEST")
    assert controller.state == UAVState.STANDBY

    # Dispatch mission
    telemetry = controller.dispatch_mission(zone_id="ZONE_C", reason="Testing verification")
    assert controller.state == UAVState.DISPATCHED
    assert telemetry["current_zone"] == "ZONE_C"
    assert telemetry["is_airborne"] is True
    assert controller.altitude_m > 0

    # Recall / Abort mission
    telemetry_abort = controller.abort_mission(reason="Testing abort")
    assert controller.state == UAVState.RETURNING
    assert "Recalled" in telemetry_abort["reason"]

def test_uav_controller_low_battery_rejection():
    controller = UAVMissionController("UAV_TEST_LOW_BAT")
    controller.battery_percent = 15.0 # below 20% threshold

    with pytest.raises(ValueError, match="Insufficient UAV battery"):
        controller.dispatch_mission(zone_id="ZONE_C", reason="Should fail")

# ============================================================================
# 4. REST API INTEGRATION TESTS
# ============================================================================

def test_radar_status_api():
    response = client.get("/api/radar/status")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "active_targets_count" in data

def test_radar_simulate_target_api():
    response = client.post("/api/radar/simulate-target", json={
        "target_id": 1,
        "x": 0.5,
        "y": 3.8,
        "speed": -1.2
    })
    assert response.status_code == 200
    data = response.json()
    assert data["target"]["target_id"] == 1
    assert data["target"]["x"] == 0.5

def test_radar_ingest_api():
    response = client.post("/api/radar/ingest", json={
        "sensor_id": "RADAR_01",
        "targets": [
            {"id": 1, "x": 50, "y": 300, "speed": -10}
        ]
    })
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ACK"
    assert data["targets_processed"] == 1

def test_radar_fused_targets_api():
    response = client.get("/api/radar/fused-targets")
    assert response.status_code == 200
    data = response.json()
    assert "fused_tracks" in data

def test_uav_telemetry_api():
    response = client.get("/api/uav/telemetry")
    assert response.status_code == 200
    data = response.json()
    assert "uav_id" in data
    assert "battery_percent" in data
    assert "state" in data

def test_uav_dispatch_and_abort_api():
    # Dispatch
    disp_res = client.post("/api/uav/dispatch", json={
        "zone_id": "ZONE_C",
        "reason": "Integration test dispatch"
    })
    assert disp_res.status_code == 200
    disp_data = disp_res.json()
    assert "UAV_DISPATCHED" in disp_data["uav_state"]

    # Abort
    abort_res = client.post("/api/uav/abort", json={
        "reason": "Integration test recall"
    })
    assert abort_res.status_code == 200
    abort_data = abort_res.json()
    assert "UAV_RETURNING" in abort_data["uav_state"]
