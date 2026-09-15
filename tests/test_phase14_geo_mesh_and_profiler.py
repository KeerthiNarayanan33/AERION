"""
SENTINEL-AI: Phase 14 Automated Test Suite
Validates:
1. Geospatial WGS-84, UTM Zone 43N, and MGRS 8-digit Coordinate Transformations (Section 34)
2. BSF/CAPF QRT Tactical Dispatch Directive Generation (Section 34)
3. Tactical Mesh Multi-Node Network Topology & Autonomous Failover (Sections 49 & 60)
4. Edge AI Hardware Accelerator Profiler & Quantization Benchmark Engine (Section 61)
5. Terrain Elevation Profile & Line-of-Sight (LOS) Radar Shadow Analysis (Sections 36 & 68)
"""

import re
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.geospatial.coordinates import geospatial_engine
from backend.network.mesh_manager import tactical_mesh_manager
from backend.ai.profiler import edge_ai_profiler
from backend.radar.terrain_los import terrain_los_analyzer

client = TestClient(app)

def test_geospatial_anchor_and_coordinate_transformations():
    """Validates base station geodetic anchor, WGS-84, UTM Zone 43N, and MGRS grid conversion."""
    res = client.get("/api/geo/anchor")
    assert res.status_code == 200
    anchor = res.json()
    assert anchor["site_id"] == "FOB_ALPHA"
    assert anchor["latitude"] == 31.6234
    assert anchor["longitude"] == 74.8721
    assert "31°37'" in anchor["latitude_dms"]
    assert "74°52'" in anchor["longitude_dms"]
    assert anchor["utm_zone"] == "43N"
    assert anchor["geodetic_datum"] == "WGS-84"

    # Test Local XY transformation
    res_xy = client.post("/api/geo/transform", json={"mode": "xy", "x_east_m": 5.0, "y_north_m": 8.0})
    assert res_xy.status_code == 200
    geo = res_xy.json()
    assert geo["range_m"] == pytest.approx(9.43, abs=0.1)
    assert 30.0 < geo["bearing_deg"] < 35.0
    assert geo["latitude"] > anchor["latitude"]
    assert geo["longitude"] > anchor["longitude"]
    assert "43R" in geo["mgrs_8digit"]
    assert "FU" in geo["mgrs_8digit"]

    # Test Polar transformation
    res_polar = client.post("/api/geo/transform", json={"mode": "polar", "range_m": 6.0, "azimuth_deg": 45.0})
    assert res_polar.status_code == 200
    polar_geo = res_polar.json()
    assert polar_geo["range_m"] == 6.0
    assert polar_geo["bearing_deg"] == 45.0

    # Test Camera Pixel Ray Projection
    res_cam = client.post("/api/geo/transform", json={"mode": "camera_pixel", "norm_u": 0.5, "norm_v": 0.5})
    assert res_cam.status_code == 200
    cam_geo = res_cam.json()
    assert cam_geo["range_m"] > 0

def test_qrt_tactical_dispatch_order():
    """Validates automated generation of BSF/CAPF Quick Reaction Team (QRT) Tactical Dispatch Directive."""
    payload = {
        "event_id": "EVT_BREACH_ZONE_C_89",
        "target_id": "INTRUDER_007",
        "classification": "person",
        "severity": "CRITICAL",
        "local_x_m": 3.2,
        "local_y_m": 5.8,
        "speed_mps": 1.7,
        "threat_zone": "ZONE_C",
        "operator_callsign": "BSF_COMMANDER_01"
    }
    res = client.post("/api/geo/qrt-dispatch", json=payload)
    assert res.status_code == 200
    order = res.json()

    assert order["status"] == "DISPATCH_AUTHORIZED"
    assert "QRT-ORD-" in order["dispatch_id"]
    assert order["threat_classification"] == "PERSON"
    assert order["severity"] == "CRITICAL"
    
    pos = order["target_tactical_position"]
    assert "43R FU" in pos["mgrs_8digit"]
    assert "31°" in pos["latitude_dms"]
    assert "74°" in pos["longitude_dms"]
    assert pos["range_from_fob_m"] > 0
    assert "bearing_azimuth" in pos
    
    assessment = order["intercept_assessment"]
    assert assessment["eta_seconds"] > 0
    assert "rules_of_engagement" in assessment

def test_georeferenced_targets_endpoint():
    """Validates /api/geo/targets returns active targets with MGRS military grid."""
    res = client.get("/api/geo/targets")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "HEALTHY"
    assert "anchor" in data
    assert "targets" in data

def test_tactical_mesh_topology_and_autonomous_failover():
    """Validates 3-node distributed mesh sentry chain, link quality metrics, and autonomous route failover."""
    # 1. Check initial healthy topology
    res = client.get("/api/mesh/topology")
    assert res.status_code == 200
    topo = res.json()

    assert topo["mesh_id"] == "BORDER_MESH_WEST_SECTOR_07"
    assert topo["leader_node"] == "NODE_01_ALPHA"
    assert topo["total_nodes_count"] == 3
    assert len(topo["links"]) == 3

    # 2. Trigger node outage failover on NODE_02_BRAVO
    res_fail = client.post("/api/mesh/simulate-failover", json={"node_id": "NODE_02_BRAVO", "outage_cause": "Fiber Cut"})
    assert res_fail.status_code == 200
    fail_data = res_fail.json()
    assert fail_data["status"] == "FAILOVER_ACTIVATED"
    assert fail_data["new_status"] == "OFFLINE"
    assert "NODE_03_CHARLIE" in fail_data["failover_route"]

    # Verify updated topology
    res_topo2 = client.get("/api/mesh/topology")
    assert res_topo2.status_code == 200
    topo2 = res_topo2.json()
    assert topo2["mesh_health"] == "DEGRADED"
    node2 = next(n for n in topo2["nodes"] if n["node_id"] == "NODE_02_BRAVO")
    assert node2["status"] == "OFFLINE"
    assert node2["failover_active"] is True
    assert node2["replicated_events_count"] > 0

    # 3. Restore node to active
    res_restore = client.post("/api/mesh/simulate-failover", json={"node_id": "NODE_02_BRAVO"})
    assert res_restore.status_code == 200
    assert res_restore.json()["status"] == "NODE_RESTORED"
    assert res_restore.json()["new_status"] == "ACTIVE"

def test_edge_ai_profiler_and_quantization_benchmarks():
    """Validates measured pipeline latencies and quantization benchmark comparing FP32, FP16, and INT8."""
    # 1. Live profile
    res_prof = client.get("/api/ai/profile/live")
    assert res_prof.status_code == 200
    prof = res_prof.json()
    assert prof["status"] == "HEALTHY"
    
    stages = prof["stages_ms"]
    assert "frame_grab" in stages
    assert "preprocessing" in stages
    assert "model_inference" in stages
    assert "nms" in stages
    assert "tracking" in stages
    assert "sensor_fusion" in stages
    assert "total_pipeline" in stages
    assert prof["theoretical_max_fps"] > 0

    # Percentage check
    pcts = prof["percentages"]
    pct_sum = sum(pcts.values())
    assert 98.0 <= pct_sum <= 102.0

    # 2. Quantization benchmark
    res_bench = client.post("/api/ai/profile/benchmark?iterations=5")
    assert res_bench.status_code == 200
    bench = res_bench.json()
    assert bench["status"] == "COMPLETED"
    assert len(bench["engines"]) == 3
    
    fp32 = next(e for e in bench["engines"] if "FP32" in e["engine_name"])
    fp16 = next(e for e in bench["engines"] if "FP16" in e["engine_name"])
    int8 = next(e for e in bench["engines"] if "INT8" in e["engine_name"])
    
    assert fp32["is_active"] is True
    assert fp16["avg_inference_ms"] < fp32["avg_inference_ms"]
    assert int8["avg_inference_ms"] < fp16["avg_inference_ms"]
    assert int8["model_size_mb"] < fp32["model_size_mb"]
    assert "3.8x" in int8["speedup_factor"]

def test_terrain_elevation_profile_and_los_shadow():
    """Validates terrain DEM transect, ray-casting visibility, shadow dead-zone, and UAV clearance solution."""
    # 1. Terrain profile & LOS
    res = client.get("/api/terrain/profile")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "HEALTHY"
    assert len(data["dem_profile"]) >= 50
    assert data["sensor_mast"]["tower_height_m"] == 10.0

    los = data["los_analysis"]
    assert los["has_dead_zone"] is True
    assert los["shadow_start_range_m"] is not None
    assert los["shadow_end_range_m"] is not None
    assert los["shadow_span_meters"] > 0
    assert los["max_occlusion_depth_m"] > 0
    assert "CRITICAL" in los["threat_assessment"]

    # 2. UAV clearance solution
    res_uav = client.get("/api/terrain/uav-los?altitude_m=25.0")
    assert res_uav.status_code == 200
    uav = res_uav.json()
    assert uav["status"] == "SOLUTION_CALCULATED"
    assert uav["uav_altitude_agl_m"] == 25.0
    assert uav["terrain_shadow_clearance_pct"] == 100.0
    assert uav["required_gimbal_pitch_deg"] < 0
