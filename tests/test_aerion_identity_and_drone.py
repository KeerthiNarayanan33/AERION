import pytest
import numpy as np
from fastapi.testclient import TestClient

from backend.main import app
from backend.ai.identity_service import identity_service
from backend.events.incident_service import incident_service
from backend.geospatial.navigation_service import navigation_service
from backend.geospatial.gps_service import gps_manager, Neo6mGPSProvider
from backend.uav.drone_provider import drone_manager, DroneFlightState
from backend.events.pir_service import pir_service

client = TestClient(app)

def test_authorized_person_registry_seeded():
    """Verify default authorized person (Keerthi) is enrolled."""
    persons = identity_service.list_persons()
    p_ids = [p["person_id"] for p in persons]
    assert "PERSON-001" in p_ids
    keerthi = next(p for p in persons if p["person_id"] == "PERSON-001")
    assert keerthi["name"] == "Keerthi"
    assert keerthi["status"] == "AUTHORIZED"
    assert "ZONE_B" in keerthi["allowed_zones"]

def test_identity_verification_pipeline_known_authorized():
    """Test identity verification for authorized person in permitted zone."""
    dummy_frame = np.full((300, 300, 3), 160, dtype=np.uint8)
    identity_service.simulate_identity("CAM_01", "Keerthi", 0.96, "AUTHORIZED")
    res = identity_service.verify_person(dummy_frame, (50, 50, 200, 200), camera_id="CAM_01", zone_id="ZONE_B")
    assert res["identity"] == "Keerthi"
    assert res["confidence"] >= 0.85
    assert res["authorization"] == "AUTHORIZED"

def test_identity_verification_pipeline_unauthorized_zone():
    """Test identity verification when authorized person enters forbidden zone."""
    dummy_frame = np.full((300, 300, 3), 160, dtype=np.uint8)
    identity_service.simulate_identity("CAM_02", "Keerthi", 0.94, "NOT_AUTHORIZED_FOR_ZONE")
    res = identity_service.verify_person(dummy_frame, (50, 50, 200, 200), camera_id="CAM_02", zone_id="ZONE_C")
    assert res["identity"] == "Keerthi"
    assert res["authorization"] == "NOT_AUTHORIZED_FOR_ZONE"

def test_identity_verification_unknown_person():
    """Test identity verification for unknown intruder."""
    dummy_frame = np.full((300, 300, 3), 160, dtype=np.uint8)
    identity_service.simulate_identity("CAM_01", "UNKNOWN", 0.92, "UNAUTHORIZED")
    res = identity_service.verify_person(dummy_frame, (50, 50, 200, 200), camera_id="CAM_01", zone_id="ZONE_B")
    assert res["identity"] == "UNKNOWN"
    assert res["confidence"] >= 0.85
    assert res["authorization"] == "UNAUTHORIZED"

def test_identity_low_confidence_handling():
    """Test low confidence handling without triggering false critical alarm."""
    identity_service.clear_simulation("CAM_01")
    tiny_frame = np.zeros((20, 20, 3), dtype=np.uint8)
    res = identity_service.verify_person(tiny_frame, (0, 0, 10, 10), camera_id="CAM_01", zone_id="ZONE_B")
    assert res["authorization"] == "UNVERIFIED"

def test_camera_to_zone_coordinate_resolution():
    """Verify ONE CAMERA = ONE ZONE mapping and coordinate retrieval."""
    zone_1 = incident_service.resolve_camera_zone("CAM_01")
    assert zone_1 in ("ZONE_B", "ZONE-002")
    lat_1, lon_1 = incident_service.resolve_zone_coordinates(zone_1)
    assert abs(lat_1 - 31.6262) < 0.001
    assert abs(lon_1 - 74.8748) < 0.001

    zone_2 = incident_service.resolve_camera_zone("CAM_02")
    assert zone_2 in ("ZONE_C", "ZONE-003")
    lat_2, lon_2 = incident_service.resolve_zone_coordinates(zone_2)
    assert abs(lat_2 - 31.6280) < 0.001
    assert abs(lon_2 - 74.8765) < 0.001

def test_navigation_service_haversine_and_bearing():
    """Test Haversine distance and true bearing calculations."""
    lat1, lon1 = 31.6240, 74.8723  # Base
    lat2, lon2 = 31.6262, 74.8748  # Zone B
    dist = navigation_service.calculate_haversine_distance(lat1, lon1, lat2, lon2)
    bearing = navigation_service.calculate_initial_bearing(lat1, lon1, lat2, lon2)
    assert 300 < dist < 380
    assert 30 < bearing < 60
    assert navigation_service.format_distance(dist) == f"{int(round(dist))} m"

    nav_eval = navigation_service.evaluate_navigation(lat1, lon1, lat2, lon2, arrival_radius_m=10.0)
    assert nav_eval["has_arrived"] is False
    assert nav_eval["navigation_status"] == "NAVIGATING"

    # Close distance -> arrived
    arrived_eval = navigation_service.evaluate_navigation(lat2, lon2, lat2, lon2, arrival_radius_m=10.0)
    assert arrived_eval["has_arrived"] is True
    assert arrived_eval["navigation_status"] == "ARRIVED"

def test_neo6m_gps_nmea_parser():
    """Test NEO-6M NMEA sentence parsing."""
    provider = Neo6mGPSProvider(port="COM_TEST")
    gga = "$GPGGA,123519,3137.4400,N,07452.3380,E,1,08,0.9,218.5,M,46.9,M,,*47"
    provider._parse_nmea_sentence(gga)
    assert abs(provider.get_latitude() - 31.6240) < 0.001
    assert abs(provider.get_longitude() - 74.8723) < 0.001
    assert provider.get_satellites() == 8
    assert provider.get_altitude() == 218.5
    assert provider.get_fix_status() == "3D FIX"

def test_simulated_gps_telemetry():
    """Test Simulated GPS provider."""
    gps_manager.set_mode("SIMULATION")
    telem = gps_manager.get_telemetry()
    assert telem["source"] == "SIMULATION"
    assert telem["is_valid"] is True
    assert telem["satellites"] >= 4

def test_security_incident_creation_and_duplicate_suppression():
    """Test incident creation on unauthorized detection and duplicate suppression."""
    inc1 = incident_service.process_unauthorized_detection(
        camera_id="CAM_01",
        zone_id="ZONE_B",
        track_id=1,
        identity="UNKNOWN",
        confidence=0.92,
        authorization="UNAUTHORIZED"
    )
    assert inc1 is not None
    assert inc1["incident_id"].startswith("INC-")
    assert inc1["camera_id"] == "CAM_01"
    assert inc1["zone_id"] == "ZONE_B"

    # Repeated frame within cooldown should return existing incident
    inc2 = incident_service.process_unauthorized_detection(
        camera_id="CAM_01",
        zone_id="ZONE_B",
        track_id=1,
        identity="UNKNOWN",
        confidence=0.93,
        authorization="UNAUTHORIZED"
    )
    assert inc2 is not None
    assert inc2["incident_id"] == inc1["incident_id"]

def test_battery_failsafe_rule_and_dispatch_block():
    """Test battery <= 20% overrides mission and triggers Return to Home."""
    drone_manager.sim_provider.set_battery(19.0)
    telem = drone_manager.get_telemetry()
    assert telem["battery_percent"] == 19.0
    assert telem["is_low_battery"] is True

    # Dispatch must be refused
    with pytest.raises(ValueError, match="below safety minimum"):
        drone_manager.dispatch(31.6262, 74.8748, "ZONE_B", "INC-TEST-BAT")

    # Reset battery for remaining tests
    drone_manager.sim_provider.set_battery(95.0)

def test_drone_flight_state_machine_and_arrival():
    """Test complete drone flight state cycle."""
    drone_manager.sim_provider.set_battery(95.0)
    drone_manager.return_home()
    drone_manager.sim_provider.state = DroneFlightState.STANDBY

    # Dispatch to target
    res = drone_manager.dispatch(31.6262, 74.8748, "ZONE_B", "INC-099")
    assert drone_manager.get_telemetry()["state"] == "DISPATCHED"

    # Step simulation
    drone_manager.sim_provider._tick_flight_dynamics()
    assert drone_manager.get_telemetry()["state"] in ("DISPATCHED", "NAVIGATING")

    # Simulate arrival
    drone_manager.sim_provider.current_lat = 31.6262
    drone_manager.sim_provider.current_lon = 74.8748
    drone_manager.sim_provider._tick_flight_dynamics()
    assert drone_manager.get_telemetry()["state"] in ("ARRIVED", "AERIAL_SCAN")

    # Start scan & verification
    drone_manager.start_scan()
    assert drone_manager.get_telemetry()["state"] == "AERIAL_SCAN"

    # Return home
    drone_manager.return_home()
    assert drone_manager.get_telemetry()["state"] == "RETURNING"

def test_single_pir_sensor_service():
    """Test single PIR-001 sensor motion trigger and mode."""
    res = pir_service.trigger_motion()
    assert res["sensor_id"] == "PIR-001"
    assert res["status"] == "MOTION_DETECTED"
    status = pir_service.get_status()
    assert status["is_active"] is True
    assert status["trigger_count"] >= 1

def test_incident_api_routes():
    """Test incident REST endpoints."""
    res = client.post("/api/incidents/trigger", json={
        "camera_id": "CAM_01",
        "zone_id": "ZONE_B",
        "identity": "UNKNOWN",
        "confidence": 0.94,
        "authorization": "UNAUTHORIZED"
    })
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "SUCCESS"
    inc_id = data["incident"]["incident_id"]

    # Active incident
    active_res = client.get("/api/incidents/active")
    assert active_res.status_code == 200
    assert active_res.json()["active_incident"] is not None

    # Resolve incident
    res_resolve = client.post(f"/api/incidents/{inc_id}/resolve", json={"operator": "Test Operator"})
    assert res_resolve.status_code == 200
    assert res_resolve.json()["status"] == "RESOLVED"

def test_identity_api_routes():
    """Test identity REST endpoints."""
    # List persons
    res = client.get("/api/identity/persons")
    assert res.status_code == 200
    assert res.json()["count"] >= 1

    # Simulate identity
    sim_res = client.post("/api/identity/simulate", json={
        "camera_id": "CAM_01",
        "identity": "Keerthi",
        "confidence": 0.97,
        "authorization": "AUTHORIZED",
        "duration": 10.0
    })
    assert sim_res.status_code == 200
    assert sim_res.json()["result"]["identity"] == "Keerthi"

    # Latest identity for camera
    latest_res = client.get("/api/identity/latest/CAM_01")
    assert latest_res.status_code == 200
    assert latest_res.json()["identity"] == "Keerthi"

    # Clear simulation
    client.post("/api/identity/simulate/clear")
