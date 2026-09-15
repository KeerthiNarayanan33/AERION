"""
SENTINEL-AI: Tactical Playbook & Evaluator Mission Demonstration REST API
Sections 71, 73, 74, & 75: Staged Intrusion Drills & Evaluator Certification Routes.
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from typing import Dict, Any

from backend.events.tactical_playbooks import tactical_playbook_engine
from backend.analytics.evaluator_certificate import evaluator_certificate_generator

playbook_router = APIRouter(prefix="/api/playbooks", tags=["Tactical Playbooks & Evaluator Drills"])


@playbook_router.get("", summary="List all available demonstration playbooks")
async def list_playbooks() -> Dict[str, Any]:
    """Returns the full catalog of tactical demonstration playbooks."""
    catalog = tactical_playbook_engine.get_playbooks_catalog()
    return {
        "status": "SUCCESS",
        "total_playbooks": len(catalog),
        "playbooks": catalog
    }


@playbook_router.get("/certificate/json", summary="Get SIH 2026 Evaluator Defense Certificate (JSON)")
@playbook_router.get("/certificate", summary="Get SIH 2026 Evaluator Defense Certificate (JSON)")
async def get_evaluator_certificate() -> Dict[str, Any]:
    """Returns the official SIH 2026 Evaluator Defense Package and HMAC-SHA256 seal."""
    cert = evaluator_certificate_generator.generate_certificate_data()
    return {"status": "SUCCESS", "certificate": cert}


@playbook_router.get("/certificate/html", summary="Get printable SIH 2026 Evaluator Defense Certificate (HTML)")
async def get_evaluator_certificate_html() -> HTMLResponse:
    """Delivers the print-ready, high-impact HTML defense certificate."""
    html_content = evaluator_certificate_generator.generate_html_certificate()
    return HTMLResponse(content=html_content, status_code=200)


@playbook_router.post("/reset", summary="Restore all demonstration playbooks and sensors to clean baseline")
async def reset_playbooks() -> Dict[str, Any]:
    """Restores all sensors, drones, tracks, and actuators to default clean state."""
    res = await tactical_playbook_engine.reset_all()
    return {"status": "SUCCESS", "result": res}


@playbook_router.get("/{playbook_id}", summary="Get specific playbook details")
async def get_playbook(playbook_id: int) -> Dict[str, Any]:
    """Returns details and stage definitions for a specific playbook."""
    catalog = tactical_playbook_engine.get_playbooks_catalog()
    match = next((p for p in catalog if p["id"] == playbook_id), None)
    if not match:
        raise HTTPException(status_code=404, detail=f"Playbook {playbook_id} not found.")
    return {"status": "SUCCESS", "playbook": match}


@playbook_router.post("/{playbook_id}/execute", summary="Execute a complete tactical demonstration drill")
async def execute_playbook(playbook_id: int) -> Dict[str, Any]:
    """
    Executes a complete multi-stage tactical drill, triggering all corresponding
    subsystems, alerts, and live WebSocket stage updates.
    """
    if playbook_id < 1 or playbook_id > 8:
        raise HTTPException(status_code=400, detail=f"Invalid playbook ID: {playbook_id}. Must be 1 to 8.")
    result = await tactical_playbook_engine.execute_playbook(playbook_id)
    return {"status": "SUCCESS", "execution": result}


@playbook_router.post("/{playbook_id}/step", summary="Step forward one stage in a playbook")
async def step_playbook(playbook_id: int) -> Dict[str, Any]:
    """
    Advances a playbook one stage at a time, designed for live evaluator walkthroughs.
    """
    if playbook_id < 1 or playbook_id > 8:
        raise HTTPException(status_code=400, detail=f"Invalid playbook ID: {playbook_id}. Must be 1 to 8.")
    result = await tactical_playbook_engine.step_playbook(playbook_id)
    return {"status": "SUCCESS", "step": result}
