/**
 * AERION Standalone Client-Side Simulation & Mock Engine
 * Automatically activates on Vercel or when no remote backend is connected.
 * Provides real-time radar trajectories, tactical camera feeds, REST mock responses,
 * and live SIH 2026 demo scenario executions directly in the browser.
 */

(function () {
    console.log('[AERION] Initializing Standalone Simulation Engine for Vercel...');

    // State
    const state = {
        systemMode: 'SIMULATION',
        scenario: 'IDLE',
        activeTargets: [
            { id: 101, x: 2.1, y: 14.5, vx: 0.15, vy: -0.3, speed: 0.8, range: 14.6, angle: 8.2, class_name: 'person', zone_id: 'ZONE_A', zone_type: 'NORMAL', confidence: 0.93 },
            { id: 102, x: -3.8, y: 19.2, vx: -0.1, vy: -0.2, speed: 0.6, range: 19.5, angle: -11.1, class_name: 'person', zone_id: 'ZONE_A', zone_type: 'NORMAL', confidence: 0.88 }
        ],
        cams: {
            CAM_01: { status: 'ONLINE', fps: 30.0, latency_ms: 12.4, resolution: '1920x1080', tracks: 2 },
            CAM_02: { status: 'ONLINE', fps: 28.5, latency_ms: 19.1, resolution: '1280x720', tracks: 0 }
        },
        uav: {
            uav_id: 'UAV_01',
            status: 'LOITERING',
            battery_percent: 94,
            altitude_m: 35.0,
            speed_mps: 6.5,
            heading_deg: 135.0,
            lat: 32.7285,
            lon: 74.8582,
            target_locked: false
        },
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
                created_at: new Date(Date.now() - 180000).toISOString(),
                description: 'Restricted fence boundary breach detected via 24GHz FMCW Radar + Optical confirmation.',
                has_video: true
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
                created_at: new Date(Date.now() - 450000).toISOString(),
                description: 'Rapid approach towards inner security perimeter.',
                has_video: true
            }
        ],
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
        ]
    };

    // Tactical Camera SVG Generator for Canvas/Stream
    function generateTacticalCamSvg(camId, status) {
        const time = new Date().toISOString().replace('T', ' ').slice(0, 19);
        const isOnline = status === 'ONLINE';
        const color = isOnline ? '#00e5ff' : '#f59e0b';
        return `data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360" viewBox="0 0 640 360">
            <rect width="100%" height="100%" fill="#050b18"/>
            <defs>
                <pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
                    <path d="M 40 0 L 0 0 0 40" fill="none" stroke="rgba(0,229,255,0.06)" stroke-width="1"/>
                </pattern>
            </defs>
            <rect width="100%" height="100%" fill="url(%23grid)" />
            
            <!-- Corner mil-spec reticles -->
            <path d="M 20 50 L 20 20 L 50 20" fill="none" stroke="${color}" stroke-width="2"/>
            <path d="M 620 50 L 620 20 L 590 20" fill="none" stroke="${color}" stroke-width="2"/>
            <path d="M 20 310 L 20 340 L 50 340" fill="none" stroke="${color}" stroke-width="2"/>
            <path d="M 620 310 L 620 340 L 590 340" fill="none" stroke="${color}" stroke-width="2"/>
            
            <!-- Center Crosshair -->
            <circle cx="320" cy="180" r="30" fill="none" stroke="rgba(0,229,255,0.25)" stroke-width="1" stroke-dasharray="4,4"/>
            <line x1="300" y1="180" x2="340" y2="180" stroke="${color}" stroke-width="1.5"/>
            <line x1="320" y1="160" x2="320" y2="200" stroke="${color}" stroke-width="1.5"/>
            
            <!-- Simulated AI Target Box if Online -->
            ${isOnline ? `
            <rect x="360" y="110" width="80" height="150" fill="rgba(0,229,255,0.08)" stroke="#00e5ff" stroke-width="1.5"/>
            <rect x="360" y="94" width="95" height="16" fill="#00e5ff"/>
            <text x="363" y="106" fill="#030712" font-family="monospace" font-size="10" font-weight="bold">TRK_101 [94%]</text>
            ` : ''}

            <!-- Tactical HUD Header -->
            <text x="30" y="38" fill="${color}" font-family="monospace" font-size="12" font-weight="bold">AERION SENTINEL // ${camId}</text>
            <text x="440" y="38" fill="#10b981" font-family="monospace" font-size="11" font-weight="bold">REC [●] ${time}</text>
            
            <!-- Tactical HUD Footer -->
            <text x="30" y="335" fill="rgba(255,255,255,0.7)" font-family="monospace" font-size="10">FPS: 30.0 | RES: 1080p | SENSOR: OPTICAL-AI | STATUS: ${status}</text>
        </svg>`;
    }

    // Intercept Mock Fetch Responses
    function setupMockApiInterceptor() {
        const origFetch = window.fetch;

        window.fetch = async function (resource, init) {
            const urlStr = typeof resource === 'string' ? resource : (resource && resource.url ? resource.url : '');
            
            // If user configured an external backend URL, use real fetch
            if (window.AERION_BACKEND_URL && window.AERION_BACKEND_URL.trim().length > 0) {
                return origFetch(resource, init);
            }

            // Mock REST APIs
            if (urlStr.includes('/api/system/health') || urlStr.includes('/api/system/status')) {
                return createJsonResponse({
                    status: 'HEALTHY',
                    system_mode: state.systemMode,
                    timestamp: new Date().toISOString(),
                    host_metrics: {
                        cpu_percent: 21.4,
                        ram_percent: 41.2,
                        gpu: {
                            available: true,
                            name: 'NVIDIA GeForce RTX 3050 (6GB VRAM)',
                            gpu_utilization_percent: 28.0,
                            memory_used_mb: 1420.0,
                            memory_total_mb: 6144.0,
                            temperature_c: 51.0
                        }
                    },
                    components: {
                        fastapi: { status: 'ONLINE', metadata: { version: '0.115.0' } },
                        radar: { status: 'ONLINE', metadata: { model: 'LD2450 24GHz FMCW mmWave' } },
                        yolo: { status: 'ONLINE', metadata: { model: 'YOLOv8n-Tactical', device: 'cuda:0' } },
                        uav: { status: 'ONLINE', metadata: { id: 'UAV_01', battery: '94%' } }
                    }
                });
            }

            if (urlStr.includes('/api/system/metrics')) {
                return createJsonResponse({
                    fps: 30.0,
                    inference_time_ms: 13.8,
                    cpu_percent: 21.4,
                    ram_percent: 41.2,
                    queue_depth: 0,
                    active_tracks: state.activeTargets.length,
                    dropped_frames: 0,
                    timestamp: new Date().toISOString()
                });
            }

            if (urlStr.includes('/api/zones')) {
                return createJsonResponse(state.zones);
            }

            if (urlStr.includes('/api/cameras/network/info')) {
                return createJsonResponse({
                    local_ip: '10.10.5.67',
                    port: 8000,
                    rtsp_url: 'rtsp://10.10.5.67:8554/cam02',
                    status: 'READY'
                });
            }

            if (urlStr.includes('/api/cameras/network/qr')) {
                // Return SVG dummy QR
                return new Response(
                    `<svg xmlns="http://www.w3.org/2000/svg" width="150" height="150" viewBox="0 0 150 150"><rect width="100%" height="100%" fill="#fff"/><rect x="15" y="15" width="40" height="40" fill="#030712"/><rect x="95" y="15" width="40" height="40" fill="#030712"/><rect x="15" y="95" width="40" height="40" fill="#030712"/><rect x="25" y="25" width="20" height="20" fill="#fff"/><rect x="105" y="25" width="20" height="20" fill="#fff"/><rect x="25" y="105" width="20" height="20" fill="#fff"/><text x="75" y="80" text-anchor="middle" font-size="10" font-family="sans-serif" fill="#030712">AERION QR</text></svg>`,
                    { status: 200, headers: { 'Content-Type': 'image/svg+xml' } }
                );
            }

            if (urlStr.includes('/api/cameras') && !urlStr.includes('/stream') && !urlStr.includes('/snapshot')) {
                return createJsonResponse([
                    {
                        id: 'CAM_01',
                        name: 'CAM_01 // Perimeter Sector Alpha',
                        type: 'FIXED_CCTV',
                        source: 'simulation',
                        status: state.cams.CAM_01.status,
                        resolution: state.cams.CAM_01.resolution,
                        fps: state.cams.CAM_01.fps,
                        latency_ms: state.cams.CAM_01.latency_ms,
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
                        status: state.cams.CAM_02.status,
                        resolution: state.cams.CAM_02.resolution,
                        fps: state.cams.CAM_02.fps,
                        latency_ms: state.cams.CAM_02.latency_ms,
                        frame_count: 8120,
                        dropped_frames: 1,
                        zone_id: 'ZONE_B',
                        enabled: true
                    }
                ]);
            }

            if (urlStr.includes('/api/radar/fused-targets')) {
                return createJsonResponse({
                    count: state.activeTargets.length,
                    fused_tracks: state.activeTargets,
                    timestamp: new Date().toISOString()
                });
            }

            if (urlStr.includes('/api/uav/telemetry')) {
                return createJsonResponse(state.uav);
            }

            if (urlStr.includes('/api/events')) {
                return createJsonResponse(state.events);
            }

            if (urlStr.includes('/api/anpr')) {
                return createJsonResponse([
                    { id: 'ANPR_01', plate_number: 'PB-08-AX-9921', vehicle_type: 'TRUCK', confidence: 0.97, timestamp: new Date().toISOString(), is_hotlisted: true }
                ]);
            }

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

            if (urlStr.includes('/api/ai/profiler')) {
                return createJsonResponse({
                    device: 'NVIDIA RTX 3050',
                    preprocess_ms: 1.8,
                    inference_ms: 8.9,
                    postprocess_ms: 2.1,
                    total_fps: 30.2,
                    memory_vram_mb: 1420
                });
            }

            // SIH 2026 Scenario Trigger Handlers
            if (urlStr.includes('/api/system/scenario/')) {
                const parts = urlStr.split('/api/system/scenario/');
                const scenarioId = parts[1] ? parts[1].split('?')[0] : '';
                executeSimulatedScenario(scenarioId);
                return createJsonResponse({ status: 'EXECUTING', scenario: scenarioId });
            }

            if (urlStr.includes('/api/system/settings/SYSTEM_MODE')) {
                return createJsonResponse({ success: true, mode: state.systemMode });
            }

            // Fallback for all other /api/ calls
            if (urlStr.startsWith('/api/') || urlStr.includes('/api/')) {
                return createJsonResponse({ success: true, status: 'STANDALONE_OK' });
            }

            // Default
            return origFetch(resource, init);
        };
    }

    function createJsonResponse(data, status = 200) {
        return new Response(JSON.stringify(data), {
            status: status,
            headers: { 'Content-Type': 'application/json' }
        });
    }

    // Dynamic Scenario Execution
    function executeSimulatedScenario(scenarioId) {
        console.log(`[SCENARIO] Executing simulated scenario: ${scenarioId}`);

        if (scenarioId === '1') {
            // 1. PATROL
            state.activeTargets = [
                { id: 201, x: -1.2, y: 16.0, vx: 0.1, vy: 0.1, speed: 0.5, range: 16.0, angle: -4.3, class_name: 'person', zone_id: 'ZONE_A', zone_type: 'NORMAL', confidence: 0.95 }
            ];
            dispatchWs('RADAR_TARGETS_UPDATE', { sensor_id: 'RADAR_01', targets: state.activeTargets });
            dispatchWs('SCENARIO_STATUS', { scenario: 1, title: 'ROUTINE PATROL', status: 'ACTIVE' });
        } else if (scenarioId === '2') {
            // 2. BORDER BREACH
            state.activeTargets = [
                { id: 666, x: 5.5, y: 11.2, vx: 0.4, vy: -0.5, speed: 2.1, range: 12.5, angle: 26.1, class_name: 'person', zone_id: 'ZONE_C', zone_type: 'RESTRICTED', confidence: 0.98 }
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
            state.events.unshift(breachEvent);
            dispatchWs('RADAR_TARGETS_UPDATE', { sensor_id: 'RADAR_01', targets: state.activeTargets });
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
            state.cams.CAM_02.status = 'OFFLINE';
            dispatchWs('CAMERA_STATUS_CHANGED', { camera_id: 'CAM_02', status: 'OFFLINE' });
            dispatchWs('SURVEILLANCE_GAP_DETECTED', {
                camera_id: 'CAM_02',
                radar_contact: true,
                directive: 'SCRAMBLE_UAV_01'
            });
            dispatchWs('SCENARIO_STATUS', { scenario: 4, title: 'OPTICAL GAP', status: 'UAV_DISPATCH_REQUIRED' });
        } else if (scenarioId === '5') {
            // 5. UAV RECON
            state.uav.status = 'INTERCEPT_INTERVENTION';
            state.uav.altitude_m = 48.0;
            state.uav.target_locked = true;
            state.uav.speed_mps = 14.5;
            dispatchWs('UAV_VERIFICATION_DISPATCHED', {
                uav_id: 'UAV_01',
                waypoint: { lat: 32.7315, lon: 74.8610 },
                status: 'EN_ROUTE'
            });
            dispatchWs('UAV_TELEMETRY_UPDATE', state.uav);
            dispatchWs('SCENARIO_STATUS', { scenario: 5, title: 'UAV RECON', status: 'TARGET_LOCKED' });
        } else if (scenarioId === 'reset') {
            // RESET
            state.cams.CAM_01.status = 'ONLINE';
            state.cams.CAM_02.status = 'ONLINE';
            state.uav.status = 'LOITERING';
            state.uav.target_locked = false;
            state.activeTargets = [
                { id: 101, x: 2.1, y: 14.5, vx: 0.15, vy: -0.3, speed: 0.8, range: 14.6, angle: 8.2, class_name: 'person', zone_id: 'ZONE_A', zone_type: 'NORMAL', confidence: 0.93 }
            ];
            dispatchWs('CAMERA_STATUS_CHANGED', { camera_id: 'CAM_01', status: 'ONLINE' });
            dispatchWs('CAMERA_STATUS_CHANGED', { camera_id: 'CAM_02', status: 'ONLINE' });
            dispatchWs('RADAR_TARGETS_UPDATE', { sensor_id: 'RADAR_01', targets: state.activeTargets });
            dispatchWs('SCENARIO_STATUS', { scenario: 0, title: 'SYSTEM RESET', status: 'NOMINAL' });
        }
    }

    function dispatchWs(eventType, data) {
        if (window.surveillanceSocket && typeof window.surveillanceSocket.dispatch === 'function') {
            window.surveillanceSocket.dispatch(eventType, data);
        } else {
            window.dispatchEvent(new CustomEvent('surveillance:event', { detail: { type: eventType, ...data } }));
        }
    }

    // Continuous Real-Time Simulation Loop
    function startStandaloneSimulationLoop() {
        // Broadcast radar updates every 100ms
        let angleStep = 0;
        setInterval(() => {
            // Only simulate if no remote backend is configured
            if (window.AERION_BACKEND_URL && window.AERION_BACKEND_URL.trim().length > 0) return;

            angleStep += 0.03;
            // Update positions realistically
            state.activeTargets.forEach((t, i) => {
                t.x += Math.sin(angleStep + i) * 0.05;
                t.y += Math.cos(angleStep + i) * 0.05;
                t.range = Math.sqrt(t.x * t.x + t.y * t.y);
                t.angle = Math.atan2(t.x, t.y) * (180 / Math.PI);
            });

            dispatchWs('RADAR_TARGETS_UPDATE', {
                sensor_id: 'RADAR_01',
                targets: state.activeTargets,
                is_simulated: true,
                timestamp: new Date().toISOString()
            });
        }, 120);

        // Broadcast telemetry heartbeat every 1.5s
        setInterval(() => {
            if (window.AERION_BACKEND_URL && window.AERION_BACKEND_URL.trim().length > 0) return;

            dispatchWs('TELEMETRY_HEARTBEAT', {
                timestamp: new Date().toISOString(),
                system_mode: state.systemMode,
                cameras: {
                    CAM_01: { status: state.cams.CAM_01.status, fps: 30.0, latency_ms: 12.0, resolution: '1920x1080' },
                    CAM_02: { status: state.cams.CAM_02.status, fps: 28.5, latency_ms: 19.0, resolution: '1280x720' }
                },
                ai: { fps: 30.2, latency_ms: 13.8 },
                radar: 'ONLINE',
                uav: state.uav
            });

            // Keep status pill as SIMULATED / ONLINE
            const wsPill = document.getElementById('wsStatus');
            if (wsPill && !wsPill.classList.contains('online')) {
                wsPill.className = 'status-pill online';
                const label = wsPill.querySelector('.ws-label');
                if (label) label.textContent = 'FEED: SIMULATED';
            }
        }, 1500);

        // Update camera stream images with dynamic tactical canvas/svg
        setInterval(() => {
            if (window.AERION_BACKEND_URL && window.AERION_BACKEND_URL.trim().length > 0) return;

            ['CAM_01', 'CAM_02'].forEach(cid => {
                const img = document.getElementById(`video-stream-${cid}`);
                if (img && img.isConnected) {
                    const svgUri = generateTacticalCamSvg(cid, state.cams[cid].status);
                    img.src = svgUri;
                }
            });
        }, 2000);
    }

    // Initialize
    setupMockApiInterceptor();
    startStandaloneSimulationLoop();

    window.aerionSimulator = {
        state,
        executeScenario: executeSimulatedScenario
    };
})();
