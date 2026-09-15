import pytest
import csv
import io
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from backend.main import app
from backend.database.database import SessionLocal, init_db
from backend.database.models import EventModel

@pytest.fixture(scope="module")
def setup_db():
    init_db()
    db = SessionLocal()
    # Insert a test event to ensure data exists for testing
    now = datetime.now(timezone.utc)
    test_evt = EventModel(
        id="EVT_AUDIT_TEST_001",
        event_type="PERIMETER_BREACH",
        severity="CRITICAL",
        camera_id="CAM_01",
        radar_id="LD2450_01",
        zone_id="ZONE_C",
        object_id="TRK_AUDIT_99",
        object_class="person",
        confidence=0.96,
        status="ACTIVE",
        start_time=now,
        updated_time=now,
        description="Audit test breach across restricted boundary",
        is_simulated=True
    )
    db.merge(test_evt)
    db.commit()
    db.close()
    yield

def test_events_summary_stats(setup_db):
    client = TestClient(app)
    res = client.get("/api/events/summary/stats")
    assert res.status_code == 200
    data = res.json()
    assert "total_events" in data
    assert "active_breaches" in data
    assert "pending_actions" in data
    assert "compiled_vaults" in data
    assert "ledger_status" in data
    assert "ledger_hash" in data
    assert data["total_events"] >= 1
    assert data["ledger_status"] == "100% VERIFIED"
    assert data["ledger_hash"].startswith("SHA256:")

def test_events_export_csv(setup_db):
    client = TestClient(app)
    res = client.get("/api/events/export/csv?severity=CRITICAL")
    assert res.status_code == 200
    assert "text/csv" in res.headers["content-type"]
    assert "attachment" in res.headers["content-disposition"]
    assert res.headers.get("x-sentinel-audit-integrity") == "SHA256-VERIFIED"

    csv_reader = csv.reader(io.StringIO(res.text))
    rows = list(csv_reader)
    assert len(rows) >= 2  # Header + at least 1 record
    headers = rows[0]
    assert "Event ID" in headers
    assert "Severity" in headers
    assert "SHA-256 Forensic Hash" in headers

    # Verify SHA-256 length in rows
    hash_idx = headers.index("SHA-256 Forensic Hash")
    for row in rows[1:]:
        assert len(row[hash_idx]) == 64

def test_events_audit_integrity(setup_db):
    client = TestClient(app)
    res = client.get("/api/events/audit/integrity")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "VERIFIED"
    assert data["integrity_score"] == "100.0%"
    assert data["tamper_detected"] is False
    assert data["total_records_audited"] >= 1
    assert data["verified_records"] >= 1
    assert len(data["ledger_hash"]) == 64
    assert "recent_audit_records" in data
    assert len(data["recent_audit_records"]) >= 1
    first_record = data["recent_audit_records"][0]
    assert "hash" in first_record
    assert len(first_record["hash"]) == 64
