from abc import ABC, abstractmethod
from typing import List, Tuple, Optional
from pydantic import BaseModel
import numpy as np

class Detection(BaseModel):
    """Represents a single detected object in image coordinates."""
    box: Tuple[int, int, int, int]  # (x1, y1, x2, y2) in pixel coordinates
    confidence: float              # 0.0 to 1.0
    class_id: int
    class_name: str                # e.g., 'person', 'car', 'truck'
    center: Tuple[int, int]        # (cx, cy) center point
    width: int
    height: int

    model_config = {
        "arbitrary_types_allowed": True
    }

class DetectionResult(BaseModel):
    """Container for batch or frame inference results with telemetry."""
    detections: List[Detection]
    inference_time_ms: float
    model_name: str
    device: str
    timestamp: float

    @property
    def count(self) -> int:
        return len(self.detections)

    @property
    def person_count(self) -> int:
        return sum(1 for d in self.detections if d.class_name == "person")

    @property
    def vehicle_count(self) -> int:
        return sum(1 for d in self.detections if d.class_name in [
            "car", "motorcycle", "bus", "truck", "bicycle"
        ])

class DetectorInterface(ABC):
    """
    Abstract interface for pluggable AI object detection models.
    Allows replacing YOLOv8 with YOLOv11, RT-DETR, or ONNX runtimes
    without modifying the surveillance pipeline.
    """

    @abstractmethod
    def load(self) -> None:
        """Loads and prepares the model on the target hardware (GPU/CPU)."""
        pass

    @abstractmethod
    def detect(self, image: np.ndarray, confidence_threshold: Optional[float] = None) -> DetectionResult:
        """
        Executes inference on a single image/frame.
        
        Args:
            image: BGR NumPy array from OpenCV.
            confidence_threshold: Minimum confidence score filter.
            
        Returns:
            DetectionResult with filtered detections and latency.
        """
        pass

    @abstractmethod
    def get_supported_classes(self) -> List[str]:
        """Returns list of target classes recognized by this model."""
        pass

    @abstractmethod
    def is_ready(self) -> bool:
        """Returns True if the model is loaded and ready for inference."""
        pass
