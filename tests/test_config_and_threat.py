import time
import pytest
import numpy as np
import cv2
from fastapi.testclient import TestClient

from backend.main import app
from backend.config import get_settings, update_runtime_settings
from backend.ai.tracker_interface import TrackedObject
from backend.ai.threat_profiler import ThreatProfiler, threat_profiler

client = TestClient(app)

# ============================================================================
# 1. DYNAMIC CONFIGURATION API TESTS (SECTION 41)
# ============================================================================

def test_get_runtime_config_api():
    res = client.get("/api/config")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "SUCCESS"
    assert "settings" in data
    assert "limits" in data
    assert "AI_INFERENCE_FPS" in data["settings"]
    assert "DETECTION_CONFIDENCE" in data["settings"]
    assert "LOITERING_THRESHOLD_SECONDS" in data["settings"]

def test_update_runtime_config_api():
    res = client.put("/api/config", json={
        "AI_INFERENCE_FPS": 20,
        "DETECTION_CONFIDENCE": 0.65,
        "LOITERING_THRESHOLD_SECONDS": 12.0,
        "PRIVACY_BLUR_ENABLED": True
    })
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "SUCCESS"
    assert data["updates"]["AI_INFERENCE_FPS"] == 20
    assert data["updates"]["DETECTION_CONFIDENCE"] == 0.65
    assert data["updates"]["PRIVACY_BLUR_ENABLED"] is True

    # Verify settings singleton updated in-memory
    s = get_settings()
    assert s.AI_INFERENCE_FPS == 20
    assert s.DETECTION_CONFIDENCE == 0.65
    assert s.LOITERING_THRESHOLD_SECONDS == 12.0
    assert s.PRIVACY_BLUR_ENABLED is True

def test_reset_runtime_config_api():
    res = client.post("/api/config/reset")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "SUCCESS"
    assert data["defaults"]["AI_INFERENCE_FPS"] == 15
    assert data["defaults"]["DETECTION_CONFIDENCE"] == 0.50

    s = get_settings()
    assert s.AI_INFERENCE_FPS == 15
    assert s.DETECTION_CONFIDENCE == 0.50

# ============================================================================
# 2. THREAT PROFILER & LOITERING TESTS (SECTION 27 & 47)
# ============================================================================

def test_threat_profiler_loitering():
    profiler = ThreatProfiler()
    now = time.time()

    track = TrackedObject(
        track_id=101,
        class_id=0,
        class_name="person",
        confidence=0.88,
        box=(50, 50, 150, 200),
        center=(100, 125),
        first_seen=now - 15.0,  # 15s in zone (exceeds default 8s threshold)
        last_seen=now,
        zone_id="ZONE_B",
        zone_name="Warning Approach Sector",
        intrusion_state="WARNING"
    )

    threat_score, is_loitering = profiler.evaluate_track_threat(track, zone_type="WARNING", now=now)
    assert is_loitering is True
    assert threat_score >= 0.50

def test_threat_profiler_normal_non_loitering():
    profiler = ThreatProfiler()
    now = time.time()

    track = TrackedObject(
        track_id=102,
        class_id=0,
        class_name="person",
        confidence=0.88,
        box=(50, 50, 150, 200),
        center=(100, 125),
        first_seen=now - 2.0,  # Only 2s in zone
        last_seen=now,
        zone_id="ZONE_A",
        zone_name="Outer Patrol Sector",
        intrusion_state="NORMAL"
    )

    threat_score, is_loitering = profiler.evaluate_track_threat(track, zone_type="NORMAL", now=now)
    assert is_loitering is False
    assert threat_score <= 0.30

def test_threat_profiler_approach_velocity_boost():
    profiler = ThreatProfiler()
    now = time.time()

    track = TrackedObject(
        track_id=103,
        class_id=0,
        class_name="person",
        confidence=0.90,
        box=(50, 50, 150, 200),
        center=(100, 125),
        first_seen=now - 1.0,
        last_seen=now,
        zone_id="ZONE_B",
        zone_name="Warning Approach Sector",
        intrusion_state="WARNING"
    )

    # Stationary vs Rapid Approach
    score_slow, _ = profiler.evaluate_track_threat(track, zone_type="WARNING", radial_speed_mps=0.0, now=now)
    score_fast, _ = profiler.evaluate_track_threat(track, zone_type="WARNING", radial_speed_mps=-2.8, now=now)

    assert score_fast > score_slow

# ============================================================================
# 3. PRIVACY BLURRED REDACTION TESTS (SECTION 46)
# ============================================================================

def test_privacy_gaussian_blurring():
    profiler = ThreatProfiler()
    # Create synthetic test image with high-contrast sharp edge inside bounding box
    img = np.zeros((400, 400, 3), dtype=np.uint8)
    img[100:250, 100:175] = 255  # Left half white, right half black

    track = TrackedObject(
        track_id=201,
        class_id=0,
        class_name="person",
        confidence=0.95,
        box=(100, 100, 250, 250),
        center=(175, 175),
        first_seen=time.time(),
        last_seen=time.time()
    )

    blurred = profiler.apply_privacy_blur(img, [track], blur_factor=31)
    assert blurred.shape == img.shape
    # The sharp vertical edge at x=175 should now be smoothed with intermediate values
    edge_region = blurred[120:200, 165:185]
    assert np.any((edge_region > 10) & (edge_region < 240))
