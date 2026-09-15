import time
from enum import Enum
from typing import Optional, Dict, Any, List, Tuple
from pydantic import BaseModel

from backend.zones.zone_logic import (
    is_point_in_polygon,
    distance_to_polygon,
    is_vector_approaching_polygon
)

class IntrusionState(str, Enum):
    NORMAL = "NORMAL"
    APPROACHING = "APPROACHING"
    WARNING = "WARNING"
    RESTRICTED_ENTRY = "RESTRICTED_ENTRY"
    ACTIVE_EVENT = "ACTIVE_EVENT"
    RESOLVED = "RESOLVED"

class ZoneInfo(BaseModel):
    id: str
    name: str
    zone_type: str  # NORMAL, WARNING, RESTRICTED
    coordinates: List[Tuple[float, float]]
    color: str

class StateTransitionRecord(BaseModel):
    object_id: str
    previous_state: IntrusionState
    current_state: IntrusionState
    zone_id: Optional[str]
    zone_name: Optional[str]
    timestamp: float
    message: str

class TargetStateMachine:
    """
    Maintains and tracks intrusion state transitions for a single tracked object
    (camera track or radar target) over its movement lifecycle.
    """
    def __init__(self, object_id: str, object_class: str = "person"):
        self.object_id = object_id
        self.object_class = object_class
        self.current_state = IntrusionState.NORMAL
        self.current_zone_id: Optional[str] = None
        self.current_zone_name: Optional[str] = None
        self.first_entered_at: Optional[float] = None
        self.last_transition_at = time.time()
        self.history: List[StateTransitionRecord] = []
        self.entry_frames_count = 0

    def evaluate(
        self,
        point: Tuple[float, float],
        velocity: Tuple[float, float],
        zones: List[ZoneInfo],
        timestamp: Optional[float] = None,
        approach_threshold: float = 0.08
    ) -> Tuple[IntrusionState, Optional[StateTransitionRecord]]:
        """
        Evaluates current position and velocity against all zones.
        Returns: (new_state, transition_record_if_changed)
        """
        ts = timestamp if timestamp is not None else time.time()
        prev_state = self.current_state
        new_state = IntrusionState.NORMAL
        target_zone: Optional[ZoneInfo] = None

        # 1. Evaluate Highest Priority: Check containment in RESTRICTED zones
        restricted_zones = [z for z in zones if z.zone_type.upper() == "RESTRICTED"]
        for rz in restricted_zones:
            if is_point_in_polygon(point, rz.coordinates):
                target_zone = rz
                if prev_state in (IntrusionState.RESTRICTED_ENTRY, IntrusionState.ACTIVE_EVENT):
                    new_state = IntrusionState.ACTIVE_EVENT
                else:
                    new_state = IntrusionState.RESTRICTED_ENTRY
                break

        # 2. Check containment in WARNING zones if not restricted
        if new_state == IntrusionState.NORMAL:
            warning_zones = [z for z in zones if z.zone_type.upper() == "WARNING"]
            for wz in warning_zones:
                if is_point_in_polygon(point, wz.coordinates):
                    target_zone = wz
                    new_state = IntrusionState.WARNING
                    break

        # 3. Check containment in NORMAL zones if not warning/restricted
        if new_state == IntrusionState.NORMAL:
            normal_zones = [z for z in zones if z.zone_type.upper() == "NORMAL"]
            for nz in normal_zones:
                if is_point_in_polygon(point, nz.coordinates):
                    target_zone = nz
                    new_state = IntrusionState.NORMAL
                    break

        # 4. If outside all zones, check if approaching any WARNING or RESTRICTED zone
        if target_zone is None:
            priority_zones = restricted_zones + [z for z in zones if z.zone_type.upper() == "WARNING"]
            for pz in priority_zones:
                if is_vector_approaching_polygon(point, velocity, pz.coordinates, threshold=approach_threshold):
                    target_zone = pz
                    new_state = IntrusionState.APPROACHING
                    break

        # 5. Check if resolving an active breach or warning
        if target_zone is None and new_state == IntrusionState.NORMAL:
            if prev_state in (
                IntrusionState.RESTRICTED_ENTRY,
                IntrusionState.ACTIVE_EVENT,
                IntrusionState.WARNING,
                IntrusionState.APPROACHING
            ):
                new_state = IntrusionState.RESOLVED

        # Handle State Transition
        transition_record: Optional[StateTransitionRecord] = None
        if new_state != prev_state:
            zone_id = target_zone.id if target_zone else None
            zone_name = target_zone.name if target_zone else None

            msg = f"Target {self.object_id} ({self.object_class}) transitioned: {prev_state.value} -> {new_state.value}"
            if zone_name:
                msg += f" in/near [{zone_name}]"

            transition_record = StateTransitionRecord(
                object_id=self.object_id,
                previous_state=prev_state,
                current_state=new_state,
                zone_id=zone_id,
                zone_name=zone_name,
                timestamp=ts,
                message=msg
            )
            self.history.append(transition_record)
            self.current_state = new_state
            self.current_zone_id = zone_id
            self.current_zone_name = zone_name
            self.last_transition_at = ts

            if new_state == IntrusionState.RESTRICTED_ENTRY:
                self.first_entered_at = ts
                self.entry_frames_count = 1
        elif new_state in (IntrusionState.RESTRICTED_ENTRY, IntrusionState.ACTIVE_EVENT):
            self.entry_frames_count += 1

        return new_state, transition_record
