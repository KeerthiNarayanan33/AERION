import time
import threading
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timezone

from backend.events.event_types import (
    EventSeverity, EventStatus, ActiveEventRecord
)
from backend.events.deduplicator import EventDeduplicator
from backend.zones.state_machine import IntrusionState
from backend.database.database import SessionLocal
from backend.database.models import EventModel
from backend.websocket.manager import ws_manager
from backend.logger import logger

class EventEngine:
    """
    Central border security event engine with continuous deduplication,
    priority scoring, real-time WebSocket distribution, and persistent SQLite storage.
    """

    def __init__(self, hysteresis_seconds: float = 4.0):
        self.deduplicator = EventDeduplicator(hysteresis_seconds=hysteresis_seconds)
        self._lock = threading.Lock()
        self._running = False
        self._sweep_thread: Optional[threading.Thread] = None
        self._last_broadcast_times: Dict[str, float] = {}

    def start(self) -> None:
        """Starts the periodic background sweep thread for stale event resolution."""
        with self._lock:
            if self._running:
                return
            self._running = True
            self._sweep_thread = threading.Thread(
                target=self._run_sweep_loop,
                daemon=True,
                name="EventEngineSweepThread"
            )
            self._sweep_thread.start()
            logger.info("EventEngine background sweeper started.")

    def stop(self) -> None:
        """Stops the event engine sweep thread."""
        with self._lock:
            self._running = False
        if self._sweep_thread and self._sweep_thread.is_alive():
            self._sweep_thread.join(timeout=2.0)
        logger.info("EventEngine stopped.")

    def _run_sweep_loop(self) -> None:
        """Periodic background loop that prunes stale events that departed or lost signal."""
        while self._running:
            try:
                with self._lock:
                    resolved = self.deduplicator.prune_stale_events()

                for record in resolved:
                    self._persist_event_to_db(record)
                    ws_manager.broadcast_sync({
                        "type": "EVENT_RESOLVED",
                        "event": record.to_dict()
                    })

            except Exception as e:
                logger.error(f"[EVENT ENGINE] Sweep loop error: {e}", exc_info=True)

            time.sleep(1.0)

    def process_target_state(
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
        is_authorized: bool = False,
        identity: Optional[str] = None,
        timestamp: Optional[float] = None
    ) -> Optional[ActiveEventRecord]:
        """
        Ingests a real-time target observation from ZoneManager or Camera/Radar sensors.
        Deduplicates against active ongoing events and broadcasts updates.
        Suppresses critical alarm broadcasts and evidence recording if the target is authorized.
        """
        now = timestamp if timestamp is not None else time.time()

        # If authorized person is observed, ensure any active event is gracefully resolved
        if is_authorized:
            with self._lock:
                active_ev = self.deduplicator.get_active_event(target_id)
                if active_ev:
                    active_ev.status = EventStatus.RESOLVED
                    active_ev.description = f"Cleared: Authorized personnel [{identity or 'Staff'}] in {zone_name}"
                    self.deduplicator._active_events.pop(target_id, None)
                    ws_manager.broadcast_sync({
                        "type": "EVENT_RESOLVED",
                        "event": active_ev.to_dict()
                    })
            return None

        with self._lock:
            action, record = self.deduplicator.process_target_observation(
                target_id=target_id,
                object_class=object_class,
                intrusion_state=intrusion_state,
                zone_id=zone_id,
                zone_name=zone_name,
                zone_type=zone_type,
                coordinates=coordinates,
                confidence=confidence,
                camera_id=camera_id,
                radar_id=radar_id,
                is_approaching_border=is_approaching_border,
                is_simulated=is_simulated,
                timestamp=now
            )

        if record is None or action == "IGNORED":
            return None

        # 1. New Event Created -> Persist to DB & Broadcast High-Priority Alert
        if action == "CREATED":
            self._persist_event_to_db(record)
            self._last_broadcast_times[record.event_id] = now
            ws_manager.broadcast_sync({
                "type": "SECURITY_ALERT",
                "event": record.to_dict()
            })
            # Trigger automated evidence recording for HIGH and CRITICAL intrusions
            if record.peak_severity in (EventSeverity.HIGH, EventSeverity.CRITICAL):
                try:
                    from backend.events.evidence_recorder import evidence_recorder
                    evidence_recorder.record_evidence_for_event(record, camera_id=camera_id)
                except Exception as e:
                    logger.error(f"[EVENT ENGINE] Failed to trigger evidence recorder: {e}")

        # 2. Event Escalated -> Immediate DB Update & Broadcast
        elif action == "ESCALATED":
            self._persist_event_to_db(record)
            self._last_broadcast_times[record.event_id] = now
            ws_manager.broadcast_sync({
                "type": "EVENT_UPDATED",
                "event": record.to_dict()
            })
            # Also broadcast SECURITY_ALERT if escalated to CRITICAL / HIGH so frontend immediately sounds sirens
            if record.peak_severity in (EventSeverity.HIGH, EventSeverity.CRITICAL):
                ws_manager.broadcast_sync({
                    "type": "SECURITY_ALERT",
                    "event": record.to_dict()
                })
            # Trigger evidence recording on severity escalation
            if record.peak_severity in (EventSeverity.HIGH, EventSeverity.CRITICAL):
                try:
                    from backend.events.evidence_recorder import evidence_recorder
                    evidence_recorder.record_evidence_for_event(record, camera_id=camera_id)
                except Exception as e:
                    logger.error(f"[EVENT ENGINE] Failed to trigger evidence recorder on escalation: {e}")

        # 3. Ongoing Continuous Update -> Throttled Broadcast & Periodic DB Sync
        elif action == "UPDATED":
            last_bc = self._last_broadcast_times.get(record.event_id, 0.0)
            if (now - last_bc) >= 0.8:
                self._last_broadcast_times[record.event_id] = now
                self._persist_event_to_db(record)
                ws_manager.broadcast_sync({
                    "type": "EVENT_UPDATED",
                    "event": record.to_dict()
                })

        return record

    def ingest_detection(self, *args, **kwargs) -> Optional[ActiveEventRecord]:
        """Convenience alias for process_target_state."""
        return self.process_target_state(*args, **kwargs)

    def acknowledge_event(
        self,
        event_id: str,
        operator_name: str = "Operator",
        notes: Optional[str] = None
    ) -> Optional[ActiveEventRecord]:
        """Operator acknowledges active alert."""
        with self._lock:
            record = self.deduplicator.acknowledge_event(event_id, operator_name, notes)

        if record:
            self._persist_event_to_db(record)
            ws_manager.broadcast_sync({
                "type": "EVENT_ACKNOWLEDGED",
                "event": record.to_dict()
            })
            logger.info(f"[EVENT ENGINE] Event {event_id} acknowledged by {operator_name}")
        return record

    def resolve_event(
        self,
        event_id: str,
        operator_name: str = "Operator"
    ) -> Optional[ActiveEventRecord]:
        """Operator manually marks an alert as resolved."""
        with self._lock:
            record = self.deduplicator.resolve_event_manually(event_id, operator_name)

        if record:
            self._persist_event_to_db(record)
            ws_manager.broadcast_sync({
                "type": "EVENT_RESOLVED",
                "event": record.to_dict()
            })
            logger.info(f"[EVENT ENGINE] Event {event_id} manually resolved by {operator_name}")
        return record

    def get_active_events(self) -> List[Dict[str, Any]]:
        """Returns all currently active events."""
        with self._lock:
            return [e.to_dict() for e in self.deduplicator.get_active_events()]

    def get_active_event(self, event_id: str) -> Optional[Dict[str, Any]]:
        """Returns specific active event details."""
        with self._lock:
            rec = self.deduplicator.get_active_event(event_id)
            return rec.to_dict() if rec else None

    def _persist_event_to_db(self, record: ActiveEventRecord) -> None:
        """Thread-safe SQLite upsert using SQLAlchemy."""
        db = SessionLocal()
        try:
            row = db.query(EventModel).filter(EventModel.id == record.event_id).first()
            now_dt = datetime.fromtimestamp(record.last_updated_time, tz=timezone.utc)
            start_dt = datetime.fromtimestamp(record.start_time, tz=timezone.utc)
            end_dt = datetime.fromtimestamp(record.resolved_at, tz=timezone.utc) if record.resolved_at else None

            if row is None:
                row = EventModel(
                    id=record.event_id,
                    event_type=f"ZONE_INTRUSION_{record.peak_severity.value}",
                    severity=record.peak_severity.value,
                    camera_id=record.camera_id,
                    radar_id=record.radar_id,
                    zone_id=record.primary_zone_id,
                    object_id=record.target_id,
                    object_class=record.object_class,
                    confidence=record.confidence,
                    status=record.status.value,
                    start_time=start_dt,
                    updated_time=now_dt,
                    end_time=end_dt,
                    description=record.description,
                    is_simulated=record.is_simulated
                )
                db.add(row)
            else:
                row.severity = record.peak_severity.value
                row.event_type = f"ZONE_INTRUSION_{record.peak_severity.value}"
                row.status = record.status.value
                row.updated_time = now_dt
                row.confidence = record.confidence
                row.description = record.description
                if end_dt:
                    row.end_time = end_dt

            db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"[EVENT ENGINE] DB persistence failed for {record.event_id}: {e}")
        finally:
            db.close()

# Global EventEngine Singleton
event_engine = EventEngine()
