from functools import lru_cache
from pathlib import Path
from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Core System
    PROJECT_NAME: str = "SIH 2026 AI-Powered Multi-Sensor Border Surveillance"
    PROJECT_VERSION: str = "1.0.0"
    SYSTEM_MODE: Literal["REAL", "SIMULATED"] = "SIMULATED"
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = True

    # Camera Acquisition
    CAMERA_DEFAULT_INDEX: int = 0
    CAMERA_FPS: int = 30
    CAMERA_WIDTH: int = 1280
    CAMERA_HEIGHT: int = 720
    WEBCAM_FLIP_HORIZONTAL: bool = False

    # AI Detection & Tracking
    AI_INFERENCE_FPS: int = 15
    DETECTION_CONFIDENCE: float = 0.50
    YOLO_MODEL_NAME: str = "yolov8n.pt"
    TRACKING_ENABLED: bool = True

    # Radar & ESP32
    RADAR_ENABLED: bool = True
    RADAR_PORT: int = 8080
    RADAR_SERIAL_PORT: str = "COM3"
    RADAR_BAUD_RATE: int = 256000
    ESP32_IP: str = "10.146.49.50"

    # Storage & Persistence
    STORAGE_DIR: str = "storage"
    DATABASE_URL: str = "sqlite:///./storage/surveillance.db"
    PRE_EVENT_SECONDS: int = 10
    POST_EVENT_SECONDS: int = 15
    RETENTION_DAYS: int = 14
    EVENT_COOLDOWN_SECONDS: int = 10

    # Sensor Fusion
    FUSION_DISTANCE_THRESHOLD: float = 2.5
    FUSION_RADAR_WEIGHT: float = 0.6
    FUSION_VISION_WEIGHT: float = 0.4
    FUSION_PROJECTION_GATE: float = 0.28

    # Threat Profiling & Privacy (Phase 10)
    LOITERING_THRESHOLD_SECONDS: float = 8.0
    PRIVACY_BLUR_ENABLED: bool = False
    THREAT_SCORING_ENABLED: bool = True
    AUDIO_ALERTS_ENABLED: bool = True
    UAV_RTB_BATTERY_PERCENT: int = 15

    # Security & RBAC (Phase 12)
    SECURITY_AUTH_ENABLED: bool = False
    SECRET_KEY: str = "SIH2026_SENTINEL_MILSPEC_SECURE_TOKEN_KEY_99"
    DEFAULT_TOKEN_EXPIRY_HOURS: int = 24

    # AERION: Person Identification & Authorization
    IDENTITY_CONFIDENCE_THRESHOLD: float = 0.38
    IDENTITY_MODEL_NAME: str = "yunet_sface"

    # AERION: Drone & GPS Incident Response
    DRONE_ID: str = "DRONE-001"
    DRONE_MODE: Literal["SIMULATION", "LIVE"] = "SIMULATION"
    GPS_MODE: Literal["SIMULATION", "LIVE"] = "SIMULATION"
    GPS_SERIAL_PORT: str = "COM4"
    GPS_BAUD_RATE: int = 9600
    UAV_ARRIVAL_RADIUS_M: float = 10.0
    UAV_HOME_LAT: float = 31.6240
    UAV_HOME_LON: float = 74.8723
    UAV_RTH_BATTERY_PERCENT: float = 20.0

    # AERION: Single PIR Sensor
    PIR_ENABLED: bool = True
    PIR_ZONE_ID: str = "ZONE_B"
    PIR_MODE: Literal["SIMULATION", "LIVE"] = "SIMULATION"
    PIR_SERIAL_PORT: str = "COM6"
    PIR_SERIAL_BAUD: int = 115200

    @property
    def base_dir(self) -> Path:
        return BASE_DIR

    @property
    def storage_path(self) -> Path:
        p = BASE_DIR / self.STORAGE_DIR
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def events_dir(self) -> Path:
        p = self.storage_path / "events"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def snapshots_dir(self) -> Path:
        p = self.storage_path / "snapshots"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def logs_dir(self) -> Path:
        p = self.storage_path / "logs"
        p.mkdir(parents=True, exist_ok=True)
        return p

# Global Settings Singleton Instance
_settings_instance: Settings = Settings()

def get_settings() -> Settings:
    return _settings_instance

def update_runtime_settings(updates: dict) -> Settings:
    """
    Updates runtime settings in-memory and dynamically propagates
    values to active singletons (InferenceManager, ZoneManager, Deduplicator).
    """
    global _settings_instance
    for k, v in updates.items():
        if hasattr(_settings_instance, k) and v is not None:
            # Type cast to field type
            target_type = type(getattr(_settings_instance, k))
            try:
                if target_type == bool and isinstance(v, str):
                    casted = v.lower() in ("true", "1", "yes")
                else:
                    casted = target_type(v)
                setattr(_settings_instance, k, casted)
            except Exception:
                setattr(_settings_instance, k, v)

    # Dynamic subsystem propagation
    try:
        from backend.ai.inference_manager import inference_manager
        if "AI_INFERENCE_FPS" in updates and updates["AI_INFERENCE_FPS"] is not None:
            inference_manager.target_fps = int(updates["AI_INFERENCE_FPS"])
        if "DETECTION_CONFIDENCE" in updates and updates["DETECTION_CONFIDENCE"] is not None:
            inference_manager.detector.confidence_threshold = float(updates["DETECTION_CONFIDENCE"])
    except Exception:
        pass

    try:
        from backend.events.event_engine import event_engine
        if "EVENT_COOLDOWN_SECONDS" in updates and updates["EVENT_COOLDOWN_SECONDS"] is not None:
            event_engine.deduplicator.hysteresis_seconds = float(updates["EVENT_COOLDOWN_SECONDS"])
    except Exception:
        pass

    try:
        from backend.events.evidence_recorder import evidence_recorder
        if "PRE_EVENT_SECONDS" in updates and updates["PRE_EVENT_SECONDS"] is not None:
            evidence_recorder.pre_event_seconds = int(updates["PRE_EVENT_SECONDS"])
        if "POST_EVENT_SECONDS" in updates and updates["POST_EVENT_SECONDS"] is not None:
            evidence_recorder.post_event_seconds = int(updates["POST_EVENT_SECONDS"])
    except Exception:
        pass

    return _settings_instance
