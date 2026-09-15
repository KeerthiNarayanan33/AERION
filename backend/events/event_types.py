from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Tuple, Optional, Dict, Any

class EventSeverity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

class EventStatus(str, Enum):
    ACTIVE = "ACTIVE"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"

@dataclass
class ActiveEventRecord:
    """In-memory representation of an ongoing intrusion event undergoing continuous deduplication."""
    event_id: str
    target_id: str
    object_class: str
    primary_zone_id: str
    primary_zone_name: str
    camera_id: Optional[str] = None
    radar_id: Optional[str] = None
    initial_severity: EventSeverity = EventSeverity.LOW
    peak_severity: EventSeverity = EventSeverity.LOW
    status: EventStatus = EventStatus.ACTIVE
    start_time: float = field(default_factory=lambda: datetime.now(timezone.utc).timestamp())
    last_updated_time: float = field(default_factory=lambda: datetime.now(timezone.utc).timestamp())
    last_detection_time: float = field(default_factory=lambda: datetime.now(timezone.utc).timestamp())
    confidence: float = 0.0
    trajectory: List[Tuple[float, float]] = field(default_factory=list)
    update_count: int = 1
    is_simulated: bool = False
    description: str = ""
    operator_notes: Optional[str] = None
    acknowledged_by: Optional[str] = None
    acknowledged_at: Optional[float] = None
    resolved_at: Optional[float] = None

    @property
    def duration_seconds(self) -> float:
        """Returns the elapsed duration of the intrusion event in seconds."""
        end = self.resolved_at if self.resolved_at else self.last_updated_time
        return max(0.0, round(end - self.start_time, 1))

    def to_dict(self) -> Dict[str, Any]:
        """Serializes active event record for API responses and WebSocket broadcasts."""
        return {
            "id": self.event_id,
            "event_type": f"ZONE_INTRUSION_{self.peak_severity.value}",
            "severity": self.peak_severity.value,
            "initial_severity": self.initial_severity.value,
            "status": self.status.value,
            "target_id": self.target_id,
            "camera_id": self.camera_id,
            "radar_id": self.radar_id,
            "zone_id": self.primary_zone_id,
            "zone_name": self.primary_zone_name,
            "object_class": self.object_class,
            "confidence": round(self.confidence, 2),
            "start_time": datetime.fromtimestamp(self.start_time, tz=timezone.utc).isoformat(),
            "updated_time": datetime.fromtimestamp(self.last_updated_time, tz=timezone.utc).isoformat(),
            "resolved_at": datetime.fromtimestamp(self.resolved_at, tz=timezone.utc).isoformat() if self.resolved_at else None,
            "duration_seconds": self.duration_seconds,
            "update_count": self.update_count,
            "trajectory_points": len(self.trajectory),
            "latest_coordinates": self.trajectory[-1] if self.trajectory else None,
            "description": self.description,
            "is_simulated": self.is_simulated,
            "is_acknowledged": self.status == EventStatus.ACKNOWLEDGED,
            "acknowledged_by": self.acknowledged_by,
            "acknowledged_at": datetime.fromtimestamp(self.acknowledged_at, tz=timezone.utc).isoformat() if self.acknowledged_at else None
        }
