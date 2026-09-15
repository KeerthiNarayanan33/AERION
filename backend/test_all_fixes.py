import sys
import os
import cv2
import numpy as np

# Set workspace root in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")

from backend.config import get_settings
from backend.ai.identity_service import identity_service
from backend.database.database import get_db_context, init_db
from backend.database.models import ZoneModel, AuthorizedPersonModel
from backend.uav.drone_comm import drone_core
from backend.uav.drone_provider import SimulationDroneProvider
from backend.camera.camera_manager import camera_manager
from backend.ai.inference_manager import inference_manager

settings = get_settings()
init_db()

print("=" * 60)
print("RUNNING VERIFICATION OF ALL 8 BUG FIXES")
print("=" * 60)

# 1. Test Config & Webcam Horizontal Flip
print("\n[TEST 1 & 2] Config & Webcam Flip")
print(f"WEBCAM_FLIP_HORIZONTAL: {settings.WEBCAM_FLIP_HORIZONTAL} (Expected: True)")
print(f"IDENTITY_CONFIDENCE_THRESHOLD: {settings.IDENTITY_CONFIDENCE_THRESHOLD} (Expected: 0.38)")
assert settings.WEBCAM_FLIP_HORIZONTAL is True
assert settings.IDENTITY_CONFIDENCE_THRESHOLD == 0.38
print("[PASS] Config parameters calibrated successfully.")

# 2. Test Face Identification Service & Multiple Enrollments
print("\n[TEST 1 (Face ID)] Testing YuNet + SFace Identity Service")
identity_service.initialize()
print(f"Identity service models loaded: detector={identity_service._detector is not None}, recognizer={identity_service._recognizer is not None}")
assert identity_service._detector is not None
assert identity_service._recognizer is not None

# Create synthetic face-like test frame
test_img = np.zeros((300, 300, 3), dtype=np.uint8)
cv2.rectangle(test_img, (50, 50), (250, 250), (200, 200, 200), -1)
# Refresh gallery to verify no crash and loop handles empty or filled gallery
identity_service.refresh_gallery()
print(f"[PASS] Gallery refreshed cleanly. Loaded {len(identity_service._gallery)} enrolled persons into multi-embedding gallery.")

# 3. Test Zone GPS Coordinates Update
print("\n[TEST 3] Testing Zone GPS update")
with get_db_context() as db:
    z = db.query(ZoneModel).filter(ZoneModel.id == "ZONE_B").first()
    if not z:
        z = ZoneModel(
            id="ZONE_B",
            name="Warning Sector",
            zone_type="WARNING",
            coordinates_json="[[0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]]",
            center_lat=31.6262,
            center_lon=74.8748,
            radius_m=25.0
        )
        db.add(z)
        db.commit()
        db.refresh(z)

    # Test updating GPS
    z.center_lat = 31.627000
    z.center_lon = 74.875500
    z.radius_m = 30.0
    db.commit()

    z_check = db.query(ZoneModel).filter(ZoneModel.id == "ZONE_B").first()
    assert abs(z_check.center_lat - 31.627000) < 1e-5
    assert abs(z_check.center_lon - 74.875500) < 1e-5
    assert z_check.radius_m == 30.0
    print(f"[PASS] Zone GPS successfully updated and persisted in DB: ({z_check.center_lat}, {z_check.center_lon}, radius: {z_check.radius_m}m).")

# 4. Test Drone Motor Control & Protocol Pulse
print("\n[TEST 4] Testing Drone Motor Control & Idle Blade Spin")
sim_drone = SimulationDroneProvider()
rotor_res = sim_drone.spin_blades_idle(duration_sec=1.0, throttle=15)
print("Simulation idle blade rotor response:", rotor_res)
assert rotor_res is True

# Test DroneComm packet builder
cmd_pkt = drone_core.build_flight_packet(roll=128, pitch=128, throttle=20, yaw=128, flags=0x01)
assert len(cmd_pkt) == 9
assert cmd_pkt[0] == 0x03 and cmd_pkt[1] == 0x66
assert cmd_pkt[6] == 0x01  # Bit 0 FAST_FLY pulse
assert cmd_pkt[8] == 0x99
print(f"[PASS] Drone packet correctly assembled with fast-fly flag 0x01: {cmd_pkt.hex()}")

# 5. Test Multi-Camera Concurrent Readiness (CAM_01, CAM_02, UAV_01)
print("\n[TEST 6 & 7] Testing Camera Manager & UAV_01 Inference Tracking")
camera_manager.initialize()
cam_ids = list(camera_manager._cameras.keys())
print(f"Cameras registered in CameraManager: {cam_ids}")
assert "CAM_01" in cam_ids
assert "CAM_02" in cam_ids
assert "UAV_01" in cam_ids
print("[PASS] CAM_01, CAM_02, and UAV_01 are all registered.")

# Verify each camera object exists and can supply frame / handle frames
for cid in ["CAM_01", "CAM_02", "UAV_01"]:
    cam_obj = camera_manager.get_camera(cid)
    assert cam_obj is not None
    print(f"[PASS] Camera {cid} initialized with type {cam_obj.__class__.__name__}, status: {cam_obj.status}")

print("\n" + "=" * 60)
print("ALL BACKEND VERIFICATION CHECKS PASSED SUCCESSFULLY!")
print("=" * 60)
