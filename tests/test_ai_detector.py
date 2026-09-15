import io
import time
import pytest
import cv2
import numpy as np
from fastapi.testclient import TestClient

from backend.ai.detector_interface import Detection, DetectionResult
from backend.ai.yolo_detector import YOLODetector
from backend.ai.annotator import annotate_frame, draw_tactical_box
from backend.ai.inference_manager import inference_manager
from backend.main import app
from backend.database.database import init_db

@pytest.fixture(scope="module", autouse=True)
def setup_ai_test():
    init_db()
    inference_manager.initialize()

client = TestClient(app)

def test_detection_data_models():
    d = Detection(
        box=(10, 20, 100, 200),
        confidence=0.88,
        class_id=0,
        class_name="person",
        center=(55, 110),
        width=90,
        height=180
    )
    assert d.class_name == "person"
    assert d.confidence == 0.88
    assert d.center == (55, 110)

    res = DetectionResult(
        detections=[d],
        inference_time_ms=15.4,
        model_name="yolov8n.pt",
        device="cuda:0",
        timestamp=time.time()
    )
    assert res.count == 1
    assert res.person_count == 1
    assert res.vehicle_count == 0

def test_annotator_tactical_boxes():
    img = np.zeros((480, 640, 3), dtype=np.uint8)
    d = Detection(
        box=(50, 50, 150, 250),
        confidence=0.92,
        class_id=0,
        class_name="person",
        center=(100, 150),
        width=100,
        height=200
    )
    annotated = annotate_frame(img, [d], fps=15.0)
    assert annotated.shape == (480, 640, 3)
    # Ensure drawing made pixels non-zero
    assert np.sum(annotated) > 0

def test_yolo_detector_instantiation():
    detector = YOLODetector()
    assert detector.model_name is not None
    assert detector.device in ["cuda:0", "cpu"]
    supported = detector.get_supported_classes()
    assert "person" in supported
    assert "car" in supported
    assert "truck" in supported

def test_inference_manager_metrics():
    metrics = inference_manager.get_metrics()
    assert "target_fps" in metrics
    assert "actual_fps" in metrics
    assert "avg_latency_ms" in metrics
    assert "confidence_threshold" in metrics

def test_ai_status_endpoint():
    response = client.get("/api/ai/status")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "metrics" in data
    assert "supported_classes" in data
    assert "person" in data["supported_classes"]

def test_ai_detections_endpoint():
    response = client.get("/api/ai/detections/CAM_01")
    assert response.status_code == 200
    data = response.json()
    assert data["camera_id"] == "CAM_01"
    assert "detections" in data
    assert "count" in data
    assert "inference_time_ms" in data

def test_on_demand_detect_endpoint():
    # Generate test image in memory
    img = np.zeros((320, 320, 3), dtype=np.uint8)
    _, encoded = cv2.imencode('.jpg', img)
    files = {"file": ("test.jpg", io.BytesIO(encoded.tobytes()), "image/jpeg")}

    # The detector will either return detections or 503 if still warming up
    response = client.post("/api/ai/detect", files=files)
    assert response.status_code in [200, 503]
    if response.status_code == 200:
        data = response.json()
        assert "detections" in data
        assert "inference_time_ms" in data
