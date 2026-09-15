import time
import uuid
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone

from backend.events.event_types import (
    EventSeverity, EventStatus, ActiveEventRecord
)
from backend.zones.state_machine import IntrusionState
from backend.logger import logger

SEVERITY_ORDER = {
    EventSeverity.LOW: 1,
    EventSeverity.MEDIUM: 2,
    EventSeverity.HIGH: 3,
    EventSeverity.CRITICAL: 4
}

class EventDeduplicator:
    """
    Intelligent spatial and temporal deduplicator for border intrusion events.
    Maintains continuous lifecycle of ongoing intrusions, suppressing duplicate alerts
    caused by sensor noise, edge-of-boundary dithering, or continuous video tracking.
    """

    def __init__(self, hysteresis_seconds: float = 4.0, update_throttle_seconds: float = 0.8):
        self.hysteresis_seconds = hysteresis_seconds
        self.update_throttle_seconds = update_throttle_seconds
        self._active_events: Dict[str, ActiveEventRecord] = {}
        self._last_broadcast_time: Dict[str, float] = {}

    def compute_severity(
        self,
        intrusion_state: IntrusionState,
        zone_type: str = "NORMAL",
        is_approaching_border: bool = False,
        loitering_duration: float = 0.0
    ) -> EventSeverity:
        """
        Rule-based severity matrix:
        - CRITICAL: Intruder entered RESTRICTED zone or ACTIVE_EVENT underway
        - HIGH: Target in WARNING zone moving towards border or long loitering
        - MEDIUM: Target APPROACHING or loitering in patrol zone
        - LOW: Normal or peripheral movement
        """
        if intrusion_state in (IntrusionState.RESTRICTED_ENTRY, IntrusionState.ACTIVE_EVENT):
            return EventSeverity.CRITICAL
        elif zone_type == "RESTRICTED":
            return EventSeverity.CRITICAL
        elif intrusion_state == IntrusionState.WARNING:
            if is_approaching_border or loitering_duration > 8.0:
                return EventSeverity.HIGH
            return EventSeverity.MEDIUM
        elif intrusion_state == IntrusionState.APPROACHING:
            return EventSeverity.MEDIUM
        return EventSeverity.LOW

    def process_target_observation(
        self,
        target_id: str,
        object_class: str,
        intrusion_state: IntrusionState,
        zone_id: str,
        zone_name: str,
        zone_type: str = "NORMAL",
        coordinates: Optional[Tuple[float, float]] = None,
        confidence: float = 0.0,
        camera_id: Optional[str] = None,
        radar_id: Optional[str] = None,
        is_approaching_border: bool = False,
        is_simulated: bool = False,
        timestamp: Optional[float] = None
    ) -> Tuple[str, Optional[ActiveEventRecord]]:
        """
        Processes a single target observation.
        Returns:
            (action, record) where action in ("CREATED", "UPDATED", "ESCALATED", "IGNORED")
        """
        now = timestamp if timestamp is not None else time.time()
        severity = self.compute_severity(
            intrusion_state=intrusion_state,
            zone_type=zone_type,
            is_approaching_border=is_approaching_border
        )

        existing = self._active_events.get(target_id)

        # 1. If target is in NORMAL state and no active event exists -> IGNORE
        if intrusion_state == IntrusionState.NORMAL and severity == EventSeverity.LOW and not existing:
            return "IGNORED", None

        # 2. If no active event exists but severity >= MEDIUM (or state != NORMAL) -> CREATE NEW ACTIVE EVENT
        if existing is None:
            if severity in (EventSeverity.MEDIUM, EventSeverity.HIGH, EventSeverity.CRITICAL):
                event_id = f"EVT_{datetime.fromtimestamp(now, tz=timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6].upper()}"
                desc = f"{severity.value} intrusion alert: {object_class} entered {zone_name} [{intrusion_state.value}]"
                
                record = ActiveEventRecord(
                    event_id=event_id,
                    target_id=target_id,
                    object_class=object_class,
                    primary_zone_id=zone_id,
                    primary_zone_name=zone_name,
                    camera_id=camera_id,
                    radar_id=radar_id,
                    initial_severity=severity,
                    peak_severity=severity,
                    status=EventStatus.ACTIVE,
                    start_time=now,
                    last_updated_time=now,
                    last_detection_time=now,
                    confidence=confidence,
                    trajectory=[coordinates] if coordinates else [],
                    update_count=1,
                    is_simulated=is_simulated,
                    description=desc
                )
                self._active_events[target_id] = record
                self._last_broadcast_time[target_id] = now
                logger.info(f"[EVENT ENGINE] Created new active event: {event_id} ({severity.value}) for target {target_id}")
                return "CREATED", record
            return "IGNORED", None

        # 3. Existing active event is present -> UPDATE CONTINUOUS LIFECYCLE
        existing.last_detection_time = now
        existing.last_updated_time = now
        existing.update_count += 1
        existing.confidence = max(existing.confidence, confidence)

        if coordinates:
            # Append to trajectory, limiting to recent 200 points for memory bounds
            existing.trajectory.append(coordinates)
            if len(existing.trajectory) > 200:
                existing.trajectory = existing.trajectory[-200:]

        action = "UPDATED"
        # Check for severity escalation
        if SEVERITY_ORDER.get(severity, 1) > SEVERITY_ORDER.get(existing.peak_severity, 1):
            existing.peak_severity = severity
            existing.primary_zone_id = zone_id
            existing.primary_zone_name = zone_name
            existing.description = f"ESCALATED to {severity.value}: {object_class} progressed to {zone_name} [{intrusion_state.value}]"
            action = "ESCALATED"
            logger.warning(f"[EVENT ENGINE] Escalated event {existing.event_id} to {severity.value} for target {target_id}")

        return action, existing

    def prune_stale_events(self, current_time: Optional[float] = None) -> List[ActiveEventRecord]:
        """
        Finds active events that have not received target observations for > hysteresis_seconds.
        Transitions them to RESOLVED and removes them from active tracking.
        """
        now = current_time if current_time is not None else time.time()
        resolved_list: List[ActiveEventRecord] = []
        stale_keys: List[str] = []

        for target_id, record in self._active_events.items():
            if (now - record.last_detection_time) > self.hysteresis_seconds:
                record.status = EventStatus.RESOLVED
                record.resolved_at = now
                resolved_list.append(record)
                stale_keys.append(target_id)
                logger.info(f"[EVENT ENGINE] Event {record.event_id} for target {target_id} RESOLVED after {record.duration_seconds}s")

        for key in stale_keys:
            self._active_events.pop(key, None)
            self._last_broadcast_time.pop(key, None)

        return resolved_list

    def acknowledge_event(
        self,
        event_id: str,
        operator_name: str = "Operator",
        notes: Optional[str] = None
    ) -> Optional[ActiveEventRecord]:
        """Marks an ongoing active event as acknowledged by a human security operator."""
        for record in self._active_events.values():
            if record.event_id == event_id:
                record.status = EventStatus.ACKNOWLEDGED
                record.acknowledged_by = operator_name
                record.acknowledged_at = time.time()
                record.operator_notes = notes
                return record
        return None

    def resolve_event_manually(
        self,
        event_id: str,
        operator_name: str = "Operator"
    ) -> Optional[ActiveEventRecord]:
        """Manually resolves an ongoing active event."""
        target_id_to_remove = None
        found_record = None

        for target_id, record in self._active_events.items():
            if record.event_id == event_id:
                record.status = EventStatus.RESOLVED
                record.resolved_at = time.time()
                record.operator_notes = f"Manually resolved by {operator_name}"
                found_record = record
                target_id_to_remove = target_id
                break

        if target_id_to_remove:
            self._active_events.pop(target_id_to_remove, None)
            self._last_broadcast_time.pop(target_id_to_remove, None)

        return found_record

    def get_active_events(self) -> List[ActiveEventRecord]:
        """Returns all currently active ongoing intrusion events."""
        return list(self._active_events.values())

    def get_active_event(self, event_id: str) -> Optional[ActiveEventRecord]:
        """Retrieves a single active event by event_id."""
        for record in self._active_events.values():
            if record.event_id == event_id:
                return record
        return None
