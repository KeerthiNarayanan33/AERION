/**
 * AERION Standalone Client-Side Simulation & Mock Engine (Comprehensive SIH Edition)
 * Enables 100% full functionality for all 12 command center tabs on Vercel without a backend server:
 * 1. Dashboard HUD (Live video feeds, KPI counters, alert feed)
 * 2. Live Cameras (Multi-grid, camera switching, aspect ratio, mirror, real webcam toggle)
 * 3. Radar Sweep (Polar 2D sweep canvas, animated blips, Doppler velocity vectors)
 * 4. Surveillance Zones (Polygonal ray-casting map, 2D Gaussian heatmap, corridor vulnerability rankings)
 * 5. Security Events (Forensic audit table, KPI cards, CSV export, tamper-evident SHA-256 seal)
 * 6. UAV Recon (Waypoint flight map, FLIR thermal optical HUD, drone controls, rotor test)
 * 7. Authorized People (Full CRUD, access levels, allowed zones, activity history)
 * 8. Site Location (GPS georeferencing, forward outpost site coordinates, zone summary)
 * 9. Devices & I/O (Input/output matrix, alert rule engine with add/toggle/delete)
 * 10. System Telemetry (Hardware status, NVIDIA GPU metrics, tactical mesh topology)
 * 11. System Config (AI inference FPS, YOLO confidence, ring buffer duration, privacy blur)
 * 12. SIH 2026 Demo Suite (All 8 scenarios: Patrol, Breach, Vehicle ANPR, Gap, UAV, Re-ID, RF Jamming, Mesh)
 */

(function () {
    // Detect environment: Check if running with an active local backend or remote gateway
    const isLocalOrigin = (
        window.location.hostname === 'localhost' ||
        window.location.hostname === '127.0.0.1' ||
        window.location.port === '8000' ||
        window.location.port === '8443'
    );
    const hasCustomBackend = !!(window.AERION_BACKEND_URL && window.AERION_BACKEND_URL.trim().length > 0);
    const forceStandalone = window.location.search.includes('standalone=true') || window.location.search.includes('mock=true');
    const isHFSpace = window.location.hostname.includes('hf.space') || window.location.hostname.includes('huggingface.co');
    const isStandaloneMode = forceStandalone || (!isLocalOrigin && !hasCustomBackend && (window.location.hostname.includes('vercel.app') || isHFSpace || window.location.protocol === 'file:'));

    if (isStandaloneMode) {
        console.log('[AERION] Initializing Comprehensive Standalone Engine for Static/Vercel hosting...');
    } else {
        console.log('[AERION] Active Backend detected at ' + (window.AERION_BACKEND_URL || window.location.origin) + '. Standalone engine in passive fallback mode.');
    }

    // Persistent in-memory data store for standalone session
    const db = {
        systemMode: 'SIMULATION',
        site: {
            site_id: 'SECTOR-NORTH-04',
            site_name: 'Jammu International Border Forward Base Alpha',
            country: 'India',
            state: 'Jammu & Kashmir',
            city: 'RS Pura Sector',
            address: 'Forward Post Bravo, Post 44, Line of Control',
            latitude: 32.7266,
            longitude: 74.8570,
            description: 'Tactical Multi-Sensor Integrated Early Warning Border Outpost.',
            updated_at: new Date().toISOString()
        },
        settings: {
            AI_INFERENCE_FPS: 30,
            DETECTION_CONFIDENCE: 0.65,
            EVENT_COOLDOWN_SECONDS: 10,
            LOITERING_THRESHOLD_SECONDS: 5,
            PRE_EVENT_SECONDS: 10,
            POST_EVENT_SECONDS: 10,
            FUSION_PROJECTION_GATE: 0.85,
            UAV_RTB_BATTERY_PERCENT: 20,
            PRIVACY_BLUR_ENABLED: false,
            THREAT_SCORING_ENABLED: true,
            AUDIO_ALERTS_ENABLED: true,
            SYSTEM_MODE: 'SIMULATION'
        },
        zones: [
            {
                id: 'ZONE_A',
                name: 'Outer Patrol Sector',
                zone_type: 'NORMAL',
                zone_subtype: 'PUBLIC',
                security_level: 'LOW',
                priority: 3,
                status: 'ACTIVE',
                coordinates: [[0.05, 0.10], [0.35, 0.10], [0.35, 0.90], [0.05, 0.90]],
                color: '#00e676',
                description: 'General buffer sector. Continuous patrol monitoring.',
                center_lat: 32.7266,
                center_lon: 74.8570,
                radius_m: 120.0,
                assigned_cameras: ['CAM_01'],
                assigned_radar: ['RADAR_01'],
                assigned_uav: [],
                authorized_persons: ['PERSON-001', 'AUTH-001', 'AUTH-002', 'AUTH-003']
            },
            {
                id: 'ZONE_B',
                name: 'Warning Approach Sector',
                zone_type: 'WARNING',
                zone_subtype: 'STAFF_ONLY',
                security_level: 'MEDIUM',
                priority: 2,
                status: 'ACTIVE',
                coordinates: [[0.35, 0.10], [0.65, 0.10], [0.65, 0.90], [0.35, 0.90]],
                color: '#ffab00',
                description: 'Intermediate warning perimeter. Heightened alert when crossed.',
                center_lat: 32.7290,
                center_lon: 74.8590,
                radius_m: 80.0,
                assigned_cameras: ['CAM_01', 'CAM_02'],
                assigned_radar: ['RADAR_01'],
                assigned_uav: ['UAV_01'],
                authorized_persons: ['PERSON-001', 'AUTH-001', 'AUTH-002']
            },
            {
                id: 'ZONE_C',
                name: 'Restricted Border Fence',
                zone_type: 'RESTRICTED',
                zone_subtype: 'CRITICAL',
                security_level: 'CRITICAL',
                priority: 1,
                status: 'ACTIVE',
                coordinates: [[0.65, 0.10], [0.95, 0.10], [0.95, 0.90], [0.65, 0.90]],
                color: '#ff1744',
                description: 'Critical zero-tolerance exclusion zone. Triggers critical alarms.',
                center_lat: 32.7315,
                center_lon: 74.8610,
                radius_m: 50.0,
                assigned_cameras: ['CAM_02'],
                assigned_radar: ['RADAR_01'],
                assigned_uav: ['UAV_01'],
                authorized_persons: ['PERSON-001']
            }
        ],
        persons: [
            {
                person_id: 'PERSON-001',
                name: 'Keerthi Narayanan',
                employee_id: 'BSF-4421',
                department: 'Operations',
                role: 'Security Administrator',
                access_level: 'ADMIN',
                status: 'AUTHORIZED',
                allowed_zones: ['ZONE_A', 'ZONE_B', 'ZONE_C'],
                phone: '+91 98400 12345',
                email: 'keerthi.n@sentinel-ai.gov',
                notes: 'Primary security administrator. Full site clearance.',
                valid_from: '2026-01-01T00:00:00Z',
                valid_until: '2027-12-31T23:59:59Z',
                created_at: '2026-01-01T00:00:00Z',
                updated_at: new Date().toISOString()
            },
            {
                person_id: 'AUTH-002',
                name: 'Arun Kumar',
                employee_id: 'BSF-4422',
                department: 'Intelligence',
                role: 'Operations Officer',
                access_level: 'ELEVATED',
                status: 'AUTHORIZED',
                allowed_zones: ['ZONE_A', 'ZONE_B'],
                phone: '+91 98400 23456',
                email: 'arun.k@sentinel-ai.gov',
                notes: 'Cleared for patrol sectors and warning approach.',
                valid_from: '2026-01-01T00:00:00Z',
                valid_until: '2027-06-30T23:59:59Z',
                created_at: '2026-01-01T00:00:00Z',
                updated_at: new Date().toISOString()
            },
            {
                person_id: 'AUTH-003',
                name: 'Meena Raj',
                employee_id: 'BSF-4423',
                department: 'Technical',
                role: 'Control Room Operator',
                access_level: 'STANDARD',
                status: 'AUTHORIZED',
                allowed_zones: ['ZONE_A'],
                phone: '+91 98400 34567',
                email: 'meena.r@sentinel-ai.gov',
                notes: 'Restricted to outer patrol sector baseline.',
                valid_from: '2026-06-01T00:00:00Z',
                valid_until: '2027-12-31T23:59:59Z',
                created_at: '2026-01-01T00:00:00Z',
                updated_at: new Date().toISOString()
            }
        ],
        alertRules: [
            {
                rule_id: 'RULE-01',
                name: 'Restricted Zone Incursion Trigger',
                priority: 'CRITICAL',
                condition: "target.zone_type == 'RESTRICTED'",
                action: { severity: 'CRITICAL', trigger_uav: true, alert_sound: true, log_incident: true },
                enabled: true
            },
            {
                rule_id: 'RULE-02',
                name: 'Optical Surveillance Gap Handover',
                priority: 'HIGH',
                condition: "camera.status == 'OFFLINE' && radar.target_detected == true",
                action: { severity: 'HIGH', trigger_uav: true, alert_sound: true, log_incident: true },
                enabled: true
            },
            {
                rule_id: 'RULE-03',
                name: 'Vehicle Hotlist License Plate Match',
                priority: 'HIGH',
                condition: 'anpr.is_hotlisted == true',
                action: { severity: 'HIGH', trigger_uav: false, alert_sound: true, log_incident: true },
                enabled: true
            },
            {
                rule_id: 'RULE-04',
                name: 'Unverified Night Crawl Anomaly',
                priority: 'MEDIUM',
                condition: "posture.type == 'CRAWLING' && ambient.light < 0.2",
                action: { severity: 'MEDIUM', trigger_uav: true, alert_sound: false, log_incident: true },
                enabled: true
            }
        ],
        events: [
            {
                id: 'EVT_20260919_104201_BREACH',
                event_type: 'ZONE_BREACH',
                zone_id: 'ZONE_C',
                zone_name: 'Restricted Border Fence',
                camera_id: 'CAM_02',
                severity: 'CRITICAL',
                peak_severity: 'CRITICAL',
                status: 'ACTIVE',
                object_class: 'person',
                track_id: 44,
                confidence: 0.94,
                start_time: new Date(Date.now() - 180000).toISOString(),
                created_at: new Date(Date.now() - 180000).toISOString(),
                description: 'Restricted fence boundary breach detected via 24GHz FMCW Radar + Optical confirmation.',
                has_video: true,
                snapshot_path: 'data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="320" height="180"><rect width="100%" height="100%" fill="%230b1329"/><circle cx="160" cy="90" r="40" fill="none" stroke="%23ff1744" stroke-width="2"/><text x="160" y="94" fill="%23ff1744" font-family="monospace" font-size="11" font-weight="bold" text-anchor="middle">CRITICAL BREACH SNAPSHOT</text></svg>'
            },
            {
                id: 'EVT_20260919_103815_WARN',
                event_type: 'ZONE_APPROACH',
                zone_id: 'ZONE_B',
                zone_name: 'Warning Approach Sector',
                camera_id: 'CAM_01',
                severity: 'HIGH',
                peak_severity: 'HIGH',
                status: 'ACKNOWLEDGED',
                object_class: 'person',
                track_id: 41,
                confidence: 0.89,
                start_time: new Date(Date.now() - 450000).toISOString(),
                created_at: new Date(Date.now() - 450000).toISOString(),
                description: 'Rapid approach towards inner security perimeter.',
                has_video: true,
                snapshot_path: 'data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="320" height="180"><rect width="100%" height="100%" fill="%230b1329"/><circle cx="160" cy="90" r="40" fill="none" stroke="%23ffab00" stroke-width="2"/><text x="160" y="94" fill="%23ffab00" font-family="monospace" font-size="11" font-weight="bold" text-anchor="middle">WARNING APPROACH SNAPSHOT</text></svg>'
            },
            {
                id: 'EVT_20260919_102005_ANPR',
                event_type: 'HOTLIST_VEHICLE',
                zone_id: 'ZONE_A',
                zone_name: 'Outer Patrol Sector',
                camera_id: 'CAM_01',
                severity: 'HIGH',
                peak_severity: 'HIGH',
                status: 'RESOLVED',
                object_class: 'truck',
                track_id: 38,
                confidence: 0.98,
                start_time: new Date(Date.now() - 1200000).toISOString(),
                created_at: new Date(Date.now() - 1200000).toISOString(),
                description: 'Hotlisted vehicle license plate PB-08-AX-9921 flagged at checkpoint.',
                has_video: true,
                snapshot_path: 'data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="320" height="180"><rect width="100%" height="100%" fill="%230b1329"/><rect x="40" y="70" width="240" height="40" fill="%23fff" stroke="%23000" stroke-width="2"/><text x="160" y="95" fill="%23000" font-family="monospace" font-size="14" font-weight="bold" text-anchor="middle">PB-08-AX-9921</text></svg>'
            }
        ],
        anprRecords: [
            {
                id: 'ANPR_REC_01',
                vehicle_track_id: 38,
                plate_text: 'PB-08-AX-9921 (TRUCK GREEN)',
                clean_plate: 'PB-08-AX-9921',
                confidence: 0.98,
                is_readable: true,
                vehicle_type: 'TRUCK',
                vehicle_color: 'GREEN',
                camera_id: 'CAM_01',
                is_hotlisted: true,
                snapshot_path: 'data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="120" height="40"><rect width="100%" height="100%" fill="%23fff" stroke="%23000" stroke-width="2"/><text x="60" y="25" fill="%23000" font-family="monospace" font-size="11" font-weight="bold" text-anchor="middle">PB-08-AX-9921</text></svg>',
                timestamp: new Date(Date.now() - 320000).toISOString()
            },
            {
                id: 'ANPR_REC_02',
                vehicle_track_id: 550,
                plate_text: 'JK-02-BB-4421 (SUV BLACK)',
                clean_plate: 'JK-02-BB-4421',
                confidence: 0.95,
                is_readable: true,
                vehicle_type: 'SUV',
                vehicle_color: 'BLACK',
                camera_id: 'CAM_01',
                is_hotlisted: false,
                snapshot_path: 'data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="120" height="40"><rect width="100%" height="100%" fill="%23fff" stroke="%23000" stroke-width="2"/><text x="60" y="25" fill="%23000" font-family="monospace" font-size="11" font-weight="bold" text-anchor="middle">JK-02-BB-4421</text></svg>',
                timestamp: new Date(Date.now() - 840000).toISOString()
            }
        ],
        // Scaled to fit within LD2450 8.0-meter radar canvas
        activeTargets: [
            { target_id: 101, id: 101, x: 0.8, y: 4.2, vx: 0.1, vy: -0.15, speed: 0.8, distance: 4.3, angle: 10.8, class_name: 'person', zone_id: 'ZONE_A', zone_type: 'NORMAL', confidence: 0.94 },
            { target_id: 102, id: 102, x: -1.5, y: 5.6, vx: -0.08, vy: -0.1, speed: 0.6, distance: 5.8, angle: -15.0, class_name: 'person', zone_id: 'ZONE_A', zone_type: 'NORMAL', confidence: 0.89 }
        ],
        cams: {
            CAM_01: { status: 'ONLINE', fps: 30.0, latency_ms: 12.4, resolution: '1920x1080' },
            CAM_02: { status: 'ONLINE', fps: 28.5, latency_ms: 19.1, resolution: '1280x720' }
        },
        uav: {
            uav_id: 'UAV_01',
            state: 'UAV_LOITER',
            status: 'LOITERING',
            armed: true,
            battery_percent: 94,
            altitude_m: 35.0,
            speed_mps: 6.5,
            heading_deg: 135.0,
            latitude: 32.7285,
            longitude: 74.8582,
            target_locked: false,
            current_zone: 'ZONE_A',
            timestamp: new Date().toISOString()
        }
    };

    let activeCamId = 'CAM_01';
    let localWebcamStream = null;
    let localWebcamVideo = null;
    let currentScenarioId = '1';

    // --- TACTICAL SVG / STREAM GENERATORS ---

    function generateTacticalCamSvg(camId, status, mode = 'LIVE') {
        const now = new Date();
        const timeStr = now.toISOString().replace('T', ' ').slice(0, 19) + '.' + String(now.getMilliseconds()).padStart(3, '0');
        const isOnline = status !== 'OFFLINE';
        const isUav = camId === 'UAV_01';
        const isCam02 = camId === 'CAM_02';

        // Target animations based on time
        const t = (now.getTime() / 1000) % 20;
        const targetX = 260 + Math.sin(t * 0.8) * 140;
        const targetY = 160 + Math.cos(t * 0.4) * 20;

        if (isUav) {
            // UAV Top-Down FLIR Thermal Feed
            const uavAlt = db.uav.altitude_m || 35.0;
            const uavBatt = db.uav.battery_percent || 94;
            const uavLocked = db.uav.target_locked;
            const lockColor = uavLocked ? '%23ff1744' : '%2310b981';

            return `data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360" viewBox="0 0 640 360">
                <rect width="100%" height="100%" fill="%2302140a"/>
                <defs>
                    <radialGradient id="flir" cx="50%" cy="50%" r="50%">
                        <stop offset="0%" stop-color="%23064e3b" stop-opacity="0.6"/>
                        <stop offset="100%" stop-color="%2302140a" stop-opacity="1"/>
                    </radialGradient>
                </defs>
                <rect width="100%" height="100%" fill="url(%23flir)"/>
                
                <!-- Compass Heading Tape -->
                <rect x="200" y="14" width="240" height="20" fill="rgba(0,0,0,0.5)" rx="3"/>
                <text x="320" y="28" fill="%2310b981" font-family="monospace" font-size="11" font-weight="bold" text-anchor="middle">◄ 030° • 045° [NE] • 060° ►</text>
                
                <!-- Target Ground Heat Signatures -->
                <circle cx="${targetX}" cy="${targetY}" r="22" fill="rgba(255,255,255,0.4)"/>
                <circle cx="${targetX}" cy="${targetY}" r="12" fill="%23ffffff"/>
                <rect x="${targetX - 25}" y="${targetY - 25}" width="50" height="50" fill="none" stroke="${lockColor}" stroke-width="2"/>
                <text x="${targetX}" y="${targetY - 32}" fill="${lockColor}" font-family="monospace" font-size="10" font-weight="bold" text-anchor="middle">TRK_UAV_LOCK [${uavLocked ? 'THREAT LOCKED' : 'SEARCHING'}]</text>

                <!-- Reticle & Horizon Pitch -->
                <circle cx="320" cy="180" r="100" fill="none" stroke="%2310b981" stroke-width="1.5" stroke-dasharray="8,6"/>
                <line x1="160" y1="180" x2="480" y2="180" stroke="%2310b981" stroke-width="1.5"/>
                <line x1="320" y1="50" x2="320" y2="310" stroke="%2310b981" stroke-width="1.5"/>
                
                <!-- Artificial Horizon Pitch Ladder -->
                <line x1="280" y1="140" x2="360" y2="140" stroke="%2310b981" stroke-width="1"/>
                <line x1="280" y1="220" x2="360" y2="220" stroke="%2310b981" stroke-width="1"/>
                
                <!-- HUD Overlays -->
                <text x="24" y="32" fill="%2310b981" font-family="monospace" font-size="12" font-weight="bold">UAV_01 // AERIAL FLIR THERMAL</text>
                <text x="24" y="52" fill="%2310b981" font-family="monospace" font-size="10">STATE: ${db.uav.state || 'AIRBORNE'}</text>
                <text x="500" y="32" fill="%2310b981" font-family="monospace" font-size="11" font-weight="bold">ALT: ${uavAlt.toFixed(1)}m</text>
                <text x="500" y="52" fill="%2310b981" font-family="monospace" font-size="10">BATT: ${uavBatt}% [●●●○]</text>
                <text x="24" y="338" fill="%2310b981" font-family="monospace" font-size="10">LAT: ${db.uav.latitude} | LON: ${db.uav.longitude} | SPD: ${db.uav.speed_mps} m/s</text>
                <text x="470" y="338" fill="%2310b981" font-family="monospace" font-size="10">GIMBAL: -45.0° | 30 FPS</text>
            </svg>`;
        }

        // CAM_01 or CAM_02 Ground Perimeter Feed
        const themeColor = isCam02 ? '%23ffab00' : '%2300e5ff';
        const sectorName = isCam02 ? 'RESTRICTED PERIMETER FENCE (SECTOR C)' : 'BORDER PATROL SECTOR (SECTOR B)';
        const isBreach = currentScenarioId === '2' || (db.events[0] && db.events[0].severity === 'CRITICAL');
        const borderColor = isBreach ? '%23ff1744' : themeColor;

        return `data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360" viewBox="0 0 640 360">
            <!-- Background Night-Vision Horizon -->
            <rect width="100%" height="100%" fill="%23050b18"/>
            <defs>
                <pattern id="tacticalGrid" width="30" height="30" patternUnits="userSpaceOnUse">
                    <path d="M 30 0 L 0 0 0 30" fill="none" stroke="rgba(0,229,255,0.05)" stroke-width="1"/>
                </pattern>
                <linearGradient id="horizonGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stop-color="%23030712"/>
                    <stop offset="60%" stop-color="%23081a2e"/>
                    <stop offset="100%" stop-color="%23030814"/>
                </linearGradient>
            </defs>
            <rect width="100%" height="100%" fill="url(%23horizonGrad)"/>
            <rect width="100%" height="100%" fill="url(%23tacticalGrid)"/>

            <!-- Perspective Perimeter Border Fence -->
            <line x1="0" y1="240" x2="640" y2="240" stroke="rgba(255,255,255,0.15)" stroke-width="1"/>
            <line x1="0" y1="260" x2="640" y2="260" stroke="rgba(255,255,255,0.2)" stroke-width="1.5"/>
            <line x1="0" y1="290" x2="640" y2="290" stroke="rgba(255,255,255,0.25)" stroke-width="2"/>
            <!-- Fence Posts -->
            <line x1="80" y1="220" x2="80" y2="330" stroke="rgba(255,255,255,0.3)" stroke-width="3"/>
            <line x1="200" y1="220" x2="200" y2="330" stroke="rgba(255,255,255,0.3)" stroke-width="3"/>
            <line x1="320" y1="220" x2="320" y2="330" stroke="rgba(255,255,255,0.3)" stroke-width="3"/>
            <line x1="440" y1="220" x2="440" y2="330" stroke="rgba(255,255,255,0.3)" stroke-width="3"/>
            <line x1="560" y1="220" x2="560" y2="330" stroke="rgba(255,255,255,0.3)" stroke-width="3"/>

            <!-- Corner HUD Brackets -->
            <path d="M 20 50 L 20 20 L 50 20" fill="none" stroke="${borderColor}" stroke-width="2"/>
            <path d="M 620 50 L 620 20 L 590 20" fill="none" stroke="${borderColor}" stroke-width="2"/>
            <path d="M 20 310 L 20 340 L 50 340" fill="none" stroke="${borderColor}" stroke-width="2"/>
            <path d="M 620 310 L 620 340 L 590 340" fill="none" stroke="${borderColor}" stroke-width="2"/>

            <!-- Center Targeting Reticle -->
            <circle cx="320" cy="180" r="30" fill="none" stroke="rgba(0,229,255,0.3)" stroke-width="1" stroke-dasharray="4,4"/>
            <line x1="290" y1="180" x2="350" y2="180" stroke="${borderColor}" stroke-width="1.5"/>
            <line x1="320" y1="150" x2="320" y2="210" stroke="${borderColor}" stroke-width="1.5"/>

            ${isBreach ? `
            <!-- CRITICAL BREACH OVERLAY -->
            <rect x="0" y="0" width="640" height="360" fill="none" stroke="%23ff1744" stroke-width="6"/>
            <rect x="${targetX - 35}" y="${targetY - 50}" width="70" height="120" fill="rgba(255,23,68,0.18)" stroke="%23ff1744" stroke-width="2.5"/>
            <rect x="${targetX - 35}" y="${targetY - 68}" width="140" height="18" fill="%23ff1744"/>
            <text x="${targetX - 32}" y="${targetY - 55}" fill="%23ffffff" font-family="monospace" font-size="10" font-weight="bold">⚠ INTRUDER #666 [99%]</text>
            <text x="${targetX - 32}" y="${targetY + 85}" fill="%23ff1744" font-family="monospace" font-size="9" font-weight="bold">FENCE INTRUSION DETECTED</text>
            ` : `
            <!-- NORMAL PEDESTRIAN TRACK -->
            <rect x="${targetX - 30}" y="${targetY - 45}" width="60" height="110" fill="rgba(0,229,255,0.08)" stroke="%2300e5ff" stroke-width="1.5"/>
            <rect x="${targetX - 30}" y="${targetY - 62}" width="110" height="17" fill="%2300e5ff"/>
            <text x="${targetX - 27}" y="${targetY - 50}" fill="%23030712" font-family="monospace" font-size="10" font-weight="bold">PERSON #101 [96%]</text>
            <text x="${targetX - 27}" y="${targetY + 78}" fill="%2300e5ff" font-family="monospace" font-size="9">SPEED: 1.2m/s | DIST: 3.8m</text>
            `}

            <!-- Header Info -->
            <text x="28" y="38" fill="${borderColor}" font-family="monospace" font-size="12" font-weight="bold">AERION SENTINEL // ${camId}</text>
            <text x="28" y="54" fill="rgba(255,255,255,0.7)" font-family="monospace" font-size="9">${sectorName}</text>
            <text x="440" y="38" fill="%2310b981" font-family="monospace" font-size="11" font-weight="bold">REC [●] ${timeStr}</text>

            <!-- Bottom Telemetry Bar -->
            <rect x="20" y="324" width="600" height="20" fill="rgba(0,0,0,0.6)" rx="2"/>
            <text x="28" y="338" fill="rgba(255,255,255,0.8)" font-family="monospace" font-size="10">FPS: 30.0 | RES: 1920x1080 | OPTICAL AI: YOLOv8 | STATUS: ${status} | COORD: 32.7266°N, 74.8570°E</text>
        </svg>`;
    }

    function generateTacticalQrSvg() {
        return `data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="240" height="240" viewBox="0 0 240 240">
            <rect width="100%" height="100%" fill="%23050b18" rx="8"/>
            <path d="M 12 36 L 12 12 L 36 12" fill="none" stroke="%2300e5ff" stroke-width="3"/>
            <path d="M 228 36 L 228 12 L 204 12" fill="none" stroke="%2300e5ff" stroke-width="3"/>
            <path d="M 12 204 L 12 228 L 36 228" fill="none" stroke="%2300e5ff" stroke-width="3"/>
            <path d="M 228 204 L 228 228 L 204 228" fill="none" stroke="%2300e5ff" stroke-width="3"/>
            <rect x="36" y="36" width="48" height="48" fill="none" stroke="%2300e5ff" stroke-width="6" rx="4"/>
            <rect x="48" y="48" width="24" height="24" fill="%2300e5ff" rx="2"/>
            <rect x="156" y="36" width="48" height="48" fill="none" stroke="%2300e5ff" stroke-width="6" rx="4"/>
            <rect x="168" y="48" width="24" height="24" fill="%2300e5ff" rx="2"/>
            <rect x="36" y="156" width="48" height="48" fill="none" stroke="%2300e5ff" stroke-width="6" rx="4"/>
            <rect x="48" y="168" width="24" height="24" fill="%2300e5ff" rx="2"/>
            <rect x="100" y="40" width="12" height="12" fill="%2300e5ff"/>
            <rect x="120" y="40" width="12" height="12" fill="%2300e5ff"/>
            <rect x="100" y="60" width="12" height="12" fill="%2300e5ff"/>
            <rect x="130" y="70" width="12" height="12" fill="%2300e5ff"/>
            <rect x="40" y="100" width="12" height="12" fill="%2300e5ff"/>
            <rect x="60" y="110" width="12" height="12" fill="%2300e5ff"/>
            <rect x="80" y="100" width="12" height="12" fill="%2300e5ff"/>
            <rect x="100" y="100" width="12" height="12" fill="%2310b981"/>
            <rect x="120" y="110" width="12" height="12" fill="%2300e5ff"/>
            <rect x="140" y="100" width="12" height="12" fill="%2300e5ff"/>
            <rect x="160" y="110" width="12" height="12" fill="%2300e5ff"/>
            <rect x="180" y="100" width="12" height="12" fill="%2300e5ff"/>
            <rect x="100" y="130" width="12" height="12" fill="%2300e5ff"/>
            <rect x="120" y="140" width="12" height="12" fill="%2310b981"/>
            <rect x="140" y="130" width="12" height="12" fill="%2300e5ff"/>
            <rect x="100" y="160" width="12" height="12" fill="%2300e5ff"/>
            <rect x="130" y="170" width="12" height="12" fill="%2300e5ff"/>
            <rect x="160" y="160" width="12" height="12" fill="%2300e5ff"/>
            <rect x="180" y="180" width="12" height="12" fill="%2300e5ff"/>
            <text x="120" y="222" fill="%2300e5ff" font-family="monospace" font-size="9" text-anchor="middle" font-weight="bold">SCAN FOR MOBILE STREAM</text>
        </svg>`;
    }

    // Expose helpers globally
    window.generateTacticalCamSvg = generateTacticalCamSvg;
    window.generateTacticalQrSvg = generateTacticalQrSvg;

    // --- HTMLImageElement INTERCEPTOR FOR ZERO 404S ---
    const originalSrcDesc = Object.getOwnPropertyDescriptor(HTMLImageElement.prototype, 'src');
    if (originalSrcDesc && originalSrcDesc.set) {
        Object.defineProperty(HTMLImageElement.prototype, 'src', {
            set: function (val) {
                if (typeof val === 'string') {
                    // Check remote backend first
                    if (window.AERION_BACKEND_URL && window.AERION_BACKEND_URL.trim().length > 0) {
                        const b = window.AERION_BACKEND_URL.replace(/\/+$/, '');
                        if (val.startsWith('/api/') || val.startsWith('/storage/')) {
                            val = b + val;
                        }
                        return originalSrcDesc.set.call(this, val);
                    }

                    // Otherwise intercept in standalone simulation mode ONLY if no active backend is present
                    if (isStandaloneMode) {
                        if (val.includes('/api/cameras/') && (val.includes('/stream') || val.includes('/snapshot'))) {
                            const cid = val.includes('CAM_02') ? 'CAM_02' : (val.includes('UAV_01') ? 'UAV_01' : 'CAM_01');
                            const svgData = generateTacticalCamSvg(cid, 'ONLINE');
                            originalSrcDesc.set.call(this, svgData);
                            setTimeout(() => { try { this.dispatchEvent(new Event('load')); } catch (_) {} }, 10);
                            return;
                        }
                        if (val.includes('/api/cameras/network/qr')) {
                            const qrData = generateTacticalQrSvg();
                            originalSrcDesc.set.call(this, qrData);
                            setTimeout(() => { try { this.dispatchEvent(new Event('load')); } catch (_) {} }, 10);
                            return;
                        }
                        if (val.includes('/storage/snapshots/')) {
                            const snapData = generateTacticalCamSvg('CAM_01', 'ONLINE', 'SNAPSHOT');
                            originalSrcDesc.set.call(this, snapData);
                            setTimeout(() => { try { this.dispatchEvent(new Event('load')); } catch (_) {} }, 10);
                            return;
                        }
                    }
                }
                return originalSrcDesc.set.call(this, val);
            },
            get: function () {
                return originalSrcDesc.get.call(this);
            },
            configurable: true,
            enumerable: true
        });
    }

    function createJsonResponse(data, status = 200) {
        return new Response(JSON.stringify(data), {
            status: status,
            headers: { 'Content-Type': 'application/json' }
        });
    }

    // --- FETCH INTERCEPTOR FOR STANDALONE REST APIS ---
    function setupMockApiInterceptor() {
        const origFetch = window.fetch;

        window.fetch = async function (resource, init = {}) {
            const urlStr = typeof resource === 'string' ? resource : (resource ? resource.url : '');
            const method = (init.method || 'GET').toUpperCase();

            // If user specified remote backend, bypass local simulation
            if (window.AERION_BACKEND_URL && window.AERION_BACKEND_URL.trim().length > 0) {
                const b = window.AERION_BACKEND_URL.replace(/\/+$/, '');
                if (typeof resource === 'string' && (resource.startsWith('/api/') || resource.startsWith('/storage/'))) {
                    resource = b + resource;
                }
                return origFetch(resource, init);
            }

            // If active local backend exists, pass through directly to real backend
            if (!isStandaloneMode) {
                return origFetch(resource, init);
            }

            // --- 1. SYSTEM HEALTH & METRICS ---
            if (urlStr.includes('/api/system/health')) {
                return createJsonResponse({
                    status: 'ONLINE',
                    system_mode: db.systemMode,
                    host_metrics: {
                        cpu_percent: 24.2 + (Math.sin(Date.now() / 3000) * 5),
                        memory_percent: 42.8,
                        gpu_percent: 36.5 + (Math.cos(Date.now() / 4000) * 8),
                        gpu_temperature_c: 54,
                        vram_used_mb: 1420,
                        disk_percent: 31.4,
                        system_uptime_seconds: 142800,
                        radar_fps: 20.0,
                        radar_latency_ms: 12.0,
                        radar_packet_loss: 0.0,
                        ai_fps: 30.2,
                        ai_latency_ms: 14.5
                    }
                });
            }

            if (urlStr.includes('/api/system/metrics')) {
                return createJsonResponse({
                    cpu_percent: 24.2 + (Math.sin(Date.now() / 3000) * 5),
                    memory_percent: 42.8,
                    gpu_percent: 36.5 + (Math.cos(Date.now() / 4000) * 8),
                    gpu_temperature_c: 54,
                    vram_used_mb: 1420,
                    disk_percent: 31.4,
                    radar_fps: 20.0,
                    ai_fps: 30.2
                });
            }

            if (urlStr.includes('/api/system/settings')) {
                if (method === 'PUT' || method === 'POST') {
                    try {
                        const body = typeof init.body === 'string' ? JSON.parse(init.body) : init.body;
                        if (urlStr.includes('SYSTEM_MODE') && body && body.value) {
                            db.systemMode = body.value;
                        } else if (body) {
                            Object.assign(db.settings, body);
                        }
                    } catch (_) {}
                    return createJsonResponse({ success: true, settings: db.settings });
                }
                return createJsonResponse({ settings: db.settings });
            }

            // --- 2. ZONES & THREAT HEATMAP ---
            if (urlStr.includes('/api/zones')) {
                if (method === 'PATCH' && urlStr.includes('/name')) {
                    const parts = urlStr.split('/api/zones/')[1].split('/name');
                    const zid = parts[0];
                    try {
                        const body = JSON.parse(init.body);
                        const z = db.zones.find(x => x.id === zid);
                        if (z && body.name) z.name = body.name;
                    } catch (_) {}
                    return createJsonResponse({ success: true });
                }
                return createJsonResponse(db.zones);
            }

            if (urlStr.includes('/api/analytics/threat-heatmap')) {
                const grid = [];
                for (let r = 0; r < 12; r++) {
                    const row = [];
                    for (let c = 0; c < 12; c++) {
                        const d1 = Math.hypot(r - 4, c - 8);
                        const d2 = Math.hypot(r - 8, c - 3);
                        const val = Math.max(0, 0.95 * Math.exp(-d1 / 3.0) + 0.65 * Math.exp(-d2 / 2.5));
                        row.push(parseFloat(val.toFixed(2)));
                    }
                    grid.push(row);
                }
                return createJsonResponse({
                    density_grid: grid,
                    total_points: 340,
                    peak_zone: 'ZONE_C',
                    peak_intensity: 0.94,
                    timestamp: new Date().toISOString()
                });
            }

            // --- 3. CAMERAS, STREAMS & NETWORK QR ---
            if (urlStr.includes('/api/cameras/network/info')) {
                return createJsonResponse({
                    local_ip: '192.168.1.44',
                    available_ips: ['192.168.1.44', '10.0.0.12', '127.0.0.1'],
                    mobile_stream_url: 'https://192.168.1.44:8443/mobile.html',
                    mobile_stream_url_https: 'https://192.168.1.44:8443/mobile.html',
                    mobile_stream_url_http: 'http://192.168.1.44:8000/mobile.html',
                    port_https: 8443,
                    port_http: 8000,
                    status: 'READY'
                });
            }

            if (urlStr.includes('/api/cameras/network/qr')) {
                const qrSvg = generateTacticalQrSvg();
                return new Response(qrSvg, { status: 200, headers: { 'Content-Type': 'image/svg+xml' } });
            }

            if (urlStr.includes('/api/cameras') && (urlStr.includes('/stream') || urlStr.includes('/snapshot'))) {
                const cid = urlStr.includes('CAM_02') ? 'CAM_02' : (urlStr.includes('UAV_01') ? 'UAV_01' : 'CAM_01');
                const svg = generateTacticalCamSvg(cid, db.cams[cid] ? db.cams[cid].status : 'ONLINE');
                return new Response(svg, { status: 200, headers: { 'Content-Type': 'image/svg+xml' } });
            }

            if (urlStr.includes('/api/cameras')) {
                return createJsonResponse([
                    {
                        id: 'CAM_01',
                        name: 'CAM_01 // Tactical Border Perimeter',
                        type: 'WEBCAM',
                        source: 'simulation',
                        status: db.cams.CAM_01.status,
                        resolution: db.cams.CAM_01.resolution,
                        fps: db.cams.CAM_01.fps,
                        latency_ms: db.cams.CAM_01.latency_ms,
                        frame_count: 9140,
                        dropped_frames: 0,
                        zone_id: 'ZONE_A',
                        enabled: true
                    },
                    {
                        id: 'CAM_02',
                        name: 'CAM_02 // Mobile Tactical Recon',
                        type: 'MOBILE_STREAM',
                        source: 'simulation',
                        status: db.cams.CAM_02.status,
                        resolution: db.cams.CAM_02.resolution,
                        fps: db.cams.CAM_02.fps,
                        latency_ms: db.cams.CAM_02.latency_ms,
                        frame_count: 8120,
                        dropped_frames: 1,
                        zone_id: 'ZONE_B',
                        enabled: true
                    },
                    {
                        id: 'UAV_01',
                        name: 'UAV_01 // Aerial FLIR Thermal Gimbal',
                        type: 'DRONE_FEED',
                        source: 'simulation',
                        status: 'ONLINE',
                        resolution: '1280x720',
                        fps: 30.0,
                        latency_ms: 18.0,
                        frame_count: 5400,
                        dropped_frames: 0,
                        zone_id: 'DYNAMIC_RECON',
                        enabled: true
                    }
                ]);
            }

            // --- 4. RADAR & UAV RECON ---
            if (urlStr.includes('/api/radar/fused-targets')) {
                return createJsonResponse({
                    count: db.activeTargets.length,
                    fused_tracks: db.activeTargets,
                    timestamp: new Date().toISOString()
                });
            }

            if (urlStr.includes('/api/radar/simulate-target')) {
                const newT = {
                    target_id: 300 + db.activeTargets.length,
                    id: 300 + db.activeTargets.length,
                    x: (Math.random() * 4 - 2),
                    y: 2.0 + Math.random() * 4,
                    vx: 0.2,
                    vy: -0.1,
                    speed: 1.1,
                    distance: 3.5,
                    angle: 12.0,
                    class_name: 'person',
                    zone_id: 'ZONE_B',
                    confidence: 0.92
                };
                db.activeTargets.push(newT);
                dispatchWs('RADAR_TARGETS_UPDATE', { sensor_id: 'RADAR_01', targets: db.activeTargets });
                return createJsonResponse({ success: true, target: newT });
            }

            if (urlStr.includes('/api/radar/ingest')) {
                return createJsonResponse({ success: true, ingested: true });
            }

            if (urlStr.includes('/api/uav/telemetry')) {
                return createJsonResponse(db.uav);
            }

            if (urlStr.includes('/api/uav/')) {
                if (urlStr.includes('patrol') || urlStr.includes('verification-request')) {
                    db.uav.state = 'UAV_PATROL';
                    db.uav.status = 'EN_ROUTE_ZONE_C';
                    db.uav.speed_mps = 12.0;
                    db.uav.altitude_m = 45.0;
                    dispatchWs('UAV_TELEMETRY_UPDATE', db.uav);
                    return createJsonResponse({ status: 'EN_ROUTE', telemetry: db.uav });
                }
                if (urlStr.includes('rtb')) {
                    db.uav.state = 'UAV_RTB';
                    db.uav.status = 'RETURNING_TO_BASE';
                    db.uav.speed_mps = 8.0;
                    db.uav.altitude_m = 20.0;
                    dispatchWs('UAV_TELEMETRY_UPDATE', db.uav);
                    return createJsonResponse({ status: 'RTB', telemetry: db.uav });
                }
                if (urlStr.includes('abort')) {
                    db.uav.state = 'UAV_STANDBY';
                    db.uav.status = 'ABORTED';
                    db.uav.altitude_m = 0.0;
                    dispatchWs('UAV_TELEMETRY_UPDATE', db.uav);
                    return createJsonResponse({ status: 'ABORTED', telemetry: db.uav });
                }
                if (urlStr.includes('rotor-test')) {
                    return createJsonResponse({ status: 'ROTOR_TEST_OK', rpm: [4200, 4210, 4190, 4205] });
                }
                return createJsonResponse({ status: 'SUCCESS', telemetry: db.uav });
            }

            // --- 5. SECURITY EVENTS & FORENSIC DOSSIER ---
            if (urlStr.includes('/api/events/summary/stats')) {
                return createJsonResponse({
                    total_events: db.events.length + 45,
                    active_breaches: db.events.filter(e => e.severity === 'CRITICAL').length,
                    pending_actions: 4,
                    compiled_vaults: 24,
                    ledger_status: '100% VERIFIED',
                    ledger_hash: 'SHA256:7B4F92C1',
                    storage_mb: 142.5,
                    max_storage_mb: 2048.0
                });
            }

            if (urlStr.includes('/api/events/export/csv')) {
                const csv = 'event_id,event_type,severity,zone_id,camera_id,timestamp\n' +
                    db.events.map(e => `${e.id},${e.event_type},${e.severity},${e.zone_id},${e.camera_id},${e.created_at}`).join('\n');
                return new Response(csv, { status: 200, headers: { 'Content-Type': 'text/csv' } });
            }

            if (urlStr.includes('/api/events') && !urlStr.includes('/acknowledge') && !urlStr.includes('/resolve')) {
                return createJsonResponse({
                    events: db.events,
                    total: db.events.length,
                    page: 1,
                    page_size: 20
                });
            }

            if (urlStr.includes('/api/events/') && (urlStr.includes('/acknowledge') || urlStr.includes('/resolve'))) {
                return createJsonResponse({ success: true, status: 'UPDATED' });
            }

            if (urlStr.includes('/api/replay/dossier')) {
                return createJsonResponse({
                    status: 'DOSSIER_GENERATED',
                    dossier_id: 'DOS_20260919_7F1A',
                    incident_id: 'INC_BREACH_744',
                    cryptographic_seal: 'SHA256:7B4F92C1D429B890A5EF',
                    legal_chain_of_custody: 'VERIFIED_MIL_STD_810G',
                    telemetry_frames: 240,
                    optical_frames: 180,
                    radar_blips: 95,
                    timestamp: new Date().toISOString()
                });
            }

            // --- 6. AUTHORIZED PEOPLE (PERSONS) ---
            if (urlStr.includes('/api/persons')) {
                if (method === 'POST') {
                    try {
                        const newP = typeof init.body === 'string' ? JSON.parse(init.body) : init.body;
                        newP.person_id = newP.person_id || `AUTH-${Date.now().toString().slice(-4)}`;
                        newP.status = 'AUTHORIZED';
                        newP.allowed_zones = newP.allowed_zones || ['ZONE_A'];
                        db.persons.unshift(newP);
                        return createJsonResponse({ success: true, person: newP });
                    } catch (_) {}
                }
                if (method === 'DELETE') {
                    const id = urlStr.split('/api/persons/')[1]?.split('?')[0];
                    db.persons = db.persons.filter(p => p.person_id !== id);
                    return createJsonResponse({ success: true });
                }
                if (urlStr.includes('/enable') || urlStr.includes('/disable')) {
                    const parts = urlStr.split('/api/persons/')[1].split('/');
                    const id = parts[0];
                    const p = db.persons.find(x => x.person_id === id);
                    if (p) p.status = urlStr.includes('/enable') ? 'AUTHORIZED' : 'DISABLED';
                    return createJsonResponse({ success: true });
                }
                if (urlStr.includes('/activity')) {
                    return createJsonResponse({
                        activities: [
                            { timestamp: new Date(Date.now() - 3600000).toISOString(), zone_id: 'ZONE_A', action: 'ENTER_ZONE', camera_id: 'CAM_01', verified: true },
                            { timestamp: new Date(Date.now() - 7200000).toISOString(), zone_id: 'ZONE_B', action: 'INSPECTION_PASS', camera_id: 'CAM_01', verified: true }
                        ],
                        total: 2
                    });
                }
                return createJsonResponse({
                    persons: db.persons,
                    total: db.persons.length
                });
            }

            // --- 7. ANPR LICENSE PLATE INTELLIGENCE ---
            if (urlStr.includes('/api/anpr')) {
                return createJsonResponse({
                    records: db.anprRecords,
                    total: db.anprRecords.length
                });
            }

            // --- 8. SITE LOCATION CONFIGURATION ---
            if (urlStr.includes('/api/site')) {
                if (method === 'POST') {
                    try {
                        const updated = typeof init.body === 'string' ? JSON.parse(init.body) : init.body;
                        Object.assign(db.site, updated);
                        db.site.updated_at = new Date().toISOString();
                    } catch (_) {}
                }
                return createJsonResponse({ site: db.site });
            }

            // --- 9. DEVICES & ALERT RULES ---
            if (urlStr.includes('/api/alert-rules')) {
                if (method === 'POST' && urlStr.includes('/toggle')) {
                    const ruleId = urlStr.split('/api/alert-rules/')[1]?.split('/')[0];
                    const r = db.alertRules.find(x => x.rule_id === ruleId);
                    if (r) r.enabled = !r.enabled;
                    return createJsonResponse({ success: true });
                }
                if (method === 'POST') {
                    try {
                        const rule = typeof init.body === 'string' ? JSON.parse(init.body) : init.body;
                        rule.rule_id = `RULE-0${db.alertRules.length + 1}`;
                        db.alertRules.push(rule);
                        return createJsonResponse({ success: true, rule });
                    } catch (_) {}
                }
                if (method === 'DELETE') {
                    const ruleId = urlStr.split('/api/alert-rules/')[1]?.split('?')[0];
                    db.alertRules = db.alertRules.filter(x => x.rule_id !== ruleId);
                    return createJsonResponse({ success: true });
                }
                return createJsonResponse({ rules: db.alertRules });
            }

            // --- 10. SYSTEM CONFIGURATION & SETTINGS ---
            if (urlStr.includes('/api/config') || urlStr.includes('/api/settings')) {
                return createJsonResponse({ settings: db.settings });
            }

            // --- 11. TACTICAL MESH TOPOLOGY ---
            if (urlStr.includes('/api/mesh/topology')) {
                return createJsonResponse({
                    active_nodes: 4,
                    topology: [
                        { id: 'NODE_01', role: 'GATEWAY', status: 'ONLINE', latency_ms: 2.1 },
                        { id: 'NODE_02', role: 'RADAR_ESP32', status: 'ONLINE', latency_ms: 4.8 },
                        { id: 'NODE_03', role: 'CAM_RELAY', status: 'ONLINE', latency_ms: 5.2 },
                        { id: 'NODE_04', role: 'UAV_DATALINK', status: 'ONLINE', latency_ms: 11.0 }
                    ]
                });
            }

            if (urlStr.includes('/api/mesh/simulate-failover')) {
                dispatchWs('TACTICAL_MESH_FAILOVER', { failed_node: 'NODE_03', rerouted_via: 'NODE_02' });
                return createJsonResponse({ status: 'FAILOVER_TRIGGERED', new_route: ['NODE_01', 'NODE_02', 'NODE_04'] });
            }

            // --- 12. EDGE AI PROFILER ---
            if (urlStr.includes('/api/ai/profiler')) {
                return createJsonResponse({
                    device: 'NVIDIA RTX 3050 (6GB VRAM)',
                    preprocess_ms: 1.8,
                    inference_ms: 8.9,
                    postprocess_ms: 2.1,
                    total_fps: 30.2,
                    memory_vram_mb: 1420
                });
            }

            // --- 13. SIH 2026 DEMO SCENARIOS ---
            if (urlStr.includes('/api/system/scenario/')) {
                const parts = urlStr.split('/api/system/scenario/');
                const scenarioId = parts[1] ? parts[1].split('?')[0] : '';
                currentScenarioId = scenarioId;
                executeSimulatedScenario(scenarioId);
                return createJsonResponse({ status: 'EXECUTING', scenario: scenarioId });
            }

            // --- 14. HARDWARE/TACTICAL EXTENSIONS ---
            if (urlStr.includes('/api/ai/handover/simulate')) {
                dispatchWs('CROSS_CAMERA_HANDOVER', {
                    track_id: 101,
                    from_camera: 'CAM_01',
                    to_camera: 'CAM_02',
                    feature_distance: 0.12,
                    confidence: 0.96
                });
                return createJsonResponse({ status: 'HANDOVER_SUCCESS' });
            }

            if (urlStr.includes('/api/radar/simulate-jamming')) {
                dispatchWs('RF_JAMMING_ALERT', {
                    channel_mhz: 24150,
                    jamming_power_dbm: -32,
                    hop_to_channel_mhz: 24220,
                    status: 'JAMMING_MITIGATED'
                });
                return createJsonResponse({ status: 'JAMMING_ALERT' });
            }

            if (urlStr.includes('/api/deterrence/')) {
                dispatchWs('DETERRENCE_STAGE_UPDATED', { stage: 2, strobe: true, siren: true, audio_db: 110 });
                return createJsonResponse({ success: true, stage: 2 });
            }

            if (urlStr.includes('/api/cuas/')) {
                dispatchWs('CUAS_STAGE_UPDATED', { status: 'NEUTRALIZED', target: 'ROGUE_UAV_09', rf_jam_active: true });
                return createJsonResponse({ success: true, status: 'CUAS_ACTIVE' });
            }

            if (urlStr.includes('/api/swarm/')) {
                dispatchWs('SWARM_TELEMETRY_UPDATE', { count: 3, leader: 'UAV_01', mode: 'FORMATION_SEARCH' });
                return createJsonResponse({ success: true, status: 'SWARM_DISPATCHED' });
            }

            if (urlStr.includes('/api/datalink/transmit')) {
                return createJsonResponse({ success: true, packets_sent: 12, encryption: 'AES-256-GCM' });
            }

            // Default fallback for any other /api/ route
            if (urlStr.startsWith('/api/') || urlStr.includes('/api/')) {
                return createJsonResponse({ success: true, status: 'STANDALONE_OK' });
            }

            // Fall through to real fetch for assets, external calls, etc.
            return origFetch(resource, init);
        };
    }

    // SIH 2026 Demo Scenarios State Machine
    function executeSimulatedScenario(scenarioId) {
        console.log(`[SCENARIO] Executing simulated scenario: ${scenarioId}`);
        currentScenarioId = scenarioId;

        if (scenarioId === '1') {
            // 1. ROUTINE PATROL
            db.activeTargets = [
                { target_id: 201, id: 201, x: -1.2, y: 4.8, vx: 0.1, vy: 0.1, speed: 0.5, distance: 4.9, angle: -14.0, class_name: 'person', zone_id: 'ZONE_A', zone_type: 'NORMAL', confidence: 0.95 }
            ];
            dispatchWs('RADAR_TARGETS_UPDATE', { sensor_id: 'RADAR_01', targets: db.activeTargets });
            dispatchWs('SCENARIO_STATUS', { scenario: 1, title: 'ROUTINE PATROL', status: 'ACTIVE' });
        } else if (scenarioId === '2') {
            // 2. BORDER BREACH
            db.activeTargets = [
                { target_id: 666, id: 666, x: 1.5, y: 2.2, vx: 0.4, vy: -0.5, speed: 2.1, distance: 2.7, angle: 34.0, class_name: 'person', zone_id: 'ZONE_C', zone_type: 'RESTRICTED', confidence: 0.98 }
            ];
            const breachEvent = {
                id: `EVT_${Date.now()}_BREACH`,
                event_type: 'ZONE_BREACH',
                zone_id: 'ZONE_C',
                zone_name: 'Restricted Border Fence',
                camera_id: 'CAM_02',
                severity: 'CRITICAL',
                peak_severity: 'CRITICAL',
                status: 'ACTIVE',
                object_class: 'person',
                track_id: 666,
                confidence: 0.98,
                created_at: new Date().toISOString(),
                description: 'CRITICAL: Hostile breach through Sector Charlie restricted fence!'
            };
            db.events.unshift(breachEvent);
            dispatchWs('RADAR_TARGETS_UPDATE', { sensor_id: 'RADAR_01', targets: db.activeTargets });
            dispatchWs('SECURITY_ALERT', { event: breachEvent });
            dispatchWs('ZONE_INTRUSION_STATE', { zone_id: 'ZONE_C', state: 'BREACH', target_count: 1 });
            dispatchWs('SCENARIO_STATUS', { scenario: 2, title: 'BORDER BREACH', status: 'CRITICAL_BREACH' });
        } else if (scenarioId === '3') {
            // 3. VEHICLE & ANPR
            dispatchWs('ANPR_PLATE_DETECTED', {
                camera_id: 'CAM_01',
                plate_number: 'DL-01-AB-1234',
                vehicle_type: 'TRUCK',
                confidence: 0.98,
                is_hotlisted: true,
                speed_kmh: 48.5,
                timestamp: new Date().toISOString()
            });
            dispatchWs('SCENARIO_STATUS', { scenario: 3, title: 'VEHICLE & ANPR', status: 'HOTLIST_MATCH' });
        } else if (scenarioId === '4') {
            // 4. CAM FAILURE & GAP
            db.cams.CAM_02.status = 'OFFLINE';
            dispatchWs('CAMERA_STATUS_CHANGED', { camera_id: 'CAM_02', status: 'OFFLINE' });
            dispatchWs('SURVEILLANCE_GAP_DETECTED', {
                camera_id: 'CAM_02',
                radar_contact: true,
                directive: 'SCRAMBLE_UAV_01'
            });
            dispatchWs('SCENARIO_STATUS', { scenario: 4, title: 'OPTICAL GAP', status: 'UAV_DISPATCH_REQUIRED' });
        } else if (scenarioId === '5') {
            // 5. UAV RECON
            db.uav.state = 'UAV_DISPATCHED';
            db.uav.status = 'INTERCEPT_INTERVENTION';
            db.uav.altitude_m = 48.0;
            db.uav.target_locked = true;
            db.uav.speed_mps = 14.5;
            dispatchWs('UAV_VERIFICATION_DISPATCHED', {
                uav_id: 'UAV_01',
                waypoint: { lat: 32.7315, lon: 74.8610 },
                status: 'EN_ROUTE'
            });
            dispatchWs('UAV_TELEMETRY_UPDATE', db.uav);
            dispatchWs('SCENARIO_STATUS', { scenario: 5, title: 'UAV RECON', status: 'TARGET_LOCKED' });
        } else if (scenarioId === 'reset') {
            // RESET
            db.cams.CAM_01.status = 'ONLINE';
            db.cams.CAM_02.status = 'ONLINE';
            db.uav.state = 'UAV_LOITER';
            db.uav.status = 'LOITERING';
            db.uav.target_locked = false;
            db.uav.altitude_m = 35.0;
            db.activeTargets = [
                { target_id: 101, id: 101, x: 0.8, y: 4.2, vx: 0.1, vy: -0.15, speed: 0.8, distance: 4.3, angle: 10.8, class_name: 'person', zone_id: 'ZONE_A', zone_type: 'NORMAL', confidence: 0.94 }
            ];
            dispatchWs('CAMERA_STATUS_CHANGED', { camera_id: 'CAM_02', status: 'ONLINE' });
            dispatchWs('RADAR_TARGETS_UPDATE', { sensor_id: 'RADAR_01', targets: db.activeTargets });
            dispatchWs('UAV_TELEMETRY_UPDATE', db.uav);
            dispatchWs('SCENARIO_STATUS', { scenario: 'reset', title: 'SYSTEM RESET', status: 'NORMAL' });
        }
    }

    // WebSocket Mock Dispatcher
    function dispatchWs(type, data) {
        if (window.wsClient && typeof window.wsClient.handleMessage === 'function') {
            window.wsClient.handleMessage({ type, data, timestamp: new Date().toISOString() });
        }
    }

    // Real Webcam Integration for Browser Demo
    async function toggleLocalWebcam() {
        const btn = document.getElementById('btnConnectLocalWebcam');
        if (localWebcamStream) {
            // Stop webcam
            localWebcamStream.getTracks().forEach(t => t.stop());
            localWebcamStream = null;
            if (localWebcamVideo) {
                localWebcamVideo.srcObject = null;
            }
            if (btn) {
                btn.style.background = 'transparent';
                btn.textContent = '📹 LIVE WEBCAM';
            }
            console.log('[WEBCAM] Local device webcam disabled.');
            return;
        }

        try {
            console.log('[WEBCAM] Requesting browser camera permissions...');
            localWebcamStream = await navigator.mediaDevices.getUserMedia({
                video: { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: 'user' }
            });

            if (!localWebcamVideo) {
                localWebcamVideo = document.createElement('video');
                localWebcamVideo.autoplay = true;
                localWebcamVideo.muted = true;
                localWebcamVideo.playsInline = true;
                localWebcamVideo.style.display = 'none';
                document.body.appendChild(localWebcamVideo);
            }
            localWebcamVideo.srcObject = localWebcamStream;
            localWebcamVideo.play();

            if (btn) {
                btn.style.background = 'rgba(234, 179, 8, 0.3)';
                btn.textContent = '📹 WEBCAM ACTIVE';
            }
            console.log('[WEBCAM] Local webcam stream initialized successfully!');
        } catch (err) {
            console.warn('[WEBCAM] Permission denied or no camera device found:', err);
            alert('Camera access was not granted or no webcam was detected on this device.');
        }
    }

    // Periodic Tactical Simulation Loops
    function startStandaloneSimulationLoop() {
        console.log('[AERION] Starting Standalone Simulation & Animation Loop...');

        // 1. Radar Targets Loop (every 100ms)
        let phase = 0;
        setInterval(() => {
            if (window.AERION_BACKEND_URL && window.AERION_BACKEND_URL.trim().length > 0) return;

            phase += 0.04;
            db.activeTargets.forEach((t, i) => {
                t.x = parseFloat((Math.sin(phase + i * 2.0) * 2.2).toFixed(2));
                t.y = parseFloat((3.6 + Math.cos(phase * 0.7 + i) * 2.2).toFixed(2));
                t.distance = parseFloat(Math.hypot(t.x, t.y).toFixed(1));
                t.angle = parseFloat((Math.atan2(t.x, t.y) * 180 / Math.PI).toFixed(1));
            });

            dispatchWs('RADAR_TARGETS_UPDATE', {
                sensor_id: 'RADAR_01',
                targets: db.activeTargets
            });
        }, 100);

        // 2. Telemetry Heartbeat (every 1.5s)
        setInterval(() => {
            if (window.AERION_BACKEND_URL && window.AERION_BACKEND_URL.trim().length > 0) return;

            dispatchWs('TELEMETRY_HEARTBEAT', {
                timestamp: new Date().toISOString(),
                system_mode: db.systemMode,
                cameras: {
                    CAM_01: { status: db.cams.CAM_01.status, fps: 30.0, latency_ms: 12.0, resolution: '1920x1080' },
                    CAM_02: { status: db.cams.CAM_02.status, fps: 28.5, latency_ms: 19.0, resolution: '1280x720' }
                },
                ai: { fps: 30.2, latency_ms: 13.8 },
                radar: 'ONLINE',
                uav: db.uav
            });

            // Keep status pill as SIMULATED / ONLINE
            const wsPill = document.getElementById('wsStatus');
            if (wsPill && !wsPill.classList.contains('online')) {
                wsPill.className = 'status-pill online';
                const label = wsPill.querySelector('.ws-label');
                if (label) label.textContent = 'FEED: SIMULATED';
            }
        }, 1500);

        // 3. Continuous Tactical Video Stream Refresh (every 750ms)
        setInterval(() => {
            if (window.AERION_BACKEND_URL && window.AERION_BACKEND_URL.trim().length > 0) return;

            // Update Tactical Monitor
            const monitorImg = document.getElementById('tacticalMonitorImg');
            if (monitorImg && monitorImg.isConnected) {
                monitorImg.src = generateTacticalCamSvg(activeCamId, db.cams[activeCamId] ? db.cams[activeCamId].status : 'ONLINE');
            }

            // Update Multi-cam grid
            const g1 = document.getElementById('gridCam01Img');
            if (g1 && g1.isConnected) g1.src = generateTacticalCamSvg('CAM_01', db.cams.CAM_01.status);

            const g2 = document.getElementById('gridCam02Img');
            if (g2 && g2.isConnected) g2.src = generateTacticalCamSvg('CAM_02', db.cams.CAM_02.status);

            const gu = document.getElementById('gridUavImg');
            if (gu && gu.isConnected) gu.src = generateTacticalCamSvg('UAV_01', 'ONLINE');

            const uavImg = document.getElementById('uavReconImg');
            if (uavImg && uavImg.isConnected) {
                uavImg.src = generateTacticalCamSvg('UAV_01', 'ONLINE');
                uavImg.style.display = 'block';
                const placeholder = document.getElementById('uavFeedPlaceholder');
                if (placeholder) placeholder.style.display = 'none';
            }

            // Forensic snapshot
            const drawerThumb = document.getElementById('drawerHeroThumb');
            if (drawerThumb && drawerThumb.isConnected && (!drawerThumb.src || drawerThumb.src.includes('404') || drawerThumb.src.includes('EVT_20260911'))) {
                drawerThumb.src = generateTacticalCamSvg('CAM_01', 'ONLINE', 'SNAPSHOT');
            }

            // Tactical QR code
            const qrImg = document.getElementById('cam02QrImage');
            if (qrImg && qrImg.isConnected && (!qrImg.src || qrImg.src.includes('/api/cameras/network/qr'))) {
                qrImg.src = generateTacticalQrSvg();
            }
        }, 750);
    }

    // Attach UI Hooks on DOM Ready
    function attachUiHooks() {
        // Track camera tab switcher to update activeCamId
        const btnCam01 = document.getElementById('btnMonitorCam01');
        const btnCam02 = document.getElementById('btnMonitorCam02');
        const btnUav = document.getElementById('btnMonitorUav');

        if (btnCam01) btnCam01.addEventListener('click', () => { activeCamId = 'CAM_01'; });
        if (btnCam02) btnCam02.addEventListener('click', () => { activeCamId = 'CAM_02'; });
        if (btnUav) btnUav.addEventListener('click', () => { activeCamId = 'UAV_01'; });

        // Connect Local Webcam button
        const btnWebcam = document.getElementById('btnConnectLocalWebcam');
        if (btnWebcam) {
            btnWebcam.addEventListener('click', toggleLocalWebcam);
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', attachUiHooks);
    } else {
        attachUiHooks();
    }

    // Initialize simulation only in standalone mode without active backend
    if (isStandaloneMode) {
        setupMockApiInterceptor();
        startStandaloneSimulationLoop();
    }

    window.aerionSimulator = {
        db,
        executeScenario: executeSimulatedScenario,
        toggleLocalWebcam
    };
})();
