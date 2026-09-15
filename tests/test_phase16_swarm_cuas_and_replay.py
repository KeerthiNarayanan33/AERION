"""
SENTINEL-AI: Phase 16 Automated Test Suite
Validates:
1. Multi-UAV Autonomous Swarm Coordination & Search Patterns (Sections 33, 52, & 63)
2. Counter-UAS (C-UAS) Aerial Rogue Drone Detection & Multi-Stage Neutralization (Sections 38, 55, & 64)
3. Offline Tactical GIS Vector Mapping Engine & MGRS Grid (Sections 37, 51, & 67)
4. Forensic Timeline Incident Replay & Court-Admissible Blackbox Dossier (Sections 26, 47, & 66)
"""

import pytest
import hashlib
import json
from fastapi.testclient import TestClient

from backend.main import app
from backend.uav.swarm_manager import swarm_mission_manager, SwarmDrone
from backend.radar.counter_uas import counter_uas_manager, CUAS_STAGES
from backend.geospatial.gis_engine import tactical_gis_engine
from backend.events.timeline_replay import timeline_replay_engine

client = TestClient(app)


# =========================================================================
# 1. MULTI-UAV AUTONOMOUS SWARM COORDINATION (Sections 33, 52, & 63)
# =========================================================================

@pytest.mark.anyio
async def test_swarm_manager_dispatch_and_telemetry():
    """Validates 3-drone swarm dispatch, altitude deconfliction, and search patterns."""
    # Ensure baseline dock
    await swarm_mission_manager.recall_swarm(reason="Test Baseline")

    status = swarm_mission_manager.get_status()
    assert status["status"] == "HEALTHY"
    assert status["total_units"] == 3
    assert status["active_airborne_units"] == 0
    assert status["active_mission"] is None

    # Dispatch swarm in Vee Formation for Creeping Line Search
    dispatch_res = await swarm_mission_manager.dispatch_swarm(
        pattern="CREEPING_LINE_SEARCH",
        zone_id="ZONE_C",
        formation="VEE_FORMATION"
    )
    assert dispatch_res["status"] == "SWARM_DISPATCHED"
    assert dispatch_res["drones_deployed"] == 3
    assert "Altitude Staggered" in dispatch_res["air_deconfliction"]

    # Verify telemetry updates
    post_dispatch = swarm_mission_manager.get_status()
    assert post_dispatch["active_airborne_units"] == 3
    assert post_dispatch["current_pattern"] == "CREEPING_LINE_SEARCH"
    assert post_dispatch["formation_mode"] == "VEE_FORMATION"
    assert post_dispatch["active_mission"] is not None
    assert post_dispatch["active_mission"]["zone_id"] == "ZONE_C"

    # Verify altitude staggering for mid-air deconfliction (Section 52)
    drone_map = {d["drone_id"]: d for d in post_dispatch["drones"]}
    assert drone_map["UAV_01"]["altitude_agl_m"] == 35.0  # Scout Alpha Optical
    assert drone_map["UAV_02"]["altitude_agl_m"] == 20.0  # Hunter Bravo FLIR LWIR
    assert drone_map["UAV_03"]["altitude_agl_m"] == 45.0  # Relay Charlie Tactical Mesh
    assert drone_map["UAV_01"]["state"] == "PATROLLING"
    assert drone_map["UAV_02"]["state"] == "PATROLLING"
    assert drone_map["UAV_03"]["state"] == "PATROLLING"


@pytest.mark.anyio
async def test_swarm_low_battery_relief_handover():
    """Validates autonomous target tracking handover from low-battery drone to relief sentry."""
    # Ensure swarm is dispatched
    await swarm_mission_manager.dispatch_swarm(pattern="EXPANDING_SQUARE", zone_id="ZONE_B")

    # Execute handover from UAV_01 to UAV_02
    handover_res = await swarm_mission_manager.execute_relief_handover(
        retiring_drone_id="UAV_01",
        relief_drone_id="UAV_02"
    )
    assert handover_res["status"] == "HANDOVER_CONFIRMED"
    details = handover_res["details"]
    assert details["retiring_unit"] == "UAV_01"
    assert details["relief_unit"] == "UAV_02"
    assert details["retiring_battery"] < 20.0  # Under critical threshold
    assert details["tracking_continuity"] == "100% UNBROKEN LOCK"

    # Verify post-handover states
    status = swarm_mission_manager.get_status()
    drone_map = {d["drone_id"]: d for d in status["drones"]}
    assert drone_map["UAV_01"]["state"] == "RTB"  # Returning to base
    assert drone_map["UAV_01"]["heading_deg"] == 215.0
    assert drone_map["UAV_02"]["state"] == "TRACKING_LOCK"  # Acquired tracking lock

    # Test error handling with invalid drone IDs
    with pytest.raises(ValueError):
        await swarm_mission_manager.execute_relief_handover("INVALID_01", "UAV_02")


@pytest.mark.anyio
async def test_swarm_recall():
    """Validates swarm recall back to base dock."""
    recall_res = await swarm_mission_manager.recall_swarm(reason="Shift handover")
    assert recall_res["status"] == "SWARM_DOCKED"
    assert recall_res["units_docked"] == 3

    status = swarm_mission_manager.get_status()
    assert status["active_airborne_units"] == 0
    assert status["active_mission"] is None
    for d in status["drones"]:
        assert d["state"] == "DOCKED"
        assert d["altitude_agl_m"] == 0.0


def test_swarm_api_endpoints():
    """Validates HTTP API routes for multi-UAV swarm control."""
    # 1. GET /api/swarm/status
    res = client.get("/api/swarm/status")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "HEALTHY"
    assert "drones" in data
    assert len(data["drones"]) == 3

    # 2. POST /api/swarm/dispatch
    res = client.post("/api/swarm/dispatch", json={
        "pattern": "PERIMETER_PATROL",
        "zone_id": "ZONE_A",
        "formation": "LINE_ABREAST"
    })
    assert res.status_code == 200
    dispatch_data = res.json()
    assert dispatch_data["status"] == "SWARM_DISPATCHED"
    assert dispatch_data["pattern"] == "PERIMETER_PATROL"

    # 3. POST /api/swarm/handover
    res = client.post("/api/swarm/handover", json={
        "retiring_drone_id": "UAV_01",
        "relief_drone_id": "UAV_02"
    })
    assert res.status_code == 200
    handover_data = res.json()
    assert handover_data["status"] == "HANDOVER_CONFIRMED"

    # 4. POST /api/swarm/handover with invalid drone
    res = client.post("/api/swarm/handover", json={
        "retiring_drone_id": "NON_EXISTENT",
        "relief_drone_id": "UAV_02"
    })
    assert res.status_code == 400

    # 5. POST /api/swarm/recall
    res = client.post("/api/swarm/recall", json={"reason": "Test Suite Cleanup"})
    assert res.status_code == 200
    recall_data = res.json()
    assert recall_data["status"] == "SWARM_DOCKED"


# =========================================================================
# 2. COUNTER-UAS (C-UAS) ROGUE DRONE NEUTRALIZATION (Sections 38, 55, & 64)
# =========================================================================

@pytest.mark.anyio
async def test_counter_uas_full_kill_chain():
    """Validates 4-stage anti-drone escalation: micro-Doppler radar -> RF jamming -> GNSS spoof -> net gun."""
    # 1. Reset Sky Shield
    reset_res = await counter_uas_manager.reset_sky_shield()
    assert reset_res["status"] == "RESET_COMPLETED"
    assert reset_res["system_state"] == "SKY_SHIELD_STANDBY"

    status = counter_uas_manager.get_status()
    assert status["current_stage"] == 0
    assert status["active_threat"] is None
    assert status["rf_jammer_active"] is False
    assert status["gnss_denial_active"] is False

    # 2. Stage 1: Radar Micro-Doppler Intrusion Detection
    sim_res = await counter_uas_manager.simulate_rogue_drone(
        callsign="ROGUE_HEXA_TEST",
        altitude_m=52.0,
        payload_type="SUSPECTED_NARCOTICS_DROP"
    )
    assert sim_res["status"] == "ROGUE_UAV_DETECTED"
    assert sim_res["threat"]["callsign"] == "ROGUE_HEXA_TEST"
    assert sim_res["threat"]["radar_signature"]["micro_doppler_blade_rate_hz"] == 240.0
    assert counter_uas_manager.current_stage == 1
    assert counter_uas_manager.system_state == "ROGUE_UAV_INTRUSION_DETECTED"

    # 3. Stage 2: Directional RF Command Link Jamming (2.4 / 5.8 GHz)
    stg2_res = await counter_uas_manager.escalate_countermeasure()
    assert stg2_res["current_stage"] == 2
    assert counter_uas_manager.rf_jammer_active is True
    assert counter_uas_manager.gnss_denial_active is False
    assert counter_uas_manager.system_state == "DIRECTIONAL_RF_JAMMING_ACTIVE"

    # 4. Stage 3: GNSS Denial & Auto-Descent Soft Landing
    stg3_res = await counter_uas_manager.escalate_countermeasure()
    assert stg3_res["current_stage"] == 3
    assert counter_uas_manager.rf_jammer_active is True
    assert counter_uas_manager.gnss_denial_active is True
    assert counter_uas_manager.system_state == "GNSS_SPOOFING_HOVER_FAILSAFE"

    # 5. Stage 4: Pneumatic Net-Gun Kinetic Capture
    stg4_res = await counter_uas_manager.escalate_countermeasure()
    assert stg4_res["current_stage"] == 4
    assert counter_uas_manager.system_state == "KINETIC_NET_GUN_AUTHORIZED"

    # Verify stage ceiling (cannot exceed Stage 4)
    stg_cap = await counter_uas_manager.escalate_countermeasure()
    assert stg_cap["current_stage"] == 4

    # 6. Neutralize and Capture Threat
    initial_neutralized = counter_uas_manager.neutralized_drones_count
    neutralize_res = await counter_uas_manager.neutralize_threat()
    assert neutralize_res["status"] == "THREAT_NEUTRALIZED"
    assert neutralize_res["total_neutralized"] == initial_neutralized + 1
    assert neutralize_res["system_state"] == "SKY_SHIELD_STANDBY"
    assert counter_uas_manager.active_threat is None
    assert counter_uas_manager.current_stage == 0


def test_counter_uas_api_endpoints():
    """Validates HTTP API routes for Counter-UAS system."""
    # 1. GET /api/cuas/status
    res = client.get("/api/cuas/status")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "HEALTHY"
    assert "all_stages" in data
    assert len(data["all_stages"]) == 4

    # 2. POST /api/cuas/simulate-threat
    res = client.post("/api/cuas/simulate-threat", json={
        "callsign": "INTRUDER_UAV_X1",
        "altitude_m": 42.0,
        "payload_type": "AMMUNITION_DROP_CANISTER"
    })
    assert res.status_code == 200
    sim_data = res.json()
    assert sim_data["status"] == "ROGUE_UAV_DETECTED"
    assert sim_data["threat"]["callsign"] == "INTRUDER_UAV_X1"

    # 3. POST /api/cuas/escalate
    res = client.post("/api/cuas/escalate", json={"operator": "TEST_OFFICER_01"})
    assert res.status_code == 200
    esc_data = res.json()
    assert esc_data["status"] == "COUNTERMEASURE_ESCALATED"

    # 4. POST /api/cuas/neutralize
    res = client.post("/api/cuas/neutralize")
    assert res.status_code == 200
    neut_data = res.json()
    assert neut_data["status"] == "THREAT_NEUTRALIZED"

    # 5. POST /api/cuas/reset
    res = client.post("/api/cuas/reset")
    assert res.status_code == 200
    assert res.json()["status"] == "RESET_COMPLETED"


# =========================================================================
# 3. OFFLINE TACTICAL GIS VECTOR MAPPING ENGINE (Sections 37, 51, & 67)
# =========================================================================

def test_tactical_gis_layers_compilation():
    """Validates 100% offline GeoJSON tactical vector layers, border fencing, and MGRS grid."""
    layers_data = tactical_gis_engine.get_tactical_vector_layers()
    assert layers_data["status"] == "LAYERS_COMPILED"
    assert layers_data["geodetic_datum"] == "WGS-84 / UTM Zone 43N"
    assert "base_station" in layers_data

    layers = layers_data["layers"]
    assert "border_pillars" in layers
    assert "zero_line" in layers
    assert "bsf_fence" in layers
    assert "surveillance_zones" in layers
    assert "sensor_fov" in layers
    assert "terrain_ravine_shadow" in layers
    assert "mgrs_grid" in layers

    # Validate Border Pillars FeatureCollection
    pillars = layers["border_pillars"]
    assert pillars["type"] == "FeatureCollection"
    assert len(pillars["features"]) == 3
    pillar_ids = [f["properties"]["id"] for f in pillars["features"]]
    assert "BP-743" in pillar_ids
    assert "BP-744" in pillar_ids
    assert "BP-745" in pillar_ids

    # Validate Zero Line and BSF Fence geometries
    assert layers["zero_line"]["geometry"]["type"] == "LineString"
    assert len(layers["zero_line"]["geometry"]["coordinates"]) >= 4
    assert layers["bsf_fence"]["geometry"]["type"] == "LineString"

    # Validate Surveillance Zones (ZONE_A, ZONE_B, ZONE_C)
    zones = layers["surveillance_zones"]["features"]
    zone_ids = [z["properties"]["id"] for z in zones]
    assert "ZONE_A" in zone_ids
    assert "ZONE_B" in zone_ids
    assert "ZONE_C" in zone_ids
    for z in zones:
        assert z["geometry"]["type"] == "Polygon"

    # Validate 100m MGRS Grid Matrix (5x5 grid = 25 cells)
    mgrs = layers["mgrs_grid"]["features"]
    assert len(mgrs) == 25
    for cell in mgrs:
        assert cell["properties"]["type"] == "MGRS_100M_CELL"
        assert cell["geometry"]["type"] == "Polygon"


def test_tactical_gis_api_endpoint():
    """Validates HTTP API endpoint GET /api/gis/vector-layers."""
    res = client.get("/api/gis/vector-layers")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "LAYERS_COMPILED"
    assert "layers" in data
    assert "border_pillars" in data["layers"]


# =========================================================================
# 4. FORENSIC TIMELINE REPLAY & BLACKBOX HISTORIAN (Sections 26, 47, & 66)
# =========================================================================

def test_timeline_replay_snapshot_and_time_travel():
    """Validates second-by-second snapshot historian and time travel scrubbing."""
    # Record current instant snapshot
    snap = timeline_replay_engine.record_snapshot()
    assert "epoch_sec" in snap
    assert "timestamp" in snap
    assert "radar_targets" in snap
    assert "active_events" in snap

    # Get timeline range
    rng = timeline_replay_engine.get_timeline_range()
    assert rng["status"] == "TIMELINE_ACTIVE"
    assert rng["total_frames"] >= 120  # Seeded initial frames
    assert rng["duration_seconds"] > 0
    assert len(rng["incident_markers"]) >= 1

    # Time-travel scrubber query to an exact historical timestamp
    target_epoch = rng["start_epoch"] + 30
    historical_state = timeline_replay_engine.get_state_at_timestamp(target_epoch)
    assert historical_state["status"] == "HISTORICAL_STATE_FOUND"
    assert historical_state["requested_epoch"] == target_epoch
    assert historical_state["delta_seconds"] <= 1
    assert "snapshot" in historical_state
    assert "radar_targets" in historical_state["snapshot"]


def test_forensic_blackbox_dossier_integrity():
    """Validates ISO 27037 compliance and SHA-256 cryptographic seal of forensic dossier."""
    dossier = timeline_replay_engine.generate_forensic_blackbox_dossier(incident_id="INCIDENT_SIH_AUDIT_2026")
    assert dossier["incident_id"] == "INCIDENT_SIH_AUDIT_2026"
    assert dossier["compliance_standard"] == "ISO/IEC 27037:2012 Digital Evidence Handling"
    assert "sha256_integrity_digest" in dossier
    assert len(dossier["sha256_integrity_digest"]) == 64  # Valid SHA-256 hex string
    assert len(dossier["chronological_telemetry"]) > 0

    # Verify cryptographic integrity: recalculate SHA-256 without the digest field
    recorded_hash = dossier["sha256_integrity_digest"]
    dossier_copy = {k: v for k, v in dossier.items() if k != "sha256_integrity_digest"}
    recalculated_hash = hashlib.sha256(json.dumps(dossier_copy, sort_keys=True).encode('utf-8')).hexdigest()
    assert recorded_hash == recalculated_hash


def test_timeline_replay_api_endpoints():
    """Validates HTTP API routes for timeline replay and blackbox dossier."""
    # 1. GET /api/replay/timeline
    res = client.get("/api/replay/timeline")
    assert res.status_code == 200
    tl_data = res.json()
    assert tl_data["status"] == "TIMELINE_ACTIVE"
    assert "start_epoch" in tl_data

    # 2. GET /api/replay/state?epoch_sec=...
    res = client.get(f"/api/replay/state?epoch_sec={tl_data['start_epoch']}")
    assert res.status_code == 200
    state_data = res.json()
    assert state_data["status"] == "HISTORICAL_STATE_FOUND"
    assert "snapshot" in state_data

    # 3. GET /api/replay/dossier?incident_id=...
    res = client.get("/api/replay/dossier?incident_id=COURT_TEST_01")
    assert res.status_code == 200
    dossier_data = res.json()
    assert dossier_data["incident_id"] == "COURT_TEST_01"
    assert "sha256_integrity_digest" in dossier_data
