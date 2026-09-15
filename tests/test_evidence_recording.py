import os
import time
import cv2
import pytest
import numpy as np
from pathlib import Path
from fastapi.testclient import TestClient

from backend.main import app
from backend.events.storage_manager import StorageManager, storage_manager
from backend.events.evidence_recorder import EvidenceRecorder, evidence_recorder
from backend.camera.frame_buffer import RollingFrameBuffer
from backend.database.database import init_db, SessionLocal
from backend.database.models import EventModel

@pytest.fixture(scope="module")
def client():
    init_db()
    return TestClient(app)

class MockCamera:
    """Mock camera with rolling frame buffer for testing evidence acquisition."""
    def __init__(self, camera_id: str = "CAM_TEST"):
        self.camera_id = camera_id
        self.buffer = RollingFrameBuffer(fps=10, buffer_seconds=4)
        for i in range(20):
            frame = np.zeros((240, 320, 3), dtype=np.uint8)
            cv2.putText(frame, f"TEST FRAME {i}", (20, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
            self.buffer.push(frame, timestamp=time.time() - (20 - i) * 0.1)

    def get_frame(self):
        item = self.buffer.get_latest()
        return item[1] if item else None

def test_storage_manager_paths_and_stats():
    sm = StorageManager(base_dir="storage")
    snap_path = sm.get_snapshot_path("TEST_EVT_001")
    vid_path = sm.get_video_path("TEST_EVT_001")

    assert snap_path.name == "TEST_EVT_001.jpg"
    assert vid_path.name == "TEST_EVT_001.mp4"

    stats = sm.get_storage_stats()
    assert "snapshot_count" in stats
    assert "video_count" in stats
    assert "total_mb" in stats
    assert "usage_percent" in stats
    assert stats["max_storage_mb"] > 0

def test_storage_retention_policy(tmp_path):
    # Test retention policy with a temporary storage directory
    test_storage = tmp_path / "storage"
    sm = StorageManager(base_dir=str(test_storage), max_storage_mb=0.001, max_age_days=1.0)

    # Create dummy files
    f1 = sm.snapshots_dir / "old_event.jpg"
    f2 = sm.events_dir / "new_event.mp4"
    f1.write_bytes(b"X" * 100)
    f2.write_bytes(b"Y" * 100)

    # Modify f1 timestamp to simulate 2 days old
    past_time = time.time() - (2 * 86400)
    os.utime(str(f1), (past_time, past_time))

    deleted = sm.enforce_retention_policy()
    assert deleted >= 1
    assert not f1.exists()

def test_evidence_snapshot_and_video_creation():
    event_id = "EVT_PYTEST_RECORDING"
    mock_cam = MockCamera("CAM_01")
    rec = EvidenceRecorder(output_fps=10)

    # 1. Capture snapshot
    snap_path = rec._capture_and_save_snapshot(event_id, mock_cam)
    assert snap_path is not None
    assert snap_path.exists()
    assert snap_path.stat().st_size > 500

    # 2. Write MP4 file from frames
    frames = [f for _, f in mock_cam.buffer.get_window(seconds=2.0)]
    assert len(frames) > 0

    vid_path = storage_manager.get_video_path(event_id)
    rec._write_mp4_file(str(vid_path), frames, event_id, "CAM_01")
    assert vid_path.exists()
    assert vid_path.stat().st_size > 1000

    # 3. Register in DB
    db = SessionLocal()
    ev = db.query(EventModel).filter(EventModel.id == event_id).first()
    if not ev:
        ev = EventModel(
            id=event_id,
            event_type="ZONE_INTRUSION_CRITICAL",
            severity="CRITICAL",
            video_path=str(vid_path),
            snapshot_path=str(snap_path),
            status="ACTIVE"
        )
        db.add(ev)
    else:
        ev.video_path = str(vid_path)
        ev.snapshot_path = str(snap_path)
    db.commit()
    db.close()

def test_evidence_api_endpoints(client):
    event_id = "EVT_PYTEST_RECORDING"

    # 1. Video playback endpoint
    vid_res = client.get(f"/api/events/{event_id}/video")
    assert vid_res.status_code == 200
    assert "video/mp4" in vid_res.headers.get("content-type", "")
    assert len(vid_res.content) > 1000

    # 2. Snapshot endpoint
    snap_res = client.get(f"/api/events/{event_id}/snapshot")
    assert snap_res.status_code == 200
    assert "image/jpeg" in snap_res.headers.get("content-type", "")
    assert len(snap_res.content) > 500

    # 3. Nonexistent video should 404
    err_res = client.get("/api/events/NONEXISTENT_EVENT_ID/video")
    assert err_res.status_code == 404

    # 4. Storage stats endpoint
    stats_res = client.get("/api/events/storage/stats")
    assert stats_res.status_code == 200
    assert "snapshot_count" in stats_res.json()
    assert "video_count" in stats_res.json()

@pytest.fixture(scope="module", autouse=True)
def cleanup_test_artifacts():
    yield
    # Cleanup pytest artifacts
    for ext, folder in [(".jpg", "storage/snapshots"), (".mp4", "storage/events")]:
        p = Path(folder) / f"EVT_PYTEST_RECORDING{ext}"
        if p.exists():
            try:
                p.unlink()
            except Exception:
                pass
