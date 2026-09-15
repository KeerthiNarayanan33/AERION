from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Text, ForeignKey
)
from sqlalchemy.orm import declarative_base

Base = declarative_base()

def utcnow():
    return datetime.now(timezone.utc)

class CameraModel(Base):
    __tablename__ = "cameras"

    id = Column(String(50), primary_key=True)
    name = Column(String(100), nullable=False)
    type = Column(String(50), nullable=False, default="WEBCAM")  # WEBCAM, IP_CAMERA, UAV
    source = Column(String(255), nullable=False, default="0")
    status = Column(String(50), nullable=False, default="OFFLINE")  # ONLINE, DEGRADED, OFFLINE, RECONNECTING
    resolution = Column(String(50), default="1280x720")
    fps = Column(Float, default=0.0)
    latency_ms = Column(Float, default=0.0)
    zone_id = Column(String(50), nullable=True)
    enabled = Column(Boolean, default=True)
    last_frame_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

class RadarSensorModel(Base):
    __tablename__ = "radar_sensors"

    id = Column(String(50), primary_key=True)
    name = Column(String(100), nullable=False)
    model = Column(String(50), default="LD2450")
    status = Column(String(50), default="OFFLINE")  # ONLINE, DEGRADED, OFFLINE
    connection_type = Column(String(50), default="SIMULATED")  # WIFI, SERIAL, SIMULATED
    ip_address = Column(String(50), nullable=True)
    port = Column(Integer, nullable=True)
    last_heartbeat = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow)

class RadarTargetModel(Base):
    __tablename__ = "radar_targets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    sensor_id = Column(String(50), nullable=False)
    target_id = Column(Integer, nullable=False)
    x = Column(Float, nullable=False)
    y = Column(Float, nullable=False)
    speed = Column(Float, nullable=False, default=0.0)
    distance = Column(Float, nullable=False, default=0.0)
    zone_id = Column(String(50), nullable=True)
    timestamp = Column(DateTime, default=utcnow)

class ZoneModel(Base):
    __tablename__ = "zones"

    id = Column(String(50), primary_key=True)
    name = Column(String(100), nullable=False)
    zone_type = Column(String(50), nullable=False, default="NORMAL")  # NORMAL, WARNING, RESTRICTED
    # New: subtype for access control
    zone_subtype = Column(String(50), default="PUBLIC")  # PUBLIC, STAFF_ONLY, RESTRICTED, CRITICAL, NO_ENTRY
    security_level = Column(String(20), default="LOW")  # LOW, MEDIUM, HIGH, CRITICAL
    priority = Column(Integer, default=3)  # 1 (highest) to 5 (lowest)
    status = Column(String(20), default="ACTIVE")  # ACTIVE, INACTIVE
    coordinates_json = Column(Text, nullable=False)  # JSON array of [x, y] normalized coordinates
    # Geo coordinates for real-world map display
    center_lat = Column(Float, nullable=True)
    center_lon = Column(Float, nullable=True)
    radius_m = Column(Float, nullable=True)  # for circular zones
    geo_coords_json = Column(Text, nullable=True)  # JSON array of [lat, lon] for polygon geo zone
    color = Column(String(20), default="#00e676")
    description = Column(Text, nullable=True)
    # Sensor assignments (JSON arrays of IDs)
    authorized_persons_json = Column(Text, default="[]")  # JSON list of person_ids
    assigned_cameras_json = Column(Text, default="[]")    # JSON list of camera_ids
    assigned_radar_json = Column(Text, default="[]")      # JSON list of radar_ids
    assigned_uav_json = Column(Text, default="[]")        # JSON list of uav_ids
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

class TrackedObjectModel(Base):
    __tablename__ = "tracked_objects"

    id = Column(Integer, primary_key=True, autoincrement=True)
    camera_id = Column(String(50), nullable=False)
    track_id = Column(Integer, nullable=False)
    object_class = Column(String(50), nullable=False)
    confidence = Column(Float, default=0.0)
    zone_id = Column(String(50), nullable=True)
    first_seen = Column(DateTime, default=utcnow)
    last_seen = Column(DateTime, default=utcnow)
    active = Column(Boolean, default=True)

class EventModel(Base):
    __tablename__ = "events"

    id = Column(String(100), primary_key=True)
    event_type = Column(String(100), nullable=False)
    severity = Column(String(50), nullable=False, default="LOW")  # LOW, MEDIUM, HIGH, CRITICAL
    camera_id = Column(String(50), nullable=True)
    radar_id = Column(String(50), nullable=True)
    zone_id = Column(String(50), nullable=True)
    object_id = Column(String(50), nullable=True)
    object_class = Column(String(50), nullable=True)
    confidence = Column(Float, default=0.0)
    status = Column(String(50), default="ACTIVE")  # ACTIVE, UPDATED, RESOLVED
    start_time = Column(DateTime, default=utcnow)
    updated_time = Column(DateTime, default=utcnow, onupdate=utcnow)
    end_time = Column(DateTime, nullable=True)
    video_path = Column(String(255), nullable=True)
    snapshot_path = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    is_simulated = Column(Boolean, default=False)

class ANPRResultModel(Base):
    __tablename__ = "anpr_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(String(100), nullable=True)
    vehicle_track_id = Column(Integer, nullable=False)
    camera_id = Column(String(50), nullable=False)
    plate_text = Column(String(50), nullable=False)
    confidence = Column(Float, default=0.0)
    snapshot_path = Column(String(255), nullable=True)
    timestamp = Column(DateTime, default=utcnow)

class SystemHealthModel(Base):
    __tablename__ = "system_health"

    id = Column(Integer, primary_key=True, autoincrement=True)
    component_name = Column(String(50), nullable=False, unique=True)
    status = Column(String(50), nullable=False, default="OFFLINE")  # ONLINE, DEGRADED, OFFLINE, STANDBY
    metrics_json = Column(Text, nullable=True)
    last_checked = Column(DateTime, default=utcnow)

class UAVStatusModel(Base):
    __tablename__ = "uav_status"

    id = Column(String(50), primary_key=True, default="UAV_01")
    state = Column(String(50), default="UAV_STANDBY")  # UAV_OFFLINE, UAV_STANDBY, UAV_AVAILABLE, UAV_VERIFICATION_REQUESTED, UAV_ACTIVE, UAV_RETURNING
    battery_percent = Column(Integer, default=100)
    current_zone = Column(String(50), nullable=True)
    stream_url = Column(String(255), nullable=True)
    target_lat = Column(Float, nullable=True)
    target_lon = Column(Float, nullable=True)
    last_ping = Column(DateTime, default=utcnow)

class SettingModel(Base):
    __tablename__ = "settings"

    key = Column(String(100), primary_key=True)
    value = Column(Text, nullable=False)
    description = Column(Text, nullable=True)

class AuthorizedPersonModel(Base):
    """Extended authorized person model with full profile, zone access, and detection tracking."""
    __tablename__ = "authorized_persons"

    # Core identity
    person_id = Column(String(50), primary_key=True)
    name = Column(String(100), nullable=False)
    employee_id = Column(String(50), nullable=True)
    department = Column(String(100), nullable=True)
    role = Column(String(100), nullable=True)

    # Contact
    phone = Column(String(30), nullable=True)
    email = Column(String(150), nullable=True)

    # Access control
    access_level = Column(String(50), default="STANDARD")  # VISITOR, STANDARD, ELEVATED, ADMIN
    status = Column(String(50), nullable=False, default="AUTHORIZED")  # AUTHORIZED, DISABLED, EXPIRED, SUSPENDED, REVOKED
    allowed_zones = Column(Text, nullable=False, default='["ZONE_A", "ZONE_B"]')  # JSON array of zone IDs
    valid_from = Column(DateTime, nullable=True)
    valid_until = Column(DateTime, nullable=True)

    # Face recognition
    reference_image_path = Column(String(255), nullable=True)
    reference_embedding = Column(Text, nullable=True)  # JSON-encoded face embedding vector

    # Detection tracking
    detection_count = Column(Integer, default=0)
    last_detected_at = Column(DateTime, nullable=True)
    last_detected_zone = Column(String(50), nullable=True)

    # Metadata
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

class SecurityIncidentModel(Base):
    __tablename__ = "security_incidents"

    incident_id = Column(String(50), primary_key=True)
    camera_id = Column(String(50), nullable=True)
    zone_id = Column(String(50), nullable=True)
    identity = Column(String(100), default="UNKNOWN")
    identity_confidence = Column(Float, default=0.0)
    authorization = Column(String(50), default="UNAUTHORIZED")  # AUTHORIZED, UNAUTHORIZED, NOT_AUTHORIZED_FOR_ZONE, UNVERIFIED
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    priority = Column(String(50), default="HIGH")  # LOW, MEDIUM, HIGH, CRITICAL
    drone_id = Column(String(50), default="DRONE-001")
    status = Column(String(50), default="INCIDENT_CREATED")
    aerial_verified = Column(Boolean, default=False)
    aerial_details = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

class SiteConfigModel(Base):
    """Site/location configuration for the surveillance installation."""
    __tablename__ = "site_config"

    site_id = Column(String(50), primary_key=True)
    site_name = Column(String(200), nullable=False, default="Surveillance Site")
    address = Column(Text, nullable=True)
    city = Column(String(100), nullable=True)
    state = Column(String(100), nullable=True)
    country = Column(String(100), nullable=True, default="India")
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    description = Column(Text, nullable=True)
    map_provider = Column(String(50), default="OFFLINE")  # OFFLINE, OPENSTREETMAP, CUSTOM
    map_api_key = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

class AlertRuleModel(Base):
    """Configurable alert rule: IF condition THEN action."""
    __tablename__ = "alert_rules"

    rule_id = Column(String(50), primary_key=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    # Conditions: JSON object with keys like person_type, zone_type, zone_access
    condition_json = Column(Text, nullable=False, default="{}")
    # Actions: JSON object with keys like severity, create_event, tracking, uav_assistance, operator_alert
    action_json = Column(Text, nullable=False, default="{}")
    enabled = Column(Boolean, default=True)
    priority = Column(Integer, default=5)  # 1 = highest priority
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)
