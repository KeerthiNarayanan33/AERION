import shutil
from pathlib import Path
from datetime import datetime
from backend.database.database import SessionLocal
from backend.database.models import EventModel

db = SessionLocal()

sample_events = [
    {
        'id': 'EVT_20260911_063227_2FFD65',
        'event_type': 'ZONE_INTRUSION_CRITICAL',
        'severity': 'CRITICAL',
        'camera_id': 'CAM_02',
        'radar_id': 'RADAR SYNC',
        'zone_id': 'ZONE_C',
        'object_id': 'CAM_02_TRK_119',
        'object_class': 'car',
        'confidence': 0.92,
        'status': 'ACTIVE',
        'display_time': '07:32:14 AM',
        'description': 'Vehicle detected moving at high speed in restricted zone. Matches known pattern for unauthorized access. High confidence match with previous incidents.'
    },
    {
        'id': 'EVT_20260911_063227_1F5CE7',
        'event_type': 'ZONE_INTRUSION_CRITICAL',
        'severity': 'CRITICAL',
        'camera_id': 'CAM_02',
        'radar_id': 'RADAR SYNC',
        'zone_id': 'ZONE_C',
        'object_id': 'CAM_02_TRK_117',
        'object_class': 'car',
        'confidence': 0.94,
        'status': 'ACKNOWLEDGED',
        'display_time': '07:32:14 AM',
        'description': 'Secondary vehicle corroboration in restricted perimeter sector.'
    },
    {
        'id': 'EVT_20260911_063226_7AB98D',
        'event_type': 'VEHICLE_SPEED_WARNING',
        'severity': 'MEDIUM',
        'camera_id': 'CAM_02',
        'radar_id': 'RADAR SYNC',
        'zone_id': 'ZONE_B',
        'object_id': 'CAM_02_TRK_116',
        'object_class': 'truck',
        'confidence': 0.89,
        'status': 'RESOLVED',
        'display_time': '07:32:26 AM',
        'description': 'Supply vehicle speed advisory resolved by logistics guard.'
    },
    {
        'id': 'EVT_20260911_063226_72AEF1',
        'event_type': 'ZONE_INTRUSION_CRITICAL',
        'severity': 'CRITICAL',
        'camera_id': 'CAM_02',
        'radar_id': 'RADAR SYNC',
        'zone_id': 'ZONE_C',
        'object_id': 'CAM_02_TRK_115',
        'object_class': 'car',
        'confidence': 0.95,
        'status': 'ACTIVE',
        'display_time': '07:32:24 AM',
        'description': 'Unauthorized perimeter approach detected by Cam 02 and Radar fusion.'
    },
    {
        'id': 'EVT_20260911_063224_54AE1B',
        'event_type': 'VEHICLE_APPROACH',
        'severity': 'MEDIUM',
        'camera_id': 'CAM_02',
        'radar_id': 'RADAR SYNC',
        'zone_id': 'ZONE_B',
        'object_id': 'CAM_02_TRK_111',
        'object_class': 'car',
        'confidence': 0.78,
        'status': 'FALSE_POSITIVE',
        'display_time': '07:32:26 AM',
        'description': 'Reflective road glare classified as false positive anomaly.'
    },
    {
        'id': 'EVT_20260911_063223_42D63D',
        'event_type': 'ZONE_INTRUSION_CRITICAL',
        'severity': 'CRITICAL',
        'camera_id': 'CAM_02',
        'radar_id': 'RADAR SYNC',
        'zone_id': 'ZONE_C',
        'object_id': 'CAM_02_TRK_110',
        'object_class': 'car',
        'confidence': 0.91,
        'status': 'ACKNOWLEDGED',
        'display_time': '07:32:20 AM',
        'description': 'Vehicle maneuver flagged for active tactical inspection.'
    },
    {
        'id': 'EVT_20260911_063223_930790',
        'event_type': 'PERIMETER_APPROACH',
        'severity': 'MEDIUM',
        'camera_id': 'CAM_02',
        'radar_id': 'RADAR SYNC',
        'zone_id': 'ZONE_B',
        'object_id': 'CAM_02_TRK_106',
        'object_class': 'car',
        'confidence': 0.85,
        'status': 'RESOLVED',
        'display_time': '07:32:16 AM',
        'description': 'Patrol team vehicle cleared via sector gate B.'
    },
    {
        'id': 'EVT_20260911_063221_ADD669',
        'event_type': 'ZONE_INTRUSION_CRITICAL',
        'severity': 'CRITICAL',
        'camera_id': 'CAM_02',
        'radar_id': 'RADAR SYNC',
        'zone_id': 'ZONE_C',
        'object_id': 'CAM_02_TRK_105',
        'object_class': 'car',
        'confidence': 0.93,
        'status': 'ACTIVE',
        'display_time': '07:32:14 AM',
        'description': 'Border fence sensor trigger requiring immediate operator review.'
    }
]

# Push timestamps into the future of any other existing records so they sit right at the top
top_time = datetime(2026, 9, 11, 12, 0, 0)
for i, ev_data in enumerate(sample_events):
    ev_id = ev_data['id']
    ev = db.query(EventModel).filter(EventModel.id == ev_id).first()
    if not ev:
        ev = EventModel(
            id=ev_id,
            event_type=ev_data['event_type'],
            severity=ev_data['severity'],
            camera_id=ev_data['camera_id'],
            radar_id=ev_data['radar_id'],
            zone_id=ev_data['zone_id'],
            object_id=ev_data['object_id'],
            object_class=ev_data['object_class'],
            confidence=ev_data['confidence'],
            status=ev_data['status'],
            start_time=datetime(2026, 9, 11, 7, 32, 14, 990000 - i * 10000),
            description=ev_data['description'],
            snapshot_path=f'storage/snapshots/{ev_id}.jpg'
        )
        db.add(ev)
    else:
        ev.severity = ev_data['severity']
        ev.camera_id = ev_data['camera_id']
        ev.radar_id = ev_data['radar_id']
        ev.zone_id = ev_data['zone_id']
        ev.object_id = ev_data['object_id']
        ev.object_class = ev_data['object_class']
        ev.confidence = ev_data['confidence']
        ev.status = ev_data['status']
        # Realistic creation timestamp matching event ID morning timeframe:
        ev.start_time = datetime(2026, 9, 11, 6, 32, max(1, 27 - i), 900000 - i * 10000)
        ev.snapshot_path = f'storage/snapshots/{ev_id}.jpg'

db.commit()

print('Database events updated.')

# Ensure snapshots exist
snap_dir = Path('storage/snapshots')
snap_dir.mkdir(parents=True, exist_ok=True)
master_snap = snap_dir / 'EVT_20260911_063227_2FFD65.jpg'
if not master_snap.exists():
    found = list(snap_dir.glob('*.jpg'))
    if found:
        shutil.copy(found[0], master_snap)

if master_snap.exists():
    for item in sample_events:
        dst = snap_dir / f"{item['id']}.jpg"
        if not dst.exists():
            shutil.copy(master_snap, dst)
print('Snapshots ready.')
