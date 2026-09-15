from abc import ABC, abstractmethod
from typing import List, Tuple, Optional
from pydantic import BaseModel
from backend.ai.detector_interface import Detection

class TrackedObject(BaseModel):
    """
    Represents a persistently tracked person or vehicle across video frames.
    """
    track_id: int
    class_id: int
    class_name: str
    confidence: float
    box: Tuple[int, int, int, int]              # (x1, y1, x2, y2)
    center: Tuple[int, int]                    # (cx, cy)
    velocity_x: float = 0.0                    # pixels/sec
    velocity_y: float = 0.0                    # pixels/sec
    speed: float = 0.0                         # pixels/sec
    trajectory: List[Tuple[int, int]] = []     # History of recent center points
    first_seen: float                          # Timestamp
    last_seen: float                           # Timestamp
    time_since_update: int = 0                 # Frames since last matched detection
    hits: int = 1                              # Number of detection matches
    age: int = 1                               # Total lifetime frames
    confirmed: bool = False                    # True after minimum hit streak
    zone_id: Optional[str] = None              # Current zone ID
    zone_name: Optional[str] = None            # Current zone Name
    intrusion_state: str = "NORMAL"            # NORMAL, APPROACHING, WARNING, RESTRICTED_ENTRY, ACTIVE_EVENT, RESOLVED
    threat_score: float = 0.0                  # Threat index (0.00 to 1.00)
    is_loitering: bool = False                 # Flagged if hovering in warning/restricted zone
    plate_text: Optional[str] = None           # Recognized vehicle license plate text
    identity: Optional[str] = None             # Recognized person name or 'UNKNOWN'
    identity_confidence: Optional[float] = None # Identity recognition confidence (0.0 to 1.0)
    authorization: Optional[str] = None       # AUTHORIZED, UNAUTHORIZED, NOT_AUTHORIZED_FOR_ZONE, UNVERIFIED

    @property
    def bbox(self) -> Tuple[int, int, int, int]:
        return self.box

    model_config = {
        "arbitrary_types_allowed": True
    }

class TrackerInterface(ABC):
    """
    Abstract interface for Multi-Object Tracking (MOT) algorithms.
    Supports pluggable tracking backends (ByteTrack, BoT-SORT, IoU Tracker).
    """

    @abstractmethod
    def update(self, detections: List[Detection], timestamp: Optional[float] = None) -> List[TrackedObject]:
        """
        Updates internal tracks with new detections from the current frame.
        
        Args:
            detections: List of Detection objects from AI detector.
            timestamp: Frame timestamp in seconds.
            
        Returns:
            List of active TrackedObject instances.
        """
        pass

    @abstractmethod
    def reset(self) -> None:
        """Resets all active tracks."""
        pass
