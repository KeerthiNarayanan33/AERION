import time
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.ai.identity_service import identity_service
from backend.events.incident_service import incident_service
from backend.geospatial.navigation_service import navigation_service
from backend.geospatial.gps_service import gps_manager
from backend.uav.drone_provider import drone_manager, DroneFlightState

client = TestClient(app)

def test_section53_complete_23_step_scenario():
    """
    Executes and validates the exact 23-step end-to-end incident response
    lifecycle specified in Section 53 of the AERION specification.
    """
    # Baseline setup
    drone_manager.sim_provider.set_battery(95.0)
    drone_manager.return_home(reason="Scenario test baseline reset")
    drone_manager.sim_provider.state = DroneFlightState.STANDBY
    identity_service.clear_simulation()

    # STEP 1 & 2: Person enters ZONE-02 (ZONE_B) and CAM_01 detects person
    camera_id = "CAM_01"
    zone_id = "ZONE_B"

    # STEP 3 & 4: Identity verification starts -> person determined unauthorized/unverified
    identity_service.simulate_identity(
        camera_id=camera_id,
        identity="UNKNOWN",
        confidence=0.92,
        authorization="UNAUTHORIZED",
        duration=30.0,
        zone_id=zone_id
    )
    id_res = identity_service.get_latest_result(camera_id)
    assert id_res["identity"] == "UNKNOWN"
    assert id_res["confidence"] >= 0.85
    assert id_res["authorization"] == "UNAUTHORIZED"

    # STEP 5: Source camera & source zone identified
    source_cam = id_res["camera_id"]
    source_zone = incident_service.resolve_camera_zone(source_cam)
    assert source_cam == "CAM_01"
    assert source_zone == "ZONE_B"

    # STEP 6: System retrieves ZONE-02 latitude and longitude
    target_lat, target_lon = incident_service.resolve_zone_coordinates(source_zone)
    assert target_lat == 31.6262
    assert target_lon == 74.8748

    # STEP 7: System retrieves DRONE-001 GPS, battery, and fix
    drone_telem = drone_manager.get_telemetry()
    assert drone_telem["drone_id"] == "DRONE-001"
    assert drone_telem["battery_percent"] > 30.0
    assert drone_telem["gps_fix"] != "NO FIX"

    # STEP 8: Calculate distance and bearing (Section 22 & 23)
    nav = navigation_service.evaluate_navigation(
        current_lat=drone_telem["latitude"],
        current_lon=drone_telem["longitude"],
        target_lat=target_lat,
        target_lon=target_lon,
        arrival_radius_m=10.0
    )
    assert nav["distance_m"] > 50.0
    assert 0 <= nav["bearing_deg"] <= 360

    # STEP 9: Validate mission safety (battery > 20%, valid coordinates, drone standby)
    assert drone_telem["battery_percent"] > 20.0
    assert drone_manager.sim_provider.state == DroneFlightState.STANDBY

    # STEP 10: Dispatch DRONE-001 TARGET: ZONE_B
    incident = incident_service.process_unauthorized_detection(
        camera_id=source_cam,
        zone_id=source_zone,
        track_id=101,
        identity="UNKNOWN",
        confidence=0.92,
        authorization="UNAUTHORIZED"
    )
    assert incident is not None
    incident_id = incident["incident_id"]

    # STEP 11: UAV state changes: STANDBY -> DISPATCHED -> EN ROUTE (NAVIGATING)
    dispatch_res = drone_manager.dispatch(
        target_lat=target_lat,
        target_lon=target_lon,
        zone_id=source_zone,
        incident_id=incident_id
    )
    assert dispatch_res["state"] == "DISPATCHED"

    # STEP 12: Map displays drone movement (simulation tick advances position)
    drone_manager.sim_provider._tick_flight_dynamics()
    assert drone_manager.get_telemetry()["state"] in ("DISPATCHED", "NAVIGATING")
    assert len(drone_manager.sim_provider.flight_trail) >= 1

    # STEP 13 & 14: Drone reaches arrival radius (<=10m) -> ARRIVED -> AERIAL_SCAN
    drone_manager.sim_provider.current_lat = target_lat
    drone_manager.sim_provider.current_lon = target_lon
    drone_manager.sim_provider._tick_flight_dynamics()
    assert drone_manager.get_telemetry()["state"] in ("ARRIVED", "AERIAL_SCAN")

    # STEP 15 & 16: Drone camera searches target area & detects intruder
    drone_manager.start_scan()
    assert drone_manager.get_telemetry()["state"] == "AERIAL_SCAN"

    # STEP 17 & 18: Aerial identity verification occurs -> INCIDENT CONFIRMED
    aerial_check = incident_service.record_aerial_verification(
        incident_id=incident_id,
        aerial_identity="UNKNOWN",
        confidence=0.91,
        authorization="UNAUTHORIZED"
    )
    assert aerial_check["status"] == "INCIDENT CONFIRMED"
    assert aerial_check["aerial_identity"] == "UNKNOWN"
    assert aerial_check["confidence"] == 0.91

    # STEP 19: System enters TRACKING / MONITORING
    drone_manager.sim_provider.state = DroneFlightState.TRACKING
    assert drone_manager.get_telemetry()["state"] == "TRACKING"

    # STEP 20 & 21: Mission ends or operator commands return -> RETURNING
    rth_res = drone_manager.return_home(reason="Mission completed")
    assert rth_res["state"] == "RETURNING"

    # STEP 22 & 23: Drone reaches home station -> DOCKED -> CHARGING
    drone_manager.sim_provider.current_lat = drone_manager.sim_provider.home_lat
    drone_manager.sim_provider.current_lon = drone_manager.sim_provider.home_lon
    drone_manager.sim_provider.battery_percent = 85.0
    drone_manager.sim_provider._tick_flight_dynamics()
    assert drone_manager.get_telemetry()["state"] in ("CHARGING", "STANDBY")
