"""
SENTINEL-AI: Intruder Posture & Carriage Anomaly Classifier
Sections 16 & 27: Prone Crawling Infiltration Detection, Crouching Analysis, and Load Carriage.

Analyzes bounding box aspect ratio (W/H), ground velocity, and vertical profile to distinguish:
- PRONE_CRAWLING: Stealth fence breach attempt (Aspect Ratio >= 1.35, low ground clearance)
- CROUCHING_LOITERING: Concealment behind terrain elevation (0.70 <= Aspect Ratio < 1.35)
- UPRIGHT_WALKING / RUNNING: Standard upright movement (Aspect Ratio < 0.70)
- LOAD_CARRIAGE_ANOMALY: Backpack / equipment payload volume expansion
"""

from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from backend.logger import logger
from backend.websocket.manager import ws_manager

class PostureClassifier:
    """
    Evaluates visual target geometry and kinematic properties
    to detect hostile stealth posture tactics.
    """
    def __init__(self):
        self.active_classifications: Dict[str, Dict[str, Any]] = {}
        self.crawling_alerts_count: int = 0

    def classify_target(
        self,
        target_id: str,
        bbox: List[float], # [x1, y1, x2, y2] normalized 0.0 - 1.0 or pixel
        speed_mps: float = 1.0,
        zone_id: str = "ZONE_C",
        has_equipment_load: bool = False
    ) -> Dict[str, Any]:
        """
        Classifies posture based on bounding box aspect ratio and ground speed.
        """
        x1, y1, x2, y2 = bbox
        width = abs(x2 - x1)
        height = max(abs(y2 - y1), 0.001)
        aspect_ratio = round(width / height, 3)

        # Tactical posture thresholds
        if aspect_ratio >= 1.35:
            posture = "PRONE_CRAWLING"
            threat_level = "CRITICAL"
            description = (
                f"STEALTH INFILTRATION TACTIC: Target is crawling prone (Aspect Ratio {aspect_ratio}). "
                "Attempting to bypass optical radar line-of-sight under perimeter wire."
            )
            is_stealth_tactic = True
            self.crawling_alerts_count += 1
        elif 0.70 <= aspect_ratio < 1.35:
            posture = "CROUCHING_CONCEALMENT"
            threat_level = "HIGH"
            description = (
                f"TACTICAL CONCEALMENT: Target is crouching/loitering (Aspect Ratio {aspect_ratio}) "
                "seeking terrain cover."
            )
            is_stealth_tactic = False
        else:
            posture = "UPRIGHT_RUNNING" if speed_mps > 2.0 else "UPRIGHT_WALKING"
            threat_level = "MEDIUM" if zone_id == "ZONE_B" else ("CRITICAL" if zone_id == "ZONE_C" else "LOW")
            description = f"Standard upright movement (Aspect Ratio {aspect_ratio}, speed {round(speed_mps, 1)} m/s)."
            is_stealth_tactic = False

        # Carriage anomaly assessment
        carriage_status = "HEAVY_LOAD_EQUIPMENT_DETECTED" if has_equipment_load else "STANDARD_PROFILE"

        record = {
            "target_id": target_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "zone_id": zone_id,
            "posture": posture,
            "aspect_ratio": aspect_ratio,
            "speed_mps": round(speed_mps, 2),
            "threat_level": threat_level,
            "is_stealth_tactic": is_stealth_tactic,
            "carriage_status": carriage_status,
            "description": description
        }
        
        self.active_classifications[target_id] = record
        return record

    async def simulate_crawling_intruder(
        self, target_id: str = "INTRUDER_STEALTH_01", zone_id: str = "ZONE_C"
    ) -> Dict[str, Any]:
        """
        Simulates detection of a prone crawling intruder attempting to crawl
        under the barbed wire border fence.
        """
        # Bounding box of crawling person: width = 0.38, height = 0.18 (AR = 2.11)
        sim_bbox = [0.42, 0.72, 0.80, 0.90]
        classification = self.classify_target(
            target_id=target_id,
            bbox=sim_bbox,
            speed_mps=0.35, # slow crawl
            zone_id=zone_id,
            has_equipment_load=True
        )

        logger.critical(f"[POSTURE CLASSIFIER] {classification['description']}")

        await ws_manager.broadcast({
            "type": "POSTURE_ANOMALY_DETECTED",
            "data": classification
        })

        return classification

    def get_active(self) -> Dict[str, Any]:
        """Returns all currently tracked target posture classifications."""
        return {
            "status": "HEALTHY",
            "total_crawling_alerts": self.crawling_alerts_count,
            "active_targets_count": len(self.active_classifications),
            "classifications": list(self.active_classifications.values())
        }

# Global singleton
posture_classifier = PostureClassifier()
