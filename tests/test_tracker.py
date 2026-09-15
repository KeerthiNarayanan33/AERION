import time
import pytest
import numpy as np
from fastapi.testclient import TestClient

from backend.ai.detector_interface import Detection
from backend.ai.tracker_interface import TrackedObject
from backend.ai.tracker import TacticalTracker, compute_iou
from backend.ai.annotator import annotate_tracked_frame
from backend.ai.inference_manager import inference_manager
from backend.main import app
from backend.database.database import init_db

@pytest.fixture(scope="module", autouse=True)
def setup_tracker_test():
    init_db()
    inference_manager.initialize()

client = TestClient(app)

def test_compute_iou():
    boxA = (10, 10, 50, 50)
    boxB = (10, 10, 50, 50)
    assert compute_iou(boxA, boxB) == 1.0

    boxC = (100, 100, 150, 150)
    assert compute_iou(boxA, boxC) == 0.0

    boxD = (30, 30, 70, 70)
    iou = compute_iou(boxA, boxD)
    assert 0.0 < iou < 1.0

def test_tracker_id_persistence_and_trajectory():
    tracker = TacticalTracker(max_age=5, min_hits=1, iou_threshold=0.2)

    # Frame 1: Person at (100, 100)
    det1 = Detection(
        box=(80, 80, 120, 120),
        confidence=0.9,
        class_id=0,
        class_name="person",
        center=(100, 100),
        width=40,
        height=40
    )
    t0 = time.time()
    tracks_f1 = tracker.update([det1], timestamp=t0)
    assert len(tracks_f1) == 1
    track_id = tracks_f1[0].track_id
    assert track_id == 1
    assert tracks_f1[0].center == (100, 100)
    assert len(tracks_f1[0].trajectory) == 1

    # Frame 2: Same person moves slightly to (106, 104)
    det2 = Detection(
        box=(86, 84, 126, 124),
        confidence=0.92,
        class_id=0,
        class_name="person",
        center=(106, 104),
        width=40,
        height=40
    )
    t1 = t0 + 0.1
    tracks_f2 = tracker.update([det2], timestamp=t1)
    assert len(tracks_f2) == 1
    assert tracks_f2[0].track_id == track_id  # Stable ID preserved!
    assert tracks_f2[0].center == (106, 104)
    assert len(tracks_f2[0].trajectory) == 2
    assert tracks_f2[0].speed > 0  # Velocity estimated

def test_tracker_multiple_objects_and_classes():
    tracker = TacticalTracker(max_age=5, min_hits=1, iou_threshold=0.2)

    p = Detection(
        box=(50, 50, 90, 90),
        confidence=0.85,
        class_id=0,
        class_name="person",
        center=(70, 70),
        width=40,
        height=40
    )
    c = Detection(
        box=(200, 200, 300, 300),
        confidence=0.95,
        class_id=2,
        class_name="car",
        center=(250, 250),
        width=100,
        height=100
    )

    tracks = tracker.update([p, c])
    assert len(tracks) == 2
    class_names = {t.class_name for t in tracks}
    assert "person" in class_names
    assert "car" in class_names

def test_tracker_track_expiry():
    tracker = TacticalTracker(max_age=3, min_hits=1, iou_threshold=0.2)
    d = Detection(
        box=(50, 50, 90, 90),
        confidence=0.85,
        class_id=0,
        class_name="person",
        center=(70, 70),
        width=40,
        height=40
    )
    tracker.update([d])
    assert len(tracker._tracks) == 1

    # Update with no detections for 4 frames (exceeding max_age=3)
    for _ in range(4):
        tracker.update([])

    assert len(tracker._tracks) == 0

def test_annotator_tracked_frame():
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    tracked_obj = TrackedObject(
        track_id=42,
        class_id=0,
        class_name="person",
        confidence=0.91,
        box=(100, 100, 200, 300),
        center=(150, 200),
        velocity_x=5.0,
        velocity_y=2.0,
        speed=5.4,
        trajectory=[(130, 190), (140, 195), (150, 200)],
        first_seen=time.time() - 1.0,
        last_seen=time.time(),
        time_since_update=0,
        hits=5,
        age=5,
        confirmed=True
    )
    out = annotate_tracked_frame(frame, [tracked_obj], fps=15.0, camera_label="CAM_01")
    assert out.shape == (480, 640, 3)
    assert np.count_nonzero(out) > 0

def test_api_tracks_endpoint():
    response = client.get("/api/ai/tracks/CAM_01")
    assert response.status_code == 200
    data = response.json()
    assert "camera_id" in data
    assert "count" in data
    assert "tracks" in data
    assert data["camera_id"] == "CAM_01"

def test_tracker_spatial_proximity_and_velocity_extrapolation():
    """Validates that fast-moving targets beyond strict IoU are tracked stably using velocity and proximity."""
    tracker = TacticalTracker(max_age=10, min_hits=1, iou_threshold=0.20)
    t0 = 1000.0

    # Frame 1: Person at (100, 100)
    d1 = Detection(
        box=(80, 80, 120, 120),
        confidence=0.88,
        class_id=0,
        class_name="person",
        center=(100, 100),
        width=40,
        height=40
    )
    trks1 = tracker.update([d1], timestamp=t0)
    assert len(trks1) == 1
    orig_id = trks1[0].track_id

    # Frame 2: Person moves rapidly to (145, 100) (IoU is now 0.0 or near 0)
    d2 = Detection(
        box=(125, 80, 165, 120),
        confidence=0.89,
        class_id=0,
        class_name="person",
        center=(145, 100),
        width=40,
        height=40
    )
    trks2 = tracker.update([d2], timestamp=t0 + 0.1)
    assert len(trks2) == 1
    # ID must be preserved via proximity association!
    assert trks2[0].track_id == orig_id
    assert trks2[0].hits == 2
    assert trks2[0].confirmed is True

def test_tracker_reacquisition_after_occlusion():
    """Validates that track recovers its original ID after a missed frame (temporary occlusion)."""
    tracker = TacticalTracker(max_age=10, min_hits=1, iou_threshold=0.20)
    t0 = 2000.0

    d1 = Detection(
        box=(200, 200, 260, 260),
        confidence=0.90,
        class_id=0,
        class_name="person",
        center=(230, 230),
        width=60,
        height=60
    )
    trks = tracker.update([d1], timestamp=t0)
    track_id = trks[0].track_id

    # Frame 2: Missed detection (e.g. temporary occluded / lighting flicker)
    tracker.update([], timestamp=t0 + 0.1)

    # Frame 3: Object reappears slightly shifted
    d3 = Detection(
        box=(215, 205, 275, 265),
        confidence=0.92,
        class_id=0,
        class_name="person",
        center=(245, 235),
        width=60,
        height=60
    )
    trks3 = tracker.update([d3], timestamp=t0 + 0.2)
    assert len(trks3) == 1
    assert trks3[0].track_id == track_id  # Recovered original track ID!
