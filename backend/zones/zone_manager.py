import json
import time
import threading
from typing import Dict, List, Optional, Tuple, Any

from backend.database.database import get_db_context
from backend.database.models import ZoneModel
from backend.zones.state_machine import (
    IntrusionState,
    ZoneInfo,
    StateTransitionRecord,
    TargetStateMachine
)
from backend.logger import logger
from backend.websocket.manager import ws_manager

class ZoneManager:
    """
    Central Manager for Surveillance Zones and Real-Time Intrusion State Machines.
    Loads and caches active polygonal zones, manages per-target state machines,
    and broadcasts state transition events to the Command Center dashboard.
    """
    _instance: Optional['ZoneManager'] = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(ZoneManager, cls).__new__(cls)
                cls._instance._zones: Dict[str, ZoneInfo] = {}
                cls._instance._state_machines: Dict[str, TargetStateMachine] = {}
                cls._instance._last_seen: Dict[str, float] = {}
                cls._instance._initialized = False
            return cls._instance

    def initialize(self) -> None:
        """Initializes and loads zones from SQLite."""
        with self._lock:
            if self._initialized:
                return
            logger.info("Initializing ZoneManager...")
            self.refresh_zones()
            self._initialized = True
            logger.info(f"ZoneManager initialized with {len(self._zones)} zones.")

    def refresh_zones(self) -> None:
        """Reloads zone polygons from database."""
        try:
            with get_db_context() as db:
                db_zones = db.query(ZoneModel).all()
                new_zones = {}
                for z in db_zones:
                    try:
                        coords = json.loads(z.coordinates_json)
                        new_zones[z.id] = ZoneInfo(
                            id=z.id,
                            name=z.name,
                            zone_type=z.zone_type,
                            coordinates=[(float(p[0]), float(p[1])) for p in coords],
                            color=z.color or "#00e676"
                        )
                    except Exception as e:
                        logger.error(f"Error parsing coordinates for zone {z.id}: {e}")

                self._zones = new_zones
                logger.info(f"Reloaded {len(self._zones)} zones into memory.")
        except Exception as e:
            logger.error(f"Failed to refresh zones from database: {e}")

    def get_zones(self) -> List[ZoneInfo]:
        """Returns all currently cached zones."""
        return list(self._zones.values())

    def get_zone(self, zone_id: str) -> Optional[ZoneInfo]:
        """Retrieves a specific zone by ID."""
        return self._zones.get(zone_id)

    def evaluate_point(
        self,
        point: Tuple[float, float],
        velocity: Tuple[float, float] = (0.0, 0.0),
        object_id: str = "TARGET_01",
        object_class: str = "person",
        timestamp: Optional[float] = None
    ) -> Tuple[IntrusionState, Optional[StateTransitionRecord]]:
        """
        Evaluates a 2D point against all defined surveillance zones,
        updating the object's intrusion state machine.
        """
        ts = timestamp if timestamp is not None else time.time()
        self._last_seen[object_id] = ts

        if object_id not in self._state_machines:
            self._state_machines[object_id] = TargetStateMachine(
                object_id=object_id,
                object_class=object_class
            )

        if not self._initialized or not self._zones:
            self.initialize()

        sm = self._state_machines[object_id]
        zones_list = list(self._zones.values())
        new_state, record = sm.evaluate(point, velocity, zones_list, timestamp=ts)

        # If state transitioned, broadcast real-time alert over WebSocket
        if record is not None:
            logger.warning(f"[ZONE ALERT] {record.message}")
            ws_manager.broadcast_sync({
                "type": "ZONE_INTRUSION_STATE",
                "object_id": record.object_id,
                "previous_state": record.previous_state.value,
                "current_state": record.current_state.value,
                "zone_id": record.zone_id,
                "zone_name": record.zone_name,
                "is_critical": record.current_state.value in ("RESTRICTED_ENTRY", "ACTIVE_EVENT"),
                "timestamp": record.timestamp,
                "message": record.message
            })

        return new_state, record

    def evaluate_camera_track(
        self,
        track_id: int,
        center_px: Tuple[int, int],
        frame_shape: Tuple[int, int],
        velocity_px: Tuple[float, float],
        object_class: str,
        camera_id: str = "CAM_01",
        is_authorized: bool = False,
        identity: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Evaluates a camera pixel coordinate (cx, cy) normalized to [0, 1]
        and updates the object's intrusion state. Suppresses alarm escalations
        if the subject is an authorized person.
        """
        h, w = frame_shape
        norm_x = min(1.0, max(0.0, center_px[0] / max(1, w)))
        norm_y = min(1.0, max(0.0, center_px[1] / max(1, h)))
        norm_vx = velocity_px[0] / max(1, w)
        norm_vy = velocity_px[1] / max(1, h)

        target_key = f"{camera_id}_TRK_{track_id}"
        state, record = self.evaluate_point(
            point=(norm_x, norm_y),
            velocity=(norm_vx, norm_vy),
            object_id=target_key,
            object_class=object_class
        )

        sm = self._state_machines[target_key]

        # If camera has a dedicated restricted zone assignment (e.g. CAM_02 Smartphone Camera monitoring ZONE_C)
        if not is_authorized and state == IntrusionState.NORMAL and camera_id == "CAM_02" and "ZONE_C" in self._zones:
            rz = self._zones["ZONE_C"]
            state = IntrusionState.RESTRICTED_ENTRY
            sm.current_state = state
            sm.current_zone_id = rz.id
            sm.current_zone_name = rz.name
            logger.warning(f"[ZONE_MANAGER] Camera {camera_id} dedicated to {rz.name}: Target {target_key} flagged as RESTRICTED_ENTRY")

        # Suppress critical alarm escalation for authorized persons in restricted zones
        if is_authorized:
            if state in (IntrusionState.RESTRICTED_ENTRY, IntrusionState.ACTIVE_EVENT):
                logger.info(f"[ZONE_MANAGER] Alarm suppressed for authorized person [{identity or target_key}] in restricted zone {sm.current_zone_name or sm.current_zone_id}")
                state = IntrusionState.NORMAL
                sm.current_state = state
            # Do not emit critical transition records for authorized individuals
            record = None

        # Feed into Event Engine for continuous deduplication and active alert tracking
        try:
            from backend.events.event_engine import event_engine
            current_zone = self._zones.get(sm.current_zone_id) if sm.current_zone_id else None
            zone_type = current_zone.zone_type if current_zone else ("RESTRICTED" if state == IntrusionState.RESTRICTED_ENTRY else "NORMAL")
            event_engine.process_target_state(
                target_id=target_key,
                object_class=object_class,
                intrusion_state=state,
                zone_id=sm.current_zone_id or "ZONE_UNASSIGNED",
                zone_name=sm.current_zone_name or "Perimeter",
                zone_type=zone_type,
                coordinates=(norm_x, norm_y),
                confidence=1.0,
                camera_id=camera_id,
                is_authorized=is_authorized,
                identity=identity,
                timestamp=time.time()
            )
        except Exception as e:
            logger.debug(f"[ZONE_MANAGER] Error forwarding to event engine: {e}")

        return {
            "state": state.value,
            "zone_id": sm.current_zone_id,
            "zone_name": sm.current_zone_name,
            "transition": record.model_dump() if record else None
        }

    def get_all_target_states(self) -> List[Dict[str, Any]]:
        """Returns current states of all actively tracked targets."""
        now = time.time()
        # Clean up targets unseen for > 30 seconds
        stale_keys = [k for k, last in self._last_seen.items() if now - last > 30.0]
        for k in stale_keys:
            self._state_machines.pop(k, None)
            self._last_seen.pop(k, None)

        results = []
        for obj_id, sm in self._state_machines.items():
            results.append({
                "object_id": sm.object_id,
                "object_class": sm.object_class,
                "current_state": sm.current_state.value,
                "zone_id": sm.current_zone_id,
                "zone_name": sm.current_zone_name,
                "last_transition_at": sm.last_transition_at,
                "history_count": len(sm.history)
            })
        return results

    def reset(self) -> None:
        """Clears all in-memory target state machines."""
        self._state_machines.clear()
        self._last_seen.clear()

zone_manager = ZoneManager()
