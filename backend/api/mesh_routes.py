"""
SENTINEL-AI: Tactical Mesh Multi-Node REST Routes
Exposes Mesh Topology, Peer Node Metrics, and Evaluator Failover Simulation.
"""

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional

from backend.network.mesh_manager import tactical_mesh_manager

router = APIRouter(prefix="/api/mesh", tags=["Tactical Mesh Multi-Node Network"])

class FailoverRequest(BaseModel):
    node_id: str = Field(default="NODE_02_BRAVO", description="Target mesh node ID")
    outage_cause: str = Field(default="Physical Line Break / Power Interruption", description="Simulated root cause")

@router.get("/topology")
def get_mesh_topology() -> Dict[str, Any]:
    """Returns current multi-node border sentry topology, link states, and failover status."""
    return tactical_mesh_manager.get_topology()

@router.post("/simulate-failover")
async def simulate_node_failover(req: Optional[FailoverRequest] = None) -> Dict[str, Any]:
    """
    Simulates node dropout or re-connection, triggering autonomous routing re-election.
    """
    node_id = req.node_id if req else "NODE_02_BRAVO"
    outage_cause = req.outage_cause if req else "Physical Line Break / Power Interruption"
    return await tactical_mesh_manager.simulate_node_failover(node_id, outage_cause)
