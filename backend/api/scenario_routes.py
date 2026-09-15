from fastapi import APIRouter, HTTPException
from backend.events.scenario_runner import scenario_runner

router = APIRouter(prefix="/api/system/scenario", tags=["SIH Demonstration Scenarios"])

@router.post("/1")
def trigger_scenario_1():
    """Triggers Demonstration Scenario 1: Normal Outer Patrol Surveillance."""
    return scenario_runner.run_scenario_1()

@router.post("/2")
def trigger_scenario_2():
    """Triggers Demonstration Scenario 2: Restricted Border Fence Intrusion."""
    return scenario_runner.run_scenario_2()

@router.post("/3")
def trigger_scenario_3():
    """Triggers Demonstration Scenario 3: Vehicle Intrusion & Automated ANPR Plate Scan."""
    return scenario_runner.run_scenario_3()

@router.post("/4")
def trigger_scenario_4():
    """Triggers Demonstration Scenario 4: Camera Failure & Surveillance Gap Anomaly."""
    return scenario_runner.run_scenario_4()

@router.post("/5")
def trigger_scenario_5():
    """Triggers Demonstration Scenario 5: Autonomous UAV Verification Mission."""
    return scenario_runner.run_scenario_5()

@router.post("/reset")
def trigger_scenario_reset():
    """Restores all sensors, camera states, and UAV to default operating baseline."""
    return scenario_runner.reset_system()
