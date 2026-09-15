import time
import pytest
import numpy as np
from fastapi.testclient import TestClient

from backend.camera.frame_buffer import RollingFrameBuffer
from backend.camera.base_camera import BaseCamera
from backend.camera.webcam import WebcamCamera
from backend.camera.camera_manager import camera_manager
from backend.main import app
from backend.database.database import init_db

@pytest.fixture(scope="module", autouse=True)
def setup_camera_test():
    init_db()
    camera_manager.initialize()

client = TestClient(app)

def test_rolling_frame_buffer():
    # 10 FPS, 2 seconds -> max 20 frames
    buf = RollingFrameBuffer(fps=10, buffer_seconds=2)
    assert buf.capacity == 20
    assert buf.current_size == 0
    assert buf.get_latest() is None

    # Push frames
    dummy_frame = np.zeros((100, 100, 3), dtype=np.uint8)
    for i in range(25):
        buf.push(dummy_frame)

    # Circular buffer caps at capacity
    assert buf.current_size == 20
    latest = buf.get_latest()
    assert latest is not None
    assert latest[1].shape == (100, 100, 3)

    # Window query
    window = buf.get_window(seconds=1.0)
    assert len(window) > 0

    # Clear
    buf.clear()
    assert buf.current_size == 0

def test_camera_manager_registry():
    cam1 = camera_manager.get_camera("CAM_01")
    assert cam1 is not None
    assert cam1.camera_id == "CAM_01"
    assert cam1.camera_type == "WEBCAM"

    cam2 = camera_manager.get_camera("CAM_02")
    assert cam2 is not None
    assert cam2.camera_type == "IP_CAMERA"

    uav_cam = camera_manager.get_camera("UAV_01")
    assert uav_cam is not None
    assert uav_cam.camera_type == "UAV"

def test_camera_snapshot_generation():
    cam1 = camera_manager.get_camera("CAM_01")
    assert cam1 is not None

    # Wait briefly for worker thread to acquire or generate first frame
    for _ in range(10):
        if cam1.get_frame() is not None:
            break
        time.sleep(0.2)

    jpeg = cam1.get_jpeg()
    assert jpeg is not None
    assert len(jpeg) > 0
    assert jpeg[:2] == b'\xff\xd8'  # Standard JPEG magic bytes

def test_camera_snapshot_endpoint():
    response = client.get("/api/cameras/CAM_01/snapshot")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert len(response.content) > 0
    assert response.content[:2] == b'\xff\xd8'

def test_camera_stream_endpoint():
    response = client.get("/api/cameras/CAM_01/stream?max_frames=2")
    assert response.status_code == 200
    assert "multipart/x-mixed-replace" in response.headers["content-type"]
    assert b"--frame" in response.content
    assert b"Content-Type: image/jpeg" in response.content

def test_camera_health_telemetry():
    response = client.get("/api/cameras/CAM_01")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "CAM_01"
    assert data["status"] in ["ONLINE", "DEGRADED", "RECONNECTING"]
    assert "fps" in data
    assert "latency_ms" in data
    assert "resolution" in data

def test_camera_config_update():
    payload = {"source": "0", "zone_id": "ZONE_B"}
    response = client.put("/api/cameras/CAM_01", json=payload)
    assert response.status_code == 200
    assert response.json()["camera_id"] == "CAM_01"

def test_camera_network_info():
    response = client.get("/api/cameras/network/info")
    assert response.status_code == 200
    data = response.json()
    assert "local_ip" in data
    assert "available_ips" in data
    assert isinstance(data["available_ips"], list)
    assert len(data["available_ips"]) > 0
    assert "port" in data
    assert "https_port" in data
    assert data["https_port"] == 8443
    assert "mobile_stream_url" in data
    assert "mobile_stream_url_https" in data
    assert "qr_svg" in data
    assert "<svg" in data["qr_svg"]
    assert "/mobile.html" in data["mobile_stream_url"]
    assert "https://" in data["mobile_stream_url_https"]

    # Test QR endpoint directly
    qr_res = client.get("/api/cameras/network/qr")
    assert qr_res.status_code == 200
    assert "image/svg+xml" in qr_res.headers.get("content-type", "")
    assert b"<svg" in qr_res.content


def test_camera_push_frame():
    import cv2
    import numpy as np

    # Generate test JPEG frame
    test_img = np.zeros((480, 640, 3), dtype=np.uint8)
    test_img[:] = (0, 255, 100)
    _, encoded = cv2.imencode('.jpg', test_img)
    raw_bytes = encoded.tobytes()

    response = client.post(
        "/api/cameras/CAM_02/push-frame",
        content=raw_bytes,
        headers={"Content-Type": "image/jpeg"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ONLINE"
    assert data["camera_id"] == "CAM_02"
    assert "640x480" in data["resolution"]

    # Verify CAM_02 in camera manager is now ONLINE
    cam2 = camera_manager.get_camera("CAM_02")
    assert cam2.status == "ONLINE"
    assert cam2.frame_count > 0

