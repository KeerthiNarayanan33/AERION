import json
from datetime import datetime, timezone
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from backend.config import get_settings
from backend.database.models import (
    Base, CameraModel, RadarSensorModel, ZoneModel,
    UAVStatusModel, SystemHealthModel, SettingModel,
    AuthorizedPersonModel, SecurityIncidentModel,
    SiteConfigModel, AlertRuleModel
)
from backend.logger import logger

settings = get_settings()

engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

from contextlib import contextmanager

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@contextmanager
def get_db_context():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def _migrate_authorized_persons(db: Session):
    """Safely add new columns to authorized_persons table if they don't exist (SQLite migration)."""
    try:
        new_cols = [
            ("employee_id", "VARCHAR(50)"),
            ("department", "VARCHAR(100)"),
            ("role", "VARCHAR(100)"),
            ("phone", "VARCHAR(30)"),
            ("email", "VARCHAR(150)"),
            ("access_level", "VARCHAR(50) DEFAULT 'STANDARD'"),
            ("valid_from", "DATETIME"),
            ("valid_until", "DATETIME"),
            ("detection_count", "INTEGER DEFAULT 0"),
            ("last_detected_at", "DATETIME"),
            ("last_detected_zone", "VARCHAR(50)"),
            ("notes", "TEXT"),
            ("updated_at", "DATETIME"),
        ]
        for col_name, col_def in new_cols:
            try:
                db.execute(text(f"ALTER TABLE authorized_persons ADD COLUMN {col_name} {col_def}"))
                db.commit()
            except Exception:
                db.rollback()  # Column already exists
    except Exception as e:
        logger.debug(f"Migration note: {e}")

def _migrate_zones(db: Session):
    """Safely add new columns to zones table (SQLite migration)."""
    try:
        new_cols = [
            ("zone_subtype", "VARCHAR(50) DEFAULT 'PUBLIC'"),
            ("security_level", "VARCHAR(20) DEFAULT 'LOW'"),
            ("priority", "INTEGER DEFAULT 3"),
            ("status", "VARCHAR(20) DEFAULT 'ACTIVE'"),
            ("center_lat", "FLOAT"),
            ("center_lon", "FLOAT"),
            ("radius_m", "FLOAT"),
            ("geo_coords_json", "TEXT"),
            ("authorized_persons_json", "TEXT DEFAULT '[]'"),
            ("assigned_cameras_json", "TEXT DEFAULT '[]'"),
            ("assigned_radar_json", "TEXT DEFAULT '[]'"),
            ("assigned_uav_json", "TEXT DEFAULT '[]'"),
            ("updated_at", "DATETIME"),
        ]
        for col_name, col_def in new_cols:
            try:
                db.execute(text(f"ALTER TABLE zones ADD COLUMN {col_name} {col_def}"))
                db.commit()
            except Exception:
                db.rollback()
    except Exception as e:
        logger.debug(f"Zone migration note: {e}")

def init_db():
    """Initializes schema and seeds default operational data."""
    # Ensure storage folder exists
    settings.storage_path

    Base.metadata.create_all(bind=engine)
    logger.info("Database tables verified/created successfully.")

    db: Session = SessionLocal()
    try:
        # Run migrations for existing tables
        _migrate_authorized_persons(db)
        _migrate_zones(db)

        # Seed Cameras if not present
        if not db.query(CameraModel).filter(CameraModel.id == "CAM_01").first():
            cam1 = CameraModel(
                id="CAM_01",
                name="Webcam (Primary Fixed CCTV)",
                type="WEBCAM",
                source=str(settings.CAMERA_DEFAULT_INDEX),
                status="ONLINE",
                resolution=f"{settings.CAMERA_WIDTH}x{settings.CAMERA_HEIGHT}",
                fps=float(settings.CAMERA_FPS),
                zone_id="ZONE_B"
            )
            cam2 = CameraModel(
                id="CAM_02",
                name="Smartphone IP Camera",
                type="IP_CAMERA",
                source="",
                status="OFFLINE",
                resolution="1920x1080",
                fps=0.0,
                zone_id="ZONE_C"
            )
            uav_cam = CameraModel(
                id="UAV_01",
                name="Drone Verification Stream",
                type="UAV",
                source="",
                status="STANDBY",
                resolution="1920x1080",
                fps=0.0,
                zone_id=None
            )
            db.add_all([cam1, cam2, uav_cam])
            logger.info("Seeded default cameras: CAM_01, CAM_02, UAV_01.")

        # Seed Radar Sensor if not present
        if not db.query(RadarSensorModel).filter(RadarSensorModel.id == "RADAR_01").first():
            radar = RadarSensorModel(
                id="RADAR_01",
                name="LD2450 24GHz mmWave Radar",
                model="LD2450",
                status="ONLINE",
                connection_type="SIMULATED" if settings.SYSTEM_MODE == "SIMULATION" else "WIFI",
                ip_address=settings.ESP32_IP,
                port=settings.RADAR_PORT
            )
            db.add(radar)
            logger.info("Seeded default radar sensor: RADAR_01.")

        # Seed Default Surveillance Zones if not present
        if not db.query(ZoneModel).first():
            zone_a = ZoneModel(
                id="ZONE_A",
                name="Outer Patrol Sector",
                zone_type="NORMAL",
                zone_subtype="PUBLIC",
                security_level="LOW",
                priority=3,
                status="ACTIVE",
                coordinates_json=json.dumps([[0.05, 0.10], [0.35, 0.10], [0.35, 0.90], [0.05, 0.90]]),
                color="#00e676",
                description="General buffer sector. Continuous patrol monitoring.",
                assigned_cameras_json=json.dumps(["CAM_01"]),
                assigned_radar_json=json.dumps(["RADAR_01"]),
                assigned_uav_json=json.dumps([]),
                authorized_persons_json=json.dumps(["PERSON-001", "AUTH-001", "AUTH-002", "AUTH-003"])
            )
            zone_b = ZoneModel(
                id="ZONE_B",
                name="Warning Approach Sector",
                zone_type="WARNING",
                zone_subtype="STAFF_ONLY",
                security_level="MEDIUM",
                priority=2,
                status="ACTIVE",
                coordinates_json=json.dumps([[0.35, 0.10], [0.65, 0.10], [0.65, 0.90], [0.35, 0.90]]),
                color="#ffab00",
                description="Intermediate warning perimeter. Heightened alert when crossed.",
                assigned_cameras_json=json.dumps(["CAM_01", "CAM_02"]),
                assigned_radar_json=json.dumps(["RADAR_01"]),
                assigned_uav_json=json.dumps(["UAV_01"]),
                authorized_persons_json=json.dumps(["PERSON-001", "AUTH-001", "AUTH-002"])
            )
            zone_c = ZoneModel(
                id="ZONE_C",
                name="Restricted Border Fence",
                zone_type="RESTRICTED",
                zone_subtype="CRITICAL",
                security_level="CRITICAL",
                priority=1,
                status="ACTIVE",
                coordinates_json=json.dumps([[0.65, 0.10], [0.95, 0.10], [0.95, 0.90], [0.65, 0.90]]),
                color="#ff1744",
                description="Critical zero-tolerance exclusion zone. Triggers critical alarms.",
                assigned_cameras_json=json.dumps(["CAM_02"]),
                assigned_radar_json=json.dumps(["RADAR_01"]),
                assigned_uav_json=json.dumps(["UAV_01"]),
                authorized_persons_json=json.dumps(["PERSON-001"])
            )
            db.add_all([zone_a, zone_b, zone_c])
            logger.info("Seeded default zones: ZONE_A, ZONE_B, ZONE_C.")

        # Seed UAV Status if not present
        if not db.query(UAVStatusModel).filter(UAVStatusModel.id == "UAV_01").first():
            uav = UAVStatusModel(
                id="UAV_01",
                state="UAV_STANDBY",
                battery_percent=95,
                current_zone="ZONE_A"
            )
            db.add(uav)

        # Seed System Health
        components = [
            ("AI_ENGINE", "ONLINE", {"model": settings.YOLO_MODEL_NAME, "target_fps": settings.AI_INFERENCE_FPS}),
            ("ESP32", "ONLINE", {"ip": settings.ESP32_IP, "protocol": "WiFi JSON"}),
            ("LD2450", "ONLINE", {"frequency": "24GHz", "type": "mmWave Track"}),
            ("CAM_01", "ONLINE", {"type": "USB Webcam", "index": settings.CAMERA_DEFAULT_INDEX}),
            ("CAM_02", "OFFLINE", {"type": "Smartphone IP Stream"}),
            ("UAV_01", "STANDBY", {"type": "Secondary Verification Drone"})
        ]
        for comp_name, status, meta in components:
            if not db.query(SystemHealthModel).filter(SystemHealthModel.component_name == comp_name).first():
                db.add(SystemHealthModel(
                    component_name=comp_name,
                    status=status,
                    metrics_json=json.dumps(meta),
                    last_checked=datetime.now(timezone.utc)
                ))

        # Seed initial settings
        defaults = [
            ("SYSTEM_MODE", settings.SYSTEM_MODE, "Current runtime operational mode (REAL/SIMULATED)"),
            ("AI_INFERENCE_FPS", str(settings.AI_INFERENCE_FPS), "Target AI inference frames per second"),
            ("DETECTION_CONFIDENCE", str(settings.DETECTION_CONFIDENCE), "Object detection threshold"),
            ("PRE_EVENT_SECONDS", str(settings.PRE_EVENT_SECONDS), "Pre-event rolling buffer duration in seconds"),
            ("POST_EVENT_SECONDS", str(settings.POST_EVENT_SECONDS), "Post-event recording duration in seconds"),
            ("RETENTION_DAYS", str(settings.RETENTION_DAYS), "Automatic storage expiration in days"),
            ("IDENTITY_CONFIDENCE_THRESHOLD", str(settings.IDENTITY_CONFIDENCE_THRESHOLD), "Face verification threshold")
        ]
        for k, v, desc in defaults:
            if not db.query(SettingModel).filter(SettingModel.key == k).first():
                db.add(SettingModel(key=k, value=v, description=desc))

        # Seed Default Authorized Person (Section 9)
        if not db.query(AuthorizedPersonModel).filter(AuthorizedPersonModel.person_id == "PERSON-001").first():
            p1 = AuthorizedPersonModel(
                person_id="PERSON-001",
                name="Keerthi",
                employee_id="EMP-001",
                department="Operations",
                role="Security Administrator",
                access_level="ADMIN",
                status="AUTHORIZED",
                allowed_zones=json.dumps(["ZONE_A", "ZONE_B", "ZONE_C", "ZONE-001", "ZONE-002"]),
                reference_image_path="/storage/snapshots/keerthi_ref.jpg",
                notes="Primary security administrator. Full access granted.",
                valid_from=datetime(2026, 1, 1, tzinfo=timezone.utc),
                valid_until=datetime(2027, 12, 31, tzinfo=timezone.utc),
            )
            db.add(p1)
            logger.info("Seeded default authorized person: PERSON-001 (Keerthi).")

        # Seed Demo Authorized Persons (AUTH-001 through AUTH-003)
        demo_persons = [
            {
                "person_id": "AUTH-001",
                "name": "Keerthi Narayanan",
                "employee_id": "BSF-4421",
                "department": "Operations",
                "role": "Security Administrator",
                "access_level": "ADMIN",
                "status": "AUTHORIZED",
                "allowed_zones": json.dumps(["ZONE_A", "ZONE_B", "ZONE_C"]),
                "phone": "+91 98400 12345",
                "email": "keerthi.n@sentinel-ai.gov",
                "notes": "Clearance Level: SECRET. Primary site administrator.",
                "valid_from": datetime(2026, 1, 1, tzinfo=timezone.utc),
                "valid_until": datetime(2027, 12, 31, tzinfo=timezone.utc),
            },
            {
                "person_id": "AUTH-002",
                "name": "Arun Kumar",
                "employee_id": "BSF-4422",
                "department": "Intelligence",
                "role": "Operations Officer",
                "access_level": "ELEVATED",
                "status": "AUTHORIZED",
                "allowed_zones": json.dumps(["ZONE_A", "ZONE_B"]),
                "phone": "+91 98400 23456",
                "email": "arun.k@sentinel-ai.gov",
                "notes": "Cleared for patrol sectors and warning perimeter.",
                "valid_from": datetime(2026, 1, 1, tzinfo=timezone.utc),
                "valid_until": datetime(2027, 6, 30, tzinfo=timezone.utc),
            },
            {
                "person_id": "AUTH-003",
                "name": "Meena Raj",
                "employee_id": "BSF-4423",
                "department": "Technical",
                "role": "Control Room Operator",
                "access_level": "STANDARD",
                "status": "AUTHORIZED",
                "allowed_zones": json.dumps(["ZONE_A"]),
                "phone": "+91 98400 34567",
                "email": "meena.r@sentinel-ai.gov",
                "notes": "Restricted to outer patrol sector.",
                "valid_from": datetime(2026, 6, 1, tzinfo=timezone.utc),
                "valid_until": datetime(2027, 5, 31, tzinfo=timezone.utc),
            },
        ]
        for pd in demo_persons:
            if not db.query(AuthorizedPersonModel).filter(AuthorizedPersonModel.person_id == pd["person_id"]).first():
                db.add(AuthorizedPersonModel(**pd))
        logger.info("Seeded demo authorized persons: AUTH-001, AUTH-002, AUTH-003.")

        # Seed Site Configuration
        if not db.query(SiteConfigModel).first():
            site = SiteConfigModel(
                site_id="SITE-001",
                site_name="AERION — Smart Border Surveillance Campus",
                address="Border Outpost Alpha, Sector 7, Attari",
                city="Amritsar",
                state="Punjab",
                country="India",
                latitude=31.6240,
                longitude=74.8723,
                description="Primary monitored forward operating base. Multi-sensor AI-powered perimeter surveillance.",
                map_provider="OFFLINE"
            )
            db.add(site)
            logger.info("Seeded default site configuration: SITE-001.")

        # Seed Default Alert Rules
        if not db.query(AlertRuleModel).first():
            rules = [
                AlertRuleModel(
                    rule_id="RULE-001",
                    name="Unknown Person in Restricted Zone",
                    description="Trigger CRITICAL alert and UAV dispatch when unknown person enters restricted area.",
                    condition_json=json.dumps({"person_type": "UNKNOWN", "zone_type": "RESTRICTED"}),
                    action_json=json.dumps({"severity": "CRITICAL", "create_event": True, "tracking": True, "uav_assistance": True, "operator_alert": True}),
                    enabled=True,
                    priority=1
                ),
                AlertRuleModel(
                    rule_id="RULE-002",
                    name="Authorized Person — Normal Entry",
                    description="Log entry event when authorized person enters their permitted zone.",
                    condition_json=json.dumps({"person_type": "AUTHORIZED", "zone_access": "PERMITTED"}),
                    action_json=json.dumps({"severity": "INFO", "create_event": True, "tracking": False, "uav_assistance": False, "operator_alert": False}),
                    enabled=True,
                    priority=5
                ),
                AlertRuleModel(
                    rule_id="RULE-003",
                    name="Authorized Person — Zone Access Violation",
                    description="Trigger HIGH alert when authorized person enters a zone they are not permitted for.",
                    condition_json=json.dumps({"person_type": "AUTHORIZED", "zone_access": "DENIED"}),
                    action_json=json.dumps({"severity": "HIGH", "create_event": True, "tracking": True, "uav_assistance": False, "operator_alert": True}),
                    enabled=True,
                    priority=2
                ),
                AlertRuleModel(
                    rule_id="RULE-004",
                    name="Unknown Person — Any Zone",
                    description="Trigger HIGH alert whenever an unknown person is detected in any zone.",
                    condition_json=json.dumps({"person_type": "UNKNOWN"}),
                    action_json=json.dumps({"severity": "HIGH", "create_event": True, "tracking": True, "uav_assistance": False, "operator_alert": True}),
                    enabled=True,
                    priority=3
                ),
            ]
            db.add_all(rules)
            logger.info("Seeded default alert rules.")

        db.commit()
        logger.info("Database initialization and initial seeding complete.")
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to initialize database defaults: {e}", exc_info=True)
    finally:
        db.close()
