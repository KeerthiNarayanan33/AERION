import io
import zipfile
import hashlib
import json
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.security.auth import create_tactical_token, verify_tactical_token
from backend.config import get_settings

client = TestClient(app)
settings = get_settings()

def test_threat_heatmap_analytics():
    """Validates 2D Gaussian KDE threat heatmap, corridor rankings, and nocturnal distribution."""
    res = client.get("/api/analytics/threat-heatmap")
    assert res.status_code == 200
    data = res.json()

    assert data["status"] == "HEALTHY"
    assert data["grid_size"] == 25
    assert len(data["density_grid"]) == 25
    assert len(data["density_grid"][0]) == 25

    # Values must be normalized between 0.0 and 1.0
    for row in data["density_grid"]:
        for val in row:
            assert 0.0 <= val <= 1.0

    # Hotspot verification
    assert len(data["hotspots"]) >= 3
    hotspot_ids = [h["id"] for h in data["hotspots"]]
    assert "HOTSPOT_ALPHA" in hotspot_ids
    assert "HOTSPOT_BRAVO" in hotspot_ids

    # Corridor vulnerability ranking verification
    assert len(data["corridors"]) == 3
    corr_c = next(c for c in data["corridors"] if "ZONE_C" in c["name"])
    assert corr_c["risk_level"] == "CRITICAL"
    assert corr_c["vulnerability_score"] >= 90

    # 24-hour temporal distribution
    assert len(data["temporal_distribution"]) == 24
    nocturnal_hours = [t for t in data["temporal_distribution"] if t["is_nocturnal"]]
    assert len(nocturnal_hours) == 7  # 22, 23, 0, 1, 2, 3, 4

def test_tamper_proof_evidence_vault_packager():
    """
    Validates generation of ISO/IEC 27037 compliant forensic evidence vault (.zip)
    and verifies that SHA-256 manifest cryptographic signatures match actual package bytes.
    """
    # 1. Create a simulated test event
    ev_payload = {
        "event_type": "RESTRICTED_ZONE_BREACH",
        "severity": "CRITICAL",
        "camera_id": "CAM_01",
        "radar_id": "RADAR_01",
        "zone_id": "ZONE_C",
        "object_id": "991",
        "object_class": "person",
        "confidence": 0.96,
        "description": "Intruder detected breaching barbed wire fence at sector charlie",
        "is_simulated": True
    }
    create_res = client.post("/api/events", json=ev_payload)
    assert create_res.status_code == 200
    create_data = create_res.json()
    event_id = create_data.get("event_id") or create_data.get("id")
    assert event_id is not None

    # 2. Download Evidence Vault ZIP
    vault_res = client.get(f"/api/events/{event_id}/vault")
    assert vault_res.status_code == 200
    assert vault_res.headers["content-type"] == "application/zip"
    assert f"SENTINEL_EVIDENCE_VAULT_{event_id}.zip" in vault_res.headers["content-disposition"]
    assert vault_res.headers.get("x-sentinel-integrity") == "SHA-256-VERIFIED"

    # 3. Inspect ZIP structure in-memory
    zip_bytes = vault_res.content
    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
        namelist = zf.namelist()
        prefix = f"SENTINEL_{event_id}/"
        assert f"{prefix}manifest.sha256" in namelist
        assert f"{prefix}incident_summary.json" in namelist
        assert f"{prefix}dossier.html" in namelist
        assert f"{prefix}trigger_snapshot.jpg" in namelist
        assert f"{prefix}evidence_clip.mp4" in namelist

        # 4. Cryptographic Forensics: Validate SHA-256 Checksums
        manifest_content = zf.read(f"{prefix}manifest.sha256").decode("utf-8")
        manifest_lines = [line.strip() for line in manifest_content.splitlines() if line.strip() and not line.startswith("#")]
        manifest_map = {}
        for line in manifest_lines:
            parts = line.split(maxsplit=1)
            if len(parts) == 2:
                manifest_map[parts[1]] = parts[0]

        summary_bytes = zf.read(f"{prefix}incident_summary.json")
        dossier_bytes = zf.read(f"{prefix}dossier.html")
        snap_bytes = zf.read(f"{prefix}trigger_snapshot.jpg")
        vid_bytes = zf.read(f"{prefix}evidence_clip.mp4")

        assert hashlib.sha256(summary_bytes).hexdigest() == manifest_map["incident_summary.json"]
        assert hashlib.sha256(dossier_bytes).hexdigest() == manifest_map["dossier.html"]
        assert hashlib.sha256(snap_bytes).hexdigest() == manifest_map["trigger_snapshot.jpg"]
        assert hashlib.sha256(vid_bytes).hexdigest() == manifest_map["evidence_clip.mp4"]

        # Validate summary metadata contents
        summary = json.loads(summary_bytes.decode("utf-8"))
        assert summary["event"]["id"] == event_id
        assert summary["classification"] == "CONFIDENTIAL // LAW ENFORCEMENT SENSITIVE"

def test_evidence_vault_not_found():
    """Asserts 404 response for non-existent incident event."""
    res = client.get("/api/events/EVT_NONEXISTENT_99999/vault")
    assert res.status_code == 404

def test_rbac_token_issuance_and_verification():
    """Validates HMAC-SHA256 tactical token minting, verification, and tamper rejection."""
    # Mint token for COMMANDER
    token_res = client.post("/api/auth/token", json={"role": "COMMANDER", "user_id": "commander_sharma"})
    assert token_res.status_code == 200
    data = token_res.json()
    assert data["role"] == "COMMANDER"
    assert data["user_id"] == "commander_sharma"
    token = data["access_token"]
    assert token.startswith("SENTINEL.")

    # Verify token via API endpoint
    verify_res = client.get("/api/auth/verify", headers={"X-Sentinel-Token": token})
    assert verify_res.status_code == 200
    vdata = verify_res.json()
    assert vdata["status"] == "AUTHENTICATED"
    assert "user" in vdata

    # Verify Bearer header support
    bearer_res = client.get("/api/auth/verify", headers={"Authorization": f"Bearer {token}"})
    assert bearer_res.status_code == 200

    # Query roles clearance hierarchy
    roles_res = client.get("/api/auth/roles")
    assert roles_res.status_code == 200
    roles_data = roles_res.json()
    assert "COMMANDER" in roles_data["roles"]
    assert "OPERATOR" in roles_data["roles"]
    assert "OBSERVER" in roles_data["roles"]

    # Tampering test: alter signature
    parts = token.split(".")
    tampered_sig = parts[2][:-4] + "0000"
    tampered_token = f"{parts[0]}.{parts[1]}.{tampered_sig}"
    with pytest.raises(ValueError, match="signature verification failed"):
        verify_tactical_token(tampered_token)

    # Tampering test: alter payload
    tampered_payload_token = f"{parts[0]}.{parts[1]}xyz.{parts[2]}"
    with pytest.raises(ValueError):
        verify_tactical_token(tampered_payload_token)
