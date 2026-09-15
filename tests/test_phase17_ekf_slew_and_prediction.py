"""
SENTINEL-AI: Phase 17 Automated Test Suite
Validates:
1. JDL Level 1 & 2 Extended Kalman Filter (EKF) Tracker & Mahalanobis Distance Gating (Sections 20, 21, & 47)
2. Autonomous Slew-to-Cue & Directed PTZ Optical Tracking (Sections 10, 20, & 32)
3. Intruder Intent & Kinematics Trajectory Forecasting with ETB & PPI (Sections 27, 47, & 63)
4. Multi-Sensor Health Matrix & Dynamic Degraded Mode Failover (Sections 28, 29, & 49)
"""

import pytest
import math
from fastapi.testclient import TestClient

from backend.main import app
from backend.fusion.ekf_tracker import ekf_fusion_tracker, EKFTrackState
from backend.fusion.slew_director import slew_to_cue_director
from backend.ai.kinematics_predictor import kinematics_predictor
from backend.system.health_matrix import sensor_health_matrix, DEGRADED_MODES

client = TestClient(app)


# =========================================================================
# 1. JDL LEVEL 1 & 2 EXTENDED KALMAN FILTER (EKF) TRACKER (Sections 20, 21, 47)
# =========================================================================

def test_ekf_process_prediction_and_radar_update():
    """Validates EKF 4D state prediction, non-linear polar radar update, and Mahalanobis gating."""
    ekf_fusion_tracker.reset()
    assert len(ekf_fusion_tracker.get_tracks()) == 0

    # 1. Initiate Track via Polar Observation (r=3.5m, theta=-0.25 rad, rdot=-1.0 m/s)
    x0 = 3.5 * math.sin(-0.25)  # ~ -0.865m
    y0 = 3.5 * math.cos(-0.25)  # ~ 3.391m
    res1 = ekf_fusion_tracker.process_radar_target(
        radar_id=101,
        x_m=x0,
        y_m=y0,
        speed_mps=-1.0,
        distance_m=3.5
    )
    assert res1["status"] == "TRACK_INITIATED"
    track_dict = res1["track"]
    assert track_dict["track_id"] == "EKF_TRK_01"
    assert abs(track_dict["position"]["x_m"] - x0) < 0.01
    assert abs(track_dict["position"]["y_m"] - y0) < 0.01

    # Check 95% spatial error ellipse
    ellipse = track_dict["error_ellipse_95"]
    assert ellipse["semi_major_m"] > 0.0
    assert ellipse["semi_minor_m"] > 0.0

    # 2. Sequential update along motion vector
    x1 = x0 + 0.02
    y1 = y0 - 0.15
    res2 = ekf_fusion_tracker.process_radar_target(
        radar_id=101,
        x_m=x1,
        y_m=y1,
        speed_mps=-1.1,
        distance_m=math.hypot(x1, y1)
    )
    assert res2["status"] == "TRACK_UPDATED"
    assert res2["mahalanobis_d2"] <= 7.815  # Within Chi-Squared 95% 3-DOF threshold

    # 3. Spurious outlier clutter test (should be rejected by Mahalanobis gate or spawn distant track)
    extreme_outlier_res = ekf_fusion_tracker.process_radar_target(
        radar_id=999,
        x_m=x0 + 15.0,  # 15 meters away
        y_m=y0 + 15.0,
        speed_mps=12.0,
        distance_m=25.0
    )
    # Should spawn a new track rather than corrupting the first track
    assert extreme_outlier_res["status"] == "TRACK_INITIATED"
    assert extreme_outlier_res["track"]["track_id"] != "EKF_TRK_01"


def test_ekf_camera_optical_ray_fusion():
    """Validates fusing camera optical ray measurement (norm_u) into active EKF track."""
    ekf_fusion_tracker.reset()
    # Seed a track near optical center
    ekf_fusion_tracker.process_radar_target(
        radar_id=102,
        x_m=-0.2,
        y_m=4.0,
        speed_mps=-0.8,
        distance_m=4.0
    )

    # Compute expected optical ray u
    theta = math.atan2(-0.2, 4.0)
    expected_u = 0.5 + (theta / math.radians(70.0))

    # Fuse optical camera measurement
    cam_res = ekf_fusion_tracker.process_camera_detection(
        camera_track_id="CAM_01_TRK_88",
        norm_u=expected_u,
        norm_v=0.52,
        class_name="person",
        confidence=0.92
    )
    assert cam_res["status"] == "CAMERA_FUSED"
    assert cam_res["mahalanobis_d2"] <= 5.991  # Within 2-DOF Chi-sq
    assert cam_res["track"]["camera_track_id"] == "CAM_01_TRK_88"
    assert cam_res["track"]["class_name"] == "person"


def test_ekf_api_endpoints():
    """Validates HTTP API routes for EKF sensor fusion tracker."""
    # 1. GET /api/fusion/ekf-tracks
    res = client.get("/api/fusion/ekf-tracks")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "TRACKS_AVAILABLE"
    assert "tracks" in data

    # 2. POST /api/fusion/fuse-observation
    res = client.post("/api/fusion/fuse-observation", json={
        "radar_id": 105,
        "x_m": -1.1,
        "y_m": 3.8,
        "speed_mps": -1.2,
        "distance_m": 3.95
    })
    assert res.status_code == 200
    fuse_data = res.json()
    assert fuse_data["status"] in ("TRACK_INITIATED", "TRACK_UPDATED")

    # 3. POST /api/fusion/reset
    res = client.post("/api/fusion/reset")
    assert res.status_code == 200
    assert res.json()["status"] == "FUSION_AND_PTZ_RESET"


# =========================================================================
# 2. AUTONOMOUS SLEW-TO-CUE & DIRECTED OPTICAL TRACKING (Sections 10, 20, 32)
# =========================================================================

@pytest.mark.anyio
async def test_slew_to_cue_angle_calculation_and_execution():
    """Validates mathematical derivation of PTZ Pan, Tilt, Zoom angles and execution."""
    await slew_to_cue_director.reset_boresight()
    status = slew_to_cue_director.get_status()
    assert status["current_angles"]["pan_deg"] == 0.0
    assert status["current_angles"]["tilt_deg"] == -15.0
    assert status["current_angles"]["zoom_factor"] == 1.0

    # Contact at lateral x = -1.5m, depth y = 4.2m, height z = 1.2m
    # Mast height is 3.5m
    # Pan = atan2(-1.5, 4.2) in deg = ~ -19.65 deg
    # Delta z = 1.2 - 3.5 = -2.3m, ground dist = sqrt(1.5^2 + 4.2^2) ~ 4.46m
    # Tilt = atan2(-2.3, 4.46) in deg = ~ -27.27 deg
    # Zoom = 4.46 / 2.0 = ~ 2.2x
    slew_res = await slew_to_cue_director.execute_slew_to_cue(
        target_id="TRK_TEST_SLEW",
        x_m=-1.5,
        y_m=4.2,
        z_m=1.2
    )
    assert slew_res["status"] == "SLEW_COMPLETED"
    assert slew_res["lock_acquired"] is True
    assert -21.0 <= slew_res["pan_deg"] <= -18.0
    assert -29.0 <= slew_res["tilt_deg"] <= -25.0
    assert 2.0 <= slew_res["zoom_factor"] <= 2.5
    assert slew_res["transit_time_ms"] > 0

    # Verify updated gimbal status
    post_status = slew_to_cue_director.get_status()
    assert post_status["target_locked"] is not None
    assert post_status["target_locked"]["target_id"] == "TRK_TEST_SLEW"
    assert post_status["target_locked"]["optical_reticle"]["tracking_status"] == "LOCKED_IN_BORESIGHT"


def test_slew_to_cue_api_endpoints():
    """Validates HTTP API endpoints for autonomous Slew-to-Cue."""
    # 1. POST /api/fusion/slew-to-cue
    res = client.post("/api/fusion/slew-to-cue", json={
        "target_id": "API_TARGET_01",
        "x_m": 1.8,
        "y_m": 3.6,
        "z_m": 1.5
    })
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "SLEW_COMPLETED"
    assert data["lock_acquired"] is True
    assert data["pan_deg"] > 0.0  # Positive pan for positive X

    # 2. GET /api/fusion/ptz-status
    res = client.get("/api/fusion/ptz-status")
    assert res.status_code == 200
    ptz_data = res.json()
    assert ptz_data["status"] == "HEALTHY"
    assert ptz_data["target_locked"]["target_id"] == "API_TARGET_01"


# =========================================================================
# 3. INTRUDER INTENT & KINEMATICS PREDICTION (Sections 27, 47, 63)
# =========================================================================

def test_kinematics_trajectory_and_etb_calculation():
    """Validates Constant Turn/Velocity path extrapolation, PPI, and ETB countdown."""
    # Target at (-1.2m, 2.2m), moving towards fence (at Y=5.0m) at vy = 0.85 m/s, vx = 0.15 m/s
    # Dist to fence = 5.0 - 2.2 = 2.8m
    # Expected ETB = 2.8 / 0.85 ~ 3.29 seconds -> CRITICAL IMMINENT BREACH
    pred = kinematics_predictor.predict_trajectory(
        target_id="INTRUDER_TEST_01",
        x_m=-1.2,
        y_m=2.2,
        vx_mps=0.15,
        vy_mps=0.85,
        turn_rate_dps=0.0
    )

    assert pred["target_id"] == "INTRUDER_TEST_01"
    assert pred["threat_urgency"] == "CRITICAL_IMMINENT_BREACH"
    assert 3.0 <= pred["estimated_time_to_breach_sec"] <= 3.5

    # Check Predicted Point of Infiltration (PPI)
    ppi = pred["predicted_point_of_infiltration"]
    assert ppi is not None
    assert ppi["y_m"] == 5.0  # Exactly at the fence
    assert "latitude" in ppi
    assert "longitude" in ppi
    assert "mgrs_grid" in ppi
    assert ppi["defense_sector"] == "ZONE_C_RESTRICTED_FENCE"

    # Check forward waypoints (T+2s, T+5s, T+10s, T+15s)
    waypoints = pred["projected_waypoints"]
    assert len(waypoints) == 4
    offsets = [w["time_offset_sec"] for w in waypoints]
    assert offsets == [2.0, 5.0, 10.0, 15.0]
    # At T+2s, Y position should be ~ 2.2 + 0.85*2 = 3.9m
    assert abs(waypoints[0]["y_m"] - 3.9) < 0.1


def test_kinematics_api_endpoints():
    """Validates HTTP API routes for kinematics prediction."""
    # 1. POST /api/kinematics/simulate-trajectory
    res = client.post("/api/kinematics/simulate-trajectory", json={
        "target_id": "API_INTRUDER_99",
        "x_m": -0.8,
        "y_m": 1.5,
        "vx_mps": 0.1,
        "vy_mps": 0.7
    })
    assert res.status_code == 200
    data = res.json()
    assert data["target_id"] == "API_INTRUDER_99"
    assert data["estimated_time_to_breach_sec"] > 0.0

    # 2. GET /api/kinematics/prediction/{target_id}
    res = client.get("/api/kinematics/prediction/API_INTRUDER_99")
    assert res.status_code == 200
    cached = res.json()
    assert cached["target_id"] == "API_INTRUDER_99"
    assert "predicted_point_of_infiltration" in cached


# =========================================================================
# 4. MULTI-SENSOR HEALTH MATRIX & DEGRADED FAILOVER (Sections 28, 29, 49)
# =========================================================================

@pytest.mark.anyio
async def test_health_matrix_metrics_and_failover_orchestration():
    """Validates 5-sensor health matrix auditing, MTBF, SNR, and dynamic mode shifts."""
    # Reset to baseline
    reset_res = await sensor_health_matrix.reset_matrix()
    assert reset_res["status"] == "FAILOVER_ACTIVATED"
    assert reset_res["active_mode"]["mode_id"] == "BALANCED_FUSION"

    matrix = sensor_health_matrix.get_matrix_status()
    assert matrix["status"] == "HEALTHY"
    assert matrix["overall_system_health_pct"] >= 90.0
    assert len(matrix["sensors"]) == 5
    sensor_ids = [s["sensor_id"] for s in matrix["sensors"]]
    assert "RADAR_LD2450" in sensor_ids
    assert "CAMERA_01_OPTICAL" in sensor_ids
    assert "CAMERA_02_IP" in sensor_ids
    assert "UAV_SWARM" in sensor_ids
    assert "TACTICAL_MESH" in sensor_ids

    # 1. Trigger Fog / Smoke Degraded Mode (Radar 90%, Optical 10%)
    fog_res = await sensor_health_matrix.trigger_failover(
        mode_id="FOG_SMOKE_DEGRADED",
        reason="Heavy morning riverbed fog detected"
    )
    assert fog_res["active_mode"]["radar_weight"] == 0.90
    assert fog_res["active_mode"]["optical_weight"] == 0.10
    updated_matrix = sensor_health_matrix.get_matrix_status()
    cam_sensor = next(s for s in updated_matrix["sensors"] if s["sensor_id"] == "CAMERA_01_OPTICAL")
    assert cam_sensor["status"] == "DEGRADED"

    # 2. Trigger Electronic Warfare Jammed Mode (Radar 10%, Optical 90%)
    jam_res = await sensor_health_matrix.trigger_failover(
        mode_id="EW_RADAR_JAMMED",
        reason="Hostile directional RF jamming on 24GHz"
    )
    assert jam_res["active_mode"]["radar_weight"] == 0.10
    assert jam_res["active_mode"]["optical_weight"] == 0.90
    updated_matrix2 = sensor_health_matrix.get_matrix_status()
    radar_sensor = next(s for s in updated_matrix2["sensors"] if s["sensor_id"] == "RADAR_LD2450")
    assert radar_sensor["status"] == "DEGRADED"

    # 3. Test Invalid Mode raises ValueError
    with pytest.raises(ValueError):
        await sensor_health_matrix.trigger_failover(mode_id="INVALID_MODE")


def test_health_matrix_api_endpoints():
    """Validates HTTP API routes for multi-sensor health matrix."""
    # 1. GET /api/health/matrix
    res = client.get("/api/health/matrix")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "HEALTHY"
    assert "active_degraded_mode" in data
    assert "sensors" in data

    # 2. POST /api/health/trigger-failover (Valid)
    res = client.post("/api/health/trigger-failover", json={
        "mode_id": "OPTICAL_FAILOVER",
        "reason": "Test camera failover"
    })
    assert res.status_code == 200
    failover_data = res.json()
    assert failover_data["status"] == "FAILOVER_ACTIVATED"
    assert failover_data["active_mode"]["mode_id"] == "OPTICAL_FAILOVER"

    # 3. POST /api/health/trigger-failover (Invalid Mode -> 400 Bad Request)
    res = client.post("/api/health/trigger-failover", json={
        "mode_id": "NON_EXISTENT_MODE"
    })
    assert res.status_code == 400

    # 4. POST /api/health/reset-matrix
    res = client.post("/api/health/reset-matrix")
    assert res.status_code == 200
    reset_data = res.json()
    assert reset_data["active_mode"]["mode_id"] == "BALANCED_FUSION"
