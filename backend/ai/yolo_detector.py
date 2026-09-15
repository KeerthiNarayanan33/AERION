import time
from pathlib import Path
from typing import List, Optional
import numpy as np

# Ensure PyTorch/Torchvision compatibility before importing Ultralytics
import backend.utils.torch_patch
from backend.ai.detector_interface import DetectorInterface, Detection, DetectionResult
from backend.config import get_settings
from backend.logger import logger

settings = get_settings()

# Target surveillance classes to filter from COCO
SURVEILLANCE_CLASSES = {
    0: "person",
    1: "bicycle",
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck"
}

class YOLODetector(DetectorInterface):
    """
    Ultralytics YOLO object detector implementation.
    Supports YOLOv8 / YOLOv11 nano/small models with hardware acceleration on NVIDIA RTX 3050.
    """
    def __init__(
        self,
        model_name: Optional[str] = None,
        confidence_threshold: float = 0.35,
        device: Optional[str] = None
    ):
        self.model_name = model_name or settings.YOLO_MODEL_NAME
        self.confidence_threshold = confidence_threshold
        self.model = None
        self._is_ready = False

        # Device selection: Auto-detect NVIDIA CUDA GPU
        if device:
            self.device = device
        else:
            try:
                import torch
                self.device = "cuda:0" if torch.cuda.is_available() else "cpu"
            except Exception:
                self.device = "cpu"

    def load(self) -> None:
        """Loads model weights onto target device."""
        if self._is_ready:
            return

        logger.info(f"Loading YOLO model '{self.model_name}' on device '{self.device}'...")
        try:
            from ultralytics import YOLO
            # Models directory
            models_dir = settings.base_dir / "models"
            models_dir.mkdir(parents=True, exist_ok=True)
            model_path = models_dir / self.model_name

            # If model file does not exist locally in models/, load by name (ultralytics will cache it)
            load_target = str(model_path) if model_path.exists() else self.model_name
            self.model = YOLO(load_target)

            # Warmup inference
            dummy_img = np.zeros((320, 320, 3), dtype=np.uint8)
            self.model(dummy_img, device=self.device, verbose=False)

            self._is_ready = True
            logger.info(f"YOLO detector successfully loaded on {self.device}.")
        except Exception as e:
            logger.error(f"Failed to load YOLO model: {e}. AI will operate in fallback mode.", exc_info=True)
            self._is_ready = False

    def detect(self, image: np.ndarray, confidence_threshold: Optional[float] = None) -> DetectionResult:
        """Executes YOLO inference on frame and returns filtered detections."""
        t_start = time.time()
        conf_thresh = confidence_threshold if confidence_threshold is not None else self.confidence_threshold

        if not self._is_ready or self.model is None:
            # Fallback when model is not ready
            return DetectionResult(
                detections=[],
                inference_time_ms=0.0,
                model_name=self.model_name,
                device="uninitialized",
                timestamp=t_start
            )

        try:
            vehicle_ids = {2, 3, 5, 7}  # car, motorcycle, bus, truck
            inference_conf = min(conf_thresh, 0.25)

            # Run inference
            results = self.model(
                image,
                conf=inference_conf,
                device=self.device,
                classes=list(SURVEILLANCE_CLASSES.keys()),
                verbose=False
            )

            detections: List[Detection] = []
            if results and len(results) > 0:
                boxes = results[0].boxes
                for box in boxes:
                    cls_id = int(box.cls[0].item())
                    conf = float(box.conf[0].item())

                    # Sensitive thresholds: vehicles at 0.25, persons at min(conf_thresh, 0.35)
                    req_conf = 0.25 if cls_id in vehicle_ids else (min(conf_thresh, 0.35) if cls_id == 0 else conf_thresh)
                    if conf < req_conf:
                        continue

                    xyxy = box.xyxy[0].tolist()
                    x1, y1, x2, y2 = int(xyxy[0]), int(xyxy[1]), int(xyxy[2]), int(xyxy[3])
                    w = max(0, x2 - x1)
                    h = max(0, y2 - y1)
                    cx = x1 + (w // 2)
                    cy = y1 + (h // 2)

                    class_name = SURVEILLANCE_CLASSES.get(cls_id, results[0].names.get(cls_id, f"obj_{cls_id}"))

                    detections.append(Detection(
                        box=(x1, y1, x2, y2),
                        confidence=round(conf, 2),
                        class_id=cls_id,
                        class_name=class_name,
                        center=(cx, cy),
                        width=w,
                        height=h
                    ))

            inference_time_ms = round((time.time() - t_start) * 1000.0, 1)

            return DetectionResult(
                detections=detections,
                inference_time_ms=inference_time_ms,
                model_name=self.model_name,
                device=self.device,
                timestamp=t_start
            )

        except Exception as e:
            logger.error(f"Error during YOLO inference: {e}")
            return DetectionResult(
                detections=[],
                inference_time_ms=round((time.time() - t_start) * 1000.0, 1),
                model_name=self.model_name,
                device=self.device,
                timestamp=t_start
            )

    def get_supported_classes(self) -> List[str]:
        return list(SURVEILLANCE_CLASSES.values())

    def is_ready(self) -> bool:
        return self._is_ready
