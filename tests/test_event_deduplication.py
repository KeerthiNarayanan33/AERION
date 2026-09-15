import pytest
import time
from datetime import datetime, timezone

from backend.events.event_types import EventSeverity, EventStatus
from backend.events.deduplicator import EventDeduplicator
from backend.events.event_engine import EventEngine
from backend.zones.state_machine import IntrusionState
from backend.database.database import SessionLocal, init_db
from backend.database.models import EventModel
from fastapi.testclient import TestClient
from backend.main import app

@pytest.fixture(scope="module")
def setup_db():
    init_db()
    yield

def test_rule_based_priority_scoring():
    dedup = EventDeduplicator()

    # Restricted entry or active event -> CRITICAL
    sev_crit1 = dedup.compute_severity(IntrusionState.RESTRICTED_ENTRY, zone_type="RESTRICTED")
    sev_crit2 = dedup.compute_severity(IntrusionState.ACTIVE_EVENT, zone_type="RESTRICTED")
    assert sev_crit1 == EventSeverity.CRITICAL
    assert sev_crit2 == EventSeverity.CRITICAL

    # Warning state approaching border -> HIGH
    sev_high = dedup.compute_severity(IntrusionState.WARNING, zone_type="WARNING", is_approaching_border=True)
    assert sev_high == EventSeverity.HIGH

    # Warning state without approach -> MEDIUM
    sev_med1 = dedup.compute_severity(IntrusionState.WARNING, zone_type="WARNING", is_approaching_border=False)
    assert sev_med1 == EventSeverity.MEDIUM

    # Approaching state -> MEDIUM
    sev_med2 = dedup.compute_severity(IntrusionState.APPROACHING, zone_type="NORMAL")
    assert sev_med2 == EventSeverity.MEDIUM

    # Normal state -> LOW
    sev_low = dedup.compute_severity(IntrusionState.NORMAL, zone_type="NORMAL")
    assert sev_low == EventSeverity.LOW

def test_continuous_deduplication_lifecycle():
    dedup = EventDeduplicator(hysteresis_seconds=3.0)
    target_id = "CAM_01_TRK_TEST_1"
    t0 = time.time()

    # Frame 1: Target enters restricted zone -> CREATED
    action1, rec1 = dedup.process_target_observation(
        target_id=target_id,
        object_class="person",
        intrusion_state=IntrusionState.RESTRICTED_ENTRY,
        zone_id="ZONE_C",
        zone_name="Restricted Fence",
        zone_type="RESTRICTED",
        coordinates=(0.45, 0.60),
        confidence=0.88,
        camera_id="CAM_01",
        timestamp=t0
    )
    assert action1 == "CREATED"
    assert rec1 is not None
    assert rec1.peak_severity == EventSeverity.CRITICAL
    assert rec1.status == EventStatus.ACTIVE
    assert len(dedup.get_active_events()) == 1

    event_id = rec1.event_id

    # Frames 2-10: Rapid consecutive observations within 1 second -> UPDATED (NOT duplicated!)
    for i in range(1, 10):
        t_frame = t0 + (i * 0.1)
        action_i, rec_i = dedup.process_target_observation(
            target_id=target_id,
            object_class="person",
            intrusion_state=IntrusionState.RESTRICTED_ENTRY,
            zone_id="ZONE_C",
            zone_name="Restricted Fence",
            zone_type="RESTRICTED",
            coordinates=(0.45 + i * 0.01, 0.60 + i * 0.01),
            confidence=0.90,
            camera_id="CAM_01",
            timestamp=t_frame
        )
        assert action_i == "UPDATED"
        assert rec_i.event_id == event_id  # Same event ID maintained!

    # Exactly 1 active event exists, NOT 10!
    active_list = dedup.get_active_events()
    assert len(active_list) == 1
    assert active_list[0].update_count == 10
    assert len(active_list[0].trajectory) == 10

def test_event_escalation():
    dedup = EventDeduplicator()
    target_id = "CAM_01_TRK_ESCALATE"
    t = time.time()

    # Step 1: Initial APPROACHING (MEDIUM)
    act1, r1 = dedup.process_target_observation(
        target_id=target_id,
        object_class="person",
        intrusion_state=IntrusionState.APPROACHING,
        zone_id="ZONE_A",
        zone_name="Outer Patrol",
        coordinates=(0.1, 0.2),
        timestamp=t
    )
    assert act1 == "CREATED"
    assert r1.peak_severity == EventSeverity.MEDIUM

    # Step 2: Progresses to WARNING with approach vector (HIGH)
    act2, r2 = dedup.process_target_observation(
        target_id=target_id,
        object_class="person",
        intrusion_state=IntrusionState.WARNING,
        zone_id="ZONE_B",
        zone_name="Approach Sector",
        coordinates=(0.3, 0.4),
        is_approaching_border=True,
        timestamp=t + 1.0
    )
    assert act2 == "ESCALATED"
    assert r2.peak_severity == EventSeverity.HIGH

    # Step 3: Breaches boundary into RESTRICTED_ENTRY (CRITICAL)
    act3, r3 = dedup.process_target_observation(
        target_id=target_id,
        object_class="person",
        intrusion_state=IntrusionState.RESTRICTED_ENTRY,
        zone_id="ZONE_C",
        zone_name="Restricted Fence",
        zone_type="RESTRICTED",
        coordinates=(0.5, 0.6),
        timestamp=t + 2.0
    )
    assert act3 == "ESCALATED"
    assert r3.peak_severity == EventSeverity.CRITICAL

def test_stale_event_pruning_and_resolution():
    dedup = EventDeduplicator(hysteresis_seconds=2.0)
    target_id = "CAM_01_TRK_STALE"
    t0 = 1000.0

    dedup.process_target_observation(
        target_id=target_id,
        object_class="person",
        intrusion_state=IntrusionState.RESTRICTED_ENTRY,
        zone_id="ZONE_C",
        zone_name="Restricted Fence",
        zone_type="RESTRICTED",
        timestamp=t0
    )
    assert len(dedup.get_active_events()) == 1

    # At t = 1001.0 (1s later), still within hysteresis -> NOT pruned
    res1 = dedup.prune_stale_events(current_time=1001.0)
    assert len(res1) == 0
    assert len(dedup.get_active_events()) == 1

    # At t = 1003.5 (> 2.0s since last detection) -> RESOLVED
    res2 = dedup.prune_stale_events(current_time=1003.5)
    assert len(res2) == 1
    assert res2[0].status == EventStatus.RESOLVED
    assert res2[0].resolved_at == 1003.5
    assert len(dedup.get_active_events()) == 0

def test_operator_acknowledgment_and_manual_resolution():
    dedup = EventDeduplicator()
    target_id = "CAM_01_TRK_ACK"
    t0 = time.time()

    _, rec = dedup.process_target_observation(
        target_id=target_id,
        object_class="person",
        intrusion_state=IntrusionState.RESTRICTED_ENTRY,
        zone_id="ZONE_C",
        zone_name="Restricted Fence",
        zone_type="RESTRICTED",
        timestamp=t0
    )
    assert rec.status == EventStatus.ACTIVE

    # Operator acknowledges
    ack_rec = dedup.acknowledge_event(rec.event_id, operator_name="Officer Sharma", notes="Camera zoomed in, team alerted.")
    assert ack_rec is not None
    assert ack_rec.status == EventStatus.ACKNOWLEDGED
    assert ack_rec.acknowledged_by == "Officer Sharma"

    # Operator manually resolves
    res_rec = dedup.resolve_event_manually(rec.event_id, operator_name="Officer Sharma")
    assert res_rec is not None
    assert res_rec.status == EventStatus.RESOLVED
    assert len(dedup.get_active_events()) == 0

def test_event_api_endpoints(setup_db):
    client = TestClient(app)

    # 1. Trigger demo intrusion via API
    post_res = client.post("/api/events", json={
        "event_type": "RESTRICTED_ENTRY",
        "severity": "CRITICAL",
        "camera_id": "CAM_01",
        "zone_id": "ZONE_C",
        "object_id": "API_TEST_TRK_01",
        "object_class": "person",
        "confidence": 0.96,
        "description": "API Test intrusion"
    })
    assert post_res.status_code == 200
    data = post_res.json()
    assert "event_id" in data
    evt_id = data["event_id"]

    # 2. Check active events endpoint
    active_res = client.get("/api/events/active")
    assert active_res.status_code == 200
    active_data = active_res.json()
    assert "active_count" in active_data
    assert any(e["id"] == evt_id for e in active_data["events"])

    # 3. Acknowledge event via API
    ack_res = client.post(f"/api/events/{evt_id}/acknowledge", json={
        "operator_name": "Test Officer",
        "notes": "Verified visually"
    })
    assert ack_res.status_code == 200
    assert ack_res.json()["status"] == "ACKNOWLEDGED"

    # 4. Resolve event via API
    resolve_res = client.post(f"/api/events/{evt_id}/resolve", json={
        "operator_name": "Test Officer"
    })
    assert resolve_res.status_code == 200
    assert resolve_res.json()["status"] == "RESOLVED"

    # 5. List events with status filter
    list_res = client.get("/api/events?status=RESOLVED")
    assert list_res.status_code == 200
    assert any(e["id"] == evt_id for e in list_res.json()["events"])
