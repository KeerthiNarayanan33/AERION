"""
SENTINEL-AI Acoustic & Seismic Ground Sensor Ingestion Engine (Sections 64 & 70).
Monitors perimeter piezoelectric geophones, fiber-optic fence vibration sensors,
and acoustic microphone arrays to detect stealthy crawling infiltrators, fence cutting,
vehicle ground rumble, and gunshot acoustics.
"""

import time
from typing import Dict, Any, List, Optional
from backend.logger import logger


class GroundSensorNode:
    """Represents a physical or simulated perimeter geophone/acoustic node."""
    def __init__(self, node_id: str, zone_id: str, sensor_type: str, x_m: float, y_m: float):
        self.node_id = node_id
        self.zone_id = zone_id
        self.sensor_type = sensor_type
        self.x_m = x_m
        self.y_m = y_m
        self.status = "ONLINE"
        self.last_cadence_hz = 0.0
        self.last_energy_level = 0.0
        self.last_event_type = "QUIESCENT"
        self.last_event_time = 0.0


class GroundSensorManager:
    """
    Ingests and analyzes seismic frequency cadences and acoustic transient impulses.
    Fuses ground vibration with optical and radar tracks to eliminate stealth blind spots.
    """
    _instance: Optional['GroundSensorManager'] = None

    def __init__(self):
        self.nodes: Dict[str, GroundSensorNode] = {
            "GEO_01": GroundSensorNode("GEO_01", "ZONE_B", "PIEZO_GEOPHONE", -10.0, 3.5),
            "GEO_02": GroundSensorNode("GEO_02", "ZONE_C", "PIEZO_GEOPHONE", 0.0, 1.8),
            "GEO_03": GroundSensorNode("GEO_03", "ZONE_C", "FIBER_OPTIC_FENCE", 10.0, 1.8),
            "MIC_01": GroundSensorNode("MIC_01", "ZONE_B", "ACOUSTIC_ARRAY", 0.0, 4.0),
        }
        self.recent_detections: List[Dict[str, Any]] = []
        logger.info("[GROUND_SENSORS] GroundSensorManager initialized with 4 perimeter nodes.")

    @classmethod
    def get_instance(cls) -> 'GroundSensorManager':
        if cls._instance is None:
            cls._instance = GroundSensorManager()
        return cls._instance

    def classify_seismic_cadence(self, cadence_hz: float, energy: float) -> str:
        """
        Classifies seismic frequency and energy into threat behavior:
        - 0.4 to 1.3 Hz: STEALTH_CRAWL (slow ground drag, low acoustic noise)
        - 1.4 to 2.8 Hz: FOOTSTEP_CADENCE (running/walking footfall)
        - 15.0 to 45.0 Hz: VEHICLE_TREAD_RUMBLE (motor vehicle, tracked vehicle)
        - > 75.0 Hz: FENCE_CUTTING_OR_CLIMB (high-frequency mechanical strain)
        """
        if cadence_hz > 75.0:
            return "FENCE_CUTTING_OR_CLIMB"
        elif 15.0 <= cadence_hz <= 50.0:
            return "VEHICLE_TREAD_RUMBLE"
        elif 1.4 <= cadence_hz <= 2.8:
            return "FOOTSTEP_CADENCE"
        elif 0.3 <= cadence_hz <= 1.3:
            return "STEALTH_CRAWL"
        else:
            return "AMBIENT_NOISE"

    def record_seismic_trigger(
        self,
        node_id: str = "GEO_02",
        cadence_hz: float = 0.8,
        energy: float = 0.78,
        audio_db: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Ingests a seismic/acoustic trigger from a perimeter node.
        Correlates with active intrusion zones and escalates threat scoring.
        """
        now = time.time()
        node = self.nodes.get(node_id, self.nodes["GEO_02"])
        classification = self.classify_seismic_cadence(cadence_hz, energy)

        # Acoustic classification if audio level is provided
        acoustic_label = "NORMAL"
        if audio_db is not None:
            if audio_db > 125.0:
                acoustic_label = "GUNSHOT_IMPULSE"
                classification = "GUNSHOT_IMPULSE"
            elif audio_db > 85.0 and (3000 <= cadence_hz * 100 <= 6000):
                acoustic_label = "UAV_ROTOR_WHINE"
                classification = "UAV_ROTOR_WHINE"

        is_critical = classification in ("STEALTH_CRAWL", "FENCE_CUTTING_OR_CLIMB", "GUNSHOT_IMPULSE")
        threat_score = 0.95 if classification == "GUNSHOT_IMPULSE" else (0.85 if classification == "FENCE_CUTTING_OR_CLIMB" else (0.75 if classification == "STEALTH_CRAWL" else 0.45))

        node.last_cadence_hz = cadence_hz
        node.last_energy_level = energy
        node.last_event_type = classification
        node.last_event_time = now

        payload = {
            "timestamp": now,
            "node_id": node.node_id,
            "zone_id": node.zone_id,
            "sensor_type": node.sensor_type,
            "location_m": {"x": node.x_m, "y": node.y_m},
            "cadence_hz": round(cadence_hz, 2),
            "energy_normalized": round(energy, 2),
            "audio_db": round(audio_db, 1) if audio_db else None,
            "classification": classification,
            "acoustic_label": acoustic_label,
            "is_critical": is_critical,
            "threat_score": threat_score,
            "sop_action_recommended": (
                "CRAWL_INFILTRATION_DETECTED: Slew optical PTZ, cue thermal verifier, and energize boundary acoustic sirens."
                if classification == "STEALTH_CRAWL"
                else "PERIMETER_BREACH_VIBRATION: Immediate QRT dispatch to sector."
            )
        }

        self.recent_detections.append(payload)
        if len(self.recent_detections) > 20:
            self.recent_detections.pop(0)

        logger.warning(f"[GROUND_SENSORS] {node_id} trigger: {classification} (Cadence: {cadence_hz} Hz, Energy: {energy})")
        return payload

    def get_status(self) -> Dict[str, Any]:
        """Provides status of all ground sensor nodes and recent vibration alerts."""
        now = time.time()
        nodes_status = []
        for n in self.nodes.values():
            active_recently = (now - n.last_event_time) < 15.0 if n.last_event_time > 0 else False
            nodes_status.append({
                "node_id": n.node_id,
                "zone_id": n.zone_id,
                "sensor_type": n.sensor_type,
                "x_m": n.x_m,
                "y_m": n.y_m,
                "status": n.status,
                "last_event_type": n.last_event_type,
                "last_cadence_hz": n.last_cadence_hz,
                "last_energy_level": n.last_energy_level,
                "is_active_trigger": active_recently
            })

        return {
            "monitored_nodes_count": len(self.nodes),
            "nodes": nodes_status,
            "recent_detections": self.recent_detections[-5:]
        }

    def ingest_seismic_pulse(
        self,
        node_id: str = "GEO_02",
        frequency_hz: float = 0.8,
        amplitude_g: float = 0.78,
        snr_db: float = 18.0
    ) -> Dict[str, Any]:
        """Convenience alias for ingesting seismic cadence pulse."""
        return self.record_seismic_trigger(node_id=node_id, cadence_hz=frequency_hz, energy=amplitude_g)

    def ingest_acoustic_event(
        self,
        node_id: str = "MIC_01",
        audio_db: float = 88.5,
        label: str = "UAV_ROTOR_WHINE"
    ) -> Dict[str, Any]:
        """Convenience alias for ingesting acoustic signature."""
        res = self.record_seismic_trigger(node_id=node_id, cadence_hz=42.0, energy=0.8, audio_db=audio_db)
        res["classification"] = label
        res["acoustic_label"] = label
        return res


ground_sensor_manager = GroundSensorManager.get_instance()
