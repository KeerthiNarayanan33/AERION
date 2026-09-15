"""
SENTINEL-AI: Tactical Mesh Multi-Node Network & Autonomous Failover Engine
Sections 49 & 60: Distributed Border Sentry Chain, Peer Heartbeats, and Relay Failover.

Models a resilient multi-node border mesh consisting of FOB Alpha, Ridge Outpost Bravo,
and Riverbed Sentry Charlie. Handles peer link dropouts, autonomous route re-election,
and decentralized event replication.
"""

import asyncio
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict

from backend.logger import logger
from backend.websocket.manager import ws_manager

@dataclass
class MeshNode:
    node_id: str
    node_name: str
    sector_covered: str
    role: str               # "LEADER", "RELAY", "SENTRY"
    status: str             # "ACTIVE", "DEGRADED", "OFFLINE"
    ip_address: str
    link_rssi_dbm: float    # Received Signal Strength Indication (-30 to -90 dBm)
    ping_latency_ms: float  # Inter-node ping latency
    packet_loss_pct: float  # Packet drop rate
    last_heartbeat: str
    failover_active: bool = False
    failover_route: Optional[str] = None
    replicated_events_count: int = 0

class TacticalMeshManager:
    """
    Manages border sentry peer nodes, dynamic routing topologies,
    and simulated link dropouts with autonomous failover.
    """
    def __init__(self):
        now = datetime.now(timezone.utc).isoformat()
        self.nodes: Dict[str, MeshNode] = {
            "NODE_01_ALPHA": MeshNode(
                node_id="NODE_01_ALPHA",
                node_name="FOB Alpha Command Hub (BP-744)",
                sector_covered="SECTOR_CENTRAL (ZONE_A, B, C)",
                role="LEADER",
                status="ACTIVE",
                ip_address="10.42.0.1",
                link_rssi_dbm=-48.0,
                ping_latency_ms=1.2,
                packet_loss_pct=0.0,
                last_heartbeat=now,
                failover_active=False
            ),
            "NODE_02_BRAVO": MeshNode(
                node_id="NODE_02_BRAVO",
                node_name="Ridge Outpost Bravo (BP-745)",
                sector_covered="SECTOR_NORTH_RIDGE",
                role="RELAY",
                status="ACTIVE",
                ip_address="10.42.0.2",
                link_rssi_dbm=-62.5,
                ping_latency_ms=14.8,
                packet_loss_pct=1.1,
                last_heartbeat=now,
                failover_active=False
            ),
            "NODE_03_CHARLIE": MeshNode(
                node_id="NODE_03_CHARLIE",
                node_name="Riverbed Sentry Charlie (BP-743)",
                sector_covered="SECTOR_SOUTH_RAVINE",
                role="RELAY",
                status="ACTIVE",
                ip_address="10.42.0.3",
                link_rssi_dbm=-68.2,
                ping_latency_ms=21.4,
                packet_loss_pct=2.3,
                last_heartbeat=now,
                failover_active=False
            )
        }
        self.failover_history: List[Dict[str, Any]] = []

    def get_topology(self) -> Dict[str, Any]:
        """Returns the full tactical mesh topology, links, and operational metrics."""
        node_list = [asdict(n) for n in self.nodes.values()]
        active_count = sum(1 for n in self.nodes.values() if n.status == "ACTIVE")
        mesh_health = "OPTIMAL" if active_count == 3 else ("DEGRADED" if active_count >= 2 else "CRITICAL")
        
        links = [
            {
                "from": "NODE_01_ALPHA",
                "to": "NODE_02_BRAVO",
                "protocol": "5GHz W-Mesh 802.11s",
                "bandwidth_mbps": 54.0 if self.nodes["NODE_02_BRAVO"].status == "ACTIVE" else 0.0,
                "status": "UP" if self.nodes["NODE_02_BRAVO"].status == "ACTIVE" else "DOWN",
                "rssi_dbm": self.nodes["NODE_02_BRAVO"].link_rssi_dbm
            },
            {
                "from": "NODE_01_ALPHA",
                "to": "NODE_03_CHARLIE",
                "protocol": "5GHz W-Mesh 802.11s",
                "bandwidth_mbps": 54.0 if self.nodes["NODE_03_CHARLIE"].status == "ACTIVE" else 0.0,
                "status": "UP" if self.nodes["NODE_03_CHARLIE"].status == "ACTIVE" else "DOWN",
                "rssi_dbm": self.nodes["NODE_03_CHARLIE"].link_rssi_dbm
            },
            {
                "from": "NODE_02_BRAVO",
                "to": "NODE_03_CHARLIE",
                "protocol": "Tactical UHF Mesh (915MHz)",
                "bandwidth_mbps": 19.2 / 1000.0, # 19.2 kbps
                "status": "STANDBY" if self.nodes["NODE_02_BRAVO"].status == "ACTIVE" else "REROUTE_ACTIVE",
                "rssi_dbm": -74.0
            }
        ]

        return {
            "mesh_id": "BORDER_MESH_WEST_SECTOR_07",
            "mesh_health": mesh_health,
            "leader_node": "NODE_01_ALPHA",
            "active_nodes_count": active_count,
            "total_nodes_count": len(self.nodes),
            "consensus_quorum": f"{active_count}/3",
            "nodes": node_list,
            "links": links,
            "failover_history": self.failover_history[-10:]
        }

    async def simulate_node_failover(
        self, node_id: str = "NODE_02_BRAVO", outage_cause: str = "Fiber Cut / Physical Line Break"
    ) -> Dict[str, Any]:
        """
        Simulates an edge node outage, triggering autonomous mesh re-routing
        and decentralized distributed event log replication.
        """
        if node_id not in self.nodes:
            return {"status": "ERROR", "message": f"Node {node_id} not found"}

        node = self.nodes[node_id]
        now = datetime.now(timezone.utc).isoformat()
        
        # Toggle state
        if node.status == "ACTIVE":
            node.status = "OFFLINE"
            node.link_rssi_dbm = -99.0
            node.packet_loss_pct = 100.0
            node.failover_active = True
            node.failover_route = "NODE_03_CHARLIE -> TACTICAL_UHF -> NODE_01_ALPHA"
            node.replicated_events_count += 4
            
            action_desc = f"Node {node_id} offline. Traffic rerouted via {node.failover_route}."
            event_record = {
                "timestamp": now,
                "event": "NODE_FAILOVER_TRIGGERED",
                "node_id": node_id,
                "outage_cause": outage_cause,
                "action": action_desc,
                "replicated_events": 4
            }
            self.failover_history.append(event_record)
            
            logger.warning(f"TACTICAL MESH: {action_desc}")
            
            await ws_manager.broadcast({
                "type": "TACTICAL_MESH_FAILOVER",
                "node_id": node_id,
                "node_name": node.node_name,
                "status": "OFFLINE",
                "outage_cause": outage_cause,
                "failover_route": node.failover_route,
                "timestamp": now
            })
            
            return {
                "status": "FAILOVER_ACTIVATED",
                "node_id": node_id,
                "new_status": "OFFLINE",
                "outage_cause": outage_cause,
                "failover_route": node.failover_route,
                "action": action_desc
            }
        else:
            # Reconnect node
            node.status = "ACTIVE"
            node.link_rssi_dbm = -62.5
            node.packet_loss_pct = 1.1
            node.failover_active = False
            node.failover_route = None
            node.last_heartbeat = now
            
            action_desc = f"Node {node_id} restored to ACTIVE. Primary 5GHz mesh links re-established."
            event_record = {
                "timestamp": now,
                "event": "NODE_RECONNECTED",
                "node_id": node_id,
                "action": action_desc
            }
            self.failover_history.append(event_record)
            
            logger.info(f"TACTICAL MESH: {action_desc}")
            
            await ws_manager.broadcast({
                "type": "TACTICAL_MESH_RECONNECTED",
                "node_id": node_id,
                "status": "ACTIVE",
                "timestamp": now
            })
            
            return {
                "status": "NODE_RESTORED",
                "node_id": node_id,
                "new_status": "ACTIVE",
                "action": action_desc
            }

    async def restore_all_nodes(self) -> Dict[str, Any]:
        """Restores all mesh nodes to default active operating state."""
        now = datetime.now(timezone.utc).isoformat()
        for node in self.nodes.values():
            node.status = "ACTIVE"
            node.link_rssi_dbm = -62.5
            node.packet_loss_pct = 1.1
            node.failover_active = False
            node.failover_route = None
            node.last_heartbeat = now
        return {"status": "ALL_NODES_RESTORED"}

# Global singleton
tactical_mesh_manager = TacticalMeshManager()
