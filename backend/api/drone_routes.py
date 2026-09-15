from datetime import datetime, timezone
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from backend.database.database import get_db
from backend.database.models import UAVStatusModel, EventModel
from backend.uav.drone_provider import drone_manager, DroneFlightState
from backend.geospatial.gps_service import gps_manager
from backend.websocket.manager import ws_manager

router = APIRouter(prefix="/api/uav", tags=["UAV / Drone"])
drone_alias_router = APIRouter(prefix="/api/drone", tags=["UAV / Drone"])

class DispatchPayload(BaseModel):
    zone_id: str = "ZONE_B"
    incident_id: Optional[str] = "INC-001"
    target_lat: Optional[float] = None
    target_lon: Optional[float] = None
    reason: Optional[str] = "Unauthorized intrusion verification"

class BatterySetPayload(BaseModel):
    battery_percent: float = 19.0

class AbortPayload(BaseModel):
    reason: str = "Operator recall / mission abort"

class DroneModePayload(BaseModel):
    mode: str = "SIMULATION"

@router.get("/status")
@router.get("/telemetry")
@drone_alias_router.get("/status")
@drone_alias_router.get("/telemetry")
def get_uav_telemetry():
    """Returns real-time DRONE-001 telemetry, GPS fix, battery, and flight state."""
    return drone_manager.get_telemetry()

@router.get("/gps-status")
def get_uav_gps_status():
    """Returns GPS sensor status and fix quality (NEO-6M or Simulation)."""
    return gps_manager.get_telemetry()

class RotorSpinPayload(BaseModel):
    duration_sec: float = 3.0
    throttle: int = 15

@router.post("/verify-rotor")
@router.post("/spin-blades")
def verify_uav_rotors(payload: Optional[RotorSpinPayload] = None):
    """
    Spins drone blade rotors at lowest speed for physical verification without flying.
    Sends arm/unlock at low throttle on UDP 192.168.1.1:7099.
    """
    dur = payload.duration_sec if payload else 3.0
    thr = payload.throttle if payload else 15
    res = drone_manager.spin_blades_idle(duration_sec=dur, throttle=thr)
    return {
        "status": "SUCCESS",
        "action": "ROTOR_BLADE_VERIFICATION",
        "duration_sec": dur,
        "throttle": thr,
        "message": "Drone blade rotors spun at minimum idle speed. No flight lift generated.",
        "telemetry": drone_manager.get_telemetry()
    }

@router.post("/dispatch")
@router.post("/verification-request")
async def dispatch_uav_mission(req: DispatchPayload, db: Session = Depends(get_db)):
    """Dispatches autonomous DRONE-001 to target zone coordinates and triggers rotor verification."""
    from backend.events.incident_service import incident_service

    # Trigger rotor blade idle spin test on physical drone
    try:
        drone_manager.spin_blades_idle(duration_sec=3.0, throttle=15)
    except Exception as rotor_err:
        pass

    target_lat = req.target_lat
    target_lon = req.target_lon

    if not target_lat or not target_lon:
        target_lat, target_lon = incident_service.resolve_zone_coordinates(req.zone_id)

    try:
        telemetry = drone_manager.dispatch(
            target_lat=target_lat,
            target_lon=target_lon,
            zone_id=req.zone_id,
            incident_id=req.incident_id or "INC-001"
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    now = datetime.now(timezone.utc)
    evt_id = f"EVT_UAV_{now.strftime('%Y%m%d_%H%M%S')}"
    event = EventModel(
        id=evt_id,
        event_type="UAV_DISPATCHED",
        severity="INFO",
        zone_id=req.zone_id,
        status="ACTIVE",
        start_time=now,
        updated_time=now,
        description=f"DRONE-001 verification dispatched to {req.zone_id} for {req.incident_id}. Reason: {req.reason}"
    )
    db.add(event)
    db.commit()

    raw_state = telemetry.get("state", "DISPATCHED")
    uav_state = raw_state if raw_state.startswith("UAV_") else f"UAV_{raw_state}"

    return {
        "message": f"DRONE-001 verification dispatched to {req.zone_id} (Rotor blade test active)",
        "uav_state": uav_state,
        "telemetry": telemetry,
        "event_id": evt_id
    }

@router.post("/return-home")
@router.post("/abort")
async def return_uav_home(req: Optional[AbortPayload] = None):
    """Commands DRONE-001 to abort mission and return to charging base station."""
    reason = req.reason if req else "Operator command"
    telemetry = drone_manager.return_home(reason=reason)
    raw_state = telemetry.get("state", "RETURNING")
    uav_state = raw_state if raw_state.startswith("UAV_") else f"UAV_{raw_state}"
    return {
        "message": "DRONE-001 Commencing Return-to-Home (RTH).",
        "uav_state": uav_state,
        "telemetry": telemetry
    }

@router.post("/start-scan")
def start_aerial_scan():
    """Commands DRONE-001 to begin aerial optical search in current sector."""
    telemetry = drone_manager.start_scan()
    return {
        "message": "Aerial verification scan initiated.",
        "telemetry": telemetry
    }

@router.post("/set-battery")
def set_uav_battery(payload: BatterySetPayload):
    """Demo simulation hook: sets battery percentage (e.g. 19% triggers immediate RTH failsafe)."""
    drone_manager.sim_provider.set_battery(payload.battery_percent)
    return {
        "message": f"Battery set to {payload.battery_percent}%",
        "telemetry": drone_manager.get_telemetry()
    }

class StepSimPayload(BaseModel):
    action: str = "arrive"
    target_lat: Optional[float] = None
    target_lon: Optional[float] = None

@router.post("/step-sim")
def step_simulation_hook(payload: StepSimPayload):
    """Simulates immediate arrival at target coordinates for demonstrations."""
    if payload.action == "arrive":
        t_lat = payload.target_lat or drone_manager.sim_provider.target_lat or 31.6262
        t_lon = payload.target_lon or drone_manager.sim_provider.target_lon or 74.8748
        drone_manager.sim_provider.current_lat = t_lat
        drone_manager.sim_provider.current_lon = t_lon
        drone_manager.sim_provider.state = DroneFlightState.ARRIVED
        drone_manager.sim_provider.start_scan()
    return {
        "status": "SUCCESS",
        "telemetry": drone_manager.get_telemetry()
    }

@router.post("/mode")
def set_uav_mode(payload: DroneModePayload):
    """Switches drone operational mode between SIMULATION and LIVE."""
    drone_manager.set_mode(payload.mode)
    gps_manager.set_mode(payload.mode)
    return {
        "status": "SUCCESS",
        "mode": drone_manager.mode,
        "telemetry": drone_manager.get_telemetry()
    }

class MotorControlPayload(BaseModel):
    throttle: int = 15
    roll: int = 128
    pitch: int = 128
    yaw: int = 128
    flags: int = 0

@router.post("/motor-control")
@router.post("/sticks")
def control_uav_motors(payload: MotorControlPayload):
    """Direct manual motor & flight stick control over UDP."""
    from backend.uav.drone_comm import drone_core
    drone_core.motor_control(
        throttle=payload.throttle,
        roll=payload.roll,
        pitch=payload.pitch,
        yaw=payload.yaw,
        flags=payload.flags
    )
    return {
        "status": "SUCCESS",
        "action": "MOTOR_CONTROL",
        "throttle": payload.throttle,
        "telemetry": drone_manager.get_telemetry()
    }

@router.post("/takeoff")
def trigger_uav_takeoff():
    """Triggers auto-takeoff / motor arming pulse."""
    from backend.uav.drone_comm import drone_core
    drone_core.trigger_takeoff()
    return {
        "status": "SUCCESS",
        "action": "TAKEOFF",
        "telemetry": drone_manager.get_telemetry()
    }

@router.post("/land")
def trigger_uav_land():
    """Triggers safe auto-landing sequence."""
    from backend.uav.drone_comm import drone_core
    drone_core.trigger_safe_land()
    return {
        "status": "SUCCESS",
        "action": "SAFE_LAND",
        "telemetry": drone_manager.get_telemetry()
    }

@router.post("/emergency-stop")
def trigger_uav_emergency_stop():
    """Triggers immediate rotor cutoff."""
    from backend.uav.drone_comm import drone_core
    drone_core.trigger_emergency_stop()
    return {
        "status": "SUCCESS",
        "action": "EMERGENCY_STOP",
        "telemetry": drone_manager.get_telemetry()
    }
