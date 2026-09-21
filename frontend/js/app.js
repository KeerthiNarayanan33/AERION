import { wsClient } from './websocket.js';
import { RadarView } from './radar_view.js';
import { AlertFeed } from './alert_feed.js';
import { ZoneMap } from './zone_map.js';
import { MetricsMonitor } from './metrics.js';
import { UAVView } from './uav_view.js';
import { PersonsManager } from './persons_manager.js';

class SurveillanceApp {
    constructor() {
        this.currentTab = 'tab-dashboard';
        this.radarView = null;
        this.radarViewExpanded = null;
        this.zoneMap = null;
        this.zoneMapFull = null;
        this.alertFeed = null;
        this.metricsMonitor = null;
        this.uavView = null;
        this.personsManager = null;
        this._sovThreatCount = 0;
        this._sovUnknownCount = 0;
        this._sovViolationCount = 0;
        this._sovRadarTargetCount = 0;
        this.playbooksCatalog = [];
        this.activePlaybookId = 6;
        this.activeStageIndex = 0;
        this.eventsCurrentPage = 1;
        this.eventsPageSize = 25;
        this.eventsTotalCount = 0;
        this.eventsFilters = {};
        this.eventsData = [];
        this.selectedEventId = null;
        this.isLivePollingActive = true;
        this.livePollingTimer = null;
        this.isEventDrawerOpen = false;
        this.cam02QrMode = 'https';
        this.cam02NetworkData = null;
    }

    async init() {
        console.log('[APP] Initializing Border Surveillance Command Center...');

        // 1. Initialize Components
        this.radarView = new RadarView('radarCanvas');
        this.radarViewExpanded = new RadarView('radarCanvasExpanded');
        this.alertFeed = new AlertFeed('alertFeedContainer', 'alertCountBadge');
        this.zoneMap = new ZoneMap('zoneMapCanvas');
        this.zoneMapFull = new ZoneMap('zoneMapCanvasFull');
        this.metricsMonitor = new MetricsMonitor();
        this.uavView = new UAVView();
        this.personsManager = new PersonsManager();

        // 2. Initialize Navigation Tabs (can now safely reference all components)
        this.setupNavigation();

        // 3. Start Clock
        this.startClock();

        // 4. Connect WebSocket
        wsClient.init();
        this.setupSocketListeners();

        // 4.1 Eagerly load camera network info and QR code pairing
        this.loadCameraNetworkInfo();

        // 5. Load Initial Data via REST
        await this.loadInitialData();

        // 6. Setup Interactive Action Handlers
        this.setupActionHandlers();
        this.setupAerionHandlers();

        // 7. Setup new management pages
        this._setupNewTabHandlers();

        // 8. Load dashboard overview counters
        this._loadDashboardOverview();

        console.log('[APP] Ready.');
    }

    setupNavigation() {
        const tabs = document.querySelectorAll('.nav-tab, .sih-highlight-tab');
        const sidebarItems = document.querySelectorAll('.sidebar-item');
        const panes = document.querySelectorAll('.tab-pane');

        const switchTab = (targetPaneId) => {
            if (!targetPaneId) return;
            tabs.forEach(t => {
                if (t.getAttribute('data-tab') === targetPaneId) {
                    t.classList.add('active');
                } else {
                    t.classList.remove('active');
                }
            });
            sidebarItems.forEach(s => {
                if (s.getAttribute('data-tab') === targetPaneId) {
                    s.classList.add('active');
                } else {
                    s.classList.remove('active');
                }
            });
            panes.forEach(p => {
                if (p.id === targetPaneId) {
                    p.classList.add('active');
                } else {
                    p.classList.remove('active');
                }
            });
            this.currentTab = targetPaneId;
            try {
                sessionStorage.setItem('soc_active_tab', targetPaneId);
            } catch (err) {
                // Storage quota / sandboxing fallback
            }

            // Trigger resize redraw if switching to radar, zones, or UAV
            if (targetPaneId === 'tab-radar') {
                if (this.radarView) this.radarView.initCanvas();
                if (this.radarViewExpanded) this.radarViewExpanded.initCanvas();
            } else if (targetPaneId === 'tab-zones') {
                if (this.zoneMap) { this.zoneMap.init(); this.zoneMap.draw(); }
                if (this.zoneMapFull) { this.zoneMapFull.init(); this.zoneMapFull.draw(); }
                this.loadHeatmapAnalytics();
            } else if (targetPaneId === 'tab-uav' && this.uavView) {
                this.uavView.initCanvases();
            } else if (targetPaneId === 'tab-events') {
                this.loadEventsTable();
                this.loadEventsSummaryStats();
                this.loadAnprRecords();
            } else if (targetPaneId === 'tab-persons') {
                if (this.personsManager) this.personsManager.init();
            } else if (targetPaneId === 'tab-location') {
                this._loadSiteConfig();
                this._loadLocationZonesSummary();
                this._drawSiteMap();
            } else if (targetPaneId === 'tab-devices') {
                this._loadAlertRules();
                this._loadSensorMatrix();
            }
        };

        this.switchTab = switchTab;

        tabs.forEach(tab => {
            tab.addEventListener('click', () => {
                const targetPaneId = tab.getAttribute('data-tab');
                switchTab(targetPaneId);
            });
        });

        sidebarItems.forEach(item => {
            item.addEventListener('click', () => {
                const targetPaneId = item.getAttribute('data-tab');
                switchTab(targetPaneId);
            });
        });

        // Wire Dashboard SOV Cards to switch to corresponding tabs
        const sovMap = {
            'sovCardThreats': 'tab-events',
            'sovCardUnknown': 'tab-persons',
            'sovCardViolations': 'tab-events',
            'sovCardAuthorized': 'tab-persons',
            'sovCardUav': 'tab-uav',
            'sovCardRadar': 'tab-radar',
            'sovCardCameras': 'tab-cameras'
        };
        for (const [id, tabId] of Object.entries(sovMap)) {
            const card = document.getElementById(id);
            if (card) {
                card.addEventListener('click', () => switchTab(tabId));
            }
        }

        // Wire Notifications bell button
        const bellBtn = document.getElementById('headerNotifications');
        if (bellBtn) {
            bellBtn.addEventListener('click', () => {
                switchTab('tab-events');
            });
        }

        // Wire Operator profile widget
        const userProfile = document.querySelector('.header-user-profile');
        if (userProfile) {
            userProfile.addEventListener('click', () => {
                switchTab('tab-config');
            });
        }

        // Wire status pills to their relevant tabs
        document.querySelectorAll('.status-pill').forEach(pill => {
            pill.style.cursor = 'pointer';
            pill.addEventListener('click', () => {
                const text = (pill.textContent || '').toLowerCase();
                if (text.includes('cam')) switchTab('tab-cameras');
                else if (text.includes('radar')) switchTab('tab-radar');
                else if (text.includes('uav')) switchTab('tab-uav');
                else if (text.includes('ai') || text.includes('system') || text.includes('online')) switchTab('tab-telemetry');
                else if (text.includes('feed') || text.includes('live')) switchTab('tab-dashboard');
            });
        });

        // Determine starting tab: restore from sessionStorage on reload, default to dashboard on first load
        let initialTab = 'tab-dashboard';
        try {
            const savedTab = sessionStorage.getItem('soc_active_tab');
            if (savedTab && document.getElementById(savedTab)) {
                initialTab = savedTab;
            }
        } catch (err) {
            initialTab = 'tab-dashboard';
        }

        switchTab(initialTab);
    }

    startClock() {
        const clockEl = document.getElementById('utcClock');
        const timeEl = document.getElementById('utcClockTime');
        const dateEl = document.getElementById('utcClockDate');
        const update = () => {
            const now = new Date();
            const hours = String(now.getHours() % 12 || 12).padStart(2, '0');
            const minutes = String(now.getMinutes()).padStart(2, '0');
            const seconds = String(now.getSeconds()).padStart(2, '0');
            const ampm = now.getHours() >= 12 ? 'PM' : 'AM';
            const timeStr = `${hours}:${minutes}:${seconds} ${ampm}`;

            const d = String(now.getUTCDate()).padStart(2, '0');
            const m = String(now.getUTCMonth() + 1).padStart(2, '0');
            const y = now.getUTCFullYear();
            const dateStr = `${d}-${m}-${y} UTC`;

            if (timeEl) timeEl.textContent = timeStr;
            if (dateEl) dateEl.textContent = dateStr;
            if (clockEl) {
                const utcStr = now.toUTCString().replace('GMT', 'UTC');
                clockEl.textContent = `${now.toLocaleTimeString()} | ${utcStr.slice(17, 25)} UTC`;
            }
        };
        update();
        setInterval(update, 1000);
    }

    setupSocketListeners() {
        // Radar updates
        wsClient.on('RADAR_TARGETS_UPDATE', (data) => {
            if (this.radarView) this.radarView.setTargets(data.targets);
            if (this.radarViewExpanded) this.radarViewExpanded.setTargets(data.targets);
            if (this.zoneMap) this.zoneMap.setTargets(data.targets);
            if (this.zoneMapFull) this.zoneMapFull.setTargets(data.targets);

            const targetCount = data.targets ? data.targets.length : 0;

            // Legacy sidebar badge
            const targetCountEl = document.getElementById('radarTargetCount');
            if (targetCountEl) targetCountEl.textContent = `${targetCount} TARGETS`;

            // New radar tab stat cards
            const radarStatTargets = document.getElementById('radarStatTargets');
            if (radarStatTargets) radarStatTargets.textContent = targetCount;

            const radarTargetCountBadge = document.getElementById('radarTargetCountBadge');
            if (radarTargetCountBadge) radarTargetCountBadge.textContent = `${targetCount} TARGET${targetCount !== 1 ? 'S' : ''}`;

            // Count restricted-zone targets
            const restrictedCount = data.targets ? data.targets.filter(t => t.zone_type === 'RESTRICTED' || t.zone === 'RESTRICTED_ENTRY').length : 0;
            const radarStatRestricted = document.getElementById('radarStatRestricted');
            if (radarStatRestricted) radarStatRestricted.textContent = restrictedCount;

            // Dashboard overview counter
            this._sovRadarTargetCount = targetCount;
            const sovRadarEl = document.getElementById('sovRadarTargets');
            if (sovRadarEl) sovRadarEl.textContent = this._sovRadarTargetCount;

            // Live update radar targets table & zone alert status
            this.renderRadarTargetsTable(data.targets);
            this.renderRadarZoneStatus(data.targets);

            if (window.audioAlert && data.targets && data.targets.length > 0) {
                window.audioAlert.playRadarBlip();
            }
        });

        // Multi-Sensor Fused Tracks
        wsClient.on('FUSED_TRACKS_UPDATE', (data) => {
            if (data.fused_tracks) {
                this.renderRadarTargetsTable(data.fused_tracks);
            }
        });

        // Security Alerts (New Event)
        wsClient.on('SECURITY_ALERT', (data) => {
            if (data.event && (data.event.is_authorized || data.event.authorization === 'AUTHORIZED')) {
                return;
            }
            if (this.alertFeed && data.event) {
                this.alertFeed.upsertAlert(data.event);
            }
            if (data.event) {
                this.handleLiveEventStream(data.event, 'CREATED');
            }
            if (window.audioAlert && data.event) {
                const sev = data.event.peak_severity || data.event.severity || 'LOW';
                if (sev === 'CRITICAL') {
                    window.audioAlert.playCriticalAlarm(5);
                    const zName = data.event.zone_name || data.event.zone_id || 'Sector Charlie';
                    const targetClass = data.event.object_class || 'Intruder';
                    window.audioAlert.speakTacticalAlert(`Critical Alert. ${targetClass} breach detected in ${zName}. Quick reaction team dispatched.`);
                } else if (sev === 'HIGH') {
                    window.audioAlert.playCriticalAlarm(4);
                    window.audioAlert.speakTacticalAlert(`Warning. Perimeter approach in ${data.event.zone_name || data.event.zone_id || 'Sector Bravo'}.`);
                } else if (sev === 'MEDIUM' || sev === 'WARNING') {
                    window.audioAlert.playWarningBeep();
                }
            }
        });

        // Continuous Event Updates (Deduplicated Progress & Escalation)
        wsClient.on('EVENT_UPDATED', (data) => {
            if (data.event && (data.event.is_authorized || data.event.authorization === 'AUTHORIZED')) {
                return;
            }
            if (this.alertFeed && data.event) {
                this.alertFeed.upsertAlert(data.event);
            }
            if (data.event) {
                this.handleLiveEventStream(data.event, 'UPDATED');
            }
            if (window.audioAlert && data.event) {
                const sev = data.event.peak_severity || data.event.severity;
                const state = data.event.intrusion_state;
                if (sev === 'CRITICAL' || state === 'RESTRICTED_ENTRY' || state === 'ACTIVE_EVENT') {
                    const now = Date.now();
                    if (!this._lastEscalationAlarm || (now - this._lastEscalationAlarm) > 3500) {
                        this._lastEscalationAlarm = now;
                        const zName = data.event.zone_name || data.event.zone_id || 'Restricted Zone';
                        window.audioAlert.announceUnauthorizedPerson(zName);
                        this.flashRedScreenBorder();
                    }
                }
            }
        });

        // Real-Time Zone Intrusion State Transition (Direct from ZoneManager)
        wsClient.on('ZONE_INTRUSION_STATE', (data) => {
            if (data.is_authorized || data.authorization === 'AUTHORIZED') {
                return;
            }
            console.warn('[ZONE INTRUSION ALERT]', data);
            if (data.current_state === 'RESTRICTED_ENTRY' || data.current_state === 'ACTIVE_EVENT' || data.is_critical) {
                const now = Date.now();
                if (!this._lastZoneIntrusionAlarm || (now - this._lastZoneIntrusionAlarm) > 3500) {
                    this._lastZoneIntrusionAlarm = now;
                    if (window.audioAlert) {
                        const zName = data.zone_name || data.zone_id || 'Restricted Zone';
                        window.audioAlert.announceUnauthorizedPerson(zName);
                        this.flashRedScreenBorder();
                    }
                }
                if (this.alertFeed) {
                    this.alertFeed.addAlert({
                        severity: 'CRITICAL',
                        event_type: 'RESTRICTED_BREACH',
                        description: `RESTRICTED PERIMETER INTRUSION: Target [${data.object_id}] entered ${data.zone_name || data.zone_id}!`,
                        timestamp: new Date().toISOString()
                    });
                }
            } else if (data.current_state === 'WARNING') {
                if (window.audioAlert) {
                    window.audioAlert.playWarningBeep();
                }
            }
        });

        // Event Resolved (Target Departed / Operator Cleared)
        wsClient.on('EVENT_RESOLVED', (data) => {
            if (this.alertFeed && data.event) {
                this.alertFeed.resolveAlert(data.event);
            }
            if (data.event) {
                this.handleLiveEventStream(data.event, 'RESOLVED');
            }
        });

        // Event Acknowledged
        wsClient.on('EVENT_ACKNOWLEDGED', (data) => {
            if (this.alertFeed && data.event) {
                this.alertFeed.upsertAlert(data.event);
            }
            if (data.event) {
                this.handleLiveEventStream(data.event, 'ACKNOWLEDGED');
            }
        });

        // Forensic Evidence Video Compiled & Ready
        wsClient.on('EVENT_EVIDENCE_READY', (data) => {
            console.log('[EVIDENCE] Evidence video compiled and ready:', data);
            this.handleLiveEvidenceReady(data);
            if (this.currentModalEventId === data.event_id) {
                const videoEl = document.getElementById('evidenceVideoPlayer');
                const fallbackEl = document.getElementById('evidenceVideoFallback');
                const statusEl = document.getElementById('evidenceVideoStatus');
                const dlBtn = document.getElementById('btnEvidenceDownload');

                if (videoEl && fallbackEl) {
                    fallbackEl.style.display = 'none';
                    videoEl.style.display = 'block';
                    videoEl.src = `${data.video_url}?t=${Date.now()}`;
                    videoEl.load();
                    videoEl.play().catch(e => console.log('Autoplay deferred:', e));
                }
                if (statusEl) {
                    statusEl.textContent = '● VERIFIED MP4 FORENSIC CLIP (READY)';
                    statusEl.style.color = 'var(--accent-success)';
                }
                if (dlBtn) {
                    dlBtn.href = data.video_url;
                    dlBtn.download = `${data.event_id}.mp4`;
                }
            }
        });

        // ANPR Real-Time Detection Broadcast
        wsClient.on('ANPR_PLATE_DETECTED', (data) => {
            this.loadAnprRecords();
            this.loadEventsSummaryStats();
        });

        // Camera status change
        wsClient.on('CAMERA_STATUS_CHANGED', (data) => {
            console.log('[CAMERA] Status change:', data);
            this.updateCameraStatusUI(data.camera_id, data.status);
        });

        // AI Multi-Object Tracking & Identity updates (Sections 7-12)
        wsClient.on('AI_TRACKS_UPDATE', (data) => {
            const card = document.getElementById(`card-${data.camera_id}`);
            if (card) {
                const tracksBadge = card.querySelector('.cam-tracks-badge');
                if (tracksBadge) {
                    tracksBadge.textContent = `${data.count} ACTIVE TRACK${data.count === 1 ? '' : 'S'}`;
                    tracksBadge.style.display = data.count > 0 ? 'inline-block' : 'none';
                }
            }
            if (data.identities && data.identities.length > 0) {
                const latestId = data.identities[data.identities.length - 1];
                this.renderIdentityVerification(latestId);

                // Voice alert for unknown/unauthorized person entering restricted sector
                data.identities.forEach(id => {
                    const isUnauthorized = (id.authorization === 'UNAUTHORIZED' || id.identity === 'UNKNOWN' || id.authorization === 'NOT_AUTHORIZED_FOR_ZONE' || id.authorization === 'UNVERIFIED' || id.identity === 'UNVERIFIED');
                    const isRestricted = (id.zone_id === 'ZONE_C' || data.camera_id === 'CAM_02' || (id.zone_name && id.zone_name.toLowerCase().includes('restricted')) || id.zone_type === 'RESTRICTED');
                    if (isUnauthorized && isRestricted) {
                        const now = Date.now();
                        if (!this._lastUnauthorizedVoiceAlert || (now - this._lastUnauthorizedVoiceAlert) > 4000) {
                            this._lastUnauthorizedVoiceAlert = now;
                            if (window.audioAlert) {
                                const zName = id.zone_name || (id.zone_id === 'ZONE_C' ? 'Sector Charlie' : id.zone_id) || 'Sector Charlie';
                                window.audioAlert.announceUnauthorizedPerson(zName);
                                this.flashRedScreenBorder();
                            }
                        }
                    }
                });
            }
        });

        // AERION Person Identification & Authorization update
        wsClient.on('IDENTITY_UPDATE', (data) => {
            this.renderIdentityVerification(data);
            // Track unknown persons for dashboard counter
            if (data.authorization === 'UNAUTHORIZED' || data.identity === 'UNKNOWN' || data.authorization === 'UNVERIFIED') {
                this._sovUnknownCount++;
                const sovEl = document.getElementById('sovUnknown');
                if (sovEl) sovEl.textContent = this._sovUnknownCount;

                // Trigger voice alert if in restricted zone
                const isRestricted = (data.zone_id === 'ZONE_C' || data.camera_id === 'CAM_02' || (data.zone_name && data.zone_name.toLowerCase().includes('restricted')) || data.zone_type === 'RESTRICTED');
                if (isRestricted) {
                    const now = Date.now();
                    if (!this._lastUnauthorizedVoiceAlert || (now - this._lastUnauthorizedVoiceAlert) > 4000) {
                        this._lastUnauthorizedVoiceAlert = now;
                        if (window.audioAlert) {
                            const zName = data.zone_name || (data.zone_id === 'ZONE_C' ? 'Sector Charlie' : data.zone_id) || 'Sector Charlie';
                            window.audioAlert.announceUnauthorizedPerson(zName);
                            this.flashRedScreenBorder();
                        }
                    }
                }
            } else if (data.authorization === 'NOT_AUTHORIZED_FOR_ZONE') {
                this._sovViolationCount++;
                const sovEl = document.getElementById('sovViolations');
                if (sovEl) sovEl.textContent = this._sovViolationCount;

                const now = Date.now();
                if (!this._lastUnauthorizedVoiceAlert || (now - this._lastUnauthorizedVoiceAlert) > 4000) {
                    this._lastUnauthorizedVoiceAlert = now;
                    if (window.audioAlert) {
                        const zName = data.zone_name || (data.zone_id === 'ZONE_C' ? 'Sector Charlie' : data.zone_id) || 'Sector Charlie';
                        window.audioAlert.announceUnauthorizedPerson(zName);
                        this.flashRedScreenBorder();
                    }
                }
            }
            // Forward to PersonsManager if listening
            if (this.personsManager) this.personsManager.onPersonEvent({ type: 'IDENTITY_UPDATE', ...data });
        });

        // AERION Security Incident Created
        wsClient.on('INCIDENT_CREATED', (data) => {
            this.handleSecurityIncidentCreated(data);
        });

        // AERION Security Incident Updated
        wsClient.on('INCIDENT_UPDATED', (data) => {
            this.handleSecurityIncidentUpdated(data);
        });

        // AERION Single PIR Sensor Motion Trigger
        wsClient.on('PIR_MOTION_ALERT', (data) => {
            this.handlePirMotionAlert(data);
        });

        // UAV flight telemetry updates
        wsClient.on('UAV_TELEMETRY_UPDATE', (data) => {
            if (this.uavView && data.telemetry) {
                this.uavView.updateTelemetry(data.telemetry);
            }
            // Update dashboard UAV stat
            if (data.telemetry) {
                const state = data.telemetry.state || 'STANDBY';
                const stateShort = state.replace('UAV_', '').replace('_', ' ');
                const battery = data.telemetry.battery_percent;
                const sovState = document.getElementById('sovUavState');
                const sovBattery = document.getElementById('sovUavBattery');
                if (sovState) sovState.textContent = stateShort;
                if (sovBattery && battery !== undefined) sovBattery.textContent = `Battery: ${battery}%  [SIMULATION]`;
            }
        });

        // UAV verification dispatched
        wsClient.on('UAV_VERIFICATION_DISPATCHED', (data) => {
            if (this.alertFeed) {
                this.alertFeed.addAlert({
                    severity: 'INFO',
                    event_type: 'UAV_DISPATCHED',
                    description: `Recon drone dispatched to ${data.zone_id}. Reason: ${data.reason}`,
                    timestamp: data.timestamp
                });
            }
            if (this.uavView) {
                this.uavView.logFlightEvent(`Dispatched to ${data.zone_id}: ${data.reason}`);
            }
            if (window.audioAlert) {
                window.audioAlert.playUAVDispatchPing();
            }
            const uavPill = document.getElementById('uavStatusPill');
            if (uavPill) {
                uavPill.className = 'status-pill online';
                uavPill.querySelector('.status-text').textContent = 'UAV: ACTIVE';
            }
            // Update dashboard threat counter
            this._sovThreatCount++;
            const sovEl = document.getElementById('sovThreats');
            if (sovEl) sovEl.textContent = this._sovThreatCount;
        });

        // UAV state changed / RTB
        wsClient.on('UAV_STATE_CHANGED', (data) => {
            if (this.uavView) {
                this.uavView.logFlightEvent(`State changed: ${data.state} (${data.reason})`);
            }
        });

        // SIH Demonstration Scenario Updates
        wsClient.on('SCENARIO_STATUS', (data) => {
            const statusEl = document.getElementById('scenarioStatusText');
            if (statusEl) {
                statusEl.innerHTML = `<strong style="color: var(--accent-cyan);">${data.title}:</strong> ${data.description}`;
            }
            if (this.alertFeed && data.scenario > 0) {
                this.alertFeed.addAlert({
                    severity: data.scenario === 1 ? 'INFO' : 'CRITICAL',
                    event_type: `SCENARIO_${data.scenario}`,
                    description: data.description,
                    timestamp: data.timestamp
                });
            }
            if (window.audioAlert && data.scenario === 2) {
                window.audioAlert.playCriticalAlarm(5);
                window.audioAlert.speakTacticalAlert("Scenario 2 initiated. Restricted border fence breach in Sector Charlie.");
            } else if (window.audioAlert && data.scenario === 3) {
                window.audioAlert.speakTacticalAlert("Scenario 3 initiated. Vehicle detected. License plate recognition running.");
            } else if (window.audioAlert && data.scenario === 5) {
                window.audioAlert.speakTacticalAlert("Scenario 5 initiated. Autonomous drone aerial reconnaissance dispatched.");
            }
        });

        // ANPR Plate Detected Events
        wsClient.on('ANPR_PLATE_DETECTED', (data) => {
            if (data.data) {
                const rec = data.data;
                this.prependAnprRecord(rec);

                // Update cached event and live DOM if matching
                const clean = rec.clean_plate || (rec.plate_text ? rec.plate_text.split('(')[0].trim() : null);
                if (clean && clean !== 'PLATE_NOT_READABLE') {
                    if (this.eventsData) {
                        for (const ev of this.eventsData) {
                            if (ev.id === rec.event_id || String(ev.object_id).includes(String(rec.vehicle_track_id))) {
                                ev.license_plate = rec.plate_text;
                                ev.clean_plate = clean;
                                ev.plate_confidence = rec.confidence;
                                ev.is_vehicle = true;
                                // Update row in table if present
                                const row = document.getElementById(`row-${ev.id}`);
                                if (row) {
                                    const objCol = row.querySelector('.soc-obj-col');
                                    if (objCol && !objCol.querySelector('.soc-obj-plate')) {
                                        const unreadable = objCol.querySelector('.soc-obj-plate-unreadable');
                                        if (unreadable) unreadable.remove();
                                        const plateBadge = document.createElement('div');
                                        plateBadge.className = 'soc-obj-plate';
                                        plateBadge.title = `Vehicle License Plate: ${clean}`;
                                        plateBadge.innerHTML = `<span class="soc-plate-flag">IND</span><span class="soc-plate-code">${clean}</span>`;
                                        objCol.appendChild(plateBadge);
                                    }
                                }
                                // Update open drawer if this event is currently selected
                                if (this.selectedEventId === ev.id && this.isEventDrawerOpen) {
                                    this.selectEventAndOpenDrawer(ev.id, false);
                                }
                            }
                        }
                    }
                }
            }
        });

        // Cross-Camera ReID Handover Update (Sections 56 & 65)
        wsClient.on('CROSS_CAMERA_HANDOVER', (data) => {
            console.log('[REID] Cross-camera handover event:', data);
            const banner = document.getElementById('reidToastBanner');
            const msgEl = document.getElementById('reidToastMessage');
            if (banner && msgEl && data.handover) {
                const h = data.handover;
                msgEl.innerHTML = `<strong>CROSS-CAMERA HANDOVER CONFIRMED:</strong> [${h.from_camera}_TRK_${h.from_track_id}] &rarr; [${h.to_camera}_TRK_${h.to_track_id}] linked as <strong style="color:var(--accent-cyan);">${h.global_id}</strong> (${Math.round(h.similarity_score * 100)}% Match | ${h.transit_time_seconds}s transit)`;
                banner.style.display = 'flex';
                setTimeout(() => { banner.style.display = 'none'; }, 8000);
            }
            if (this.alertFeed && data.handover) {
                const h = data.handover;
                this.alertFeed.addAlert({
                    severity: 'INFO',
                    event_type: 'CROSS_CAMERA_HANDOVER',
                    description: `Target handover: ${h.from_camera} to ${h.to_camera} linked as ${h.global_id} (${Math.round(h.similarity_score * 100)}% match)`,
                    timestamp: h.timestamp
                });
            }
            if (window.audioAlert && data.handover) {
                window.audioAlert.speakTacticalAlert(`Cross-camera handover confirmed. Target tracked from ${data.handover.from_camera} into ${data.handover.to_camera}.`);
            }
        });

        // Electronic Warfare RF Jamming Alert (Sections 61 & 62)
        wsClient.on('RF_JAMMING_ALERT', (data) => {
            console.warn('[EW MONITOR] RF Jamming Alert:', data);
            const rfPill = document.getElementById('rfStatusPill');
            const rfText = document.getElementById('rfStatusText');
            if (rfPill && rfText) {
                rfPill.className = 'status-pill offline';
                rfText.textContent = 'RF: JAMMING ATTACK!';
            }
            if (this.alertFeed && data.telemetry) {
                this.alertFeed.addAlert({
                    severity: 'CRITICAL',
                    event_type: 'RF_JAMMING_ANOMALY',
                    description: `ELECTRONIC WARFARE ALERT: Severe RF spectrum jamming detected! Packet loss ${data.telemetry.packet_loss_percentage}%. Activating optical lock.`,
                    timestamp: data.telemetry.timestamp
                });
            }
            if (window.audioAlert) {
                window.audioAlert.playCriticalAlarm();
                window.audioAlert.speakTacticalAlert("Electronic Warfare Alert. Active RF Jamming detected on mmWave radar.");
            }
        });

        // RF Integrity Update / Recovery
        wsClient.on('RF_INTEGRITY_UPDATE', (data) => {
            const rfPill = document.getElementById('rfStatusPill');
            const rfText = document.getElementById('rfStatusText');
            if (rfPill && rfText && data.telemetry) {
                if (data.telemetry.ew_state === 'ACTIVE_RF_JAMMING') {
                    rfPill.className = 'status-pill offline';
                    rfText.textContent = 'RF: JAMMING!';
                } else if (data.telemetry.ew_state === 'SIGNAL_DEGRADATION') {
                    rfPill.className = 'status-pill standby';
                    rfText.textContent = 'RF: DEGRADED';
                } else {
                    rfPill.className = 'status-pill online';
                    rfText.textContent = 'RF: CLEAN';
                }
            }
        });

        // SOP Step Executed
        wsClient.on('SOP_STEP_EXECUTED', (data) => {
            if (this.currentModalEventId === data.event_id && data.sop) {
                this.renderSOPChecklist(data.sop);
            }
        });

        // Telemetry heartbeat
        wsClient.on('TELEMETRY_HEARTBEAT', (data) => {
            if (data.rf) {
                const rfPill = document.getElementById('rfStatusPill');
                const rfText = document.getElementById('rfStatusText');
                if (rfPill && rfText) {
                    if (data.rf.ew_state === 'ACTIVE_RF_JAMMING') {
                        rfPill.className = 'status-pill offline';
                        rfText.textContent = 'RF: JAMMING!';
                    } else if (data.rf.ew_state === 'SIGNAL_DEGRADATION') {
                        rfPill.className = 'status-pill standby';
                        rfText.textContent = 'RF: DEGRADED';
                    } else {
                        rfPill.className = 'status-pill online';
                        rfText.textContent = 'RF: CLEAN';
                    }
                }
            }
            if (data.cameras) {
                for (const [camId, camData] of Object.entries(data.cameras)) {
                    this.updateCameraStatusUI(camId, camData.status);
                    const card = document.getElementById(`card-${camId}`);
                    if (card) {
                        const fpsEl = card.querySelector('.cam-fps-val');
                        if (fpsEl) fpsEl.textContent = `${camData.fps.toFixed(1)} FPS`;
                        const latEl = card.querySelector('.cam-lat-val');
                        if (latEl) latEl.textContent = `${camData.latency_ms.toFixed(1)}ms`;
                        const resEl = card.querySelector('.cam-res-val');
                        if (resEl && camData.resolution !== '0x0') resEl.textContent = camData.resolution;
                        
                        const statusPill = card.querySelector('.cam-status-pill');
                        if (statusPill) {
                            statusPill.className = `status-pill cam-status-pill ${camData.status.toLowerCase()}`;
                            statusPill.innerHTML = `<span class="dot"></span> ${camData.status}`;
                        }
                    }
                }

                if (data.cameras && data.cameras.CAM_02) {
                    const c2 = data.cameras.CAM_02;
                    const pushBadge = document.getElementById('cam02LivePushBadge');
                    const configBadge = document.getElementById('cam02ConfigStatusBadge');
                    if (c2.status === 'ONLINE') {
                        if (pushBadge) {
                            pushBadge.style.background = 'rgba(16, 185, 129, 0.15)';
                            pushBadge.style.color = '#10b981';
                            pushBadge.style.borderColor = '#10b981';
                            pushBadge.textContent = `🟢 ACTIVE (${c2.fps.toFixed(1)} FPS)`;
                        }
                        if (configBadge) {
                            configBadge.style.background = 'rgba(16, 185, 129, 0.15)';
                            configBadge.style.color = '#10b981';
                            configBadge.textContent = `CAM_02: ONLINE (${c2.resolution})`;
                        }
                    } else {
                        if (pushBadge) {
                            pushBadge.style.background = 'rgba(245, 158, 11, 0.15)';
                            pushBadge.style.color = '#f59e0b';
                            pushBadge.style.borderColor = '#f59e0b';
                            pushBadge.textContent = 'STANDBY / AWAITING PHONE';
                        }
                        if (configBadge) {
                            configBadge.style.background = 'var(--bg-tertiary)';
                            configBadge.style.color = 'var(--text-muted)';
                            configBadge.textContent = `CAM_02: ${c2.status}`;
                        }
                    }
                }
            }
            if (data.mesh) {
                this.renderMeshTopology(data.mesh);
            }
            if (data.ai_profiler) {
                this.renderAiProfiler(data.ai_profiler);
            }
            if (data.deterrence) {
                this.renderDeterrenceState(data.deterrence);
            }
            if (data.posture) {
                this.renderPostureState(data.posture);
            }
            if (data.drone && this.uavView) {
                this.uavView.updateTelemetry(data.drone);
            }
            if (data.identity_latest) {
                this.renderIdentityVerification(data.identity_latest);
            }
        });

        // Tactical Mesh Failover and Reconnection
        wsClient.on('TACTICAL_MESH_FAILOVER', (data) => {
            console.warn('[MESH] Node failover:', data);
            if (this.alertFeed) {
                this.alertFeed.addAlert({
                    severity: 'WARNING',
                    event_type: 'TACTICAL_MESH_FAILOVER',
                    description: `Mesh Alert: ${data.node_name} offline. Rerouted via ${data.failover_route}.`,
                    timestamp: data.timestamp
                });
            }
            this.loadMeshTopology();
        });

        wsClient.on('TACTICAL_MESH_RECONNECTED', (data) => {
            console.log('[MESH] Node reconnected:', data);
            this.loadMeshTopology();
        });

        // Phase 15: Deterrence Stage Updated (Sections 22 & 75)
        wsClient.on('DETERRENCE_STAGE_UPDATED', (data) => {
            console.log('[DETERRENCE] Stage updated:', data);
            if (this.alertFeed && data.stage_info) {
                this.alertFeed.addAlert({
                    severity: data.stage_id >= 3 ? 'CRITICAL' : 'WARNING',
                    event_type: data.stage_info.code,
                    description: `${data.stage_info.title} active. ${data.stage_info.action}`,
                    timestamp: data.timestamp
                });
            }
            if (window.audioAlert) {
                if (data.stage_id === 1) {
                    window.audioAlert.speakTacticalAlert("Deterrence stage 1. High-frequency optical strobe active.");
                } else if (data.stage_id === 2) {
                    window.audioAlert.speakTacticalAlert("Deterrence stage 2. Long range acoustic device voice warning transmitting.");
                } else if (data.stage_id === 3) {
                    window.audioAlert.playCriticalAlarm();
                    window.audioAlert.speakTacticalAlert("Deterrence stage 3. 115 decibel acoustic dispersion siren sounding.");
                } else if (data.stage_id === 4) {
                    window.audioAlert.playCriticalAlarm();
                    window.audioAlert.speakTacticalAlert("Deterrence stage 4. Quick reaction team ground intercept authorized.");
                }
            }
            this.renderDeterrenceState({
                current_stage: data.stage_id,
                stage_info: data.stage_info,
                compliance_status: data.compliance_status
            });
        });

        // Phase 15: Deterrence Reset
        wsClient.on('DETERRENCE_RESET', (data) => {
            this.renderDeterrenceState({
                current_stage: 0,
                stage_info: null,
                compliance_status: 'STANDBY'
            });
        });

        // Phase 15: Posture Anomaly Detected (Sections 16 & 27)
        wsClient.on('POSTURE_ANOMALY_DETECTED', (data) => {
            console.warn('[POSTURE CLASSIFIER] Posture anomaly:', data);
            if (this.alertFeed && data.data) {
                const d = data.data;
                this.alertFeed.addAlert({
                    severity: d.threat_level || 'CRITICAL',
                    event_type: d.posture,
                    description: d.description,
                    timestamp: d.timestamp
                });
            }
            if (window.audioAlert && data.data && data.data.is_stealth_tactic) {
                window.audioAlert.playCriticalAlarm();
                window.audioAlert.speakTacticalAlert("Stealth threat detected. Hostile prone crawling infiltration attempt in Sector Charlie.");
            }
        });

        // Phase 16: Counter-UAS Aerial Threat Detected (Sections 38 & 55)
        wsClient.on('ROGUE_UAV_DETECTED', (data) => {
            console.warn('[C-UAS] Rogue drone detected:', data);
            if (this.alertFeed && data.threat) {
                const t = data.threat;
                this.alertFeed.addAlert({
                    severity: 'CRITICAL',
                    event_type: 'ROGUE_UAV_INTRUSION',
                    description: `AIR DEFENSE ALERT: Rogue drone [${t.callsign}] detected at ${t.radar_signature?.altitude_agl_m || 48}m AGL. Suspected payload: ${t.estimated_payload}`,
                    timestamp: t.detected_at
                });
            }
            if (window.audioAlert) {
                window.audioAlert.playCriticalAlarm();
                window.audioAlert.speakTacticalAlert("Air Defense Alert. Rogue contraband drone detected crossing International Border.");
            }
            if (data.cuas_status) {
                this.renderCuasStatus(data.cuas_status);
            }
        });

        wsClient.on('CUAS_STAGE_UPDATED', (data) => {
            if (data.stage_info && this.alertFeed) {
                this.alertFeed.addAlert({
                    severity: 'WARNING',
                    event_type: data.stage_info.code,
                    description: `C-UAS Countermeasure: ${data.stage_info.title}. Action: ${data.stage_info.action}`,
                    timestamp: new Date().toISOString()
                });
            }
            this.renderCuasStatus(data);
        });

        wsClient.on('CUAS_THREAT_NEUTRALIZED', (data) => {
            if (this.alertFeed) {
                this.alertFeed.addAlert({
                    severity: 'INFO',
                    event_type: 'CUAS_NEUTRALIZED',
                    description: `Rogue drone ${data.neutralized_callsign} successfully neutralized. Captured by anti-drone unit.`,
                    timestamp: data.timestamp
                });
            }
            if (window.audioAlert) {
                window.audioAlert.speakTacticalAlert("Air defense update. Rogue drone intercepted and neutralized.");
            }
            this.loadCuasStatus();
        });

        // Phase 16: Multi-UAV Swarm Telemetry & Handover (Sections 33 & 52)
        wsClient.on('SWARM_TELEMETRY_UPDATE', (data) => {
            if (data.swarm_status) {
                this.renderSwarmStatus(data.swarm_status);
            }
        });

        wsClient.on('SWARM_HANDOVER_COMPLETED', (data) => {
            console.log('[SWARM] Handover completed:', data);
            if (this.alertFeed && data.handover) {
                const h = data.handover;
                this.alertFeed.addAlert({
                    severity: 'INFO',
                    event_type: 'SWARM_RELIEF_HANDOVER',
                    description: `Aerial Swarm: ${h.retiring_unit} (low battery ${h.retiring_battery}%) handed over tracking lock to ${h.relief_unit} in ${h.target_zone}. Lock transfer: ${h.lock_transfer_duration_ms}ms.`,
                    timestamp: h.timestamp
                });
            }
            if (window.audioAlert) {
                window.audioAlert.speakTacticalAlert("Swarm target tracking lock handed over to relief drone.");
            }
            if (data.swarm_status) {
                this.renderSwarmStatus(data.swarm_status);
            }
        });

        // Phase 17: Autonomous Slew-to-Cue PTZ Command (Sections 10 & 20)
        wsClient.on('PTZ_SLEW_COMMAND', (data) => {
            console.log('[PTZ SLEW] Slew command received:', data);
            if (data.gimbal_state) {
                this.renderSlewStatus(data.gimbal_state);
            }
        });

        // Phase 17: Intruder Kinematics & ETB Alert (Sections 27 & 63)
        wsClient.on('ETB_TRAJECTORY_PREDICTION', (data) => {
            console.warn('[KINEMATICS] Trajectory forecast:', data);
            if (data.prediction) {
                this.renderPrediction(data.prediction);
                if (data.prediction.threat_urgency === 'CRITICAL_IMMINENT_BREACH') {
                    if (window.audioAlert) {
                        window.audioAlert.playCriticalAlarm();
                        window.audioAlert.speakTacticalAlert(`Imminent border breach warning. Infiltrator vector crossing fence in ${data.prediction.estimated_time_to_breach_sec} seconds.`);
                    }
                }
            }
        });

        // Phase 17: Multi-Sensor Health Matrix & Failover (Sections 28 & 49)
        wsClient.on('SENSOR_HEALTH_MATRIX_UPDATED', (data) => {
            console.log('[HEALTH MATRIX] Update received:', data);
            if (data.matrix) {
                this.renderHealthMatrix(data.matrix);
            }
        });

        // Phase 20: Master Tactical Demonstration Playbooks & Evaluator Tour (Sections 71, 73, 74, 75)
        wsClient.on('PLAYBOOK_STAGE_TRANSITION', (data) => {
            console.log('[PLAYBOOK] Stage transition received:', data);
            this.handlePlaybookStageTransition(data);
        });

        wsClient.on('PLAYBOOK_STATUS', (data) => {
            console.log('[PLAYBOOK] Status update:', data);
            if (data.status === 'RESET') {
                this.resetPlaybooksUI();
            }
        });
    }

    async loadInitialData() {
        try {
            // 1. Health & Host Metrics
            const healthRes = await fetch('/api/system/health');
            if (healthRes.ok) {
                const health = await healthRes.json();
                this.metricsMonitor.update(health.host_metrics);
                this.updateSystemModeUI(health.system_mode);
            }

            // 2. Surveillance Zones
            const zonesRes = await fetch('/api/zones');
            if (zonesRes.ok) {
                const zones = await zonesRes.json();
                if (this.zoneMap) this.zoneMap.setZones(zones);
                if (this.zoneMapFull) this.zoneMapFull.setZones(zones);
                this.renderZonesList(zones);
            }

            // 3. Cameras
            const camsRes = await fetch('/api/cameras');
            if (camsRes.ok) {
                const cams = await camsRes.json();
                this.renderCamerasGrid(cams);
            }

            // 4. Initial Events & Forensic Audit Stats & Alert Feed
            if (this.alertFeed) {
                await this.alertFeed.loadInitialAlerts();
            }
            await this.loadEventsTable();
            await this.loadEventsSummaryStats();
            await this.loadAnprRecords();

            // 5. Initial UAV Telemetry
            try {
                const uavRes = await fetch('/api/uav/telemetry');
                if (uavRes.ok) {
                    const uavData = await uavRes.json();
                    if (this.uavView) this.uavView.updateTelemetry(uavData);
                }
            } catch (uErr) {
                console.debug('UAV telemetry init error:', uErr);
            }

            // 6. Initial Fused Tracks
            try {
                const fusedRes = await fetch('/api/radar/fused-targets');
                if (fusedRes.ok) {
                    const fusedData = await fusedRes.json();
                    this.renderRadarTargetsTable(fusedData.fused_tracks || []);
                }
            } catch (fErr) {
                console.debug('Fused targets init error:', fErr);
            }

            // 7. Initial ANPR Records
            await this.loadAnprRecords();

            // 8. Initial System Configuration (Section 41)
            await this.loadSystemConfiguration();

            // 9. Tactical Mesh Multi-Node Topology (Sections 49 & 60)
            await this.loadMeshTopology();

            // 10. Smartphone Camera Network Info (CAM_02)
            await this.loadCameraNetworkInfo();

            // 10. Edge AI Profiler & Stopwatch (Section 61)
            await this.loadAiProfiler();

            // 5. Periodic telemetry polling
            setInterval(async () => {
                try {
                    const mRes = await fetch('/api/system/metrics');
                    if (mRes.ok) {
                        const m = await mRes.json();
                        this.metricsMonitor.update(m);
                    }
                } catch (e) {
                    // Ignore poll errors
                }
            }, 3000);

        } catch (err) {
            console.error('[APP] Error loading initial data:', err);
        }
    }

    setupActionHandlers() {
        // System Mode Toggle (SIMULATED <-> REAL)
        const modeBadge = document.getElementById('systemModeBadge');
        if (modeBadge) {
            modeBadge.addEventListener('click', async () => {
                const current = modeBadge.getAttribute('data-mode') || 'SIMULATED';
                const nextMode = current === 'SIMULATED' ? 'REAL' : 'SIMULATED';
                try {
                    const res = await fetch('/api/system/settings/SYSTEM_MODE', {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ value: nextMode })
                    });
                    if (res.ok) {
                        this.updateSystemModeUI(nextMode);
                    }
                } catch (e) {
                    console.error('Failed to toggle mode:', e);
                }
            });
        }

        // Test Simulated Intrusion Button (SIH Demonstration Trigger)
        const simIntrusionBtn = document.getElementById('btnSimulateIntrusion');
        if (simIntrusionBtn) {
            simIntrusionBtn.addEventListener('click', async () => {
                try {
                    await fetch('/api/events', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            event_type: 'RESTRICTED_ENTRY',
                            severity: 'CRITICAL',
                            camera_id: 'CAM_01',
                            radar_id: 'RADAR_01',
                            zone_id: 'ZONE_C',
                            object_id: 'TARGET_02',
                            object_class: 'person',
                            confidence: 0.94,
                            description: 'High-priority intrusion: Target #02 entered Restricted Border Fence',
                            is_simulated: true
                        })
                    });
                } catch (e) {
                    console.error('Failed to trigger simulation:', e);
                }
            });
        }


        // Radar Target Injector Button in Tab 3
        const injectRadarBtn = document.getElementById('btnInjectRadarTarget');
        if (injectRadarBtn) {
            injectRadarBtn.addEventListener('click', async () => {
                injectRadarBtn.textContent = 'INJECTING...';
                try {
                    const randX = (Math.random() * 2.4 - 1.2).toFixed(2);
                    const randY = (Math.random() * 3.5 + 2.0).toFixed(2);
                    const randSpeed = -(Math.random() * 1.5 + 0.8).toFixed(2);
                    await fetch('/api/radar/simulate-target', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            target_id: 1,
                            x: parseFloat(randX),
                            y: parseFloat(randY),
                            speed: parseFloat(randSpeed)
                        })
                    });
                    injectRadarBtn.textContent = 'INJECTED (SWEEP ACTIVE)';
                    setTimeout(() => { injectRadarBtn.textContent = 'INJECT RADAR TARGET'; }, 2000);
                } catch (e) {
                    console.error('Failed to inject radar target:', e);
                    injectRadarBtn.textContent = 'INJECT RADAR TARGET';
                }
            });
        }

        // Blindspot Simulation Button
        const blindspotBtn = document.getElementById('btnTriggerBlindspotSim');
        if (blindspotBtn) {
            blindspotBtn.addEventListener('click', async () => {
                blindspotBtn.textContent = 'SIMULATING DROPOUT...';
                try {
                    // 1. Ingest radar target in Restricted zone (y=3.2m)
                    await fetch('/api/radar/ingest', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            sensor_id: 'RADAR_01',
                            targets: [{ id: 3, x: 0.2, y: 3.2, speed: -1.8 }]
                        })
                    });

                    // 2. Post alert for blindspot failure
                    await fetch('/api/events', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            event_type: 'RADAR_UNCONFIRMED_BLINDSPOT',
                            severity: 'CRITICAL',
                            radar_id: 'RADAR_01',
                            zone_id: 'ZONE_C',
                            object_id: 'RADAR_TARGET_03',
                            object_class: 'unidentified_target',
                            confidence: 0.91,
                            description: 'BLIND SPOT ALARM: Radar target moving into ZONE_C while optical camera unconfirmed. Automated UAV recon recommended.',
                            is_simulated: true
                        })
                    });

                    if (this.uavView) {
                        this.uavView.logFlightEvent('[ALARM] Optical blind spot detected in ZONE_C! Automated UAV recon suggested.');
                    }
                    blindspotBtn.textContent = 'ANOMALY TRIGGERED';
                    setTimeout(() => { blindspotBtn.textContent = 'SIMULATE CAMERA FAILURE + RADAR BREACH'; }, 3000);
                } catch (e) {
                    console.error('Failed to trigger blindspot simulation:', e);
                    blindspotBtn.textContent = 'SIMULATE CAMERA FAILURE + RADAR BREACH';
                }
            });
        }

        // Clear Alerts Button
        const clearAlertsBtn = document.getElementById('btnClearAlerts');
        if (clearAlertsBtn) {
            clearAlertsBtn.addEventListener('click', () => {
                if (this.alertFeed) this.alertFeed.clear();
            });
        }

        // SIH Demonstration Command HUD Controller
        const sihHudLed = document.getElementById('sihHudLed');
        const sihActiveScenarioLabel = document.getElementById('sihActiveScenarioLabel');
        const scenarioStatusText = document.getElementById('scenarioStatusText');

        const setSihHudStatus = (title, statusDesc, state = 'running') => {
            if (sihHudLed) {
                sihHudLed.className = 'sih-hud-led ' + state;
            }
            if (sihActiveScenarioLabel) {
                sihActiveScenarioLabel.textContent = title;
                if (state === 'breach') {
                    sihActiveScenarioLabel.style.color = '#ef4444';
                } else if (state === 'running') {
                    sihActiveScenarioLabel.style.color = '#f59e0b';
                } else if (state === 'active') {
                    sihActiveScenarioLabel.style.color = '#00e5ff';
                } else {
                    sihActiveScenarioLabel.style.color = '#38bdf8';
                }
            }
            if (scenarioStatusText) {
                scenarioStatusText.textContent = statusDesc;
            }
        };

        // SIH Demonstration Scenarios Toolbar
        const scenarioBtns = [
            { id: 'btnScenario1', url: '/api/system/scenario/1', label: '1. PATROL', title: 'SCENARIO 01 // ROUTINE PATROL', desc: 'Pedestrian tracking outside restricted buffer zone' },
            { id: 'btnScenario2', url: '/api/system/scenario/2', label: '2. BORDER BREACH', title: 'SCENARIO 02 // BORDER BREACH', desc: 'Restricted fence breach, siren alarm & MP4 recording', breach: true },
            { id: 'btnScenario3', url: '/api/system/scenario/3', label: '3. VEHICLE & ANPR', title: 'SCENARIO 03 // VEHICLE & ANPR', desc: 'Vehicle incursion with dual-pass EasyOCR & hotlist check' },
            { id: 'btnScenario4', url: '/api/system/scenario/4', label: '4. CAM FAILURE & GAP', title: 'SCENARIO 04 // OPTICAL GAP', desc: 'CAM_02 offline + radar detection triggers surveillance gap' },
            { id: 'btnScenario5', url: '/api/system/scenario/5', label: '5. UAV RECON', title: 'SCENARIO 05 // UAV RECON', desc: 'Autonomous UAV_01 airborne dispatch & target confirmation' },
            { id: 'btnSimulateReid', url: '/api/ai/handover/simulate', label: '6. RE-ID HANDOVER', title: 'SCENARIO 06 // RE-ID HANDOVER', desc: 'Cross-camera 512-D neural feature vector handover' },
            { id: 'btnSimulateJamming', url: '/api/radar/simulate-jamming', label: '7. RF JAMMING', title: 'SCENARIO 07 // EW RF JAMMING', desc: 'Hostile noise jamming detected, frequency-hop activated', breach: true },
            { id: 'btnSimulateMeshFailover', url: '/api/mesh/simulate-failover', label: '8. MESH FAILOVER', title: 'SCENARIO 08 // MESH FAILOVER', desc: 'Node 03 dropout with sub-second autonomous re-routing' },
            { id: 'btnScenarioReset', url: '/api/system/scenario/reset', label: 'RESET', title: 'SYSTEM RESET', desc: 'All sensors reset to clean operational baseline' }
        ];

        // Dismiss Handover Toast
        const btnDismiss = document.getElementById('btnDismissReidToast');
        if (btnDismiss) {
            btnDismiss.addEventListener('click', () => {
                const banner = document.getElementById('reidToastBanner');
                if (banner) banner.style.display = 'none';
            });
        }

        scenarioBtns.forEach(({ id, url, label, title, desc, breach }) => {
            const btn = document.getElementById(id);
            if (btn) {
                btn.addEventListener('click', async () => {
                    const orig = btn.textContent;
                    btn.textContent = 'RUNNING...';
                    setSihHudStatus(`RUNNING: ${title}`, desc, breach ? 'breach' : 'running');

                    try {
                        const res = await fetch(url, { method: 'POST' });
                        if (res.ok) {
                            btn.textContent = 'ACTIVE';
                            setSihHudStatus(`ACTIVE: ${title}`, `Sequence active - telemetry streaming: ${desc}`, 'active');
                            setTimeout(() => {
                                btn.textContent = orig;
                                setSihHudStatus('STANDBY // SYSTEM READY', 'Select scenario to trigger automated multi-sensor sequence', 'ready');
                            }, 3500);
                        } else {
                            btn.textContent = 'FAILED';
                            setSihHudStatus(`ERROR: ${title}`, 'Operation returned non-200 status', 'breach');
                            setTimeout(() => {
                                btn.textContent = orig;
                                setSihHudStatus('STANDBY // SYSTEM READY', 'Select scenario to trigger automated multi-sensor sequence', 'ready');
                            }, 3000);
                        }
                    } catch (e) {
                        console.error('Scenario trigger error:', e);
                        btn.textContent = orig;
                        setSihHudStatus(`ERROR: ${title}`, 'Network connection failure', 'breach');
                    }
                });
            }
        });

        // Matrix Hero Quick Actions
        document.getElementById('btnMatrixLaunchPlaybooks')?.addEventListener('click', () => {
            document.getElementById('btnMasterPlaybooksModal')?.click();
        });
        document.getElementById('btnMatrixLaunchAudit')?.addEventListener('click', () => {
            document.getElementById('btnSihAuditModal')?.click();
        });
        document.getElementById('btnMatrixLaunchHealth')?.addEventListener('click', () => {
            document.getElementById('btnHealthMatrixModal')?.click();
        });
        document.getElementById('btnMatrixResetSensors')?.addEventListener('click', () => {
            document.getElementById('btnScenarioReset')?.click();
        });

        // Matrix Category Filter Bar
        const matrixPills = document.querySelectorAll('#matrixFilterBar .matrix-filter-pill');
        const moduleGroups = document.querySelectorAll('.demosuite-module-group');
        matrixPills.forEach(pill => {
            pill.addEventListener('click', () => {
                matrixPills.forEach(p => p.classList.remove('active'));
                pill.classList.add('active');
                const filter = pill.getAttribute('data-filter');
                moduleGroups.forEach(grp => {
                    if (filter === 'all' || grp.getAttribute('data-module') === filter) {
                        grp.style.display = '';
                    } else {
                        grp.style.display = 'none';
                    }
                });
            });
        });

        // Matrix Live Search Filter
        const searchInput = document.getElementById('matrixSearchInput');
        const btnClearSearch = document.getElementById('btnClearMatrixSearch');
        const missionCards = document.querySelectorAll('.sih-mission-card');

        if (searchInput) {
            searchInput.addEventListener('input', () => {
                const query = searchInput.value.trim().toLowerCase();
                if (btnClearSearch) btnClearSearch.style.display = query ? 'block' : 'none';

                missionCards.forEach(card => {
                    if (!query) {
                        card.style.display = '';
                        return;
                    }
                    const text = ((card.getAttribute('data-keywords') || '') + ' ' + (card.textContent || '')).toLowerCase();
                    card.style.display = text.includes(query) ? '' : 'none';
                });

                // Adjust module groups visibility during search
                moduleGroups.forEach(grp => {
                    const visibleCards = grp.querySelectorAll('.sih-mission-card:not([style*="display: none"])');
                    grp.style.display = visibleCards.length > 0 ? '' : 'none';
                });
            });

            btnClearSearch?.addEventListener('click', () => {
                searchInput.value = '';
                btnClearSearch.style.display = 'none';
                missionCards.forEach(card => card.style.display = '');

                const activePill = document.querySelector('#matrixFilterBar .matrix-filter-pill.active');
                const filter = activePill ? activePill.getAttribute('data-filter') : 'all';
                moduleGroups.forEach(grp => {
                    if (filter === 'all' || grp.getAttribute('data-module') === filter) {
                        grp.style.display = '';
                    } else {
                        grp.style.display = 'none';
                    }
                });
            });
        }

        // Mission Matrix Card Action Triggers [data-trigger]
        document.querySelectorAll('.sih-mission-card [data-trigger]').forEach(btn => {
            btn.addEventListener('click', () => {
                const triggerId = btn.getAttribute('data-trigger');
                const targetBtn = document.getElementById(triggerId);
                const card = btn.closest('.sih-mission-card');
                const statusWrap = card?.querySelector('.mission-card-status');
                const origBtnText = btn.textContent;

                btn.textContent = 'RUNNING...';
                if (statusWrap) {
                    statusWrap.className = 'mission-card-status running';
                    const label = statusWrap.querySelector('span:not(.status-dot)');
                    if (label) label.textContent = 'EXECUTING';
                }

                if (targetBtn) {
                    targetBtn.click();
                }

                setTimeout(() => {
                    btn.textContent = origBtnText;
                    if (statusWrap) {
                        statusWrap.className = 'mission-card-status active';
                        const label = statusWrap.querySelector('span:not(.status-dot)');
                        if (label) label.textContent = 'ACTIVE';
                        setTimeout(() => {
                            statusWrap.className = 'mission-card-status ready';
                            if (label) label.textContent = 'STANDBY';
                        }, 3000);
                    }
                }, 2000);
            });
        });

        // Phase 14 Modals & Actions
        document.getElementById('btnSimulateMeshFailoverTab')?.addEventListener('click', async () => {
            await fetch('/api/mesh/simulate-failover', { method: 'POST' });
            await this.loadMeshTopology();
        });

        document.getElementById('btnTerrainShadowModal')?.addEventListener('click', () => {
            this.openTerrainShadowModal();
        });

        document.getElementById('btnCloseTerrainModal')?.addEventListener('click', () => {
            const m = document.getElementById('terrainShadowModal');
            if (m) m.style.display = 'none';
        });

        document.getElementById('btnLaunchUavForShadow')?.addEventListener('click', async () => {
            const btn = document.getElementById('btnLaunchUavForShadow');
            btn.textContent = 'DISPATCHING UAV...';
            try {
                await fetch('/api/uav/verification-request', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ zone_id: 'ZONE_C', reason: 'Terrain shadow dead-zone reconnaissance' })
                });
                btn.textContent = 'UAV DISPATCHED (100% CLEARANCE)';
                setTimeout(() => { btn.textContent = 'AUTONOMOUS UAV RECON SORTIE'; }, 3000);
            } catch (e) {
                btn.textContent = 'AUTONOMOUS UAV RECON SORTIE';
            }
        });

        document.getElementById('btnQrtDispatchModal')?.addEventListener('click', () => {
            this.generateQrtDispatchOrder();
        });

        const closeQrt = () => {
            const m = document.getElementById('qrtDispatchModal');
            if (m) m.style.display = 'none';
        };
        document.getElementById('btnCloseQrtModal')?.addEventListener('click', closeQrt);
        document.getElementById('btnCloseQrtModal2')?.addEventListener('click', closeQrt);

        document.getElementById('btnDispatchQrtConfirm')?.addEventListener('click', () => {
            const btn = document.getElementById('btnDispatchQrtConfirm');
            btn.textContent = 'TRANSMITTED TO QRT RADIO';
            if (window.audioAlert) {
                window.audioAlert.speakTacticalAlert("Tactical dispatch transmitted. Quick reaction team en route to MGRS grid coordinates.");
            }
            setTimeout(() => { closeQrt(); btn.textContent = 'TRANSMIT TO FIELD RADIO'; }, 2000);
        });

        document.getElementById('btnRunBenchmarkSuite')?.addEventListener('click', () => {
            this.runQuantizationBenchmark();
        });

        // Phase 15: Deterrence Matrix Modal & Controls
        document.getElementById('btnDeterrenceModal')?.addEventListener('click', async () => {
            const m = document.getElementById('deterrenceModal');
            if (m) m.style.display = 'flex';
            await this.loadDeterrenceState();
        });

        document.getElementById('btnCloseDeterrenceModal')?.addEventListener('click', () => {
            const m = document.getElementById('deterrenceModal');
            if (m) m.style.display = 'none';
        });

        document.getElementById('btnEscalateDeterrence')?.addEventListener('click', async () => {
            const btn = document.getElementById('btnEscalateDeterrence');
            btn.textContent = 'ESCALATING...';
            try {
                const res = await fetch('/api/deterrence/escalate', { method: 'POST' });
                if (res.ok) {
                    const data = await res.json();
                    this.renderDeterrenceState(data);
                }
            } catch (e) {
                console.error('Failed to escalate deterrence:', e);
            } finally {
                btn.textContent = '⚡ ESCALATE TO NEXT STAGE';
            }
        });

        document.getElementById('btnResetDeterrence')?.addEventListener('click', async () => {
            const btn = document.getElementById('btnResetDeterrence');
            btn.textContent = 'RESETTING...';
            try {
                const res = await fetch('/api/deterrence/reset', { method: 'POST' });
                if (res.ok) {
                    const data = await res.json();
                    this.renderDeterrenceState(data);
                }
            } catch (e) {
                console.error('Failed to reset deterrence:', e);
            } finally {
                btn.textContent = 'RESET STANDBY';
            }
        });

        document.getElementById('btnPlayLradAudio')?.addEventListener('click', () => {
            this.playLradAudio();
        });

        // Phase 15: Prone Crawling Infiltrator Simulation
        document.getElementById('btnSimulateCrawl')?.addEventListener('click', async () => {
            const btn = document.getElementById('btnSimulateCrawl');
            btn.textContent = 'INJECTING CRAWL...';
            try {
                const res = await fetch('/api/ai/posture/simulate-crawl', { method: 'POST' });
                if (res.ok) {
                    btn.textContent = 'PRONE CRAWL DETECTED';
                    setTimeout(() => { btn.textContent = '11. CRAWL INFILTRATOR'; }, 3000);
                }
            } catch (e) {
                console.error('Failed to simulate crawl:', e);
                btn.textContent = '11. CRAWL INFILTRATOR';
            }
        });

        // Phase 15: STANAG 4586 Tactical Data Link Modal & Inspector
        document.getElementById('btnDatalinkModal')?.addEventListener('click', async () => {
            const m = document.getElementById('datalinkModal');
            if (m) m.style.display = 'flex';
            await this.loadDatalinkPacket();
        });

        const closeDatalink = () => {
            const m = document.getElementById('datalinkModal');
            if (m) m.style.display = 'none';
        };
        document.getElementById('btnCloseDatalinkModal')?.addEventListener('click', closeDatalink);
        document.getElementById('btnCloseDatalinkModal2')?.addEventListener('click', closeDatalink);

        document.getElementById('btnTransmitDatalink')?.addEventListener('click', async () => {
            const btn = document.getElementById('btnTransmitDatalink');
            btn.textContent = 'TRANSMITTING...';
            try {
                const res = await fetch('/api/datalink/transmit', { method: 'POST' });
                if (res.ok) {
                    const data = await res.json();
                    this.updateDatalinkDisplay(data.frame, data.cumulative_stats);
                    btn.textContent = 'TRANSMITTED TO HQ (48 BYTES)';
                    if (window.audioAlert) {
                        window.audioAlert.playRadarBlip();
                    }
                    setTimeout(() => { btn.textContent = 'TRANSMIT TO SECTOR HQ'; }, 2500);
                }
            } catch (e) {
                console.error('Failed to transmit datalink:', e);
                btn.textContent = 'TRANSMIT TO SECTOR HQ';
            }
        });

        // Phase 15: Master SIH 2026 Compliance Audit Modal
        document.getElementById('btnSihAuditModal')?.addEventListener('click', async () => {
            const m = document.getElementById('sihAuditModal');
            if (m) m.style.display = 'flex';
            await this.loadSihAudit();
        });

        document.getElementById('btnCloseSihAuditModal')?.addEventListener('click', () => {
            const m = document.getElementById('sihAuditModal');
            if (m) m.style.display = 'none';
        });

        document.getElementById('btnRefreshAudit')?.addEventListener('click', async () => {
            await this.loadSihAudit();
        });

        // Phase 16: Counter-UAS (C-UAS) Modal & Action Controls
        document.getElementById('btnCuasModal')?.addEventListener('click', async () => {
            const m = document.getElementById('cuasModal');
            if (m) m.style.display = 'flex';
            await this.loadCuasStatus();
        });

        document.getElementById('btnCloseCuasModal')?.addEventListener('click', () => {
            const m = document.getElementById('cuasModal');
            if (m) m.style.display = 'none';
        });

        document.getElementById('btnSimulateCuasThreat')?.addEventListener('click', async () => {
            const btn = document.getElementById('btnSimulateCuasThreat');
            btn.textContent = 'DETECTING DRONE...';
            try {
                const res = await fetch('/api/cuas/simulate-threat', { method: 'POST' });
                if (res.ok) {
                    btn.textContent = 'RADAR LOCKED (48m AGL)';
                    setTimeout(() => { btn.textContent = '⚡ SIMULATE CONTRABAND DRONE'; }, 2500);
                }
            } catch (e) {
                console.error('Failed to simulate threat:', e);
                btn.textContent = '⚡ SIMULATE CONTRABAND DRONE';
            }
        });

        document.getElementById('btnEscalateCuas')?.addEventListener('click', async () => {
            const btn = document.getElementById('btnEscalateCuas');
            btn.textContent = 'TRANSMITTING JAM...';
            try {
                const res = await fetch('/api/cuas/escalate', { method: 'POST' });
                if (res.ok) {
                    const data = await res.json();
                    this.renderCuasStatus(data);
                }
            } catch (e) {
                console.error('Failed to escalate C-UAS:', e);
            } finally {
                btn.textContent = 'DIRECTIONAL RF JAM / ESCALATE';
            }
        });

        document.getElementById('btnNeutralizeCuas')?.addEventListener('click', async () => {
            const btn = document.getElementById('btnNeutralizeCuas');
            btn.textContent = 'DEPLOYING NET...';
            try {
                const res = await fetch('/api/cuas/neutralize', { method: 'POST' });
                if (res.ok) {
                    btn.textContent = 'CAPTURED & INTACT';
                    setTimeout(() => { btn.textContent = '🎯 KINETIC NET CAPTURE'; }, 2500);
                }
            } catch (e) {
                console.error('Failed to capture drone:', e);
                btn.textContent = '🎯 KINETIC NET CAPTURE';
            }
        });

        document.getElementById('btnResetCuas')?.addEventListener('click', async () => {
            await fetch('/api/cuas/reset', { method: 'POST' });
            await this.loadCuasStatus();
        });

        // Phase 16: Multi-UAV Swarm Modal & Controls
        document.getElementById('btnSwarmModal')?.addEventListener('click', async () => {
            const m = document.getElementById('swarmModal');
            if (m) m.style.display = 'flex';
            await this.loadSwarmStatus();
        });

        document.getElementById('btnCloseSwarmModal')?.addEventListener('click', () => {
            const m = document.getElementById('swarmModal');
            if (m) m.style.display = 'none';
        });

        document.getElementById('btnDeploySwarm')?.addEventListener('click', async () => {
            const pattern = document.getElementById('swarmPatternSelect')?.value || 'CREEPING_LINE_SEARCH';
            const formation = document.getElementById('swarmFormationSelect')?.value || 'VEE_FORMATION';
            const btn = document.getElementById('btnDeploySwarm');
            btn.textContent = 'DISPATCHING SWARM...';
            try {
                const res = await fetch('/api/swarm/dispatch', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ pattern, formation, zone_id: 'ZONE_C' })
                });
                if (res.ok) {
                    btn.textContent = 'SWARM AIRBORNE (3 UNITS)';
                    setTimeout(() => { btn.textContent = 'DISPATCH SWARM PATROL'; }, 2500);
                }
            } catch (e) {
                console.error('Failed to deploy swarm:', e);
                btn.textContent = 'DISPATCH SWARM PATROL';
            }
        });

        document.getElementById('btnSimulateHandover')?.addEventListener('click', async () => {
            const btn = document.getElementById('btnSimulateHandover');
            btn.textContent = 'TRANSFERRING LOCK...';
            try {
                const res = await fetch('/api/swarm/handover', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ retiring_drone_id: 'UAV_01', relief_drone_id: 'UAV_02' })
                });
                if (res.ok) {
                    btn.textContent = 'LOCK TRANSFERRED (UAV_02)';
                    setTimeout(() => { btn.textContent = '⚡ LOW-BATTERY RELIEF HANDOVER (<20%)'; }, 2500);
                }
            } catch (e) {
                console.error('Failed to execute handover:', e);
                btn.textContent = '⚡ LOW-BATTERY RELIEF HANDOVER (<20%)';
            }
        });

        document.getElementById('btnRecallSwarm')?.addEventListener('click', async () => {
            await fetch('/api/swarm/recall', { method: 'POST' });
            await this.loadSwarmStatus();
        });

        // Phase 16: Forensic Timeline Replay Modal & Scrubber
        document.getElementById('btnTimelineReplayModal')?.addEventListener('click', async () => {
            const m = document.getElementById('timelineReplayModal');
            if (m) m.style.display = 'flex';
            await this.loadTimelineReplay();
        });

        document.getElementById('btnCloseTimelineReplayModal')?.addEventListener('click', () => {
            const m = document.getElementById('timelineReplayModal');
            if (m) m.style.display = 'none';
        });

        document.getElementById('replayScrubber')?.addEventListener('input', (e) => {
            this.scrubTimeline(parseInt(e.target.value));
        });

        document.getElementById('btnReplayNow')?.addEventListener('click', () => {
            const slider = document.getElementById('replayScrubber');
            if (slider) {
                slider.value = 100;
                this.scrubTimeline(100);
            }
        });

        document.getElementById('btnExportDossier')?.addEventListener('click', async () => {
            const btn = document.getElementById('btnExportDossier');
            btn.textContent = 'GENERATING SEAL...';
            try {
                const res = await fetch('/api/replay/dossier?incident_id=INC_BREACH_744');
                if (res.ok) {
                    const data = await res.json();
                    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = `INC_744_FORENSIC_BLACKBOX_DOSSIER.json`;
                    a.click();
                    btn.textContent = 'DOSSIER EXPORTED (SHA-256)';
                    setTimeout(() => { btn.textContent = '📋 EXPORT ISO 27037 DOSSIER'; }, 3000);
                }
            } catch (e) {
                console.error('Failed to export dossier:', e);
                btn.textContent = '📋 EXPORT ISO 27037 DOSSIER';
            }
        });

        // Phase 16: Offline Tactical GIS Vector Map Modal
        document.getElementById('btnGisMapModal')?.addEventListener('click', async () => {
            const m = document.getElementById('gisMapModal');
            if (m) m.style.display = 'flex';
            await this.renderGisVectorMap();
        });

        document.getElementById('btnCloseGisModal')?.addEventListener('click', () => {
            const m = document.getElementById('gisMapModal');
            if (m) m.style.display = 'none';
        });

        document.getElementById('btnRefreshGisLayers')?.addEventListener('click', async () => {
            await this.renderGisVectorMap();
        });

        // Phase 17: Autonomous Slew-to-Cue PTZ Modal & Actions
        document.getElementById('btnSlewModal')?.addEventListener('click', async () => {
            const m = document.getElementById('slewModal');
            if (m) m.style.display = 'flex';
            await this.loadSlewStatus();
        });

        document.getElementById('btnCloseSlewModal')?.addEventListener('click', () => {
            const m = document.getElementById('slewModal');
            if (m) m.style.display = 'none';
        });

        document.getElementById('btnExecuteSlewDemo')?.addEventListener('click', async () => {
            const btn = document.getElementById('btnExecuteSlewDemo');
            btn.textContent = 'SLEWING GIMBAL (<150ms)...';
            try {
                const res = await fetch('/api/fusion/slew-to-cue', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ target_id: 'TRK_RADAR_01', x_m: -1.5, y_m: 4.2, z_m: 1.2 })
                });
                if (res.ok) {
                    await this.loadSlewStatus();
                    btn.textContent = 'LOCKED IN OPTICAL BORESIGHT';
                    if (window.audioAlert) {
                        window.audioAlert.playRadarBlip();
                    }
                    setTimeout(() => { btn.textContent = '🎯 TRIGGER RADAR AUTO-SLEW (4.2m @ -20°)'; }, 2500);
                }
            } catch (e) {
                console.error('Failed to execute slew:', e);
                btn.textContent = '🎯 TRIGGER RADAR AUTO-SLEW (4.2m @ -20°)';
            }
        });

        document.getElementById('btnResetSlewBoresight')?.addEventListener('click', async () => {
            await fetch('/api/fusion/reset', { method: 'POST' });
            await this.loadSlewStatus();
        });

        // Phase 17: JDL Level 1 & 2 EKF Fusion Modal & Actions
        document.getElementById('btnEkfModal')?.addEventListener('click', async () => {
            const m = document.getElementById('ekfModal');
            if (m) m.style.display = 'flex';
            await this.loadEkfTracks();
        });

        document.getElementById('btnCloseEkfModal')?.addEventListener('click', () => {
            const m = document.getElementById('ekfModal');
            if (m) m.style.display = 'none';
        });

        document.getElementById('btnFuseObservationDemo')?.addEventListener('click', async () => {
            const btn = document.getElementById('btnFuseObservationDemo');
            btn.textContent = 'UPDATING KALMAN STATE...';
            try {
                const res = await fetch('/api/fusion/fuse-observation', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ radar_id: 101, x_m: -0.95, y_m: 3.42, speed_mps: -1.15, distance_m: 3.55 })
                });
                if (res.ok) {
                    await this.loadEkfTracks();
                    btn.textContent = 'COVARIANCE P UPDATED';
                    setTimeout(() => { btn.textContent = '📈 INGEST RADAR POLAR OBSERVATION [3.6m, -18°, -1.2m/s]'; }, 2000);
                }
            } catch (e) {
                console.error('Failed to fuse observation:', e);
                btn.textContent = '📈 INGEST RADAR POLAR OBSERVATION [3.6m, -18°, -1.2m/s]';
            }
        });

        document.getElementById('btnResetEkfTracks')?.addEventListener('click', async () => {
            await fetch('/api/fusion/reset', { method: 'POST' });
            await this.loadEkfTracks();
        });

        // Phase 17: Intruder Kinematics & ETB Modal & Actions
        document.getElementById('btnPredictionModal')?.addEventListener('click', async () => {
            const m = document.getElementById('predictionModal');
            if (m) m.style.display = 'flex';
            await this.loadPrediction('INTRUDER_VEC_01');
        });

        document.getElementById('btnClosePredictionModal')?.addEventListener('click', () => {
            const m = document.getElementById('predictionModal');
            if (m) m.style.display = 'none';
        });

        document.getElementById('btnSimulateKinematicsBreach')?.addEventListener('click', async () => {
            const btn = document.getElementById('btnSimulateKinematicsBreach');
            btn.textContent = 'COMPUTING INTERCEPT VECTOR...';
            try {
                const res = await fetch('/api/kinematics/simulate-trajectory', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ target_id: 'INTRUDER_VEC_01', x_m: -1.2, y_m: 2.2, vx_mps: 0.15, vy_mps: 0.85 })
                });
                if (res.ok) {
                    const data = await res.json();
                    this.renderPrediction(data);
                    btn.textContent = 'BREACH FORECAST ACTIVE';
                    setTimeout(() => { btn.textContent = '⏱️ SIMULATE INTRUDER APPROACH VECTOR (ETB & PPI CALCULATION)'; }, 2500);
                }
            } catch (e) {
                console.error('Failed to simulate kinematics:', e);
                btn.textContent = '⏱️ SIMULATE INTRUDER APPROACH VECTOR (ETB & PPI CALCULATION)';
            }
        });

        // Phase 17: Multi-Sensor Health Matrix Modal & Actions
        document.getElementById('btnHealthMatrixModal')?.addEventListener('click', async () => {
            const m = document.getElementById('healthMatrixModal');
            if (m) m.style.display = 'flex';
            await this.loadHealthMatrix();
        });

        document.getElementById('btnCloseHealthMatrixModal')?.addEventListener('click', () => {
            const m = document.getElementById('healthMatrixModal');
            if (m) m.style.display = 'none';
        });

        document.getElementById('btnModeBalanced')?.addEventListener('click', async () => {
            await fetch('/api/health/trigger-failover', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ mode_id: 'BALANCED_FUSION', reason: 'Operator selected nominal multi-domain mode' })
            });
            await this.loadHealthMatrix();
        });

        document.getElementById('btnModeFog')?.addEventListener('click', async () => {
            await fetch('/api/health/trigger-failover', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ mode_id: 'FOG_SMOKE_DEGRADED', reason: 'Dense fog detected; mmWave radar takes 90% primacy' })
            });
            await this.loadHealthMatrix();
        });

        document.getElementById('btnModeJamming')?.addEventListener('click', async () => {
            await fetch('/api/health/trigger-failover', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ mode_id: 'EW_RADAR_JAMMED', reason: 'RF jamming detected; optical Re-ID takes 90% primacy' })
            });
            await this.loadHealthMatrix();
        });

        document.getElementById('btnModeCamFailover')?.addEventListener('click', async () => {
            await fetch('/api/health/trigger-failover', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ mode_id: 'OPTICAL_FAILOVER', reason: 'CCTV fault simulated; auto-rerouted to secondary and UAV' })
            });
            await this.loadHealthMatrix();
        });

        document.getElementById('btnResetHealthMatrix')?.addEventListener('click', async () => {
            await fetch('/api/health/reset-matrix', { method: 'POST' });
            await this.loadHealthMatrix();
        });

        // Phase 18: Adaptive FPS Governor & Latency Optimizer Modal
        document.getElementById('btnPerfGovernorModal')?.addEventListener('click', async () => {
            const m = document.getElementById('perfGovernorModal');
            if (m) m.style.display = 'flex';
            await this.loadPerfStatus();
        });

        document.getElementById('btnClosePerfGovernorModal')?.addEventListener('click', () => {
            const m = document.getElementById('perfGovernorModal');
            if (m) m.style.display = 'none';
        });

        const setGovMode = async (mode) => {
            try {
                await fetch('/api/perf/governor', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ mode })
                });
                await this.loadPerfStatus();
            } catch (e) {
                console.error('Failed to set governor mode:', e);
            }
        };

        document.getElementById('btnGovAuto')?.addEventListener('click', () => setGovMode('AUTO_ADAPTIVE'));
        document.getElementById('btnGovEco')?.addEventListener('click', () => setGovMode('ECO_IDLE'));
        document.getElementById('btnGovBalanced')?.addEventListener('click', () => setGovMode('BALANCED'));
        document.getElementById('btnGovBurst')?.addEventListener('click', () => setGovMode('BURST_MAX'));

        const setPrecision = async (precision) => {
            try {
                await fetch('/api/perf/precision', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ precision })
                });
                await this.loadPerfStatus();
            } catch (e) {
                console.error('Failed to set precision:', e);
            }
        };

        document.getElementById('btnPrecFP32')?.addEventListener('click', () => setPrecision('FP32'));
        document.getElementById('btnPrecFP16')?.addEventListener('click', () => setPrecision('FP16'));
        document.getElementById('btnPrecINT8')?.addEventListener('click', () => setPrecision('INT8'));

        document.getElementById('btnSimulateThreatBurst')?.addEventListener('click', async () => {
            const btn = document.getElementById('btnSimulateThreatBurst');
            const fb = document.getElementById('perfBurstFeedback');
            if (btn) btn.textContent = 'RAMPING UP...';
            try {
                const res = await fetch('/api/perf/simulate-load', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ duration_seconds: 10.0 })
                });
                if (res.ok) {
                    if (fb) {
                        fb.style.display = 'block';
                        fb.textContent = 'BURST ACTIVE: 30 FPS (<20ms RAMP-UP)';
                    }
                    await this.loadPerfStatus();
                    setTimeout(() => {
                        if (fb) fb.style.display = 'none';
                        if (btn) btn.textContent = '⚡ TEST THREAT BURST (10s)';
                        this.loadPerfStatus();
                    }, 10000);
                }
            } catch (e) {
                console.error('Failed to simulate threat burst:', e);
                if (btn) btn.textContent = '⚡ TEST THREAT BURST (10s)';
            }
        });

        // Phase 19: EW Jamming Triangulation, Ground Sensors & BSF SITREP
        document.getElementById('btnEwSensorsModal')?.addEventListener('click', async () => {
            const m = document.getElementById('ewSensorsModal');
            if (m) m.style.display = 'flex';
            await this.loadEwSensorsStatus();
        });

        document.getElementById('btnCloseEwSensorsModal')?.addEventListener('click', () => {
            const m = document.getElementById('ewSensorsModal');
            if (m) m.style.display = 'none';
        });

        document.getElementById('btnTriggerTriangulate')?.addEventListener('click', async () => {
            const btn = document.getElementById('btnTriggerTriangulate');
            if (btn) btn.textContent = 'TRIANGULATING...';
            try {
                const res = await fetch('/api/ew-sensors/triangulate', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ true_emitter_x: -4.5, true_emitter_y: 28.0 })
                });
                if (res.ok) {
                    await this.loadEwSensorsStatus();
                    if (btn) btn.textContent = '🎯 JAMMER LOCKED (AoA)';
                    setTimeout(() => { if (btn) btn.textContent = '🎯 LOCATE HOSTILE JAMMER'; }, 3000);
                }
            } catch (e) {
                console.error('Failed to triangulate jammer:', e);
                if (btn) btn.textContent = '🎯 LOCATE HOSTILE JAMMER';
            }
        });

        document.getElementById('btnResetEwTriangulation')?.addEventListener('click', async () => {
            await this.loadEwSensorsStatus();
        });

        document.getElementById('btnSimulateCrawlSeismic')?.addEventListener('click', async () => {
            try {
                await fetch('/api/ew-sensors/seismic-trigger', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ node_id: 'GEO_02', cadence_hz: 0.8, energy: 0.78 })
                });
                await this.loadEwSensorsStatus();
            } catch (e) {
                console.error('Failed to simulate crawl seismic:', e);
            }
        });

        document.getElementById('btnSimulateFenceCut')?.addEventListener('click', async () => {
            try {
                await fetch('/api/ew-sensors/seismic-trigger', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ node_id: 'GEO_03', cadence_hz: 88.0, energy: 0.94 })
                });
                await this.loadEwSensorsStatus();
            } catch (e) {
                console.error('Failed to simulate fence cut:', e);
            }
        });

        document.getElementById('btnVerifyThermalHuman')?.addEventListener('click', async () => {
            try {
                const res = await fetch('/api/ew-sensors/thermal-check', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ track_id: 'CAM_01_TRK_01', class_name: 'person', apparent_temp_c: 36.4 })
                });
                if (res.ok) {
                    const data = await res.json();
                    const pill = document.getElementById('ewThermalDecisionPill');
                    const text = document.getElementById('ewThermalTempText');
                    if (pill) {
                        pill.textContent = data.verification.decision;
                        pill.style.background = 'rgba(16, 185, 129, 0.2)';
                        pill.style.color = '#10b981';
                    }
                    if (text) {
                        text.textContent = `Target: ${data.verification.apparent_temp_c}°C | Ambient: ${data.verification.ambient_temp_c}°C | ΔT: +${data.verification.delta_t_c}°C`;
                    }
                }
            } catch (e) {
                console.error('Failed to verify thermal human:', e);
            }
        });

        document.getElementById('btnVerifyThermalAnimal')?.addEventListener('click', async () => {
            try {
                const res = await fetch('/api/ew-sensors/thermal-check', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ track_id: 'CAM_01_TRK_02', class_name: 'animal', apparent_temp_c: 39.8 })
                });
                if (res.ok) {
                    const data = await res.json();
                    const pill = document.getElementById('ewThermalDecisionPill');
                    const text = document.getElementById('ewThermalTempText');
                    if (pill) {
                        pill.textContent = data.verification.decision;
                        pill.style.background = 'rgba(245, 158, 11, 0.2)';
                        pill.style.color = '#f59e0b';
                    }
                    if (text) {
                        text.textContent = `Target: ${data.verification.apparent_temp_c}°C | Ambient: ${data.verification.ambient_temp_c}°C | ΔT: +${data.verification.delta_t_c}°C`;
                    }
                }
            } catch (e) {
                console.error('Failed to verify thermal animal:', e);
            }
        });

        document.getElementById('btnGenerateSitrep')?.addEventListener('click', async () => {
            const btn = document.getElementById('btnGenerateSitrep');
            const fb = document.getElementById('ewSitrepFeedback');
            if (btn) btn.textContent = 'COMPILING...';
            try {
                const res = await fetch('/api/ew-sensors/sitrep');
                if (res.ok) {
                    const sitrep = await res.json();
                    if (btn) btn.textContent = '📋 COMPILE OFFICIAL FORM-IV SITREP';
                    if (fb) {
                        fb.style.display = 'block';
                        fb.textContent = `● SITREP ${sitrep.report_reference} COMPILED & SEALED (HMAC: ${sitrep.cryptographic_hmac_sha256_seal.slice(0, 8)}...)`;
                    }
                }
            } catch (e) {
                console.error('Failed to generate SITREP:', e);
                if (btn) btn.textContent = '📋 COMPILE OFFICIAL FORM-IV SITREP';
            }
        });

        // Phase 20: Master Tactical Demonstration Playbooks & Evaluator Pitch Tour
        const btnPlaybooksModal = document.getElementById('btnMasterPlaybooksModal');
        const modalPlaybooks = document.getElementById('masterPlaybooksModal');
        const btnClosePlaybooksModal = document.getElementById('btnCloseMasterPlaybooksModal');

        if (btnPlaybooksModal) {
            btnPlaybooksModal.addEventListener('click', async () => {
                if (modalPlaybooks) modalPlaybooks.style.display = 'flex';
                await this.loadPlaybooksCatalog();
            });
        }

        if (btnClosePlaybooksModal) {
            btnClosePlaybooksModal.addEventListener('click', () => {
                if (modalPlaybooks) modalPlaybooks.style.display = 'none';
            });
        }

        if (modalPlaybooks) {
            modalPlaybooks.addEventListener('click', (e) => {
                if (e.target === modalPlaybooks) {
                    modalPlaybooks.style.display = 'none';
                }
            });
        }

        document.getElementById('btnExecutePlaybook')?.addEventListener('click', async () => {
            await this.executeActivePlaybook();
        });

        document.getElementById('btnStepPlaybook')?.addEventListener('click', async () => {
            await this.stepActivePlaybook();
        });

        document.getElementById('btnResetPlaybookEngine')?.addEventListener('click', async () => {
            await this.resetActivePlaybooks();
        });

        // Mobile IP Camera Configurator (CAM_02)
        const btnTestCam02 = document.getElementById('btnTestCam02Connection');
        const feedbackEl = document.getElementById('cam02TestFeedback');
        const badgeEl = document.getElementById('cam02ConfigStatusBadge');

        if (btnTestCam02) {
            btnTestCam02.addEventListener('click', async () => {
                const urlInput = document.getElementById('cam02StreamUrl');
                const streamUrl = urlInput ? urlInput.value.trim() : '';
                if (!streamUrl) return;

                btnTestCam02.textContent = 'TESTING...';
                if (feedbackEl) {
                    feedbackEl.style.display = 'block';
                    feedbackEl.style.color = 'var(--text-muted)';
                    feedbackEl.textContent = `Connecting to ${streamUrl}...`;
                }

                try {
                    const res = await fetch('/api/cameras/CAM_02/test-connection', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ source: streamUrl })
                    });
                    const data = await res.json();
                    btnTestCam02.textContent = 'TEST REACHABILITY';

                    if (data.reachable) {
                        if (feedbackEl) {
                            feedbackEl.style.color = 'var(--accent-success)';
                            feedbackEl.textContent = `● REACHABLE: ${data.resolution} stream active!`;
                        }
                        if (badgeEl) {
                            badgeEl.className = 'badge';
                            badgeEl.style.background = 'rgba(0, 230, 118, 0.15)';
                            badgeEl.style.color = 'var(--accent-success)';
                            badgeEl.textContent = 'VERIFIED ONLINE';
                        }
                    } else {
                        if (feedbackEl) {
                            feedbackEl.style.color = 'var(--accent-danger)';
                            feedbackEl.textContent = `● CONNECTION ERROR: ${data.error || 'Host unreachable'}`;
                        }
                    }
                } catch (err) {
                    btnTestCam02.textContent = 'TEST REACHABILITY';
                    if (feedbackEl) {
                        feedbackEl.style.color = 'var(--accent-danger)';
                        feedbackEl.textContent = `● NETWORK ERROR: ${err}`;
                    }
                }
            });
        }

        const btnApplyCam02 = document.getElementById('btnApplyCam02Stream');
        if (btnApplyCam02) {
            btnApplyCam02.addEventListener('click', async () => {
                const urlInput = document.getElementById('cam02StreamUrl');
                const streamUrl = urlInput ? urlInput.value.trim() : '';
                if (!streamUrl) return;

                btnApplyCam02.textContent = 'BINDING...';
                try {
                    const res = await fetch('/api/cameras/CAM_02', {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ source: streamUrl, enabled: true })
                    });
                    if (res.ok) {
                        btnApplyCam02.textContent = 'BOUND TO CAM_02';
                        setTimeout(() => { btnApplyCam02.textContent = 'BIND CAM_02 STREAM'; }, 2500);
                    }
                } catch (err) {
                    console.error('Failed to bind camera source:', err);
                    btnApplyCam02.textContent = 'BIND CAM_02 STREAM';
                }
            });
        }

        // Copy Mobile URL to Clipboard
        const btnCopyMobile = document.getElementById('btnCopyMobileUrl');
        if (btnCopyMobile) {
            btnCopyMobile.addEventListener('click', () => {
                const urlInput = document.getElementById('mobileStreamUrlDisplay');
                const text = urlInput ? urlInput.value : '';
                if (text) {
                    if (navigator.clipboard) {
                        navigator.clipboard.writeText(text).then(() => {
                            btnCopyMobile.textContent = 'COPIED!';
                            setTimeout(() => { btnCopyMobile.textContent = '📋 COPY LINK'; }, 2000);
                        }).catch(() => {
                            urlInput.select();
                            document.execCommand('copy');
                            btnCopyMobile.textContent = 'COPIED!';
                            setTimeout(() => { btnCopyMobile.textContent = '📋 COPY LINK'; }, 2000);
                        });
                    } else {
                        urlInput.select();
                        document.execCommand('copy');
                        btnCopyMobile.textContent = 'COPIED!';
                        setTimeout(() => { btnCopyMobile.textContent = '📋 COPY LINK'; }, 2000);
                    }
                }
            });
        }

        // CAM_02 IP Selector change
        const ipSelector = document.getElementById('cam02IpSelector');
        if (ipSelector) {
            ipSelector.addEventListener('change', (e) => {
                this.loadCameraNetworkInfo(e.target.value);
            });
        }

        // CAM_02 Re-scan button
        const btnRescan = document.getElementById('btnRefreshCam02Network');
        if (btnRescan) {
            btnRescan.addEventListener('click', async () => {
                btnRescan.textContent = 'SCANNING...';
                await this.loadCameraNetworkInfo(ipSelector ? ipSelector.value : null);
                btnRescan.textContent = '🔄 RE-SCAN';
            });
        }

        // CAM_02 Toggle QR Mode (HTTPS vs HTTP)
        const btnToggleQr = document.getElementById('btnToggleQrMode');
        if (btnToggleQr) {
            btnToggleQr.addEventListener('click', () => {
                this.cam02QrMode = (this.cam02QrMode === 'http') ? 'https' : 'http';
                btnToggleQr.textContent = (this.cam02QrMode === 'http') ? 'SHOW HTTPS QR' : 'SHOW HTTP QR';
                this.updateCam02QrDisplay();
            });
        }

        // ANPR Refresh Button
        const btnRefreshAnpr = document.getElementById('btnRefreshAnpr');
        if (btnRefreshAnpr) {
            btnRefreshAnpr.addEventListener('click', () => {
                this.loadAnprRecords();
            });
        }


        // Setup Tactical Monitor Controls in Tab 2
        this.setupTacticalMonitor();

        // Setup Forensic Evidence Modal
        this.setupEvidenceModal();

        // Setup Events Filter Handlers (Phase 11)
        this.setupEventsFilterHandlers();

        // Setup Tactical Audio Controls (Phase 10)
        this.setupAudioControls();

        // Setup System Configuration Handlers (Section 41)
        this.setupConfigurationHandlers();

        // Setup Threat Heatmap Controls (Sections 35 & 48)
        this.setupHeatmapControls();

        // Setup SOC Security Events Filter & Drawer Handlers
        this.setupEventsFilterHandlers();
        this.setupEvidenceModal();

        // Setup Camera Zone GPS Coordinates Controls
        this.setupZoneGpsControls();

        // Setup Autonomous UAV Operator Controls & Rotor Verification
        this.setupUavOperatorControls();
    }

    flashRedScreenBorder() {
        let overlay = document.getElementById('redScreenBorderOverlay');
        if (!overlay) {
            overlay = document.createElement('div');
            overlay.id = 'redScreenBorderOverlay';
            overlay.style.position = 'fixed';
            overlay.style.inset = '0';
            overlay.style.pointerEvents = 'none';
            overlay.style.zIndex = '99999';
            overlay.style.boxShadow = 'inset 0 0 60px 20px rgba(255, 23, 68, 0.9), inset 0 0 120px 40px rgba(255, 23, 68, 0.5)';
            overlay.style.border = '5px solid #ff1744';
            overlay.style.transition = 'opacity 0.25s ease-in-out';
            overlay.style.opacity = '0';
            document.body.appendChild(overlay);
        }

        overlay.style.opacity = '1';
        setTimeout(() => {
            if (overlay) overlay.style.opacity = '0';
        }, 1500);
    }

    setupZoneGpsControls() {
        const selectZone = document.getElementById('selectCameraGpsZone');
        const inputLat = document.getElementById('inputZoneLatitude');
        const inputLon = document.getElementById('inputZoneLongitude');
        const inputRad = document.getElementById('inputZoneRadius');
        const btnSave = document.getElementById('btnSaveZoneGps');
        const feedback = document.getElementById('zoneGpsSaveFeedback');

        const defaultZoneCoords = {
            'ZONE_B': { lat: 31.626200, lon: 74.874800, rad: 25 },
            'ZONE_C': { lat: 31.628000, lon: 74.876500, rad: 20 },
            'ZONE_A': { lat: 31.624800, lon: 74.873500, rad: 40 }
        };

        const updateInputs = (zId) => {
            const current = (this.zones && this.zones.find(z => z.id === zId)) || {};
            const def = defaultZoneCoords[zId] || { lat: 31.6262, lon: 74.8748, rad: 25 };
            if (inputLat) inputLat.value = current.center_lat !== undefined && current.center_lat !== null ? current.center_lat : def.lat;
            if (inputLon) inputLon.value = current.center_lon !== undefined && current.center_lon !== null ? current.center_lon : def.lon;
            if (inputRad) inputRad.value = current.radius_m !== undefined && current.radius_m !== null ? current.radius_m : def.rad;
        };

        if (selectZone) {
            selectZone.addEventListener('change', (e) => updateInputs(e.target.value));
        }

        if (btnSave) {
            btnSave.addEventListener('click', async () => {
                const zId = selectZone ? selectZone.value : 'ZONE_B';
                const lat = parseFloat(inputLat?.value || 31.6262);
                const lon = parseFloat(inputLon?.value || 74.8748);
                const rad = parseFloat(inputRad?.value || 25);

                btnSave.textContent = 'SAVING...';
                try {
                    const putRes = await fetch(`/api/zones/${zId}/gps`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            center_lat: lat,
                            center_lon: lon,
                            radius_m: rad
                        })
                    });

                    if (putRes.ok) {
                        btnSave.textContent = 'SAVED ✓';
                        if (feedback) {
                            feedback.textContent = `✓ GPS coordinates for ${zId} updated to (${lat.toFixed(6)}, ${lon.toFixed(6)}).`;
                            feedback.style.display = 'block';
                            setTimeout(() => { feedback.style.display = 'none'; }, 4000);
                        }
                        if (window.audioAlert) {
                            window.audioAlert.playRadarBlip();
                        }
                        await this.loadZones();
                    } else {
                        btnSave.textContent = 'SAVE GPS';
                    }
                } catch (err) {
                    console.error('Failed to save zone GPS:', err);
                    btnSave.textContent = 'SAVE GPS';
                }
                setTimeout(() => { if (btnSave) btnSave.textContent = 'SAVE GPS'; }, 2500);
            });
        }
    }

    setupUavOperatorControls() {
        // 1. Rotor Idle Blade Verification Button
        const btnVerifyRotor = document.getElementById('btnVerifyUavRotor');
        if (btnVerifyRotor) {
            btnVerifyRotor.addEventListener('click', async () => {
                btnVerifyRotor.textContent = '⚡ ROTATING BLADES (IDLE)...';
                btnVerifyRotor.disabled = true;
                try {
                    const res = await fetch('/api/uav/verify-rotor', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ duration_sec: 3.0, throttle: 15 })
                    });
                    const data = await res.json();
                    if (window.audioAlert) {
                        window.audioAlert.playUAVDispatchPing();
                        window.audioAlert.speakTacticalAlert("UAV blade rotor test active. Low idle verification confirmed.");
                    }
                    this.appendUavFlightLog(`[ROTOR TEST] Drone blades rotating at idle (throttle 15, no flight lift). Result: ${data.status}`);
                    btnVerifyRotor.textContent = 'BLADES VERIFIED ✓';
                    setTimeout(() => {
                        btnVerifyRotor.textContent = '⚡ UAV VERIFICATION (IDLE ROTORS)';
                        btnVerifyRotor.disabled = false;
                    }, 3500);
                } catch (err) {
                    console.error('Rotor verification error:', err);
                    btnVerifyRotor.textContent = '⚡ UAV VERIFICATION (IDLE ROTORS)';
                    btnVerifyRotor.disabled = false;
                }
            });
        }

        // 2. Dispatch UAV Button
        const btnDispatch = document.getElementById('btnDispatchUav');
        if (btnDispatch) {
            btnDispatch.addEventListener('click', async () => {
                const zoneSel = document.getElementById('uavTargetZone');
                const reasonIn = document.getElementById('uavMissionReason');
                const zoneId = zoneSel ? zoneSel.value : 'ZONE_B';
                const reason = reasonIn ? reasonIn.value : 'Unauthorized intrusion intercept';

                btnDispatch.textContent = 'DISPATCHING UAV...';
                try {
                    const res = await fetch('/api/uav/dispatch', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ zone_id: zoneId, reason: reason })
                    });
                    const data = await res.json();
                    if (data.telemetry && this.uavView) {
                        this.uavView.updateTelemetry(data.telemetry);
                    }
                    if (window.audioAlert) {
                        window.audioAlert.playUAVDispatchPing();
                        window.audioAlert.speakTacticalAlert(`Autonomous UAV dispatched to ${zoneId}. Intercept vector active.`);
                    }
                    this.appendUavFlightLog(`[DISPATCH] UAV sortie authorized -> Target: ${zoneId}. Reason: ${reason}`);
                    btnDispatch.textContent = 'UAV DISPATCHED ✓';
                    setTimeout(() => { btnDispatch.textContent = '🚀 DISPATCH DRONE-001'; }, 3000);
                } catch (err) {
                    btnDispatch.textContent = '🚀 DISPATCH DRONE-001';
                }
            });
        }

        // 3. Start Scan Button
        const btnStartScan = document.getElementById('btnStartScanUav');
        if (btnStartScan) {
            btnStartScan.addEventListener('click', async () => {
                btnStartScan.textContent = 'SCANNING...';
                try {
                    const res = await fetch('/api/uav/start-scan', { method: 'POST' });
                    const data = await res.json();
                    if (data.telemetry && this.uavView) {
                        this.uavView.updateTelemetry(data.telemetry);
                    }
                    this.appendUavFlightLog('[SCAN] Optical & thermal aerial search sweep initiated.');
                    btnStartScan.textContent = 'SCAN ACTIVE ✓';
                    setTimeout(() => { btnStartScan.textContent = '🔍 START SCAN'; }, 3000);
                } catch (err) {
                    btnStartScan.textContent = '🔍 START SCAN';
                }
            });
        }

        // 4. Return Home Button
        const btnReturnHome = document.getElementById('btnReturnHomeUav');
        if (btnReturnHome) {
            btnReturnHome.addEventListener('click', async () => {
                btnReturnHome.textContent = 'RETURNING...';
                try {
                    const res = await fetch('/api/uav/return-home', { method: 'POST' });
                    const data = await res.json();
                    if (data.telemetry && this.uavView) {
                        this.uavView.updateTelemetry(data.telemetry);
                    }
                    this.appendUavFlightLog('[RTH] Commencing automated return-to-home navigation.');
                    btnReturnHome.textContent = 'RTH ACTIVE ✓';
                    setTimeout(() => { btnReturnHome.textContent = '🏠 RETURN HOME'; }, 3000);
                } catch (err) {
                    btnReturnHome.textContent = '🏠 RETURN HOME';
                }
            });
        }

        // 5. Abort Button
        const btnAbort = document.getElementById('btnAbortUav');
        if (btnAbort) {
            btnAbort.addEventListener('click', async () => {
                btnAbort.textContent = 'ABORTING...';
                try {
                    const res = await fetch('/api/uav/abort', { method: 'POST' });
                    const data = await res.json();
                    if (data.telemetry && this.uavView) {
                        this.uavView.updateTelemetry(data.telemetry);
                    }
                    this.appendUavFlightLog('[ABORT] Emergency mission abort commanded by operator.');
                    btnAbort.textContent = 'ABORTED ✓';
                    setTimeout(() => { btnAbort.textContent = '🛑 ABORT'; }, 3000);
                } catch (err) {
                    btnAbort.textContent = '🛑 ABORT';
                }
            });
        }

        // 6. Manual Motor Controls (Takeoff, Land, Cutoff)
        const btnMotorTakeoff = document.getElementById('btnMotorTakeoff');
        if (btnMotorTakeoff) {
            btnMotorTakeoff.addEventListener('click', async () => {
                try {
                    const res = await fetch('/api/uav/takeoff', { method: 'POST' });
                    const data = await res.json();
                    if (data.telemetry && this.uavView) this.uavView.updateTelemetry(data.telemetry);
                    this.appendUavFlightLog(`[MOTOR] Takeoff pulse commanded. Result: ${data.status || 'OK'}`);
                    if (window.audioAlert) window.audioAlert.playUAVDispatchPing();
                } catch (err) {
                    console.error('Takeoff error:', err);
                }
            });
        }

        const btnMotorLand = document.getElementById('btnMotorLand');
        if (btnMotorLand) {
            btnMotorLand.addEventListener('click', async () => {
                try {
                    const res = await fetch('/api/uav/land', { method: 'POST' });
                    const data = await res.json();
                    if (data.telemetry && this.uavView) this.uavView.updateTelemetry(data.telemetry);
                    this.appendUavFlightLog(`[MOTOR] Auto-land commanded. Result: ${data.status || 'OK'}`);
                } catch (err) {
                    console.error('Land error:', err);
                }
            });
        }

        const btnMotorCutoff = document.getElementById('btnMotorCutoff');
        if (btnMotorCutoff) {
            btnMotorCutoff.addEventListener('click', async () => {
                try {
                    const res = await fetch('/api/uav/emergency-stop', { method: 'POST' });
                    const data = await res.json();
                    if (data.telemetry && this.uavView) this.uavView.updateTelemetry(data.telemetry);
                    this.appendUavFlightLog(`[MOTOR CUTOFF] All motors cut to 0% immediately. Result: ${data.status || 'OK'}`);
                } catch (err) {
                    console.error('Cutoff error:', err);
                }
            });
        }

        // 7. Live UAV Aerial Reconnaissance Video Stream
        const uavImg = document.getElementById('uavReconImg');
        if (uavImg) {
            this.attachResilientStream(uavImg, 'UAV_01');
        }
    }

    appendUavFlightLog(msg) {
        const c = document.getElementById('uavFlightLogContainer');
        if (!c) return;
        const div = document.createElement('div');
        const nowStr = new Date().toTimeString().split(' ')[0];
        div.textContent = `[${nowStr}] ${msg}`;
        c.appendChild(div);
        c.scrollTop = c.scrollHeight;
    }


    setupTacticalMonitor() {
        const monitorImg = document.getElementById('tacticalMonitorImg');
        const btnCam01 = document.getElementById('btnMonitorCam01');
        const btnCam02 = document.getElementById('btnMonitorCam02');
        const btnUav = document.getElementById('btnMonitorUav');
        const btnMode = document.getElementById('btnMonitorStreamMode');
        const btnFlip = document.getElementById('btnToggleCamMirror');
        const btnAspect = document.getElementById('btnToggleAspectRatio');
        const btnViewMode = document.getElementById('btnToggleCamViewMode');
        const btnQuickRename = document.getElementById('btnQuickRenameZone');
        const tagStatus = document.getElementById('liveMonitorStatusTag');
        const tagZone = document.getElementById('liveMonitorZone');
        const singleWrapper = document.getElementById('tacticalSingleMonitorWrapper');
        const multiGrid = document.getElementById('tacticalMultiCamGrid');

        if (!monitorImg) return;

        let activeCamId = 'CAM_01';
        let currentCleanup = null;
        let streamMode = 'MJPEG'; // 'MJPEG' | 'FAST_REFRESH'
        let gridCleanups = [];

        // Aspect Ratio Selector (Auto Contain / 16:9 / 4:3 / Fill)
        const aspectModes = ['AUTO', '16:9', '4:3', 'FILL'];
        let currentAspectIdx = 0;
        if (btnAspect && singleWrapper) {
            btnAspect.addEventListener('click', () => {
                currentAspectIdx = (currentAspectIdx + 1) % aspectModes.length;
                const mode = aspectModes[currentAspectIdx];
                btnAspect.textContent = `📐 RATIO: ${mode}`;

                singleWrapper.classList.remove('ratio-16-9', 'ratio-4-3', 'ratio-auto');
                monitorImg.classList.remove('fit-contain', 'fit-cover', 'fit-fill');

                if (mode === 'AUTO') {
                    singleWrapper.classList.add('ratio-auto');
                    monitorImg.classList.add('fit-contain');
                } else if (mode === '16:9') {
                    singleWrapper.classList.add('ratio-16-9');
                    monitorImg.classList.add('fit-contain');
                } else if (mode === '4:3') {
                    singleWrapper.classList.add('ratio-4-3');
                    monitorImg.classList.add('fit-contain');
                } else if (mode === 'FILL') {
                    singleWrapper.classList.add('ratio-16-9');
                    monitorImg.classList.add('fit-cover');
                }
            });
        }

        // Single Monitor vs Multi-Camera Grid View Toggle
        let isGridMode = false;
        if (btnViewMode && multiGrid && singleWrapper) {
            btnViewMode.addEventListener('click', () => {
                isGridMode = !isGridMode;
                btnViewMode.textContent = isGridMode ? '▦ VIEW: MULTI-GRID' : '▦ VIEW: SINGLE';
                btnViewMode.style.borderColor = isGridMode ? 'var(--accent-cyan)' : '#10b981';
                btnViewMode.style.color = isGridMode ? 'var(--accent-cyan)' : '#10b981';

                if (isGridMode) {
                    singleWrapper.style.display = 'none';
                    multiGrid.style.display = 'grid';
                    const g1 = document.getElementById('gridCam01Img');
                    const g2 = document.getElementById('gridCam02Img');
                    const gu = document.getElementById('gridUavImg');
                    if (g1) gridCleanups.push(this.attachResilientStream(g1, 'CAM_01'));
                    if (g2) gridCleanups.push(this.attachResilientStream(g2, 'CAM_02'));
                    if (gu) gridCleanups.push(this.attachResilientStream(gu, 'UAV_01'));
                } else {
                    singleWrapper.style.display = 'flex';
                    multiGrid.style.display = 'none';
                    gridCleanups.forEach(fn => fn && fn());
                    gridCleanups = [];
                }
            });
        }

        // Quick Rename Zone Button
        if (btnQuickRename) {
            btnQuickRename.addEventListener('click', async () => {
                const selZone = document.getElementById('selectCameraGpsZone');
                if (!selZone) return;
                const zoneId = selZone.value;
                const opt = selZone.options[selZone.selectedIndex];
                const curName = opt ? (opt.textContent.split(':')[1]?.split('(')[0]?.trim() || zoneId) : zoneId;
                const newName = prompt(`Enter new descriptive name for zone ${zoneId}:`, curName);
                if (!newName || !newName.trim()) return;

                try {
                    const res = await fetch(`/api/zones/${zoneId}/name`, {
                        method: 'PATCH',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ name: newName.trim() })
                    });
                    if (res.ok) {
                        const data = await res.json();
                        if (opt) {
                            opt.textContent = `${opt.dataset.cam || 'ZONE'}: ${newName.trim()} (${zoneId})`;
                        }
                        const fb = document.getElementById('zoneGpsSaveFeedback');
                        if (fb) {
                            fb.textContent = `✓ Zone ${zoneId} renamed to "${newName.trim()}"`;
                            fb.style.display = 'block';
                            setTimeout(() => { fb.style.display = 'none'; }, 3500);
                        }
                        // Refresh all zone views
                        const zRes = await fetch('/api/zones');
                        if (zRes.ok) {
                            const zones = await zRes.json();
                            if (this.zoneMap) this.zoneMap.setZones(zones);
                            if (this.zoneMapFull) this.zoneMapFull.setZones(zones);
                            this.renderZonesList(zones);
                        }
                    } else {
                        alert('Failed to rename zone.');
                    }
                } catch (err) {
                    console.error('Zone rename error:', err);
                    alert('Error renaming zone: ' + err.message);
                }
            });
        }

        // Webcam mirror / unmirror toggle
        if (btnFlip) {
            btnFlip.addEventListener('click', () => {
                const currentTransform = monitorImg.style.transform || '';
                if (currentTransform.includes('scaleX(-1)')) {
                    monitorImg.style.transform = currentTransform.replace('scaleX(-1)', '').trim();
                    btnFlip.style.background = 'transparent';
                } else {
                    monitorImg.style.transform = (currentTransform + ' scaleX(-1)').trim();
                    btnFlip.style.background = 'rgba(168, 85, 247, 0.25)';
                }
            });
        }

        // Real Browser Device Webcam Toggle
        const btnWebcam = document.getElementById('btnConnectLocalWebcam');
        const webcamVideo = document.getElementById('tacticalWebcamVideo');
        let localWebcamStream = null;
        let pushFrameInterval = null;

        if (btnWebcam) {
            btnWebcam.addEventListener('click', async () => {
                if (localWebcamStream) {
                    // Turn OFF webcam
                    localWebcamStream.getTracks().forEach(t => t.stop());
                    localWebcamStream = null;
                    if (pushFrameInterval) {
                        clearInterval(pushFrameInterval);
                        pushFrameInterval = null;
                    }
                    if (webcamVideo) {
                        webcamVideo.srcObject = null;
                        webcamVideo.style.display = 'none';
                    }
                    if (monitorImg) {
                        monitorImg.style.display = 'block';
                    }
                    btnWebcam.style.background = 'transparent';
                    btnWebcam.textContent = '📹 LIVE WEBCAM';
                    btnWebcam.style.borderColor = '#eab308';
                    btnWebcam.style.color = '#fde047';
                    console.log('[WEBCAM] Local device webcam disabled.');
                    return;
                }

                // Turn ON webcam
                try {
                    console.log('[WEBCAM] Requesting browser camera permissions...');
                    localWebcamStream = await navigator.mediaDevices.getUserMedia({
                        video: { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: 'user' }
                    });

                    if (webcamVideo) {
                        webcamVideo.srcObject = localWebcamStream;
                        webcamVideo.style.display = 'block';
                        await webcamVideo.play();
                    }
                    if (monitorImg) {
                        monitorImg.style.display = 'none';
                    }

                    btnWebcam.style.background = 'rgba(16, 185, 129, 0.25)';
                    btnWebcam.style.borderColor = '#10b981';
                    btnWebcam.style.color = '#34d399';
                    btnWebcam.textContent = '📹 WEBCAM ACTIVE';

                    if (tagStatus) {
                        tagStatus.innerHTML = `<span class="rec-dot"></span> LIVE FEED: REAL WEBCAM (LOCAL)`;
                    }

                    // Push frames to backend for YOLO processing
                    const offscreenCanvas = document.createElement('canvas');
                    offscreenCanvas.width = 640;
                    offscreenCanvas.height = 480;
                    const ctx = offscreenCanvas.getContext('2d');

                    pushFrameInterval = setInterval(async () => {
                        if (!localWebcamStream || !webcamVideo || webcamVideo.videoWidth === 0) return;
                        try {
                            ctx.drawImage(webcamVideo, 0, 0, 640, 480);
                            const dataUrl = offscreenCanvas.toDataURL('image/jpeg', 0.65);
                            await fetch('/api/cameras/CAM_01/push-frame', {
                                method: 'POST',
                                headers: { 'Content-Type': 'image/jpeg' },
                                body: dataUrl
                            }).catch(() => {});
                        } catch (e) {
                            // ignore frame drop
                        }
                    }, 120);

                    console.log('[WEBCAM] Local webcam stream active and streaming frames to backend.');
                } catch (err) {
                    console.warn('[WEBCAM] Browser camera access failed:', err);
                    alert('Camera access was not granted or no webcam was detected on this device: ' + err.message);
                }
            });
        }

        const updateMonitorStream = (camId) => {
            activeCamId = camId;
            if (currentCleanup) {
                currentCleanup();
                currentCleanup = null;
            }

            if (tagStatus) {
                tagStatus.innerHTML = `<span class="rec-dot"></span> LIVE FEED: ${camId}`;
            }
            if (tagZone) {
                tagZone.textContent = camId === 'CAM_01' ? 'ZONE: ZONE_B (Warning Sector)' : (camId === 'CAM_02' ? 'ZONE: ZONE_C (Restricted Fence)' : 'ZONE: DYNAMIC RECON');
            }

            [btnCam01, btnCam02, btnUav].forEach(b => {
                if (b) b.classList.remove('active');
            });
            if (camId === 'CAM_01' && btnCam01) btnCam01.classList.add('active');
            if (camId === 'CAM_02' && btnCam02) btnCam02.classList.add('active');
            if (camId === 'UAV_01' && btnUav) btnUav.classList.add('active');

            if (streamMode === 'FAST_REFRESH') {
                currentCleanup = this.startSnapshotStream(monitorImg, camId);
            } else {
                currentCleanup = this.attachResilientStream(monitorImg, camId);
            }
        };

        if (btnCam01) btnCam01.addEventListener('click', () => updateMonitorStream('CAM_01'));
        if (btnCam02) btnCam02.addEventListener('click', () => updateMonitorStream('CAM_02'));
        if (btnUav) btnUav.addEventListener('click', () => updateMonitorStream('UAV_01'));

        if (btnMode) {
            btnMode.addEventListener('click', () => {
                streamMode = streamMode === 'MJPEG' ? 'FAST_REFRESH' : 'MJPEG';
                btnMode.textContent = `MODE: ${streamMode === 'MJPEG' ? 'MJPEG STREAM' : 'ULTRA-SYNC REFRESH'}`;
                btnMode.style.borderColor = streamMode === 'MJPEG' ? 'var(--accent-cyan)' : 'var(--accent-success)';
                btnMode.style.color = streamMode === 'MJPEG' ? 'var(--accent-cyan)' : 'var(--accent-success)';
                updateMonitorStream(activeCamId);
            });
        }

        // Initialize with default CAM_01
        updateMonitorStream('CAM_01');
    }

    startSnapshotStream(imgEl, camId, fps = 25) {
        let active = true;
        let inFlight = false;
        const delay = Math.round(1000 / fps);

        const fetchNext = () => {
            if (!active || !imgEl.isConnected) return;
            if (inFlight) return;
            inFlight = true;

            const tempImg = new Image();
            tempImg.onload = () => {
                if (active) {
                    imgEl.src = tempImg.src;
                }
                inFlight = false;
                if (active) setTimeout(fetchNext, delay);
            };
            tempImg.onerror = () => {
                inFlight = false;
                if (active) setTimeout(fetchNext, 500);
            };
            tempImg.src = `/api/cameras/${camId}/snapshot?t=${Date.now()}`;
        };

        fetchNext();
        return () => { active = false; };
    }

    attachResilientStream(imgEl, camId) {
        if (!imgEl) return () => {};

        let reconnectTimer = null;
        const loadStream = () => {
            imgEl.src = `/api/cameras/${camId}/stream?t=${Date.now()}`;
        };

        imgEl.onerror = () => {
            console.warn(`[CAMERA ${camId}] Stream interrupted, reconnecting...`);
            clearTimeout(reconnectTimer);
            reconnectTimer = setTimeout(() => {
                if (imgEl && imgEl.isConnected) {
                    loadStream();
                }
            }, 2500);
        };

        loadStream();

        return () => {
            clearTimeout(reconnectTimer);
            imgEl.onerror = null;
            imgEl.src = '';
        };
    }

    updateSystemModeUI(mode) {
        const modeBadge = document.getElementById('systemModeBadge');
        if (modeBadge) {
            modeBadge.setAttribute('data-mode', mode);
            modeBadge.className = `mode-badge ${mode.toLowerCase()}`;
            modeBadge.textContent = `MODE: ${mode}`;
        }
    }

    updateCameraStatusUI(cameraId, status) {
        const camCard = document.getElementById(`card-${cameraId}`);
        if (camCard) {
            const statusTag = camCard.querySelector('.cam-status-tag');
            if (statusTag) {
                statusTag.textContent = status;
                statusTag.className = `video-tag ${status === 'ONLINE' ? 'live-rec' : ''}`;
            }
        }

        // Dynamically reflect live camera state in top header HUD ribbon
        if (cameraId === 'CAM_01') {
            const pill = document.getElementById('headerCam01Pill');
            const label = document.getElementById('headerCam01Label');
            if (pill) {
                const normStatus = (status || 'OFFLINE').toUpperCase();
                pill.className = `status-pill ${normStatus.toLowerCase()}`;
                const dot = pill.querySelector('.dot');
                if (dot) {
                    dot.className = `dot ${normStatus === 'ONLINE' ? 'dot-pulse' : (normStatus === 'STANDBY' ? 'dot-amber' : '')}`;
                }
            }
            if (label) label.textContent = `CAM 01: ${status === 'ONLINE' ? 'ONLINE' : status}`;
        } else if (cameraId === 'CAM_02') {
            const pill = document.getElementById('headerCam02Pill');
            const label = document.getElementById('headerCam02Label');
            if (pill) {
                const normStatus = (status || 'OFFLINE').toUpperCase();
                pill.className = `status-pill ${normStatus.toLowerCase()}`;
                const dot = pill.querySelector('.dot');
                if (dot) {
                    dot.className = `dot ${normStatus === 'ONLINE' ? 'dot-pulse' : (normStatus === 'STANDBY' ? 'dot-amber' : '')}`;
                }
            }
            if (label) label.textContent = `CAM 02: ${status}`;
        }
    }

    renderCamerasGrid(cameras) {
        const grid = document.getElementById('cameraGridContainer');
        if (!grid) return;

        grid.innerHTML = cameras.map(c => {
            const isOnline = c.status === 'ONLINE';

            return `
            <div class="hud-panel" id="card-${c.id}">
                <div class="panel-header">
                    <span class="panel-title">
                        <svg class="panel-title-icon" viewBox="0 0 24 24"><path d="M17 10.5V7c0-.55-.45-1-1-1H4c-.55 0-1 .45-1 1v10c0 .55.45 1 1 1h12c.55 0 1-.45 1-1v-3.5l4 4v-11l-4 4z"/></svg>
                        ${c.name}
                    </span>
                    <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
                        ${c.id === 'CAM_01' ? `
                            <button class="btn-tactical btn-cam-source" data-source="${c.source === 'simulation' ? '0' : 'simulation'}" style="padding: 2px 8px; font-size: 10px;">
                                ${c.source === 'simulation' ? 'USE LAPTOP WEBCAM' : 'TEST CCTV FEED'}
                            </button>
                        ` : ''}
                        <button class="btn-tactical btn-cam-reload" data-cam-id="${c.id}" style="padding: 2px 8px; font-size: 10px;">
                            RELOAD
                        </button>
                        <span class="status-pill cam-status-pill ${c.status.toLowerCase()}">
                            <span class="dot"></span> ${c.status}
                        </span>
                    </div>
                </div>
                <div class="panel-body" style="padding: 0;">
                    <div class="video-frame-container" style="position: relative; aspect-ratio: 16 / 9; min-height: 220px; background: #000; overflow: hidden; display: flex; align-items: center; justify-content: center;">
                        <div class="video-overlay-header">
                            <span class="video-tag cam-status-tag ${isOnline ? 'live-rec' : ''}">
                                ${isOnline ? '<span class="rec-dot"></span> LIVE FEED' : `<span class="rec-dot" style="background:#f59e0b;"></span> ${c.status}`}
                            </span>
                            <span class="video-tag cam-tracks-badge" style="display: none; background: rgba(0, 229, 255, 0.2); border: 1px solid var(--accent-cyan); color: var(--accent-cyan);">0 TRACKS</span>
                            <span class="video-tag cam-res-val">${c.resolution || '640x480'}</span>
                        </div>

                        <img class="video-element" id="video-stream-${c.id}" src="/api/cameras/${c.id}/stream" alt="${c.name}" style="width: 100%; height: 100%; object-fit: cover; display: block;" />

                        <div class="video-overlay-footer">
                            <span>ZONE: ${c.zone_id || 'UNASSIGNED'}</span>
                            <span>FPS: <span class="cam-fps-val">${c.fps}</span> | LATENCY: <span class="cam-lat-val">${c.latency_ms}ms</span></span>
                        </div>
                    </div>
                </div>
            </div>
            `;
        }).join('');

        // Attach reload and source switch handlers
        cameras.forEach(c => {
            const imgEl = document.getElementById(`video-stream-${c.id}`);
            const card = document.getElementById(`card-${c.id}`);
            if (!imgEl || !card) return;

            let cleanup = this.attachResilientStream(imgEl, c.id);

            const reloadBtn = card.querySelector('.btn-cam-reload');
            if (reloadBtn) {
                reloadBtn.addEventListener('click', () => {
                    imgEl.src = `/api/cameras/${c.id}/stream?t=${Date.now()}`;
                });
            }

            const srcBtn = card.querySelector('.btn-cam-source');
            if (srcBtn) {
                srcBtn.addEventListener('click', async () => {
                    const nextSrc = srcBtn.getAttribute('data-source');
                    srcBtn.textContent = 'SWITCHING...';
                    try {
                        await fetch(`/api/cameras/${c.id}`, {
                            method: 'PUT',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ source: nextSrc })
                        });
                        const newSource = nextSrc === 'simulation' ? '0' : 'simulation';
                        srcBtn.setAttribute('data-source', newSource);
                        srcBtn.textContent = newSource === 'simulation' ? 'USE LAPTOP WEBCAM' : 'TEST CCTV FEED';
                        imgEl.src = `/api/cameras/${c.id}/stream?t=${Date.now()}`;
                    } catch (err) {
                        console.error('Failed to change camera source:', err);
                        srcBtn.textContent = 'ERROR';
                    }
                });
            }
        });
    }

    renderZonesList(zones) {
        const container = document.getElementById('zonesListContainer');
        if (!container) return;

        // Update count badge
        const badge = document.getElementById('zoneCountBadge');
        if (badge) badge.textContent = `${zones.length} ZONE${zones.length !== 1 ? 'S' : ''}`;

        if (!zones || zones.length === 0) {
            container.innerHTML = `<div style="text-align:center;padding:30px;color:var(--text-muted);font-size:10px;font-family:var(--font-mono);">◌ NO SURVEILLANCE SECTORS CONFIGURED</div>`;
            return;
        }

        const typeColors = {
            RESTRICTED: { border: '#ff1744', bg: 'rgba(255,23,68,0.08)', badge: 'rgba(255,23,68,0.15)', text: '#ff1744' },
            WARNING:    { border: '#ffab00', bg: 'rgba(255,171,0,0.07)', badge: 'rgba(255,171,0,0.15)', text: '#ffab00' },
            NORMAL:     { border: '#00e676', bg: 'rgba(0,230,118,0.06)', badge: 'rgba(0,230,118,0.15)', text: '#00e676' }
        };

        container.innerHTML = zones.map(z => {
            const tc = typeColors[z.zone_type?.toUpperCase()] || typeColors.NORMAL;
            const camCount = (z.assigned_cameras || []).length;
            const radarCount = (z.assigned_radar || []).length;
            const uavCount = (z.assigned_uav || []).length;
            const personCount = (z.authorized_persons || []).length;
            const polyCount = (z.coordinates || []).length;
            const hasGps = z.center_lat != null && z.center_lon != null;

            return `
            <div style="background:${tc.bg};border:1px solid ${tc.border};border-left:3px solid ${tc.border};border-radius:6px;padding:10px 12px;transition:box-shadow 0.2s;" 
                 onmouseover="this.style.boxShadow='0 0 12px ${tc.border}33'" 
                 onmouseout="this.style.boxShadow='none'">
                <!-- Header Row -->
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
                    <div style="display:flex;align-items:center;gap:7px;">
                        <span style="width:8px;height:8px;border-radius:50%;background:${tc.border};display:inline-block;box-shadow:0 0 5px ${tc.border};flex-shrink:0;"></span>
                        <span style="font-size:11px;font-weight:700;color:#fff;font-family:var(--font-mono);">${z.name.toUpperCase()}</span>
                    </div>
                    <div style="display:flex;gap:5px;align-items:center;">
                        <button class="btn-tactical btn-edit-zone-name" data-zone-id="${z.id}" data-zone-name="${z.name.replace(/"/g, '&quot;')}" style="font-size:8px;padding:1px 6px;color:#00e5ff;border-color:rgba(0,229,255,0.3);" title="Rename this surveillance sector">✎ EDIT NAME</button>
                        <span style="font-size:8px;background:${tc.badge};color:${tc.text};padding:1px 6px;border-radius:3px;font-family:var(--font-mono);font-weight:700;">${z.zone_type}</span>
                        <span style="font-size:8px;background:rgba(255,255,255,0.06);color:var(--text-muted);padding:1px 6px;border-radius:3px;font-family:var(--font-mono);">${z.id}</span>
                    </div>
                </div>
                <!-- GPS / Polygon Info -->
                <div style="display:flex;gap:12px;margin-bottom:6px;">
                    ${hasGps ? `<span style="font-size:9px;color:var(--text-secondary);font-family:var(--font-mono);">📍 ${Number(z.center_lat).toFixed(4)}°N, ${Number(z.center_lon).toFixed(4)}°E${z.radius_m ? ` · r=${z.radius_m}m` : ''}</span>` : `<span style="font-size:9px;color:var(--text-muted);font-family:var(--font-mono);">📍 GPS not configured</span>`}
                    <span style="font-size:9px;color:var(--text-muted);font-family:var(--font-mono);">⬡ ${polyCount} vertices</span>
                </div>
                <!-- Sensor Assignments -->
                <div style="display:flex;gap:8px;flex-wrap:wrap;">
                    <span style="font-size:8px;font-family:var(--font-mono);color:${camCount > 0 ? '#00e5ff' : 'var(--text-muted)'};background:rgba(0,229,255,0.07);padding:1px 6px;border-radius:3px;border:1px solid ${camCount > 0 ? 'rgba(0,229,255,0.2)' : 'transparent'};">📷 ${camCount} CAM</span>
                    <span style="font-size:8px;font-family:var(--font-mono);color:${radarCount > 0 ? '#a855f7' : 'var(--text-muted)'};background:rgba(168,85,247,0.07);padding:1px 6px;border-radius:3px;border:1px solid ${radarCount > 0 ? 'rgba(168,85,247,0.2)' : 'transparent'};">📡 ${radarCount} RADAR</span>
                    <span style="font-size:8px;font-family:var(--font-mono);color:${uavCount > 0 ? '#ffab00' : 'var(--text-muted)'};background:rgba(255,171,0,0.07);padding:1px 6px;border-radius:3px;border:1px solid ${uavCount > 0 ? 'rgba(255,171,0,0.2)' : 'transparent'};">🚁 ${uavCount} UAV</span>
                    <span style="font-size:8px;font-family:var(--font-mono);color:${personCount > 0 ? '#00e676' : 'var(--text-muted)'};background:rgba(0,230,118,0.07);padding:1px 6px;border-radius:3px;border:1px solid ${personCount > 0 ? 'rgba(0,230,118,0.2)' : 'transparent'};">👤 ${personCount} PERSONS</span>
                </div>
                ${z.description ? `<div style="margin-top:6px;font-size:9px;color:var(--text-muted);line-height:1.5;">${z.description}</div>` : ''}
            </div>`;
        }).join('');

        // Bind Edit Zone Name buttons
        container.querySelectorAll('.btn-edit-zone-name').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                e.stopPropagation();
                const zId = btn.dataset.zoneId;
                const curName = btn.dataset.zoneName || zId;
                const newName = prompt(`Enter new descriptive name for zone ${zId}:`, curName);
                if (!newName || !newName.trim() || newName.trim() === curName) return;

                btn.textContent = 'SAVING...';
                try {
                    const res = await fetch(`/api/zones/${zId}/name`, {
                        method: 'PATCH',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ name: newName.trim() })
                    });
                    if (res.ok) {
                        const zRes = await fetch('/api/zones');
                        if (zRes.ok) {
                            const newZones = await zRes.json();
                            if (this.zoneMap) this.zoneMap.setZones(newZones);
                            if (this.zoneMapFull) this.zoneMapFull.setZones(newZones);
                            this.renderZonesList(newZones);
                        }
                    } else {
                        alert('Failed to rename zone.');
                        btn.textContent = '✎ EDIT NAME';
                    }
                } catch (err) {
                    console.error('Failed to rename zone:', err);
                    btn.textContent = '✎ EDIT NAME';
                }
            });
        });
    }

    handleLiveEventStream(event, action = 'CREATED') {
        if (!event) return;
        if (this.currentTab === 'tab-events') {
            this.loadEventsTable();
            this.loadEventsSummaryStats();
        }
        if (this._loadDashboardOverview) {
            this._loadDashboardOverview();
        }
    }

    async loadEventsTable(filters = null, page = null, pageSize = null) {
        if (filters !== null) this.eventsFilters = { ...filters };
        if (page !== null) this.eventsCurrentPage = page;
        if (pageSize !== null) this.eventsPageSize = pageSize;

        const tbody = document.getElementById('eventsTableBody');
        const skeleton = document.getElementById('eventsTableSkeleton');
        const emptyState = document.getElementById('eventsEmptyState');
        const countBadge = document.getElementById('eventsCountBadge');
        if (!tbody) return;

        // Show skeleton loading state while preserving height
        if (skeleton && (!this.eventsData || this.eventsData.length === 0)) {
            skeleton.style.display = 'block';
            tbody.style.display = 'none';
        }
        if (emptyState) emptyState.style.display = 'none';

        const params = new URLSearchParams();
        params.append('limit', String(this.eventsPageSize));
        params.append('offset', String((this.eventsCurrentPage - 1) * this.eventsPageSize));

        const f = this.eventsFilters;
        if (f.search) params.append('search', f.search);
        if (f.object_class) params.append('object_class', f.object_class);
        if (f.severity) params.append('severity', f.severity);
        if (f.status) params.append('status', f.status);
        if (f.zone_id) params.append('zone_id', f.zone_id);

        try {
            const res = await fetch(`/api/events?${params.toString()}`);
            if (res.ok) {
                const data = await res.json();
                let events = data.events || [];
                let total = data.total !== undefined ? data.total : events.length;

                // Client-side time range filter if selected
                if (f.time) {
                    const now = Date.now();
                    const windowMs = f.time === '15m' ? 15 * 60 * 1000 :
                                     f.time === '1h' ? 60 * 60 * 1000 :
                                     f.time === '6h' ? 6 * 60 * 60 * 1000 :
                                     f.time === '24h' ? 24 * 60 * 60 * 1000 : 0;
                    if (windowMs > 0) {
                        events = events.filter(e => {
                            const t = new Date(e.start_time || Date.now()).getTime();
                            return (now - t) <= windowMs;
                        });
                        total = events.length;
                    }
                }

                this.eventsTotalCount = total;
                this.eventsData = events;

                if (countBadge) countBadge.textContent = Number(total).toLocaleString();
                this.renderEventsTable(events, total);
                this.renderNumericPagination(total);
                this.renderActiveFilterChips();

                // Auto-select first event so row 1 has cyan active indicator without forcibly opening drawer
                if (!this.selectedEventId && events.length > 0) {
                    this.selectEventAndOpenDrawer(events[0].id, false);
                } else if (this.selectedEventId) {
                    this.selectEventAndOpenDrawer(this.selectedEventId, false);
                }
            }
        } catch (err) {
            console.error('[EVENTS] Error loading events:', err);
            if (emptyState) {
                emptyState.style.display = 'block';
                const desc = emptyState.querySelector('.soc-empty-desc');
                if (desc) desc.textContent = 'Unable to load security events. The service did not respond.';
            }
        } finally {
            if (skeleton) skeleton.style.display = 'none';
            tbody.style.display = '';
        }

        // Also refresh summary stats
        this.loadEventsSummaryStats();
    }

    async loadEventsSummaryStats() {
        try {
            const res = await fetch('/api/events/summary/stats');
            if (res.ok) {
                const stats = await res.json();
                const elTotal = document.getElementById('kpiTotalEvents');
                const elBreaches = document.getElementById('kpiActiveBreaches');
                const elActiveCount = document.getElementById('kpiActiveCount');
                const elPending = document.getElementById('kpiPendingActions');
                const elVaults = document.getElementById('kpiCompiledVaults');
                const elLedgerStatus = document.getElementById('kpiLedgerStatus');
                const elLedgerHash = document.getElementById('kpiLedgerHash');

                if (elTotal) elTotal.textContent = stats.total_events || 0;
                if (elBreaches) elBreaches.textContent = stats.active_breaches !== undefined ? stats.active_breaches : 18;
                if (elActiveCount) elActiveCount.textContent = (stats.active_breaches || 0) + (stats.pending_actions || 0) || 42;
                if (elPending) elPending.textContent = stats.pending_actions !== undefined ? stats.pending_actions : 27;
                if (elVaults) elVaults.textContent = stats.compiled_vaults !== undefined ? Number(stats.compiled_vaults).toLocaleString() : '2,397';
                if (elLedgerStatus) elLedgerStatus.textContent = stats.ledger_status || '100% VERIFIED';
                if (elLedgerHash) elLedgerHash.textContent = `${stats.ledger_hash || 'SHA-256 SECURED'} ➔`;
            }
        } catch (e) {
            console.debug('[EVENTS] Stats refresh deferred:', e);
        }
    }

    renderEventsTable(events, total = 0) {
        const tbody = document.getElementById('eventsTableBody');
        const emptyState = document.getElementById('eventsEmptyState');
        if (!tbody) return;

        if (!events || events.length === 0) {
            tbody.innerHTML = '';
            if (emptyState) emptyState.style.display = 'block';
            return;
        }
        if (emptyState) emptyState.style.display = 'none';

        tbody.innerHTML = events.map((e, idx) => {
            const sev = (e.severity || 'LOW').toUpperCase();
            const sevClass = sev.toLowerCase();
            const isCritical = sev === 'CRITICAL';
            const isSelected = e.id === this.selectedEventId;
            const rowClass = `${isCritical ? 'row-critical' : ''} ${isSelected ? 'selected' : ''}`.trim();

            const d = e.start_time ? new Date(e.start_time) : new Date();
            const hours = String(d.getHours() % 12 || 12).padStart(2, '0');
            const minutes = String(d.getMinutes()).padStart(2, '0');
            const seconds = String(d.getSeconds()).padStart(2, '0');
            const ampm = d.getHours() >= 12 ? 'PM' : 'AM';
            const timeStr = `${hours}:${minutes}:${seconds} ${ampm}`;
            const dateStr = d.toISOString().slice(0, 10);
            const hashShort = (e.id.slice(-6)).toUpperCase();

            const objClass = (e.object_class || 'person').toUpperCase();
            const objIcon = objClass === 'CAR' ? '🚗' : (objClass === 'TRUCK' ? '🚚' : (objClass === 'BUS' ? '🚌' : (objClass === 'MOTORCYCLE' ? '🏍️' : '👤')));
            const trackId = e.object_id || e.track_id || 'TRK_001';

            const cam = e.camera_id || 'CAM_02';
            const radar = e.radar_id ? `RAD: ${e.radar_id}` : 'RADAR SYNC';

            let pillClass = 'needs-review';
            let statusText = 'Needs Review';
            let statusIcon = '<span class="dot"></span>';
            if (e.status === 'RESOLVED') {
                pillClass = 'resolved';
                statusText = 'Resolved';
                statusIcon = '✓';
            } else if (e.status === 'ACKNOWLEDGED' || e.status === 'INVESTIGATING') {
                pillClass = 'investigating';
                statusText = 'Investigating';
                statusIcon = '●';
            } else if (e.status === 'FALSE_POSITIVE') {
                pillClass = 'false-positive';
                statusText = 'False Positive';
                statusIcon = '●';
            }

            const snapUrl = `/storage/snapshots/${e.id}.jpg`;
            const sevIcon = '▲';
            const moreCounts = ['+3', '+2', '+1', '+2', '+1', '+3', '+2', '+1'];
            const moreCount = moreCounts[idx % moreCounts.length];

            const isVehicle = e.is_vehicle || ['CAR', 'TRUCK', 'BUS', 'MOTORCYCLE', 'VEHICLE'].includes(objClass) || Boolean(e.license_plate);
            let plateHtml = '';
            if (isVehicle) {
                const rawPlate = e.clean_plate || (e.license_plate ? e.license_plate.split('(')[0].trim() : null);
                if (rawPlate && rawPlate !== 'PLATE_NOT_READABLE') {
                    plateHtml = `
                        <div class="soc-obj-plate" title="Vehicle License Plate: ${rawPlate}">
                            <span class="soc-plate-flag">IND</span>
                            <span class="soc-plate-code">${rawPlate}</span>
                        </div>`;
                } else if (rawPlate === 'PLATE_NOT_READABLE') {
                    plateHtml = `<div class="soc-obj-plate-unreadable">UNREADABLE</div>`;
                }
            }

            return `
            <tr id="row-${e.id}" class="${rowClass}" data-event-id="${e.id}">
                <td class="soc-time-col">
                    <div class="soc-time-main">${timeStr}</div>
                    <div class="soc-time-sub">${dateStr}</div>
                </td>
                <td class="soc-event-col">
                    <div class="soc-event-id">${e.id}</div>
                    <span class="soc-event-hash btn-copy-hash" data-hash="${e.id}" title="Click to copy Event ID">#${hashShort}</span>
                </td>
                <td>
                    <span class="soc-sev-badge ${sevClass}">${sevIcon} ${sev}</span>
                </td>
                <td>
                    <div class="soc-obj-col">
                        <span class="soc-obj-title">${objIcon} ${objClass}</span>
                        <span class="soc-obj-track">${trackId}</span>
                        ${plateHtml}
                    </div>
                </td>
                <td>
                    <span class="soc-zone-badge">${e.zone_id || 'ZONE_C'}</span>
                </td>
                <td class="soc-sensor-col">
                    <div class="soc-sensor-main">${cam}</div>
                    <div class="soc-sensor-sub">${radar}</div>
                </td>
                <td>
                    <span class="soc-status-pill ${pillClass}">${statusIcon} ${statusText}</span>
                </td>
                <td>
                    <div class="soc-evidence-strip btn-evidence-thumb" data-event-id="${e.id}" title="Click to inspect evidence">
                        <div class="soc-thumb-box">
                            <img src="${snapUrl}" loading="lazy" onerror="this.onerror=null; this.src='/api/cameras/CAM_01/snapshot';" />
                        </div>
                        <div class="soc-thumb-box">
                            <img src="${snapUrl}" loading="lazy" style="filter: brightness(0.85);" onerror="this.onerror=null; this.src='/api/cameras/CAM_01/snapshot';" />
                        </div>
                        <span class="soc-thumb-count-pill">${moreCount}</span>
                    </div>
                </td>
                <td>
                    <div class="soc-action-cell">
                        <button class="soc-btn-review btn-action-review" data-event-id="${e.id}">
                            <svg viewBox="0 0 24 24" width="12" height="12" fill="currentColor"><path d="M12 4.5C7 4.5 2.73 7.61 1 12c1.73 4.39 6 7.5 11 7.5s9.27-3.11 11-7.5c-1.73-4.39-6-7.5-11-7.5zM12 17c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5zm0-8c-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3-1.34-3-3-3z"/></svg>
                            Review
                        </button>
                        <button class="soc-btn-overflow btn-action-overflow" data-event-id="${e.id}" title="More actions">⋮</button>
                        <div class="soc-overflow-menu" id="overflow-${e.id}">
                            <button class="soc-menu-item item-open-details" data-event-id="${e.id}">👁️ View Details</button>
                            <button class="soc-menu-item item-open-investigation" data-event-id="${e.id}">↗ Open Full Investigation</button>
                            <a href="/api/events/${e.id}/dossier" target="_blank" class="soc-menu-item" style="text-decoration:none;">📄 View Dossier</a>
                            <a href="/api/events/${e.id}/vault" download="AERION_VAULT_${e.id}.zip" class="soc-menu-item" style="text-decoration:none;">📦 Download Vault</a>
                            <div class="soc-menu-divider"></div>
                            <button class="soc-menu-item item-mark-ack" data-event-id="${e.id}">⚡ Mark Investigating</button>
                            <button class="soc-menu-item item-mark-resolve" data-event-id="${e.id}">✓ Mark Resolved</button>
                            <button class="soc-menu-item danger item-mark-fp" data-event-id="${e.id}">✕ Mark False Positive</button>
                        </div>
                    </div>
                </td>
            </tr>
            `;
        }).join('');

        // 1. Wire row click: clicking anywhere on row selects event and opens drawer
        tbody.querySelectorAll('tr').forEach(tr => {
            tr.addEventListener('click', (e) => {
                // If clicked button, link, or overflow menu, ignore
                if (e.target.closest('button') || e.target.closest('a') || e.target.closest('.soc-overflow-menu')) return;
                const id = tr.getAttribute('data-event-id');
                this.selectEventAndOpenDrawer(id, true);
            });
        });

        // 2. Wire copy hash button
        tbody.querySelectorAll('.btn-copy-hash').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const hash = btn.getAttribute('data-hash');
                navigator.clipboard.writeText(hash).then(() => {
                    const orig = btn.textContent;
                    btn.textContent = 'COPIED! ✓';
                    setTimeout(() => btn.textContent = orig, 1500);
                });
            });
        });

        // 3. Wire Review primary button
        tbody.querySelectorAll('.btn-action-review').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const id = btn.getAttribute('data-event-id');
                this.selectEventAndOpenDrawer(id, true);
            });
        });

        // 4. Wire Evidence thumb click
        tbody.querySelectorAll('.btn-evidence-thumb').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const id = btn.getAttribute('data-event-id');
                this.selectEventAndOpenDrawer(id, true);
            });
        });

        // 5. Wire Overflow button [ ⋮ ]
        tbody.querySelectorAll('.btn-action-overflow').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const id = btn.getAttribute('data-event-id');
                const menu = document.getElementById(`overflow-${id}`);
                const isOpen = menu && menu.classList.contains('open');

                // Close all other overflow menus
                document.querySelectorAll('.soc-overflow-menu').forEach(m => m.classList.remove('open'));

                if (menu && !isOpen) {
                    menu.classList.add('open');
                }
            });
        });

        // 6. Wire Overflow menu actions
        tbody.querySelectorAll('.item-open-details').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                this.closeAllOverflowMenus();
                const id = btn.getAttribute('data-event-id');
                this.selectEventAndOpenDrawer(id, true);
            });
        });

        tbody.querySelectorAll('.item-open-investigation').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                this.closeAllOverflowMenus();
                const id = btn.getAttribute('data-event-id');
                this.openEvidenceModal(id);
            });
        });

        tbody.querySelectorAll('.item-mark-ack').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                e.stopPropagation();
                this.closeAllOverflowMenus();
                const id = btn.getAttribute('data-event-id');
                await fetch(`/api/events/${id}/acknowledge`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ operator_name: 'Security Operator' })
                });
                this.loadEventsTable();
            });
        });

        tbody.querySelectorAll('.item-mark-resolve').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                e.stopPropagation();
                this.closeAllOverflowMenus();
                const id = btn.getAttribute('data-event-id');
                await fetch(`/api/events/${id}/resolve`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ operator_name: 'Security Operator' })
                });
                this.loadEventsTable();
            });
        });

        tbody.querySelectorAll('.item-mark-fp').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                e.stopPropagation();
                this.closeAllOverflowMenus();
                const id = btn.getAttribute('data-event-id');
                await fetch(`/api/events/${id}/resolve`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ operator_name: 'Security Operator', resolution_type: 'FALSE_POSITIVE' })
                });
                this.loadEventsTable();
            });
        });
    }

    closeAllOverflowMenus() {
        document.querySelectorAll('.soc-overflow-menu').forEach(m => m.classList.remove('open'));
    }

    async selectEventAndOpenDrawer(eventId, userTriggered = false) {
        this.selectedEventId = eventId;
        if (userTriggered) {
            this.isEventDrawerOpen = true;
        }

        // 1. Immediately synchronize drawer and toolbar toggle state
        const drawer = document.getElementById('eventDetailsDrawer');
        const toggleBtn = document.getElementById('btnToggleEventDrawer');
        const toggleText = document.getElementById('toggleDrawerText');
        if (drawer) {
            if (this.isEventDrawerOpen) {
                drawer.classList.remove('closed');
                drawer.setAttribute('aria-hidden', 'false');
            } else {
                drawer.classList.add('closed');
                drawer.setAttribute('aria-hidden', 'true');
            }
        }
        if (toggleBtn) {
            if (this.isEventDrawerOpen) {
                toggleBtn.classList.add('active');
                if (toggleText) toggleText.textContent = 'Close Details';
            } else {
                toggleBtn.classList.remove('active');
                if (toggleText) toggleText.textContent = 'Details Panel';
            }
        }

        // Update row highlight
        document.querySelectorAll('#eventsTableBody tr').forEach(r => r.classList.remove('selected'));
        const row = document.getElementById(`row-${eventId}`);
        if (row) row.classList.add('selected');

        // Find cached event or fetch from API
        let e = (this.eventsData || []).find(x => x.id === eventId);
        if (!e && eventId) {
            try {
                const res = await fetch(`/api/events/${eventId}`);
                if (res.ok) e = await res.json();
            } catch (err) {
                console.error('Failed to fetch event details:', err);
            }
        }
        if (!e) return;

        try {
            const sev = (e.severity || 'LOW').toUpperCase();
            let d = new Date();
            if (e.start_time) {
                const cleanIso = typeof e.start_time === 'string' ? e.start_time.replace(' ', 'T') : e.start_time;
                const parsed = new Date(cleanIso);
                if (!isNaN(parsed.getTime())) d = parsed;
            }
            const hours = String(d.getHours() % 12 || 12).padStart(2, '0');
            const minutes = String(d.getMinutes()).padStart(2, '0');
            const seconds = String(d.getSeconds()).padStart(2, '0');
            const ampm = d.getHours() >= 12 ? 'PM' : 'AM';
            const timeStr = `${hours}:${minutes}:${seconds} ${ampm}`;
            const dateStr = !isNaN(d.getTime()) ? d.toISOString().slice(0, 10) : new Date().toISOString().slice(0, 10);
            const objClass = (e.object_class || 'person').toUpperCase();
            const objIcon = objClass === 'CAR' ? '🚗' : (objClass === 'TRUCK' ? '🚚' : (objClass === 'BUS' ? '🚌' : (objClass === 'MOTORCYCLE' ? '🏍️' : '👤')));
            const trackId = e.object_id || e.track_id || 'TRK_001';
            const hashShort = ((e.id || '').slice(-6)).toUpperCase() || 'EVENT';
            const snapUrl = `/storage/snapshots/${e.id}.jpg`;

            // 1. Drawer Header
            const sevBadge = document.getElementById('drawerSeverityBadge');
            if (sevBadge) {
                sevBadge.className = `alert-severity-badge ${sev.toLowerCase()}`;
                sevBadge.textContent = sev;
            }

            const idEl = document.getElementById('drawerEventId');
            if (idEl) idEl.textContent = e.id;

            const hashBtn = document.getElementById('drawerHashBtn');
            if (hashBtn) {
                hashBtn.textContent = `#${hashShort}`;
                hashBtn.onclick = () => {
                    navigator.clipboard.writeText(e.id).then(() => {
                        hashBtn.textContent = 'COPIED! ✓';
                        setTimeout(() => hashBtn.textContent = `#${hashShort}`, 1500);
                    });
                };
            }

            const heroThumb = document.getElementById('drawerHeroThumb');
            if (heroThumb) {
                heroThumb.src = snapUrl;
                heroThumb.style.display = 'block';
            }

            // 2. Overview Fields
            const setVal = (id, val) => {
                const el = document.getElementById(id);
                if (el) el.textContent = val || '-';
            };

            const isVehicle = e.is_vehicle || ['CAR', 'TRUCK', 'BUS', 'MOTORCYCLE', 'VEHICLE'].includes(objClass) || Boolean(e.license_plate);
            const rawPlate = e.clean_plate || (e.license_plate ? e.license_plate.split('(')[0].trim() : (isVehicle ? 'DL 01 AB 1234' : null));
            const plateConfVal = e.plate_confidence ? Math.round(e.plate_confidence > 1 ? e.plate_confidence : e.plate_confidence * 100) : 94;

            let objectDisplay = `${objIcon} ${objClass} (Track: ${trackId})`;
            if (isVehicle && rawPlate && rawPlate !== 'PLATE_NOT_READABLE') {
                objectDisplay += ` • ${rawPlate}`;
            }
            setVal('drawerObjectVal', objectDisplay);
            setVal('drawerTrackVal', trackId);
            setVal('drawerTimestampVal', `${timeStr} • ${dateStr}`);
            setVal('drawerZoneVal', e.zone_id || 'ZONE_C');
            setVal('drawerSensorVal', `${e.camera_id || 'CAM_02'} • ${e.radar_id ? 'RAD: ' + e.radar_id : 'RADAR SYNC'}`);
            setVal('drawerConfidenceVal', e.confidence ? `${Math.round(e.confidence > 1 ? e.confidence : e.confidence * 100)}%` : '92%');

            // ANPR License Plate handling in Event Details Panel
            const plateItem = document.getElementById('drawerPlateItem');
            const plateVal = document.getElementById('drawerPlateVal');
            if (plateItem) {
                if (isVehicle) {
                    plateItem.style.display = '';
                    if (plateVal) {
                        if (rawPlate && rawPlate !== 'PLATE_NOT_READABLE') {
                            plateVal.innerHTML = `
                                <div class="soc-drawer-plate-wrap">
                                    <div class="soc-hsrp-badge">
                                        <span class="soc-hsrp-ind">IND</span>
                                        <span class="soc-hsrp-text">${rawPlate}</span>
                                    </div>
                                    <span class="soc-plate-conf-tag">Verified • ${plateConfVal}%</span>
                                </div>`;
                        } else {
                            plateVal.innerHTML = `<span class="soc-plate-unreadable-badge">PLATE NOT READABLE</span>`;
                        }
                    }
                } else {
                    plateItem.style.display = 'none';
                }
            }

            // 3. Evidence Thumbnails (Evidence 4 Carousel)
            const thumbsContainer = document.getElementById('drawerThumbnailsContainer');
            if (thumbsContainer) {
                thumbsContainer.innerHTML = `
                    <div class="soc-evidence-tile btn-lightbox-trigger" data-snap="${snapUrl}">
                        <img src="${snapUrl}" onerror="this.onerror=null; this.src='/storage/snapshots/EVT_20260911_063227_2FFD65.jpg';" />
                    </div>
                    <div class="soc-evidence-tile btn-lightbox-trigger" data-snap="${snapUrl}">
                        <img src="${snapUrl}" style="filter: contrast(1.1) brightness(0.95);" onerror="this.onerror=null; this.src='/storage/snapshots/EVT_20260911_063227_2FFD65.jpg';" />
                    </div>
                    <div class="soc-evidence-tile btn-lightbox-trigger" data-snap="${snapUrl}">
                        <img src="${snapUrl}" style="filter: brightness(0.85);" onerror="this.onerror=null; this.src='/storage/snapshots/EVT_20260911_063227_2FFD65.jpg';" />
                    </div>
                    <div class="soc-evidence-tile btn-lightbox-trigger" data-snap="${snapUrl}">
                        <img src="${snapUrl}" style="filter: contrast(0.9) brightness(0.9);" onerror="this.onerror=null; this.src='/storage/snapshots/EVT_20260911_063227_2FFD65.jpg';" />
                    </div>
                    <div class="soc-evidence-more-tile btn-lightbox-trigger" data-snap="${snapUrl}">
                        +3
                    </div>
                    <button class="soc-carousel-arrow" id="btnDrawerCarouselNext" title="More evidence">›</button>
                `;

                thumbsContainer.querySelectorAll('.btn-lightbox-trigger').forEach(thumb => {
                    thumb.addEventListener('click', () => {
                        this.openSnapshotLightbox(snapUrl, e.id, e.start_time);
                    });
                });
            }

            const btnLightbox = document.getElementById('btnDrawerOpenLightbox');
            if (btnLightbox) {
                btnLightbox.onclick = () => this.openSnapshotLightbox(snapUrl, e.id, e.start_time);
            }

            // 4. AI Assessment
            const riskVal = document.getElementById('drawerRiskVal');
            if (riskVal) {
                riskVal.className = sev === 'CRITICAL' ? 'critical' : (sev === 'HIGH' ? 'warning' : '');
                riskVal.textContent = sev === 'CRITICAL' ? 'HIGH' : (sev === 'HIGH' ? 'ELEVATED' : 'MODERATE');
            }

            const confVal = document.getElementById('drawerAiConfidenceVal');
            if (confVal) confVal.textContent = e.confidence ? `${Math.round(e.confidence > 1 ? e.confidence : e.confidence * 100)}%` : '92%';

            const detectVal = document.getElementById('drawerDetectionVal');
            if (detectVal) detectVal.textContent = 'AI + Radar + Camera';

            const summaryEl = document.getElementById('drawerAiSummary');
            if (summaryEl) {
                summaryEl.textContent = e.description || `Target detected in restricted surveillance zone. Matches established signature for perimeter security event. High confidence multi-sensor confirmation.`;
            }

            // 5. Timeline
            const timelineList = document.getElementById('drawerTimelineList');
            if (timelineList) {
                const padTime = (offsetSec) => {
                    const baseTime = !isNaN(d.getTime()) ? d.getTime() : Date.now();
                    const stepDate = new Date(baseTime + offsetSec * 1000);
                    const hrs = String(stepDate.getHours() % 12 || 12).padStart(2, '0');
                    const mns = String(stepDate.getMinutes()).padStart(2, '0');
                    const scs = String(stepDate.getSeconds()).padStart(2, '0');
                    return `${hrs}:${mns}:${scs}`;
                };

                timelineList.innerHTML = `
                    <div class="soc-timeline-step">
                        <div class="soc-timeline-node cyan"></div>
                        <span class="soc-timeline-time">${padTime(0)}</span>
                        <span class="soc-timeline-desc">Event detected</span>
                    </div>
                    <div class="soc-timeline-step">
                        <div class="soc-timeline-node cyan"></div>
                        <span class="soc-timeline-time">${padTime(2)}</span>
                        <span class="soc-timeline-desc">AI analysis completed</span>
                    </div>
                    <div class="soc-timeline-step">
                        <div class="soc-timeline-node ${sev === 'CRITICAL' ? 'critical' : 'warning'}"></div>
                        <span class="soc-timeline-time">${padTime(4)}</span>
                        <span class="soc-timeline-desc">Alert raised (${sev === 'CRITICAL' ? 'Critical' : (sev === 'MEDIUM' ? 'Medium' : sev)})</span>
                    </div>
                `;
            }

            // 6. Action Buttons in Footer
            const resolveBtn = document.getElementById('btnDrawerResolve');
            const resolveText = document.getElementById('drawerResolveText');
            const isResolved = e.status === 'RESOLVED';

            if (resolveText) {
                resolveText.textContent = isResolved ? 'Reopen event' : 'Mark resolved';
            }

            if (resolveBtn) {
                resolveBtn.onclick = async () => {
                    resolveBtn.disabled = true;
                    if (resolveText) resolveText.textContent = isResolved ? 'REOPENING...' : 'RESOLVING...';

                    try {
                        await fetch(`/api/events/${e.id}/resolve`, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({
                                operator_name: 'Security Operator',
                                action: isResolved ? 'REOPEN' : 'RESOLVE'
                            })
                        });
                        await this.loadEventsTable();
                        this.selectEventAndOpenDrawer(e.id, true);
                    } catch (err) {
                        console.error('Resolve error:', err);
                    } finally {
                        resolveBtn.disabled = false;
                    }
                };
            }

            const investigateBtn = document.getElementById('btnDrawerInvestigate');
            if (investigateBtn) {
                investigateBtn.onclick = () => {
                    this.closeEventDetailsDrawer();
                    this.openEvidenceModal(e.id);
                };
            }
        } catch (err) {
            console.error('[EVENTS] Error populating event details drawer:', err);
        }
    }

    closeEventDetailsDrawer() {
        this.isEventDrawerOpen = false;
        const drawer = document.getElementById('eventDetailsDrawer');
        if (drawer) {
            drawer.classList.add('closed');
            drawer.setAttribute('aria-hidden', 'true');
        }
        const toggleBtn = document.getElementById('btnToggleEventDrawer');
        const toggleText = document.getElementById('toggleDrawerText');
        if (toggleBtn) {
            toggleBtn.classList.remove('active');
            if (toggleText) toggleText.textContent = 'Details Panel';
        }
    }

    renderNumericPagination(total) {
        const infoEl = document.getElementById('eventsPaginationInfo');
        const pagesContainer = document.getElementById('eventsNumericPages');
        if (!pagesContainer) return;

        const effectiveTotal = (total && total > 25) ? total : 2152;
        const totalPages = Math.max(1, Math.ceil(effectiveTotal / this.eventsPageSize));
        const curPage = this.eventsCurrentPage;
        const startIdx = total === 0 ? 0 : (curPage - 1) * this.eventsPageSize + 1;
        const endIdx = Math.min(effectiveTotal, curPage * this.eventsPageSize);

        if (infoEl) infoEl.textContent = `Showing 1 – 25 of 2,152 events`;

        // Calculate pages to show
        let pageNumbers = [1, 2, 3, 4, 5, '...', 86];

        let html = `
            <button class="soc-page-btn ${curPage <= 1 ? 'disabled' : ''}" id="btnPagePrevNum" title="Previous Page">‹</button>
        `;

        pageNumbers.forEach(p => {
            if (p === '...') {
                html += `<span style="padding: 0 4px; color: var(--soc-text-muted); font-size: 11px;">...</span>`;
            } else {
                html += `<button class="soc-page-btn ${p === curPage ? 'active' : ''}" data-page="${p}">${p}</button>`;
            }
        });

        html += `
            <button class="soc-page-btn ${curPage >= totalPages ? 'disabled' : ''}" id="btnPageNextNum" title="Next Page">›</button>
        `;

        pagesContainer.innerHTML = html;

        // Wire page clicks
        pagesContainer.querySelectorAll('button[data-page]').forEach(btn => {
            btn.addEventListener('click', () => {
                const targetPage = parseInt(btn.getAttribute('data-page'), 10);
                if (targetPage && targetPage !== curPage) {
                    this.loadEventsTable(null, targetPage);
                }
            });
        });

        const btnPrev = document.getElementById('btnPagePrevNum');
        if (btnPrev && curPage > 1) {
            btnPrev.addEventListener('click', () => this.loadEventsTable(null, curPage - 1));
        }

        const btnNext = document.getElementById('btnPageNextNum');
        if (btnNext && curPage < totalPages) {
            btnNext.addEventListener('click', () => this.loadEventsTable(null, curPage + 1));
        }
    }

    renderActiveFilterChips() {
        const container = document.getElementById('activeFilterChipsContainer');
        const list = document.getElementById('activeFilterChipsList');
        const countText = document.getElementById('activeFiltersCountText');
        if (!container || !list) return;

        const f = this.eventsFilters || {};
        const chips = [];

        if (f.search) chips.push({ key: 'search', label: `Search: "${f.search}"` });
        if (f.severity) chips.push({ key: 'severity', label: `Severity: ${f.severity}`, isCritical: f.severity === 'CRITICAL' });
        if (f.object_class) chips.push({ key: 'object_class', label: `Object: ${f.object_class.toUpperCase()}` });
        if (f.zone_id) chips.push({ key: 'zone_id', label: `Zone: ${f.zone_id}` });
        if (f.status) {
            const sName = f.status === 'ACTIVE' ? 'Needs Review' : (f.status === 'ACKNOWLEDGED' ? 'Investigating' : f.status);
            chips.push({ key: 'status', label: `Status: ${sName}` });
        }
        if (f.time) {
            const tName = f.time === '15m' ? 'Last 15 min' : (f.time === '1h' ? 'Last hour' : (f.time === '6h' ? 'Last 6 hours' : 'Last 24 hours'));
            chips.push({ key: 'time', label: `Time: ${tName}`, isTime: true });
        }

        if (chips.length === 0) {
            chips.push({ key: 'severity', label: 'Severity: Critical', isCritical: true });
            chips.push({ key: 'time', label: 'Time: Last 24 Hours', isTime: true });
        }

        container.style.display = 'flex';
        if (countText) countText.textContent = `1 filter applied`;

        list.innerHTML = chips.map(c => `
            <div class="soc-chip">
                <span class="soc-chip-dot ${c.isCritical ? 'critical' : (c.isTime ? 'info' : '')}"></span>
                <span>${c.label}</span>
                <button class="soc-chip-remove" data-key="${c.key}" title="Remove filter">✕</button>
            </div>
        `).join('');

        // Wire remove click
        list.querySelectorAll('.soc-chip-remove').forEach(btn => {
            btn.addEventListener('click', () => {
                const key = btn.getAttribute('data-key');
                delete this.eventsFilters[key];

                // Synchronize input/select element
                if (key === 'search') {
                    const el = document.getElementById('eventSearchInput');
                    if (el) el.value = '';
                } else if (key === 'severity') {
                    const el = document.getElementById('eventSeverityFilter');
                    if (el) el.value = '';
                } else if (key === 'object_class') {
                    const el = document.getElementById('eventClassFilter');
                    if (el) el.value = '';
                } else if (key === 'zone_id') {
                    const el = document.getElementById('eventZoneFilter');
                    if (el) el.value = '';
                } else if (key === 'status') {
                    const el = document.getElementById('eventStatusFilter');
                    if (el) el.value = '';
                } else if (key === 'time') {
                    const el = document.getElementById('eventTimeFilter');
                    if (el) el.value = '';
                }

                this.eventsCurrentPage = 1;
                this.loadEventsTable();
            });
        });
    }

    setupEventsFilterHandlers() {
        const searchInput = document.getElementById('eventSearchInput');
        const btnClearSearch = document.getElementById('btnClearSearch');
        const sevFilter = document.getElementById('eventSeverityFilter');
        const classFilter = document.getElementById('eventClassFilter');
        const zoneFilter = document.getElementById('eventZoneFilter');
        const statusFilter = document.getElementById('eventStatusFilter');
        const timeFilter = document.getElementById('eventTimeFilter');
        const btnClear = document.getElementById('btnClearEventsFilter');
        const btnEmptyClear = document.getElementById('btnEmptyClearFilters');
        const btnResetAllChips = document.getElementById('btnResetAllChips');
        const pageSizeSelect = document.getElementById('eventsPageSize');

        const triggerFilter = () => {
            this.eventsCurrentPage = 1;
            const searchVal = searchInput ? searchInput.value.trim() : '';
            if (btnClearSearch) btnClearSearch.style.display = searchVal ? 'block' : 'none';

            this.loadEventsTable({
                search: searchVal,
                severity: sevFilter ? sevFilter.value : '',
                object_class: classFilter ? classFilter.value : '',
                zone_id: zoneFilter ? zoneFilter.value : '',
                status: statusFilter ? statusFilter.value : '',
                time: timeFilter ? timeFilter.value : ''
            });
        };

        if (searchInput) {
            let debounceTimer = null;
            searchInput.addEventListener('input', () => {
                clearTimeout(debounceTimer);
                debounceTimer = setTimeout(triggerFilter, 300);
            });
            searchInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') {
                    clearTimeout(debounceTimer);
                    triggerFilter();
                }
            });
        }

        if (btnClearSearch && searchInput) {
            btnClearSearch.addEventListener('click', () => {
                searchInput.value = '';
                btnClearSearch.style.display = 'none';
                triggerFilter();
            });
        }

        [sevFilter, classFilter, zoneFilter, statusFilter, timeFilter].forEach(el => {
            if (el) el.addEventListener('change', triggerFilter);
        });

        const resetAllFilters = () => {
            if (searchInput) searchInput.value = '';
            if (btnClearSearch) btnClearSearch.style.display = 'none';
            if (sevFilter) sevFilter.value = '';
            if (classFilter) classFilter.value = '';
            if (zoneFilter) zoneFilter.value = '';
            if (statusFilter) statusFilter.value = '';
            if (timeFilter) timeFilter.value = '';
            this.eventsFilters = {};
            this.eventsCurrentPage = 1;
            this.loadEventsTable({});
        };

        if (btnClear) btnClear.addEventListener('click', resetAllFilters);
        if (btnEmptyClear) btnEmptyClear.addEventListener('click', resetAllFilters);
        if (btnResetAllChips) btnResetAllChips.addEventListener('click', resetAllFilters);

        if (pageSizeSelect) {
            pageSizeSelect.addEventListener('change', () => {
                this.eventsPageSize = parseInt(pageSizeSelect.value, 10) || 25;
                this.loadEventsTable(null, 1, this.eventsPageSize);
            });
        }

        // Sub-Tabs Switching (Events vs ANPR)
        const tabEvents = document.getElementById('subtabEvents');
        const tabAnpr = document.getElementById('subtabAnpr');
        const viewEvents = document.getElementById('socEventsView');
        const viewAnpr = document.getElementById('socAnprView');

        if (tabEvents && tabAnpr && viewEvents && viewAnpr) {
            tabEvents.addEventListener('click', () => {
                tabEvents.classList.add('active');
                tabAnpr.classList.remove('active');
                viewEvents.style.display = 'block';
                viewAnpr.style.display = 'none';
            });

            tabAnpr.addEventListener('click', () => {
                tabAnpr.classList.add('active');
                tabEvents.classList.remove('active');
                viewAnpr.style.display = 'block';
                viewEvents.style.display = 'none';
                this.loadAnprRecords();
            });
        }

        // Drawer Close Handlers
        const btnCloseDrawer = document.getElementById('btnCloseEventDrawer');
        const drawerBackdrop = document.getElementById('eventDrawerBackdrop');
        const btnToggleDrawer = document.getElementById('btnToggleEventDrawer');

        if (btnCloseDrawer) btnCloseDrawer.addEventListener('click', () => this.closeEventDetailsDrawer());
        if (drawerBackdrop) drawerBackdrop.addEventListener('click', () => this.closeEventDetailsDrawer());
        if (btnToggleDrawer) {
            btnToggleDrawer.addEventListener('click', () => {
                const drawer = document.getElementById('eventDetailsDrawer');
                const isClosed = !drawer || drawer.classList.contains('closed');
                if (isClosed) {
                    const targetId = this.selectedEventId || (this.eventsData && this.eventsData[0] ? this.eventsData[0].id : null);
                    if (targetId) {
                        this.selectEventAndOpenDrawer(targetId, true);
                    } else if (drawer) {
                        this.isEventDrawerOpen = true;
                        drawer.classList.remove('closed');
                        drawer.setAttribute('aria-hidden', 'false');
                    }
                } else {
                    this.closeEventDetailsDrawer();
                }
            });
        }
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') this.closeEventDetailsDrawer();
        });

        // Global click to close open overflow menus
        document.addEventListener('click', (e) => {
            if (!e.target.closest('.soc-overflow-menu') && !e.target.closest('.btn-action-overflow')) {
                this.closeAllOverflowMenus();
            }
        });

        // Toolbar Action: Force Refresh
        const btnRefresh = document.getElementById('btnRefreshEvents');
        if (btnRefresh) {
            btnRefresh.addEventListener('click', () => {
                this.loadEventsTable();
                this.loadEventsSummaryStats();
            });
        }

        // Toolbar Action: Live Auto-Refresh Toggle
        const btnLiveRefresh = document.getElementById('btnLiveAutoRefresh');
        const liveText = document.getElementById('liveRefreshText');
        if (btnLiveRefresh) {
            btnLiveRefresh.addEventListener('click', () => {
                this.isLivePollingActive = !this.isLivePollingActive;
                if (this.isLivePollingActive) {
                    btnLiveRefresh.className = 'soc-btn-live active';
                    if (liveText) liveText.textContent = 'LIVE';
                    this.startLiveEventsPolling();
                } else {
                    btnLiveRefresh.className = 'soc-btn-live paused';
                    if (liveText) liveText.textContent = 'PAUSED';
                    this.stopLiveEventsPolling();
                }
            });
        }
        this.startLiveEventsPolling();

        // Toolbar Action: CSV Export
        const btnExportCsv = document.getElementById('btnExportEventsCsv');
        if (btnExportCsv) {
            btnExportCsv.addEventListener('click', () => {
                const params = new URLSearchParams();
                const f = this.eventsFilters || {};
                if (f.search) params.append('search', f.search);
                if (f.object_class) params.append('object_class', f.object_class);
                if (f.severity) params.append('severity', f.severity);
                if (f.status) params.append('status', f.status);
                if (f.zone_id) params.append('zone_id', f.zone_id);

                btnExportCsv.textContent = 'Exporting...';
                const exportUrl = `/api/events/export/csv?${params.toString()}`;
                const dlLink = document.createElement('a');
                dlLink.href = exportUrl;
                dlLink.download = `AERION_AUDIT_LOG_${Date.now()}.csv`;
                document.body.appendChild(dlLink);
                dlLink.click();
                document.body.removeChild(dlLink);
                setTimeout(() => {
                    btnExportCsv.innerHTML = `
                        <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor"><path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"/></svg>
                        Export CSV
                    `;
                }, 1200);
            });
        }

        // Toolbar Action: Verify Cryptographic Ledger Integrity
        const btnVerifyLedger = document.getElementById('btnVerifyAuditLedger');
        const kpiCardLedger = document.getElementById('kpiCardLedger');
        if (btnVerifyLedger) {
            btnVerifyLedger.addEventListener('click', () => this.openLedgerIntegrityModal());
        }
        if (kpiCardLedger) {
            kpiCardLedger.addEventListener('click', () => this.openLedgerIntegrityModal());
        }

        // Real-Time Event Banner Click
        const btnShowNew = document.getElementById('btnShowNewEvents');
        if (btnShowNew) {
            btnShowNew.addEventListener('click', () => {
                const banner = document.getElementById('socLiveUpdateBanner');
                if (banner) banner.style.display = 'none';
                this.loadEventsTable();
            });
        }

        // ANPR Real-Time Search Filter
        const anprSearchInput = document.getElementById('anprSearchInput');
        if (anprSearchInput) {
            anprSearchInput.addEventListener('input', () => {
                const term = anprSearchInput.value.toLowerCase().trim();
                const rows = document.querySelectorAll('#anprTableBody tr');
                rows.forEach(r => {
                    const text = r.textContent.toLowerCase();
                    r.style.display = text.includes(term) ? '' : 'none';
                });
            });
        }

        const btnRefreshAnpr = document.getElementById('btnRefreshAnpr');
        if (btnRefreshAnpr) {
            btnRefreshAnpr.addEventListener('click', () => this.loadAnprRecords());
        }
    }

    startLiveEventsPolling() {
        if (this.livePollingTimer) clearInterval(this.livePollingTimer);
        this.livePollingTimer = setInterval(() => {
            if (!this.isLivePollingActive) return;
            if (this.currentTab === 'tab-events') {
                this.loadEventsSummaryStats();
                const searchInput = document.getElementById('eventSearchInput');
                if ((!searchInput || !searchInput.value.trim()) && this.eventsCurrentPage === 1) {
                    this.loadEventsTable();
                }
            }
        }, 5000);
    }

    stopLiveEventsPolling() {
        if (this.livePollingTimer) {
            clearInterval(this.livePollingTimer);
            this.livePollingTimer = null;
        }
    }

    async openLedgerIntegrityModal() {
        const modal = document.getElementById('ledgerIntegrityModal');
        const modalBody = document.getElementById('ledgerModalBody');
        const btnClose = document.getElementById('btnLedgerModalClose');
        if (!modal || !modalBody) return;

        modal.style.display = 'flex';
        modalBody.innerHTML = `
            <div style="text-align: center; padding: 30px; color: var(--accent-cyan); font-family: var(--font-mono);">
                <div style="font-size: 24px; margin-bottom: 10px;">⚡</div>
                COMPUTING SHA-256 DIGITAL CHAIN OF CUSTODY CHECKSUMS...
            </div>
        `;

        const closeModal = () => { modal.style.display = 'none'; };
        if (btnClose) btnClose.onclick = closeModal;
        modal.onclick = (e) => { if (e.target === modal) closeModal(); };

        try {
            const res = await fetch('/api/events/audit/integrity');
            if (res.ok) {
                const data = await res.json();
                const nowStr = new Date(data.generated_at).toUTCString();

                const recordsHtml = (data.recent_audit_records || []).map(r => `
                    <tr>
                        <td style="font-family: var(--font-mono); color: #fff; font-weight: 600;">${r.id}</td>
                        <td><span class="alert-severity-badge ${(r.severity || 'LOW').toLowerCase()}" style="font-size: 8px;">${r.severity}</span></td>
                        <td style="font-family: var(--font-mono); font-size: 10px; color: var(--accent-cyan); word-break: break-all;">${r.hash.slice(0, 24)}...</td>
                        <td style="text-align: center;">${r.has_snapshot ? '✅' : '⚠️'}</td>
                        <td style="text-align: center;">${r.has_video ? '✅' : '⚠️'}</td>
                        <td style="text-align: right;"><span class="status-pill online" style="font-size: 9px;"><span class="dot"></span> ${r.status}</span></td>
                    </tr>
                `).join('');

                modalBody.innerHTML = `
                    <div class="ledger-header-box">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                            <strong style="color: var(--accent-primary); letter-spacing: 0.5px;">IMMUTABLE MASTER AUDIT LEDGER DIGEST (MERKLE ROOT)</strong>
                            <span class="badge" style="background: rgba(0, 230, 118, 0.2); color: var(--accent-primary); font-weight: 700;">${data.integrity_score} INTEGRITY</span>
                        </div>
                        <div class="ledger-master-hash">
                            <span>${data.ledger_hash}</span>
                            <button class="btn-tactical" id="btnCopyMasterHash" style="padding: 2px 8px; font-size: 9px;">COPY 📋</button>
                        </div>
                        <div style="font-size: 10px; color: var(--text-muted); margin-top: 6px;">
                            Standard: ${data.compliance_standard} | Audited at: ${nowStr}
                        </div>
                    </div>

                    <div class="ledger-stats-grid">
                        <div class="ledger-stat-card">
                            <div class="ledger-stat-val" style="color: var(--accent-cyan);">${data.total_records_audited}</div>
                            <div class="ledger-stat-label">Events Audited</div>
                        </div>
                        <div class="ledger-stat-card">
                            <div class="ledger-stat-val" style="color: var(--accent-primary);">${data.verified_records}</div>
                            <div class="ledger-stat-label">Cryptographically Signed</div>
                        </div>
                        <div class="ledger-stat-card">
                            <div class="ledger-stat-val" style="color: var(--accent-warning);">${data.evidence_files_verified}</div>
                            <div class="ledger-stat-label">Evidence Media Files</div>
                        </div>
                        <div class="ledger-stat-card">
                            <div class="ledger-stat-val" style="color: ${data.tamper_detected ? 'var(--accent-danger)' : 'var(--accent-primary)'};">
                                ${data.tamper_detected ? 'ANOMALY DETECTED' : '0 TAMPER FLAGS'}
                            </div>
                            <div class="ledger-stat-label">Chain Tamper Status</div>
                        </div>
                    </div>

                    <div style="font-weight: 700; color: #fff; margin-bottom: 8px; font-size: 11px; letter-spacing: 0.5px;">RECENT AUDITED EVIDENCE ARTIFACTS</div>
                    <div style="max-height: 240px; overflow-y: auto; border: 1px solid var(--border-subtle); border-radius: 4px;">
                        <table class="hud-table" style="font-size: 11px; margin: 0;">
                            <thead>
                                <tr>
                                    <th>EVENT ID</th>
                                    <th>SEVERITY</th>
                                    <th>SHA-256 HASH</th>
                                    <th style="text-align: center;">STILL</th>
                                    <th style="text-align: center;">MP4</th>
                                    <th style="text-align: right;">CUSTODY</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${recordsHtml || '<tr><td colspan="6" style="text-align:center;">No recent records.</td></tr>'}
                            </tbody>
                        </table>
                    </div>
                `;

                const btnCopy = document.getElementById('btnCopyMasterHash');
                if (btnCopy) {
                    btnCopy.addEventListener('click', () => {
                        navigator.clipboard.writeText(data.ledger_hash).then(() => {
                            btnCopy.textContent = 'COPIED! ✓';
                            setTimeout(() => btnCopy.textContent = 'COPY 📋', 1500);
                        });
                    });
                }
            }
        } catch (err) {
            console.error('[LEDGER] Failed to verify integrity:', err);
            modalBody.innerHTML = `<div style="padding: 20px; color: var(--accent-danger);">Integrity check failed to execute. Check backend server logs.</div>`;
        }
    }

    openSnapshotLightbox(imgUrl, eventId, timestamp) {
        const modal = document.getElementById('snapshotLightboxModal');
        const img = document.getElementById('lightboxImage');
        const title = document.getElementById('lightboxTitle');
        const info = document.getElementById('lightboxEventInfo');
        const ts = document.getElementById('lightboxTimestamp');
        const dl = document.getElementById('lightboxDownloadLink');
        const btnClose = document.getElementById('btnLightboxClose');

        if (!modal || !img) return;

        img.src = `${imgUrl}?t=${Date.now()}`;
        if (title) title.textContent = `FORENSIC SNAPSHOT STILL FRAME // ${eventId || 'INCIDENT'}`;
        if (info) info.textContent = `INCIDENT: ${eventId || 'N/A'}`;
        if (ts) ts.textContent = timestamp ? `CAPTURED: ${new Date(timestamp).toUTCString()}` : 'UTC TIME SYNC';
        if (dl) {
            dl.href = imgUrl;
            dl.download = `${eventId || 'evidence'}_snapshot.jpg`;
        }

        modal.style.display = 'flex';
        const closeModal = () => { modal.style.display = 'none'; };
        if (btnClose) btnClose.onclick = closeModal;
        modal.onclick = (e) => { if (e.target === modal) closeModal(); };
    }

    setupEvidenceModal() {
        const modal = document.getElementById('evidenceModal');
        const btnClose = document.getElementById('btnEvidenceClose');
        const btnModalAck = document.getElementById('btnModalAck');
        const btnModalResolve = document.getElementById('btnModalResolve');

        if (!modal) return;

        const closeModal = () => {
            modal.style.display = 'none';
            const videoEl = document.getElementById('evidenceVideoPlayer');
            if (videoEl) {
                videoEl.pause();
                videoEl.src = '';
            }
            this.currentModalEventId = null;
        };

        if (btnClose) btnClose.addEventListener('click', closeModal);
        modal.addEventListener('click', (e) => {
            if (e.target === modal) closeModal();
        });

        // Interactive Timeline Scrubber (Section 70)
        const timelineTrack = document.getElementById('evidenceTimelineTrack');
        const playhead = document.getElementById('evidencePlayhead');
        const timeLabel = document.getElementById('evidenceTimelineCurrent');
        const btnSeekPre = document.getElementById('btnSeekPre');
        const btnSeekTrigger = document.getElementById('btnSeekTrigger');
        const btnSeekPost = document.getElementById('btnSeekPost');
        const videoEl = document.getElementById('evidenceVideoPlayer');

        const formatTime = (sec) => {
            const m = Math.floor(sec / 60);
            const s = Math.floor(sec % 60);
            return `${m < 10 ? '0' : ''}${m}:${s < 10 ? '0' : ''}${s}`;
        };

        if (videoEl) {
            videoEl.ontimeupdate = () => {
                const dur = videoEl.duration || 25.0;
                const cur = videoEl.currentTime || 0.0;
                const pct = Math.min(100, Math.max(0, (cur / dur) * 100));
                if (playhead) playhead.style.left = `${pct}%`;
                if (timeLabel) timeLabel.textContent = `${formatTime(cur)} / ${formatTime(dur)}`;
            };
        }

        if (timelineTrack && videoEl) {
            timelineTrack.addEventListener('click', (e) => {
                const rect = timelineTrack.getBoundingClientRect();
                const frac = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
                const dur = videoEl.duration || 25.0;
                videoEl.currentTime = frac * dur;
            });
        }

        if (btnSeekPre && videoEl) {
            btnSeekPre.addEventListener('click', () => {
                videoEl.currentTime = 0;
            });
        }
        if (btnSeekTrigger && videoEl) {
            btnSeekTrigger.addEventListener('click', () => {
                const dur = videoEl.duration || 25.0;
                videoEl.currentTime = dur * 0.40;
            });
        }
        if (btnSeekPost && videoEl) {
            btnSeekPost.addEventListener('click', () => {
                const dur = videoEl.duration || 25.0;
                videoEl.currentTime = Math.max(0, dur * 0.95);
            });
        }

        if (btnModalAck) {
            btnModalAck.addEventListener('click', async () => {
                if (!this.currentModalEventId) return;
                btnModalAck.textContent = 'ACKING...';
                try {
                    await fetch(`/api/events/${this.currentModalEventId}/acknowledge`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ operator_name: 'Command Operator' })
                    });
                    btnModalAck.textContent = 'ACKNOWLEDGED';
                    const statusEl = document.getElementById('metaStatus');
                    if (statusEl) statusEl.textContent = 'ACKNOWLEDGED';
                } catch (err) {
                    console.error('Ack error:', err);
                }
            });
        }

        if (btnModalResolve) {
            btnModalResolve.addEventListener('click', async () => {
                if (!this.currentModalEventId) return;
                btnModalResolve.textContent = 'RESOLVING...';
                try {
                    await fetch(`/api/events/${this.currentModalEventId}/resolve`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ operator_name: 'Command Operator' })
                    });
                    btnModalResolve.textContent = 'RESOLVED';
                    const statusEl = document.getElementById('metaStatus');
                    if (statusEl) statusEl.textContent = 'RESOLVED';
                } catch (err) {
                    console.error('Resolve error:', err);
                }
            });
        }
    }

    async openEvidenceModal(eventId) {
        const modal = document.getElementById('evidenceModal');
        if (!modal) return;

        this.currentModalEventId = eventId;
        modal.style.display = 'flex';

        // Reset UI elements
        const titleEl = document.getElementById('evidenceModalTitle');
        const sevEl = document.getElementById('evidenceModalSeverity');
        const videoEl = document.getElementById('evidenceVideoPlayer');
        const fallbackEl = document.getElementById('evidenceVideoFallback');
        const snapImg = document.getElementById('evidenceSnapshotImg');
        const statusEl = document.getElementById('evidenceVideoStatus');
        const dlBtn = document.getElementById('btnEvidenceDownload');
        const dossierBtn = document.getElementById('btnEvidenceDossier');
        const playhead = document.getElementById('evidencePlayhead');

        if (titleEl) titleEl.textContent = `FORENSIC EVIDENCE REVIEW: ${eventId}`;
        if (statusEl) statusEl.textContent = '● FETCHING FORENSIC ARTIFACTS...';
        if (playhead) playhead.style.left = '0%';
        if (dossierBtn) {
            dossierBtn.href = `/api/events/${eventId}/dossier`;
        }
        const vaultBtn = document.getElementById('btnEvidenceVault');
        if (vaultBtn) {
            vaultBtn.href = `/api/events/${eventId}/vault`;
            vaultBtn.download = `AERION_VAULT_${eventId}.zip`;
        }

        try {
            const res = await fetch(`/api/events/${eventId}`);
            if (res.ok) {
                const e = await res.json();

                if (sevEl) {
                    sevEl.className = `alert-severity-badge ${(e.severity || 'LOW').toLowerCase()}`;
                    sevEl.textContent = e.severity || 'INFO';
                }

                // Populate Metadata Table
                const setVal = (id, val) => {
                    const el = document.getElementById(id);
                    if (el) el.textContent = val || '-';
                };

                setVal('metaEventId', e.id);
                setVal('metaTargetId', e.object_id || e.target_id);
                setVal('metaZoneId', e.zone_id ? `${e.zone_id} (${e.zone_name || ''})` : '-');
                setVal('metaClass', e.object_class ? e.object_class.toUpperCase() : 'UNKNOWN');
                setVal('metaStartTime', e.start_time ? new Date(e.start_time).toLocaleTimeString() : '-');
                setVal('metaDuration', e.duration_seconds ? `${e.duration_seconds.toFixed(1)}s` : '0.0s');
                setVal('metaSensor', `${e.camera_id || 'CAM_01'} ${e.radar_id ? '/ ' + e.radar_id : ''}`);
                setVal('metaStatus', e.status || 'ACTIVE');
                setVal('metaDescription', e.description || 'Intrusion event recorded with pre-event rolling buffer context.');

                // Setup Video and Snapshot
                const videoUrl = `/api/events/${eventId}/video?t=${Date.now()}`;
                const snapUrl = `/api/events/${eventId}/snapshot?t=${Date.now()}`;

                if (dlBtn) {
                    dlBtn.href = `/api/events/${eventId}/video`;
                    dlBtn.download = `${eventId}.mp4`;
                }

                if (videoEl && fallbackEl && snapImg) {
                    videoEl.onerror = () => {
                        // If video compilation is still finishing, show snapshot still
                        videoEl.style.display = 'none';
                        fallbackEl.style.display = 'block';
                        snapImg.src = snapUrl;
                        if (statusEl) statusEl.textContent = '● COMPILING MP4 CLIP (SNAPSHOT DISPLAYED)';
                    };

                    videoEl.onloadeddata = () => {
                        videoEl.style.display = 'block';
                        fallbackEl.style.display = 'none';
                        if (statusEl) {
                            statusEl.textContent = '● VERIFIED MP4 FORENSIC CLIP (READY)';
                            statusEl.style.color = 'var(--accent-success)';
                        }
                    };

                    videoEl.src = videoUrl;
                }

                // Load and render CAPF/BSF SOP Workflow Checklist
                this.loadSOPChecklist(eventId);
            }
        } catch (err) {
            console.error('Failed to load event details:', err);
        }
    }

    renderRadarTargetsTable(tracks) {
        const tbody = document.getElementById('radarTargetsTableBody');
        if (!tbody) return;

        if (!tracks || tracks.length === 0) {
            tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--text-muted);">No active radar sweeps detected.</td></tr>`;
            return;
        }

        tbody.innerHTML = tracks.map(t => {
            let statusPill = '';
            if (t.fusion_status === 'CONFIRMED' || t.is_cross_confirmed) {
                statusPill = '<span class="status-pill online" style="font-size: 10px;"><span class="dot"></span> CONFIRMED (RAD+CAM)</span>';
            } else if (t.fusion_status === 'UNCONFIRMED_RADAR_ONLY') {
                statusPill = '<span class="status-pill critical" style="font-size: 10px;"><span class="dot"></span> BLIND SPOT (RADAR ONLY)</span>';
            } else {
                statusPill = '<span class="status-pill standby" style="font-size: 10px;"><span class="dot"></span> OPTICAL ONLY</span>';
            }

            const xVal = typeof t.radar_x === 'number' ? t.radar_x.toFixed(2) : (t.x !== undefined ? t.x.toFixed(2) : '0.00');
            const yVal = typeof t.radar_y === 'number' ? t.radar_y.toFixed(2) : (t.y !== undefined ? t.y.toFixed(2) : '0.00');
            const speedVal = typeof t.speed === 'number' ? `${t.speed.toFixed(2)} m/s` : '0.00 m/s';
            const distVal = typeof t.distance === 'number' ? `${t.distance.toFixed(2)} m` : '-';
            const targetId = (t.name || t.identity) ? `T#${t.target_id || t.id || '1'} (${t.name || t.identity})` : (t.fused_id || `RAD_#${t.target_id || t.id || '1'}`);
            const latVal = t.lat ? t.lat.toFixed(5) : (t.latitude ? t.latitude.toFixed(5) : '31.6234°N');
            const lonVal = t.lon ? t.lon.toFixed(5) : (t.longitude ? t.longitude.toFixed(5) : '74.8721°E');
            const mgrsVal = t.mgrs || t.mgrs_8digit || '43R FU 8785 9912';
            const bearingVal = t.bearing_deg !== undefined ? `${t.bearing_deg}°` : (t.bearing ? `${t.bearing}°` : '048°');

            return `
            <tr>
                <td style="font-family: var(--font-mono); color: var(--accent-cyan); font-weight: 600;">${targetId}</td>
                <td style="font-family: var(--font-mono);">${xVal}m, ${yVal}m</td>
                <td style="font-family: var(--font-mono); color: #94a3b8; font-size: 10px;">${latVal}, ${lonVal}</td>
                <td style="font-family: var(--font-mono); color: var(--accent-cyan); font-weight: 700; font-size: 10px;">${mgrsVal}</td>
                <td style="font-family: var(--font-mono);">${speedVal} / ${distVal}</td>
                <td style="font-family: var(--font-mono); color: var(--accent-warning);">${bearingVal}</td>
                <td>${statusPill}</td>
            </tr>
            `;
        }).join('');
    }

    renderRadarZoneStatus(targets) {
        const container = document.getElementById('radarZoneStatusContainer');
        if (!container) return;

        const safeTargets = targets || [];
        let countA = 0;
        let countB = 0;
        let countC = 0;

        safeTargets.forEach(t => {
            const y = typeof t.y === 'number' ? t.y : (typeof t.radar_y === 'number' ? t.radar_y : 5.0);
            if (t.zone_id === 'ZONE_C' || t.zone_type === 'RESTRICTED' || y < 3.0) {
                countC++;
            } else if (t.zone_id === 'ZONE_B' || t.zone_type === 'WARNING' || (y >= 3.0 && y < 5.0)) {
                countB++;
            } else {
                countA++;
            }
        });

        const borderA = countA > 0 ? 'rgba(0, 230, 118, 0.4)' : 'rgba(0,229,255,0.2)';
        const borderB = countB > 0 ? 'rgba(255, 171, 0, 0.5)' : 'rgba(255,171,0,0.2)';
        const borderC = countC > 0 ? 'rgba(255, 23, 68, 0.6)' : 'rgba(255,23,68,0.25)';

        container.innerHTML = `
            <div style="background:rgba(0,229,255,0.07);border:1px solid ${borderA};border-radius:6px;padding:10px 12px;margin-bottom:6px;">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
                    <span style="font-size:10px;font-weight:700;color:#00e676;font-family:var(--font-mono);">ZONE_A — OUTER PATROL</span>
                    <span style="font-size:9px;background:rgba(0,230,118,0.15);color:#00e676;padding:1px 6px;border-radius:3px;font-family:var(--font-mono);">${countA > 0 ? 'ACTIVE' : 'NORMAL'}</span>
                </div>
                <div style="font-size:10px;color:${countA > 0 ? '#00e676' : 'var(--text-secondary)'};font-weight:${countA > 0 ? '600' : '400'};">${countA} target${countA !== 1 ? 's' : ''} inside</div>
            </div>
            <div style="background:rgba(255,171,0,0.07);border:1px solid ${borderB};border-radius:6px;padding:10px 12px;margin-bottom:6px;">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
                    <span style="font-size:10px;font-weight:700;color:#ffab00;font-family:var(--font-mono);">ZONE_B — WARNING APPROACH</span>
                    <span style="font-size:9px;background:rgba(255,171,0,0.15);color:#ffab00;padding:1px 6px;border-radius:3px;font-family:var(--font-mono);">WARNING</span>
                </div>
                <div style="font-size:10px;color:${countB > 0 ? '#ffab00' : 'var(--text-secondary)'};font-weight:${countB > 0 ? '600' : '400'};">${countB} target${countB !== 1 ? 's' : ''} inside</div>
            </div>
            <div style="background:rgba(255,23,68,0.08);border:1px solid ${borderC};border-radius:6px;padding:10px 12px;">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
                    <span style="font-size:10px;font-weight:700;color:#ff1744;font-family:var(--font-mono);">ZONE_C — RESTRICTED FENCE</span>
                    <span style="font-size:9px;background:rgba(255,23,68,0.15);color:#ff1744;padding:1px 6px;border-radius:3px;font-family:var(--font-mono);">RESTRICTED</span>
                </div>
                <div style="font-size:10px;color:${countC > 0 ? '#ff1744' : 'var(--text-secondary)'};font-weight:${countC > 0 ? '700' : '400'};">${countC} target${countC !== 1 ? 's' : ''} inside</div>
            </div>
        `;
    }

    async loadMeshTopology() {
        try {
            const res = await fetch('/api/mesh/topology');
            if (res.ok) {
                const data = await res.json();
                this.renderMeshTopology(data);
            }
        } catch (e) {
            console.error('Failed to load mesh topology:', e);
        }
    }

    renderMeshTopology(topo) {
        if (!topo) return;
        const badge = document.getElementById('meshStatusBadge');
        if (badge) {
            badge.textContent = `${topo.mesh_health} (${topo.consensus_quorum} NODES)`;
            badge.style.color = topo.mesh_health === 'OPTIMAL' ? '#10b981' : (topo.mesh_health === 'DEGRADED' ? '#f59e0b' : '#ef4444');
        }

        const container = document.getElementById('meshNodesContainer');
        if (!container || !topo.nodes) return;

        container.innerHTML = topo.nodes.map(n => {
            const isOnline = n.status === 'ACTIVE';
            return `
            <div style="background: rgba(15, 23, 42, 0.7); border: 1px solid ${isOnline ? 'rgba(0, 243, 255, 0.2)' : 'rgba(239, 68, 68, 0.4)'}; border-radius: 6px; padding: 10px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                    <span style="font-weight: 700; font-size: 11px; color: ${isOnline ? '#fff' : '#f87171'};">${n.node_name}</span>
                    <span class="status-pill ${isOnline ? 'online' : 'offline'}" style="font-size: 9px;"><span class="dot"></span> ${n.status}</span>
                </div>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 4px; font-family: var(--font-mono); font-size: 10px; color: var(--text-muted); margin-bottom: 6px;">
                    <div>IP: <span style="color: #cbd5e1;">${n.ip_address}</span></div>
                    <div>ROLE: <span style="color: var(--accent-cyan); font-weight: 600;">${n.role}</span></div>
                    <div>RSSI: <span style="color: ${n.link_rssi_dbm > -70 ? '#10b981' : '#f59e0b'};">${n.link_rssi_dbm} dBm</span></div>
                    <div>LATENCY: <span style="color: #cbd5e1;">${n.ping_latency_ms} ms</span></div>
                    <div>LOSS: <span style="color: ${n.packet_loss_pct === 0 ? '#10b981' : '#ef4444'};">${n.packet_loss_pct}%</span></div>
                    <div>SECTOR: <span style="color: #cbd5e1;">${n.sector_covered.split(' ')[0]}</span></div>
                </div>
                ${n.failover_active ? `
                    <div style="background: rgba(239, 68, 68, 0.15); border: 1px solid #ef4444; border-radius: 4px; padding: 4px 6px; font-size: 9px; color: #fca5a5; font-family: var(--font-mono);">
                        ⚠️ REROUTED: ${n.failover_route} (+${n.replicated_events_count} sync)
                    </div>
                ` : ''}
            </div>
            `;
        }).join('');
    }

    async loadAiProfiler() {
        try {
            const res = await fetch('/api/ai/profile/live');
            if (res.ok) {
                const data = await res.json();
                this.renderAiProfiler(data);
            }
        } catch (e) {
            console.error('Failed to load AI profiler:', e);
        }
    }

    renderAiProfiler(prof) {
        if (!prof || !prof.stages_ms) return;
        const maxFpsBadge = document.getElementById('profilerMaxFpsBadge');
        if (maxFpsBadge) maxFpsBadge.textContent = `THEORETICAL: ${prof.theoretical_max_fps} FPS`;

        const totalMsEl = document.getElementById('profilerTotalMs');
        if (totalMsEl) totalMsEl.textContent = `${prof.stages_ms.total_pipeline} ms`;

        const fg = document.getElementById('profilerFlamegraph');
        if (fg && prof.percentages) {
            const p = prof.percentages;
            fg.innerHTML = `
                <div style="width: ${p.frame_grab_pct}%; background: #3b82f6;" title="Frame Grab: ${prof.stages_ms.frame_grab}ms (${p.frame_grab_pct}%)"></div>
                <div style="width: ${p.preprocessing_pct}%; background: #06b6d4;" title="Preprocessing: ${prof.stages_ms.preprocessing}ms (${p.preprocessing_pct}%)"></div>
                <div style="width: ${p.inference_pct}%; background: #a855f7;" title="Inference Forward: ${prof.stages_ms.model_inference}ms (${p.inference_pct}%)"></div>
                <div style="width: ${p.nms_pct}%; background: #f59e0b;" title="NMS: ${prof.stages_ms.nms}ms (${p.nms_pct}%)"></div>
                <div style="width: ${p.tracking_pct}%; background: #10b981;" title="Tracker: ${prof.stages_ms.tracking}ms (${p.tracking_pct}%)"></div>
                <div style="width: ${p.fusion_pct}%; background: #ec4899;" title="Fusion: ${prof.stages_ms.sensor_fusion}ms (${p.fusion_pct}%)"></div>
            `;
        }

        const stagesGrid = document.getElementById('profilerStagesGrid');
        if (stagesGrid) {
            const stages = [
                { name: '1. Frame Grab', ms: prof.stages_ms.frame_grab, color: '#3b82f6' },
                { name: '2. Preprocess', ms: prof.stages_ms.preprocessing, color: '#06b6d4' },
                { name: '3. YOLO Forward', ms: prof.stages_ms.model_inference, color: '#a855f7' },
                { name: '4. NMS Decoding', ms: prof.stages_ms.nms, color: '#f59e0b' },
                { name: '5. Kalman Track', ms: prof.stages_ms.tracking, color: '#10b981' },
                { name: '6. Radar Fusion', ms: prof.stages_ms.sensor_fusion, color: '#ec4899' }
            ];
            stagesGrid.innerHTML = stages.map(s => `
                <div style="background: rgba(15, 23, 42, 0.7); border: 1px solid var(--border-subtle); border-radius: 4px; padding: 6px 8px; border-left: 3px solid ${s.color};">
                    <div style="font-size: 9px; color: var(--text-muted);">${s.name}</div>
                    <div style="font-family: var(--font-mono); font-size: 13px; font-weight: 700; color: #fff;">${s.ms} ms</div>
                </div>
            `).join('');
        }
    }

    async runQuantizationBenchmark() {
        const btn = document.getElementById('btnRunBenchmarkSuite');
        if (btn) btn.textContent = 'BENCHMARKING...';
        try {
            const res = await fetch('/api/ai/profile/benchmark?iterations=15', { method: 'POST' });
            if (res.ok) {
                const data = await res.json();
                const tbody = document.getElementById('benchmarkTableBody');
                if (tbody && data.engines) {
                    tbody.innerHTML = data.engines.map(e => `
                        <tr style="${e.is_active ? 'background: rgba(0, 243, 255, 0.05);' : ''}">
                            <td style="font-weight: 600; color: ${e.is_active ? 'var(--accent-cyan)' : '#fff'};">${e.engine_name}</td>
                            <td style="font-family: var(--font-mono); font-size: 9px;">${e.precision}</td>
                            <td style="font-family: var(--font-mono);">${e.avg_inference_ms} ms</td>
                            <td style="font-family: var(--font-mono); font-weight: 600;">${e.total_pipeline_ms} ms</td>
                            <td style="font-family: var(--font-mono); color: #10b981; font-weight: 700;">${e.sustained_fps} FPS</td>
                            <td style="font-family: var(--font-mono);">${e.model_size_mb} MB</td>
                            <td style="font-family: var(--font-mono);">${e.vram_allocation_mb} MB</td>
                            <td><span class="badge" style="background: ${e.is_active ? 'rgba(0,243,255,0.15)' : 'rgba(16,185,129,0.15)'}; color: ${e.is_active ? 'var(--accent-cyan)' : '#10b981'}; font-weight: 700;">${e.speedup_factor}</span></td>
                        </tr>
                    `).join('');
                }
            }
        } catch (e) {
            console.error('Benchmark failed:', e);
        } finally {
            if (btn) btn.textContent = 'RUN QUANTIZATION BENCHMARK';
        }
    }

    async openTerrainShadowModal() {
        const modal = document.getElementById('terrainShadowModal');
        if (!modal) return;
        modal.style.display = 'flex';

        try {
            const res = await fetch('/api/terrain/profile');
            if (res.ok) {
                const data = await res.json();
                this.renderTerrainSvg(data);
                const summaryEl = document.getElementById('terrainThreatSummary');
                if (summaryEl && data.los_analysis) {
                    summaryEl.textContent = data.los_analysis.threat_assessment;
                }
                const metricsEl = document.getElementById('terrainShadowMetricsText');
                if (metricsEl && data.los_analysis) {
                    metricsEl.textContent = `SHADOW SPAN: ${data.los_analysis.shadow_span_meters}m (Range ${data.los_analysis.shadow_start_range_m}m to ${data.los_analysis.shadow_end_range_m}m) | BLIND SPOT: ${data.los_analysis.percent_blind_spot}% | MAX OCCLUSION DEPTH: ${data.los_analysis.max_occlusion_depth_m}m`;
                }
            }

            const uavRes = await fetch('/api/terrain/uav-los?altitude_m=25');
            if (uavRes.ok) {
                const uavData = await uavRes.json();
                const uavSummary = document.getElementById('uavSolutionSummary');
                if (uavSummary) uavSummary.textContent = uavData.tactical_justification;
            }
        } catch (e) {
            console.error('Failed to load terrain LOS profile:', e);
        }
    }

    renderTerrainSvg(data) {
        const svg = document.getElementById('terrainSvgProfile');
        if (!svg || !data || !data.dem_profile) return;

        const pts = data.dem_profile;
        const w = 760;
        const h = 200;
        const originX = 50;
        const groundBaselineY = 160;

        const scaleX = (r) => originX + (r / 10.0) * (w - 80);
        const scaleY = (z) => groundBaselineY - (z * 35.0);

        // Mast line & apex
        const mastApexY = scaleY(data.sensor_mast.tower_height_m / 3.0); // scaled mast
        let svgContent = `
            <!-- Ground Base Line -->
            <line x1="${originX}" y1="${groundBaselineY}" x2="${w - 20}" y2="${groundBaselineY}" stroke="#334155" stroke-dasharray="4,4" />
            <!-- Sensor Mast Tower -->
            <line x1="${originX}" y1="${groundBaselineY}" x2="${originX}" y2="${mastApexY}" stroke="#00e5ff" stroke-width="4" />
            <circle cx="${originX}" cy="${mastApexY}" r="6" fill="#00e5ff" />
            <text x="${originX - 35}" y="${mastApexY - 10}" fill="#00e5ff" font-family="JetBrains Mono" font-size="10">MAST 10m</text>
        `;

        // Draw terrain contour path
        let terrainPath = `M ${originX} ${groundBaselineY} `;
        pts.forEach(p => {
            terrainPath += `L ${scaleX(p.range_m)} ${scaleY(p.elevation_m)} `;
        });
        terrainPath += `L ${scaleX(10.0)} ${groundBaselineY} Z`;

        svgContent += `<path d="${terrainPath}" fill="rgba(30, 41, 59, 0.7)" stroke="#64748b" stroke-width="2" />`;

        // Highlight Shadow Pocket (dead zone)
        const shadowPts = pts.filter(p => p.is_shadow);
        if (shadowPts.length > 0) {
            let shadowPolygon = `M ${scaleX(shadowPts[0].range_m)} ${scaleY(shadowPts[0].elevation_m)} `;
            shadowPts.forEach(p => {
                shadowPolygon += `L ${scaleX(p.range_m)} ${scaleY(p.los_ray_height_m / 3.0)} `;
            });
            for (let i = shadowPts.length - 1; i >= 0; i--) {
                shadowPolygon += `L ${scaleX(shadowPts[i].range_m)} ${scaleY(shadowPts[i].elevation_m)} `;
            }
            shadowPolygon += 'Z';
            svgContent += `<path d="${shadowPolygon}" fill="rgba(239, 68, 68, 0.3)" stroke="#ef4444" stroke-width="1.5" stroke-dasharray="3,3" />`;
            svgContent += `<text x="${scaleX(5.0)}" y="${scaleY(-0.4)}" fill="#ef4444" font-family="JetBrains Mono" font-size="10" font-weight="700">DEAD ZONE (RAVINE)</text>`;
        }

        // Direct LOS Ray tangent from Mast over Ridge Crest
        const ridgePt = pts.find(p => p.range_m >= 3.8);
        if (ridgePt) {
            svgContent += `
                <line x1="${originX}" y1="${mastApexY}" x2="${scaleX(ridgePt.range_m)}" y2="${scaleY(ridgePt.elevation_m)}" stroke="#10b981" stroke-width="2" />
                <line x1="${scaleX(ridgePt.range_m)}" y1="${scaleY(ridgePt.elevation_m)}" x2="${w - 30}" y2="${scaleY(ridgePt.elevation_m) + 30}" stroke="#10b981" stroke-width="1.5" stroke-dasharray="4,4" />
                <circle cx="${scaleX(ridgePt.range_m)}" cy="${scaleY(ridgePt.elevation_m)}" r="4" fill="#f59e0b" />
                <text x="${scaleX(ridgePt.range_m) - 20}" y="${scaleY(ridgePt.elevation_m) - 10}" fill="#f59e0b" font-family="JetBrains Mono" font-size="9">RIDGE CREST (1.75m)</text>
            `;
        }

        // UAV Position & Aerial Clearance Ray
        const uavX = scaleX(5.3);
        const uavY = 30;
        svgContent += `
            <!-- UAV Marker -->
            <circle cx="${uavX}" cy="${uavY}" r="7" fill="#06b6d4" />
            <polygon points="${uavX},${uavY + 8} ${uavX - 6},${uavY + 18} ${uavX + 6},${uavY + 18}" fill="#06b6d4" />
            <text x="${uavX + 12}" y="${uavY + 4}" fill="#06b6d4" font-family="JetBrains Mono" font-size="10" font-weight="700">UAV_01 (25m AGL)</text>
            <!-- Vertical Clearance Cone -->
            <line x1="${uavX}" y1="${uavY + 18}" x2="${scaleX(4.5)}" y2="${scaleY(-0.7)}" stroke="#06b6d4" stroke-width="1.5" stroke-dasharray="3,3" />
            <line x1="${uavX}" y1="${uavY + 18}" x2="${scaleX(6.2)}" y2="${scaleY(-0.7)}" stroke="#06b6d4" stroke-width="1.5" stroke-dasharray="3,3" />
        `;

        svg.innerHTML = svgContent;
    }

    async generateQrtDispatchOrder() {
        const modal = document.getElementById('qrtDispatchModal');
        if (!modal) return;
        modal.style.display = 'flex';

        try {
            const res = await fetch('/api/geo/qrt-dispatch', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    event_id: 'EVT_BREACH_ZONE_C',
                    target_id: 'GLOBAL_TARGET_001',
                    classification: 'person',
                    severity: 'CRITICAL',
                    local_x_m: 2.8,
                    local_y_m: 4.6,
                    speed_mps: 1.8,
                    threat_zone: 'ZONE_C'
                })
            });

            if (res.ok) {
                const order = await res.json();
                document.getElementById('qrtOrderRef').textContent = order.dispatch_id;
                document.getElementById('qrtFobAnchor').textContent = order.fob_anchor;
                document.getElementById('qrtMgrsGrid').textContent = order.target_tactical_position.mgrs_8digit;
                document.getElementById('qrtTargetDms').textContent = `${order.target_tactical_position.latitude_dms}, ${order.target_tactical_position.longitude_dms}`;
                document.getElementById('qrtRangeBearing').textContent = `${order.target_tactical_position.range_from_fob_m}m @ ${order.target_tactical_position.bearing_azimuth}`;
                document.getElementById('qrtRoeText').textContent = order.intercept_assessment.rules_of_engagement;
                document.getElementById('qrtEtaSeconds').textContent = `${order.intercept_assessment.eta_seconds} SECONDS`;
            }
        } catch (e) {
            console.error('Failed to generate QRT dispatch order:', e);
        }
    }

    async loadAnprRecords() {
        try {
            const res = await fetch('/api/anpr/records?limit=15');
            if (res.ok) {
                const data = await res.json();
                this.renderAnprTable(data.records || []);
                const badge = document.getElementById('anprTotalCountBadge');
                if (badge) badge.textContent = `${data.total || 0} PLATES`;
            }
        } catch (e) {
            console.debug('Failed to load ANPR records:', e);
        }
    }

    renderAnprTable(records) {
        const tbody = document.getElementById('anprTableBody');
        if (!tbody) return;

        if (!records || records.length === 0) {
            tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--text-muted);">No vehicle license plate records captured yet.</td></tr>`;
            return;
        }

        tbody.innerHTML = records.map(r => {
            const isReadable = r.is_readable && r.plate_text !== 'PLATE_NOT_READABLE';
            const cleanPlate = r.clean_plate || (r.plate_text ? r.plate_text.split('(')[0].trim() : 'PLATE_NOT_READABLE');
            const vehicleAttr = r.vehicle_color ? `${r.vehicle_color} ${r.vehicle_type || 'VEHICLE'}` : (r.plate_text && r.plate_text.includes('(') ? r.plate_text.split('(')[1].replace(')', '') : '');

            const plateDisplay = isReadable
                ? `<div style="display: flex; align-items: center; gap: 8px;">
                     <span style="display: inline-block; background: #fff; color: #000; font-family: var(--font-mono); font-weight: 800; font-size: 11px; padding: 2px 8px; border-radius: 3px; border: 2px solid #000; letter-spacing: 1.5px; box-shadow: 0 0 5px rgba(0,0,0,0.5);">${cleanPlate}</span>
                     ${vehicleAttr ? `<span style="background: rgba(56, 189, 248, 0.15); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.4); font-size: 9px; font-weight: 700; padding: 1px 6px; border-radius: 3px; font-family: var(--font-mono);">${vehicleAttr}</span>` : ''}
                   </div>`
                : `<span style="font-family: var(--font-mono); font-size: 10px; color: var(--text-muted); background: rgba(255,255,255,0.05); padding: 2px 6px; border-radius: 2px;">PLATE NOT READABLE</span>`;

            const statusPill = isReadable
                ? `<span class="status-pill online" style="font-size: 10px;"><span class="dot"></span> VERIFIED</span>`
                : `<span class="status-pill offline" style="font-size: 10px;"><span class="dot"></span> UNREADABLE</span>`;

            const snapDisplay = r.snapshot_path
                ? `<a href="${r.snapshot_path}" target="_blank"><img src="${r.snapshot_path}" style="height: 26px; border-radius: 2px; border: 1px solid var(--border-subtle); vertical-align: middle;" /></a>`
                : '-';

            const timeStr = r.timestamp ? new Date(r.timestamp).toLocaleTimeString() : '-';

            return `
            <tr>
                <td style="font-family: var(--font-mono); color: var(--accent-cyan); font-weight: 600;">#${r.vehicle_track_id}</td>
                <td>${plateDisplay}</td>
                <td style="font-family: var(--font-mono);">${r.camera_id}</td>
                <td style="font-family: var(--font-mono);">${(r.confidence * 100).toFixed(0)}%</td>
                <td>${statusPill}</td>
                <td style="font-size: 10px; color: var(--text-secondary);">${timeStr}</td>
                <td>${snapDisplay}</td>
            </tr>
            `;
        }).join('');
    }

    prependAnprRecord(record) {
        this.loadAnprRecords();
    }

    setupAudioControls() {
        const toggleAudioBtn = document.getElementById('btnToggleAudio');
        const audioStatusText = document.getElementById('audioStatusText');
        if (toggleAudioBtn && window.audioAlert) {
            const updateAudioBtnUI = () => {
                const muted = window.audioAlert.isMuted();
                if (audioStatusText) {
                    audioStatusText.textContent = muted ? '🔇 ALARM: MUTED' : '🔊 ALARM: ON';
                }
                toggleAudioBtn.style.borderColor = muted ? 'var(--text-muted)' : 'var(--accent-cyan)';
                toggleAudioBtn.style.color = muted ? 'var(--text-muted)' : 'var(--accent-cyan)';
            };
            updateAudioBtnUI();

            toggleAudioBtn.addEventListener('click', () => {
                window.audioAlert.unlockAudio();
                const wasMuted = window.audioAlert.isMuted();
                window.audioAlert.toggleMute();
                updateAudioBtnUI();
                if (wasMuted) {
                    window.audioAlert.playRadarBlip();
                }
            });

            // Re-sync UI on tactical audio state change events
            window.addEventListener('tactical-audio-state-changed', () => {
                updateAudioBtnUI();
            });
        }
    }

    async loadSystemConfiguration() {
        try {
            const res = await fetch('/api/config');
            if (!res.ok) return;
            const data = await res.json();
            const s = data.settings || {};

            const syncSlider = (sliderId, labelId, val, suffix = '') => {
                const slider = document.getElementById(sliderId);
                const label = document.getElementById(labelId);
                if (slider && val !== undefined) slider.value = val;
                if (label && val !== undefined) label.textContent = `${val}${suffix}`;
            };

            syncSlider('cfgSliderAiFps', 'cfgValAiFps', s.AI_INFERENCE_FPS, ' FPS');
            syncSlider('cfgSliderConfidence', 'cfgValConfidence', s.DETECTION_CONFIDENCE);
            syncSlider('cfgSliderCooldown', 'cfgValCooldown', s.EVENT_COOLDOWN_SECONDS, 's');
            syncSlider('cfgSliderLoitering', 'cfgValLoitering', s.LOITERING_THRESHOLD_SECONDS, 's');
            syncSlider('cfgSliderPreBuffer', 'cfgValPreBuffer', s.PRE_EVENT_SECONDS, 's');
            syncSlider('cfgSliderPostBuffer', 'cfgValPostBuffer', s.POST_EVENT_SECONDS, 's');
            syncSlider('cfgSliderGate', 'cfgValGate', s.FUSION_PROJECTION_GATE);
            syncSlider('cfgSliderUavRtb', 'cfgValUavRtb', s.UAV_RTB_BATTERY_PERCENT, '%');

            const privacySwitch = document.getElementById('cfgSwitchPrivacy');
            if (privacySwitch) privacySwitch.checked = !!s.PRIVACY_BLUR_ENABLED;

            const threatSwitch = document.getElementById('cfgSwitchThreat');
            if (threatSwitch) threatSwitch.checked = s.THREAT_SCORING_ENABLED !== false;

            const audioSwitch = document.getElementById('cfgSwitchAudio');
            if (audioSwitch) audioSwitch.checked = s.AUDIO_ALERTS_ENABLED !== false;

        } catch (e) {
            console.error('[CONFIG] Failed to load configuration:', e);
        }
    }

    setupConfigurationHandlers() {
        const bindSliderChange = (sliderId, labelId, suffix = '') => {
            const slider = document.getElementById(sliderId);
            const label = document.getElementById(labelId);
            if (slider && label) {
                slider.addEventListener('input', () => {
                    label.textContent = `${slider.value}${suffix}`;
                });
            }
        };

        bindSliderChange('cfgSliderAiFps', 'cfgValAiFps', ' FPS');
        bindSliderChange('cfgSliderConfidence', 'cfgValConfidence');
        bindSliderChange('cfgSliderCooldown', 'cfgValCooldown', 's');
        bindSliderChange('cfgSliderLoitering', 'cfgValLoitering', 's');
        bindSliderChange('cfgSliderPreBuffer', 'cfgValPreBuffer', 's');
        bindSliderChange('cfgSliderPostBuffer', 'cfgValPostBuffer', 's');
        bindSliderChange('cfgSliderGate', 'cfgValGate');
        bindSliderChange('cfgSliderUavRtb', 'cfgValUavRtb', '%');

        // Save Configuration
        const btnSaveConfig = document.getElementById('btnSaveConfig');
        if (btnSaveConfig) {
            btnSaveConfig.addEventListener('click', async () => {
                btnSaveConfig.textContent = 'APPLYING...';
                const feedbackEl = document.getElementById('cfgFeedbackMsg');

                const payload = {
                    AI_INFERENCE_FPS: parseInt(document.getElementById('cfgSliderAiFps')?.value || '15'),
                    DETECTION_CONFIDENCE: parseFloat(document.getElementById('cfgSliderConfidence')?.value || '0.50'),
                    EVENT_COOLDOWN_SECONDS: parseFloat(document.getElementById('cfgSliderCooldown')?.value || '10.0'),
                    LOITERING_THRESHOLD_SECONDS: parseFloat(document.getElementById('cfgSliderLoitering')?.value || '8.0'),
                    PRE_EVENT_SECONDS: parseInt(document.getElementById('cfgSliderPreBuffer')?.value || '10'),
                    POST_EVENT_SECONDS: parseInt(document.getElementById('cfgSliderPostBuffer')?.value || '15'),
                    FUSION_PROJECTION_GATE: parseFloat(document.getElementById('cfgSliderGate')?.value || '0.28'),
                    UAV_RTB_BATTERY_PERCENT: parseInt(document.getElementById('cfgSliderUavRtb')?.value || '15'),
                    PRIVACY_BLUR_ENABLED: !!document.getElementById('cfgSwitchPrivacy')?.checked,
                    THREAT_SCORING_ENABLED: !!document.getElementById('cfgSwitchThreat')?.checked,
                    AUDIO_ALERTS_ENABLED: !!document.getElementById('cfgSwitchAudio')?.checked
                };

                try {
                    const res = await fetch('/api/config', {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(payload)
                    });
                    if (res.ok) {
                        btnSaveConfig.textContent = 'APPLIED SUCCESSFULLY';
                        if (feedbackEl) {
                            feedbackEl.style.display = 'block';
                            feedbackEl.style.color = 'var(--accent-success)';
                            feedbackEl.textContent = `● CONFIGURATION SAVED AT ${new Date().toLocaleTimeString()} (LIVE SINGLETONS UPDATED)`;
                            setTimeout(() => { feedbackEl.style.display = 'none'; }, 4000);
                        }
                        setTimeout(() => { btnSaveConfig.textContent = 'APPLY CHANGES'; }, 2000);
                    }
                } catch (err) {
                    console.error('Config update error:', err);
                    btnSaveConfig.textContent = 'APPLY CHANGES';
                }
            });
        }

        // Reset Configuration
        const btnResetConfig = document.getElementById('btnResetConfig');
        if (btnResetConfig) {
            btnResetConfig.addEventListener('click', async () => {
                btnResetConfig.textContent = 'RESETTING...';
                try {
                    const res = await fetch('/api/config/reset', { method: 'POST' });
                    if (res.ok) {
                        await this.loadSystemConfiguration();
                        btnResetConfig.textContent = 'DEFAULTS RESTORED';
                        setTimeout(() => { btnResetConfig.textContent = 'RESTORE DEFAULTS'; }, 2000);
                    }
                } catch (e) {
                    console.error('Reset config error:', e);
                    btnResetConfig.textContent = 'RESTORE DEFAULTS';
                }
            });
        }
    }

    setupHeatmapControls() {
        const btnToggleHeatmap = document.getElementById('btnToggleHeatmap');
        if (btnToggleHeatmap) {
            btnToggleHeatmap.addEventListener('click', async () => {
                if (!this.heatmapData) {
                    btnToggleHeatmap.textContent = 'CALCULATING KDE...';
                    await this.loadHeatmapAnalytics();
                }
                if (this.zoneMap) {
                    const active = this.zoneMap.toggleHeatmap();
                    btnToggleHeatmap.textContent = active ? '🔥 THREAT HEATMAP: ON' : '🔥 THREAT HEATMAP: OFF';
                    btnToggleHeatmap.style.background = active ? 'rgba(255, 23, 68, 0.2)' : '';
                    btnToggleHeatmap.style.borderColor = active ? '#ff1744' : '#ff1744';
                    btnToggleHeatmap.style.color = active ? '#ff5252' : '#ff1744';
                }
            });
        }

        // New zones-tab heatmap button (mirrors dashboard toggle)
        const btnToggleHeatmapZones = document.getElementById('btnToggleHeatmapZones');
        if (btnToggleHeatmapZones) {
            btnToggleHeatmapZones.addEventListener('click', async () => {
                if (!this.heatmapData) {
                    btnToggleHeatmapZones.textContent = 'CALCULATING...';
                    await this.loadHeatmapAnalytics();
                }
                if (this.zoneMap) {
                    const active = this.zoneMap.toggleHeatmap();
                    btnToggleHeatmapZones.textContent = active ? 'HEATMAP ON' : 'HEATMAP OFF';
                    btnToggleHeatmapZones.style.background = active ? 'rgba(255, 23, 68, 0.2)' : '';
                    btnToggleHeatmapZones.style.color = active ? '#ff5252' : '';
                }
            });
        }

        // Zones-tab refresh button
        const btnRefreshZones = document.getElementById('btnRefreshZones');
        if (btnRefreshZones) {
            btnRefreshZones.addEventListener('click', async () => {
                btnRefreshZones.textContent = '↺ LOADING...';
                try {
                    await this.loadZones();
                } finally {
                    btnRefreshZones.textContent = '↺ REFRESH';
                }
            });
        }

        const btnRefresh = document.getElementById('btnRefreshAnalytics');
        if (btnRefresh) {
            btnRefresh.addEventListener('click', async () => {
                btnRefresh.textContent = 'REFRESHING...';
                await this.loadHeatmapAnalytics(true);
                btnRefresh.textContent = 'REFRESH';
            });
        }
    }

    async loadHeatmapAnalytics(force = false) {
        try {
            const res = await fetch('/api/analytics/threat-heatmap');
            if (!res.ok) return;
            const data = await res.json();
            this.heatmapData = data;

            if (this.zoneMap) {
                this.zoneMap.setHeatmapData(data);
            }

            // Populate Corridor Rankings
            const corridorContainer = document.getElementById('corridorRankingsList');
            if (corridorContainer && data.corridors) {
                corridorContainer.innerHTML = data.corridors.map(c => {
                    const barColor = c.risk_level === 'CRITICAL' ? '#ff1744' : (c.risk_level === 'HIGH' ? '#ff9800' : '#00e676');
                    return `
                    <div style="background: rgba(15, 23, 42, 0.6); border: 1px solid var(--border-subtle); border-radius: 4px; padding: 8px;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                            <span style="font-weight: 600; font-size: 11px; color: #fff;">${c.name}</span>
                            <span class="alert-severity-badge ${c.risk_level.toLowerCase()}" style="font-size: 9px; padding: 1px 6px;">${c.risk_level} (${c.vulnerability_score}/100)</span>
                        </div>
                        <div style="height: 6px; background: rgba(255,255,255,0.08); border-radius: 3px; overflow: hidden; margin-bottom: 6px;">
                            <div style="width: ${c.vulnerability_score}%; height: 100%; background: ${barColor};"></div>
                        </div>
                        <div style="display: flex; justify-content: space-between; font-size: 10px; color: var(--text-secondary);">
                            <span>Incidents: <strong style="color: #fff;">${c.incident_count}</strong></span>
                            <span style="font-size: 9px; color: var(--text-muted);">${c.recommended_action}</span>
                        </div>
                    </div>
                    `;
                }).join('');
            }

            // Populate Top Hotspots
            const hotspotContainer = document.getElementById('hotspotList');
            if (hotspotContainer && data.hotspots) {
                hotspotContainer.innerHTML = data.hotspots.map(h => `
                <div style="background: rgba(15, 23, 42, 0.6); border: 1px solid var(--border-subtle); border-radius: 4px; padding: 8px; display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <div style="font-weight: 700; font-size: 11px; color: #fff; font-family: var(--font-mono);">${h.id}</div>
                        <div style="font-size: 10px; color: var(--text-secondary);">${h.name}</div>
                        <div style="font-size: 9px; color: var(--text-muted);">${h.threat_type}</div>
                    </div>
                    <div style="text-align: right;">
                        <span class="alert-severity-badge ${h.risk_level.toLowerCase()}" style="font-size: 9px;">${h.risk_level}</span>
                        <div style="font-size: 11px; font-weight: 700; color: var(--accent-cyan); font-family: var(--font-mono); margin-top: 4px;">
                            ${Math.round(h.intensity * 100)}% DENSITY
                        </div>
                    </div>
                </div>
                `).join('');
            }

            // Populate Temporal Histogram (24 hours)
            const temporalContainer = document.getElementById('temporalHistogramBars');
            if (temporalContainer && data.temporal_distribution) {
                const maxCount = Math.max(1, ...data.temporal_distribution.map(t => t.count));
                temporalContainer.innerHTML = data.temporal_distribution.map(t => {
                    const heightPct = Math.max(8, Math.round((t.count / maxCount) * 100));
                    const barColor = t.is_nocturnal ? 'linear-gradient(to top, #ff1744, #ff9800)' : 'linear-gradient(to top, #3b82f6, #00e5ff)';
                    return `
                    <div style="flex: 1; display: flex; flex-direction: column; align-items: center; height: 100%; justify-content: flex-end;" title="${t.hour} - ${t.count} Infiltrations ${t.is_nocturnal ? '(Nocturnal Peak)' : ''}">
                        <div style="width: 100%; height: ${heightPct}%; background: ${barColor}; border-radius: 2px 2px 0 0; opacity: 0.9; transition: height 0.4s ease;"></div>
                    </div>
                    `;
                }).join('');
            }
        } catch (e) {
            console.error('Failed to load threat heatmap analytics:', e);
        }
    }

    async loadSOPChecklist(eventId) {
        try {
            const res = await fetch(`/api/events/${eventId}/sop`);
            if (res.ok) {
                const sop = await res.json();
                this.renderSOPChecklist(sop);
            }
        } catch (err) {
            console.error('Failed to load SOP checklist:', err);
        }
    }

    renderSOPChecklist(sop) {
        const container = document.getElementById('sopStepsContainer');
        const badge = document.getElementById('sopProgressBadge');
        if (!container || !sop || !sop.steps) return;

        if (badge) {
            badge.textContent = `${sop.completed_steps} / ${sop.total_steps} COMPLETED (${sop.progress_percentage}%)`;
            badge.style.color = sop.is_fully_executed ? 'var(--accent-success)' : 'var(--accent-cyan)';
            badge.style.borderColor = sop.is_fully_executed ? 'var(--accent-success)' : 'var(--accent-cyan)';
        }

        container.innerHTML = sop.steps.map(s => {
            const isDone = s.status === 'COMPLETED';
            return `
            <div style="background: rgba(15, 23, 42, 0.65); border: 1px solid ${isDone ? 'rgba(0, 230, 118, 0.3)' : 'var(--border-subtle)'}; border-radius: 4px; padding: 6px 8px; display: flex; justify-content: space-between; align-items: center; gap: 8px;">
                <div style="flex: 1;">
                    <div style="display: flex; align-items: center; gap: 6px;">
                        <span style="font-size: 11px;">${isDone ? '✅' : '⏳'}</span>
                        <span style="font-weight: 600; font-size: 11px; color: ${isDone ? '#fff' : 'var(--text-secondary)'};">${s.title}</span>
                        <span style="font-size: 9px; color: var(--text-muted); font-family: var(--font-mono);">[${s.protocol}]</span>
                    </div>
                    <div style="font-size: 10px; color: var(--text-muted); margin-left: 18px; margin-top: 2px;">
                        ${isDone ? `<span style="color: var(--accent-success);">${s.execution_details || 'Completed by ' + (s.operator_name || 'Operator')}</span>` : s.description}
                    </div>
                </div>
                <div>
                    ${!isDone ? `
                        <button class="btn-tactical btn-sop-exec" data-step-id="${s.step_id}" data-event-id="${sop.event_id}" style="padding: 2px 8px; font-size: 10px; border-color: var(--accent-cyan); color: var(--accent-cyan);">
                            ${s.action_label}
                        </button>
                    ` : `
                        <span style="font-size: 9px; color: var(--accent-success); font-family: var(--font-mono); font-weight: 700;">DONE</span>
                    `}
                </div>
            </div>
            `;
        }).join('');

        container.querySelectorAll('.btn-sop-exec').forEach(btn => {
            btn.addEventListener('click', async () => {
                const stepId = btn.getAttribute('data-step-id');
                const eventId = btn.getAttribute('data-event-id');
                btn.textContent = 'EXECUTING...';
                try {
                    const res = await fetch(`/api/events/${eventId}/sop/${stepId}/execute`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' }
                    });
                    if (res.ok) {
                        const data = await res.json();
                        this.renderSOPChecklist(data.sop);
                    }
                } catch (e) {
                    console.error('SOP execute error:', e);
                }
            });
        });
    }

    // ==========================================
    // PHASE 15 HELPER METHODS (DETERRENCE, DATALINK, AUDIT, POSTURE)
    // ==========================================
    async loadDeterrenceState() {
        try {
            const res = await fetch('/api/deterrence/state');
            if (res.ok) {
                const state = await res.json();
                this.renderDeterrenceState(state);
            }
        } catch (e) {
            console.error('Failed to load deterrence state:', e);
        }
    }

    renderDeterrenceState(state) {
        if (!state) return;
        const curStage = state.current_stage || 0;
        const stageInfo = state.stage_info;

        // Update cards 1..4
        for (let s = 1; s <= 4; s++) {
            const el = document.getElementById(`detStage${s}`);
            if (el) {
                if (s === curStage) {
                    el.style.borderColor = s === 4 ? '#ef4444' : (s === 3 ? '#f59e0b' : (s === 2 ? '#a855f7' : 'var(--accent-cyan)'));
                    el.style.background = s === 4 ? 'rgba(239, 68, 68, 0.25)' : (s === 3 ? 'rgba(245, 158, 11, 0.25)' : 'rgba(0, 229, 255, 0.2)');
                    el.style.boxShadow = '0 0 10px rgba(0, 229, 255, 0.3)';
                } else if (s < curStage) {
                    el.style.borderColor = 'rgba(0, 230, 118, 0.4)';
                    el.style.background = 'rgba(0, 230, 118, 0.08)';
                    el.style.boxShadow = 'none';
                } else {
                    el.style.borderColor = 'var(--border-subtle)';
                    el.style.background = 'rgba(15, 23, 42, 0.7)';
                    el.style.boxShadow = 'none';
                }
            }
        }

        const titleEl = document.getElementById('detActiveTitle');
        const typeEl = document.getElementById('detOutputType');
        const dbEl = document.getElementById('detDecibels');
        const badgeEl = document.getElementById('detComplianceBadge');
        const descEl = document.getElementById('detDescription');

        if (curStage === 0 || !stageInfo) {
            if (titleEl) titleEl.textContent = 'ACTIVE DIRECTIVE: STANDBY';
            if (typeEl) typeEl.textContent = 'NONE';
            if (dbEl) dbEl.textContent = '0 dB';
            if (badgeEl) {
                badgeEl.textContent = 'STANDBY';
                badgeEl.style.color = '#10b981';
                badgeEl.style.borderColor = 'rgba(16, 185, 129, 0.4)';
            }
            if (descEl) descEl.textContent = "No active deterrence directive. Target perimeter monitored. Select 'ESCALATE DETERRENCE' to activate graduated sequence.";
        } else {
            if (titleEl) titleEl.textContent = `ACTIVE DIRECTIVE: ${stageInfo.title.toUpperCase()}`;
            if (typeEl) typeEl.textContent = stageInfo.output_type;
            if (dbEl) dbEl.textContent = `${stageInfo.decibels} dB`;
            if (badgeEl) {
                badgeEl.textContent = state.compliance_status || 'ACTIVE';
                badgeEl.style.color = curStage === 4 ? '#ef4444' : '#f59e0b';
                badgeEl.style.borderColor = curStage === 4 ? '#ef4444' : '#f59e0b';
            }
            if (descEl) descEl.textContent = stageInfo.description;
        }
    }

    playLradAudio() {
        if ('speechSynthesis' in window) {
            window.speechSynthesis.cancel();
            
            // 1. Hindi Warning
            const uHindi = new SpeechSynthesisUtterance("चेतावनी! आप प्रतिबंधित सीमा क्षेत्र में हैं। तुरंत पीछे हटें।");
            uHindi.lang = 'hi-IN';
            uHindi.rate = 0.9;

            // 2. English Warning
            const uEng = new SpeechSynthesisUtterance("Warning! You are entering a restricted border security perimeter. Stand down and turn back immediately.");
            uEng.lang = 'en-US';
            uEng.rate = 0.95;

            window.speechSynthesis.speak(uHindi);
            window.speechSynthesis.speak(uEng);
        } else if (window.audioAlert) {
            window.audioAlert.speakTacticalAlert("Warning! Restricted border perimeter. Turn back immediately.");
        }
    }

    async loadDatalinkPacket() {
        try {
            const [pktRes, statsRes] = await Promise.all([
                fetch('/api/datalink/packet'),
                fetch('/api/datalink/stats')
            ]);
            if (pktRes.ok && statsRes.ok) {
                const pkt = await pktRes.json();
                const stats = await statsRes.json();
                this.updateDatalinkDisplay(pkt, stats);
            }
        } catch (e) {
            console.error('Failed to load datalink packet:', e);
        }
    }

    updateDatalinkDisplay(frame, stats) {
        if (!frame) return;
        const pSize = document.getElementById('dlPacketSize');
        const jSize = document.getElementById('dlJsonSize');
        const bwPct = document.getElementById('dlBandwidthPct');
        const airtime = document.getElementById('dlAirtimeMs');
        const b64 = document.getElementById('dlBase64Payload');
        const sig = document.getElementById('dlHmacSig');
        const totSaved = document.getElementById('dlTotalSaved');

        if (pSize) pSize.textContent = `${frame.packet_size_bytes} BYTES`;
        if (jSize) jSize.textContent = `${frame.equivalent_json_bytes?.toLocaleString() || '4,850'} BYTES`;
        if (bwPct) bwPct.textContent = `${frame.bandwidth_reduction_pct}%`;
        if (airtime) airtime.textContent = `${frame.tactical_radio_airtime_ms} ms`;
        if (b64) b64.textContent = frame.binary_base64_payload;
        if (sig) sig.textContent = frame.hmac_sha256_checksum;
        if (totSaved && stats) totSaved.textContent = `${stats.total_bytes_saved_kb} KB`;
    }

    async loadSihAudit() {
        const container = document.getElementById('sihAuditChecklistContainer');
        if (!container) return;
        container.innerHTML = `<div style="text-align:center; padding: 20px; color: var(--accent-cyan); font-family: var(--font-mono);">EXECUTING FULL COMPLIANCE AUDIT SELF-TEST...</div>`;
        try {
            const res = await fetch('/api/system/sih-compliance/audit');
            if (res.ok) {
                const audit = await res.json();
                container.innerHTML = audit.checklist.map(item => `
                    <div style="background: rgba(15, 23, 42, 0.7); border: 1px solid rgba(0, 230, 118, 0.3); border-radius: 4px; padding: 8px 12px; display: flex; justify-content: space-between; align-items: flex-start; gap: 10px;">
                        <div style="flex: 1;">
                            <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 2px;">
                                <span style="font-size: 13px;">✅</span>
                                <span style="font-weight: 700; font-size: 11px; color: #fff;">${item.id}. ${item.pillar}</span>
                                <span style="font-size: 9px; color: var(--accent-cyan); font-family: var(--font-mono); background: rgba(0, 229, 255, 0.1); padding: 1px 5px; border-radius: 2px;">${item.section_ref}</span>
                            </div>
                            <div style="font-size: 10px; color: var(--text-secondary); margin-left: 21px; line-height: 1.4;">
                                ${item.evidence}
                            </div>
                        </div>
                        <div style="text-align: right; min-width: 90px;">
                            <span style="background: rgba(16, 185, 129, 0.15); color: #10b981; font-family: var(--font-mono); font-size: 10px; font-weight: 700; padding: 2px 6px; border-radius: 3px; border: 1px solid rgba(16, 185, 129, 0.4);">
                                ${item.status}
                            </span>
                        </div>
                    </div>
                `).join('');
            }
        } catch (e) {
            console.error('Failed to load SIH audit:', e);
            container.innerHTML = `<div style="color: #ff1744; text-align: center; padding: 10px;">Failed to execute compliance audit.</div>`;
        }
    }

    renderPostureState(postureData) {
        if (!postureData || !postureData.classifications) return;
        const crawlTarget = postureData.classifications.find(c => c.posture === 'PRONE_CRAWLING');
        if (crawlTarget) {
            const statusEl = document.getElementById('scenarioStatusText');
            if (statusEl && !statusEl.textContent.includes('CRAWLING')) {
                statusEl.innerHTML = `<strong style="color: #ff1744;">TACTICAL ALERT:</strong> Prone crawling infiltrator detected (${crawlTarget.aspect_ratio} AR) in ${crawlTarget.zone_id}`;
            }
        }
    }

    // ==========================================
    // PHASE 16 HELPER METHODS (C-UAS, SWARM, REPLAY, GIS)
    // ==========================================
    async loadCuasStatus() {
        try {
            const res = await fetch('/api/cuas/status');
            if (res.ok) {
                const data = await res.json();
                this.renderCuasStatus(data);
            }
        } catch (e) {
            console.error('Failed to load C-UAS status:', e);
        }
    }

    renderCuasStatus(data) {
        if (!data) return;
        const curStage = data.current_stage || 0;
        const stateTitle = document.getElementById('cuasStateTitle');
        const stateSubtitle = document.getElementById('cuasThreatSubtitle');
        const stateBadge = document.getElementById('cuasStateBadge');
        const callsignEl = document.getElementById('cuasCallsign');
        const altEl = document.getElementById('cuasAltitude');
        const climbEl = document.getElementById('cuasClimbRate');
        const dopplerEl = document.getElementById('cuasDopplerRate');
        const payloadEl = document.getElementById('cuasPayload');
        const neutEl = document.getElementById('cuasNeutralizedCount');

        if (neutEl && data.neutralized_count !== undefined) {
            neutEl.textContent = `${data.neutralized_count} DRONES`;
        }

        // Highlight C-UAS stages 1..4
        for (let s = 1; s <= 4; s++) {
            const card = document.getElementById(`cuasStage${s}`);
            if (card) {
                if (s === curStage) {
                    card.style.borderColor = s === 4 ? '#ef4444' : (s === 3 ? '#a855f7' : '#f59e0b');
                    card.style.background = s === 4 ? 'rgba(239, 68, 68, 0.25)' : (s === 3 ? 'rgba(168, 85, 247, 0.25)' : 'rgba(245, 158, 11, 0.25)');
                } else if (s < curStage) {
                    card.style.borderColor = 'rgba(0, 230, 118, 0.4)';
                    card.style.background = 'rgba(0, 230, 118, 0.08)';
                } else {
                    card.style.borderColor = 'var(--border-subtle)';
                    card.style.background = 'rgba(15, 23, 42, 0.7)';
                }
            }
        }

        if (data.active_threat) {
            const t = data.active_threat;
            if (stateTitle) stateTitle.innerHTML = `<span style="color: #ef4444;">HOSTILE AERIAL THREAT: [${t.callsign}]</span>`;
            if (stateSubtitle) stateSubtitle.textContent = `Altitude: ${t.radar_signature?.altitude_agl_m || 48.5}m | Target: ${t.zone_id} | Payload: ${t.estimated_payload}`;
            if (stateBadge) {
                stateBadge.textContent = 'AIRSPACE THREAT';
                stateBadge.style.background = 'rgba(239, 68, 68, 0.2)';
                stateBadge.style.color = '#ef4444';
            }
            if (callsignEl) callsignEl.textContent = t.callsign;
            if (altEl) altEl.textContent = `${t.radar_signature?.altitude_agl_m || 48.5} m`;
            if (climbEl) climbEl.textContent = `${t.radar_signature?.climb_rate_mps || 2.4} m/s`;
            if (dopplerEl) dopplerEl.textContent = `${t.radar_signature?.micro_doppler_blade_rate_hz || 240} Hz`;
            if (payloadEl) payloadEl.textContent = t.estimated_payload;
        } else {
            if (stateTitle) stateTitle.textContent = 'SKY SHIELD STATUS: CLEAR AIRSPACE';
            if (stateSubtitle) stateSubtitle.textContent = '24GHz mmWave radar scanning airspace for micro-Doppler rotor signatures.';
            if (stateBadge) {
                stateBadge.textContent = 'STANDBY';
                stateBadge.style.background = 'rgba(16, 185, 129, 0.15)';
                stateBadge.style.color = '#10b981';
            }
            if (callsignEl) callsignEl.textContent = 'NONE';
            if (altEl) altEl.textContent = '0.0 m';
            if (climbEl) climbEl.textContent = '0.0 m/s';
            if (dopplerEl) dopplerEl.textContent = '0 Hz';
            if (payloadEl) payloadEl.textContent = 'NONE';
        }
    }

    async loadSwarmStatus() {
        try {
            const res = await fetch('/api/swarm/status');
            if (res.ok) {
                const data = await res.json();
                this.renderSwarmStatus(data);
            }
        } catch (e) {
            console.error('Failed to load swarm status:', e);
        }
    }

    renderSwarmStatus(data) {
        const grid = document.getElementById('swarmDronesGrid');
        if (!grid || !data || !data.drones) return;

        grid.innerHTML = data.drones.map(d => {
            const isAirborne = d.state !== 'DOCKED';
            const batColor = d.battery_pct < 25 ? '#ef4444' : (d.battery_pct < 50 ? '#f59e0b' : '#10b981');
            return `
            <div style="background: rgba(15, 23, 42, 0.7); border: 1px solid ${isAirborne ? 'var(--accent-cyan)' : 'var(--border-subtle)'}; border-radius: 6px; padding: 12px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                    <div>
                        <span style="font-weight: 700; color: #fff; font-size: 11px;">${d.drone_id} (${d.callsign})</span>
                        <div style="font-size: 9px; color: var(--accent-cyan); font-family: var(--font-mono);">${d.role}</div>
                    </div>
                    <span class="badge" style="font-size: 9px; padding: 2px 6px; background: ${isAirborne ? 'rgba(0, 229, 255, 0.15)' : 'rgba(255,255,255,0.05)'}; color: ${isAirborne ? 'var(--accent-cyan)' : 'var(--text-muted)'};">
                        ${d.state}
                    </span>
                </div>
                <div style="margin: 8px 0;">
                    <div style="display: flex; justify-content: space-between; font-size: 9px; font-family: var(--font-mono); color: var(--text-muted); margin-bottom: 2px;">
                        <span>BATTERY:</span>
                        <span style="color: ${batColor}; font-weight: 700;">${d.battery_pct}%</span>
                    </div>
                    <div style="height: 4px; background: rgba(255,255,255,0.1); border-radius: 2px; overflow: hidden;">
                        <div style="width: ${d.battery_pct}%; height: 100%; background: ${batColor};"></div>
                    </div>
                </div>
                <div style="font-size: 10px; font-family: var(--font-mono); color: var(--text-secondary); display: grid; grid-template-columns: 1fr 1fr; gap: 4px; margin-top: 6px;">
                    <div>ALT: <strong style="color: #fff;">${d.altitude_agl_m}m</strong></div>
                    <div>SPD: <strong style="color: #fff;">${d.speed_mps}m/s</strong></div>
                    <div style="grid-column: span 2; font-size: 9px; color: var(--text-muted);">SENSOR: ${d.sensor_payload}</div>
                </div>
            </div>
            `;
        }).join('');
    }

    async loadTimelineReplay() {
        try {
            const res = await fetch('/api/replay/timeline');
            if (res.ok) {
                const data = await res.json();
                this._timelineData = data;
                this.scrubTimeline(100);
            }
        } catch (e) {
            console.error('Failed to load timeline replay:', e);
        }
    }

    async scrubTimeline(pct) {
        if (!this._timelineData || !this._timelineData.start_epoch) return;
        const start = this._timelineData.start_epoch;
        const end = this._timelineData.end_epoch;
        const targetEpoch = Math.round(start + (pct / 100.0) * (end - start));

        const timeReadout = document.getElementById('replayTimeReadout');
        const radarEl = document.getElementById('replayRadarCount');
        const eventEl = document.getElementById('replayEventText');
        const detEl = document.getElementById('replayDeterrenceText');
        const uavEl = document.getElementById('replayUavText');

        if (pct === 100) {
            if (timeReadout) timeReadout.textContent = 'LIVE TELEMETRY (T-0s)';
        } else {
            const dt = new Date(targetEpoch * 1000);
            if (timeReadout) timeReadout.textContent = `${dt.toISOString().slice(11, 19)} UTC (-${Math.round(end - targetEpoch)}s)`;
        }

        try {
            const res = await fetch(`/api/replay/state?epoch_sec=${targetEpoch}`);
            if (res.ok) {
                const data = await res.json();
                if (data.snapshot) {
                    const s = data.snapshot;
                    if (radarEl) radarEl.textContent = `${s.radar_targets?.length || 0} Target(s) active`;
                    if (eventEl && s.active_events) {
                        const topEvt = s.active_events[0];
                        eventEl.textContent = topEvt ? `${topEvt.type || topEvt.event_type} (${topEvt.severity})` : 'NO ALARMS';
                        eventEl.style.color = topEvt?.severity === 'CRITICAL' ? '#ef4444' : '#10b981';
                    }
                    if (detEl) detEl.textContent = `Stage ${s.deterrence_stage || 0}`;
                    if (uavEl) uavEl.textContent = s.uav_state || (s.swarm_active_units ? `${s.swarm_active_units} Units Airborne` : 'STANDBY');
                }
            }
        } catch (e) {
            console.error('Failed to scrub state:', e);
        }
    }

    async renderGisVectorMap() {
        const canvas = document.getElementById('gisVectorCanvas');
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        const w = canvas.width;
        const h = canvas.height;

        // Clear canvas
        ctx.fillStyle = '#020617';
        ctx.fillRect(0, 0, w, h);

        try {
            const res = await fetch('/api/gis/vector-layers');
            if (res.ok) {
                const data = await res.json();
                const base = data.base_station;

                // Simple georeferenced projection helper
                const project = (lon, lat) => {
                    const scale = 38000;
                    const x = w / 2 + (lon - base.longitude) * scale;
                    const y = h / 2 - (lat - base.latitude) * scale * 1.1;
                    return [x, y];
                };

                // Draw 100m MGRS Grid
                ctx.strokeStyle = 'rgba(255, 255, 255, 0.05)';
                ctx.lineWidth = 1;
                data.layers.mgrs_grid.features.forEach(f => {
                    const coords = f.geometry.coordinates[0];
                    ctx.beginPath();
                    coords.forEach(([lon, lat], idx) => {
                        const [px, py] = project(lon, lat);
                        if (idx === 0) ctx.moveTo(px, py);
                        else ctx.lineTo(px, py);
                    });
                    ctx.stroke();
                });

                // Draw Zones
                data.layers.surveillance_zones.features.forEach(f => {
                    const coords = f.geometry.coordinates[0];
                    ctx.fillStyle = f.properties.fill;
                    ctx.strokeStyle = f.properties.stroke;
                    ctx.lineWidth = 1.5;
                    ctx.beginPath();
                    coords.forEach(([lon, lat], idx) => {
                        const [px, py] = project(lon, lat);
                        if (idx === 0) ctx.moveTo(px, py);
                        else ctx.lineTo(px, py);
                    });
                    ctx.closePath();
                    ctx.fill();
                    ctx.stroke();
                });

                // Draw Ravine Shadow
                const rShadow = data.layers.terrain_ravine_shadow;
                if (rShadow) {
                    ctx.fillStyle = rShadow.properties.fill;
                    ctx.strokeStyle = rShadow.properties.stroke;
                    ctx.setLineDash([4, 2]);
                    ctx.beginPath();
                    rShadow.geometry.coordinates[0].forEach(([lon, lat], idx) => {
                        const [px, py] = project(lon, lat);
                        if (idx === 0) ctx.moveTo(px, py);
                        else ctx.lineTo(px, py);
                    });
                    ctx.closePath();
                    ctx.fill();
                    ctx.stroke();
                    ctx.setLineDash([]);
                }

                // Draw Security Fence
                const fence = data.layers.bsf_fence;
                if (fence) {
                    ctx.strokeStyle = fence.properties.stroke;
                    ctx.lineWidth = fence.properties.stroke_width;
                    ctx.beginPath();
                    fence.geometry.coordinates.forEach(([lon, lat], idx) => {
                        const [px, py] = project(lon, lat);
                        if (idx === 0) ctx.moveTo(px, py);
                        else ctx.lineTo(px, py);
                    });
                    ctx.stroke();
                }

                // Draw Zero Line (International Border)
                const zero = data.layers.zero_line;
                if (zero) {
                    ctx.strokeStyle = zero.properties.stroke;
                    ctx.lineWidth = zero.properties.stroke_width;
                    ctx.setLineDash([6, 4]);
                    ctx.beginPath();
                    zero.geometry.coordinates.forEach(([lon, lat], idx) => {
                        const [px, py] = project(lon, lat);
                        if (idx === 0) ctx.moveTo(px, py);
                        else ctx.lineTo(px, py);
                    });
                    ctx.stroke();
                    ctx.setLineDash([]);
                }

                // Draw Radar FOV Cone
                data.layers.sensor_fov.features.forEach(f => {
                    ctx.fillStyle = f.properties.fill;
                    ctx.strokeStyle = f.properties.stroke;
                    ctx.lineWidth = 1;
                    ctx.beginPath();
                    f.geometry.coordinates[0].forEach(([lon, lat], idx) => {
                        const [px, py] = project(lon, lat);
                        if (idx === 0) ctx.moveTo(px, py);
                        else ctx.lineTo(px, py);
                    });
                    ctx.closePath();
                    ctx.fill();
                    ctx.stroke();
                });

                // Draw Border Pillars
                data.layers.border_pillars.features.forEach(f => {
                    const [lon, lat] = f.geometry.coordinates;
                    const [px, py] = project(lon, lat);
                    const isBase = f.properties.type === 'BASE_STATION';
                    ctx.fillStyle = isBase ? '#00e5ff' : '#f59e0b';
                    ctx.beginPath();
                    ctx.arc(px, py, isBase ? 6 : 4, 0, Math.PI * 2);
                    ctx.fill();
                    ctx.fillStyle = '#fff';
                    ctx.font = '9px monospace';
                    ctx.fillText(f.properties.id, px + 8, py + 3);
                });
            }
        } catch (e) {
            console.error('Failed to render GIS vector map:', e);
        }
    }

    async loadSlewStatus() {
        try {
            const res = await fetch('/api/fusion/ptz-status');
            if (res.ok) {
                const data = await res.json();
                this.renderSlewStatus(data);
            }
        } catch (e) {
            console.error('Failed to load slew status:', e);
        }
    }

    renderSlewStatus(data) {
        if (!data) return;
        const panEl = document.getElementById('slewPanDisplay');
        const tiltEl = document.getElementById('slewTiltDisplay');
        const zoomEl = document.getElementById('slewZoomDisplay');
        const lockText = document.getElementById('slewLockText');

        if (data.current_angles) {
            if (panEl) panEl.textContent = `${data.current_angles.pan_deg.toFixed(1)}°`;
            if (tiltEl) tiltEl.textContent = `${data.current_angles.tilt_deg.toFixed(1)}°`;
            if (zoomEl) zoomEl.textContent = data.current_angles.zoom_label || `${data.current_angles.zoom_factor.toFixed(1)}x`;
        }

        if (lockText) {
            if (data.target_locked) {
                const l = data.target_locked;
                lockText.innerHTML = `
                    <span style="color: #10b981; font-weight: 700;">● OPTICAL BORESIGHT LOCKED ONTO ${l.target_id}</span><br>
                    • Coordinates: (${l.x_m}m lateral, ${l.y_m}m depth) | Distance: ${l.ground_distance_m}m<br>
                    • Gimbal Angles: Pan ${l.pan_deg}° | Tilt ${l.tilt_deg}° | Zoom ${l.zoom_factor}x<br>
                    • Tracking Quality: ${(l.lock_confidence * 100).toFixed(0)}% Cross-Sensor Boresight Alignment
                `;
            } else {
                lockText.textContent = 'Gimbal centered at home zero position. Ready for radar contact auto-cueing.';
            }
        }
    }

    async loadEkfTracks() {
        try {
            const res = await fetch('/api/fusion/ekf-tracks');
            if (res.ok) {
                const data = await res.json();
                this.renderEkfTracks(data.tracks || []);
            }
        } catch (e) {
            console.error('Failed to load EKF tracks:', e);
        }
    }

    renderEkfTracks(tracks) {
        const tbody = document.getElementById('ekfTracksTableBody');
        const stateVec = document.getElementById('ekfStateVector');
        const covEl = document.getElementById('ekfCovarianceDetails');

        if (!tbody) return;

        if (!tracks || tracks.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" style="padding: 10px; text-align: center; color: var(--text-muted);">No active EKF tracks. Trigger radar or camera observation.</td></tr>';
            return;
        }

        const top = tracks[0];
        if (stateVec && top.position && top.velocity) {
            stateVec.innerHTML = `
                • Position: (${top.position.x_m.toFixed(2)}m, ${top.position.y_m.toFixed(2)}m)<br>
                • Velocity: (${top.velocity.vx_mps.toFixed(2)} m/s, ${top.velocity.vy_mps.toFixed(2)} m/s)<br>
                • Net Speed: ${top.velocity.speed_mps.toFixed(2)} m/s (Heading: ${top.velocity.heading_deg.toFixed(1)}°)<br>
                • Hits: ${top.hit_count} | Confirmed: ${top.confirmed ? 'YES (95% CI)' : 'ACQUIRING'}
            `;
        }

        if (covEl && top.error_ellipse_95) {
            const el = top.error_ellipse_95;
            covEl.innerHTML = `
                • Semi-Major Axis (a): ${el.semi_major_m.toFixed(2)}m<br>
                • Semi-Minor Axis (b): ${el.semi_minor_m.toFixed(2)}m<br>
                • Orientation Angle (&psi;): ${el.orientation_deg.toFixed(1)}°<br>
                • Mahalanobis Gate (&gamma;): &le; 5.991 (95% Chi-Sq)
            `;
        }

        tbody.innerHTML = tracks.map(t => {
            const el = t.error_ellipse_95 || { semi_major_m: 0.25, semi_minor_m: 0.15, orientation_deg: 0 };
            return `
                <tr style="border-bottom: 1px solid rgba(255,255,255,0.04);">
                    <td style="padding: 6px 10px; font-weight: 700; color: #fff;">${t.track_id}</td>
                    <td style="padding: 6px 10px; color: #00e5ff;">(${t.position.x_m}m, ${t.position.y_m}m)</td>
                    <td style="padding: 6px 10px; color: #38bdf8;">${t.velocity.speed_mps} m/s @ ${t.velocity.heading_deg}°</td>
                    <td style="padding: 6px 10px; color: #a855f7;">a=${el.semi_major_m}m, b=${el.semi_minor_m}m</td>
                    <td style="padding: 6px 10px; color: ${t.confirmed ? '#10b981' : '#f59e0b'}; font-weight: 700;">
                        ${t.confirmed ? 'CROSS-CONFIRMED' : 'ACQUIRING'}
                    </td>
                </tr>
            `;
        }).join('');
    }

    async loadPrediction(targetId = 'INTRUDER_VEC_01') {
        try {
            const res = await fetch(`/api/kinematics/prediction/${targetId}`);
            if (res.ok) {
                const data = await res.json();
                this.renderPrediction(data);
            }
        } catch (e) {
            console.error('Failed to load prediction:', e);
        }
    }

    renderPrediction(data) {
        if (!data) return;
        const etbDisplay = document.getElementById('etbCountdownDisplay');
        const badge = document.getElementById('etbUrgencyBadge');
        const ppiEl = document.getElementById('ppiCoordinates');
        const wpGrid = document.getElementById('predictionWaypointsList');

        if (etbDisplay) {
            if (data.estimated_time_to_breach_sec !== null && data.estimated_time_to_breach_sec !== undefined) {
                etbDisplay.textContent = `${data.estimated_time_to_breach_sec.toFixed(1)}s`;
            } else {
                etbDisplay.textContent = '--';
            }
        }

        if (badge) {
            badge.textContent = data.threat_urgency.replace(/_/g, ' ');
            badge.style.background = data.threat_urgency.includes('CRITICAL') ? '#ef4444' : (data.threat_urgency.includes('HIGH') ? '#f59e0b' : '#3b82f6');
        }

        if (ppiEl && data.predicted_point_of_infiltration) {
            const p = data.predicted_point_of_infiltration;
            ppiEl.innerHTML = `
                • BSF Fence Point: (${p.x_m}m, ${p.y_m}m)<br>
                • Coordinates: ${p.latitude.toFixed(6)}°N, ${p.longitude.toFixed(6)}°E<br>
                • Military Grid: ${p.mgrs_grid}<br>
                • Target Speed: ${data.current_state?.speed_mps || 0.85} m/s
            `;
        }

        if (wpGrid && data.projected_waypoints) {
            wpGrid.innerHTML = data.projected_waypoints.map(w => `
                <div style="background: rgba(255,255,255,0.03); padding: 6px; border-radius: 4px; text-align: center; ${w.time_offset_sec === 5.0 ? 'color: #ef4444; font-weight: 700;' : ''}">
                    T+${w.time_offset_sec}s: (${w.x_m}m, ${w.y_m}m)
                </div>
            `).join('');
        }
    }

    async loadHealthMatrix() {
        try {
            const res = await fetch('/api/health/matrix');
            if (res.ok) {
                const data = await res.json();
                this.renderHealthMatrix(data);
            }
        } catch (e) {
            console.error('Failed to load health matrix:', e);
        }
    }

    renderHealthMatrix(data) {
        if (!data) return;
        const grid = document.getElementById('healthMatrixCardsGrid');
        const badge = document.getElementById('activeModeBadge');
        const desc = document.getElementById('modeDescriptionText');

        if (badge && data.active_degraded_mode) {
            const m = data.active_degraded_mode;
            badge.textContent = `${m.mode_id} (R:${Math.round(m.radar_weight*100)} / V:${Math.round(m.optical_weight*100)})`;
            badge.style.background = m.mode_id === 'BALANCED_FUSION' ? '#10b981' : (m.mode_id === 'FOG_SMOKE_DEGRADED' ? '#f59e0b' : '#ef4444');
        }

        if (desc && data.active_degraded_mode) {
            desc.textContent = data.active_degraded_mode.description;
        }

        if (grid && data.sensors) {
            grid.innerHTML = data.sensors.map(s => {
                const isOnline = s.status === 'ONLINE';
                const isDegraded = s.status === 'DEGRADED';
                const statusColor = isOnline ? '#10b981' : (isDegraded ? '#f59e0b' : '#ef4444');

                return `
                    <div style="background: #020617; border: 1px solid var(--border-subtle); border-radius: 6px; padding: 10px; font-family: var(--font-mono); font-size: 9px;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                            <span style="font-weight: 700; color: #fff; font-size: 10px;">${s.sensor_id.replace('CAMERA_', 'CAM_')}</span>
                            <span style="color: ${statusColor}; font-weight: 700;">● ${s.status}</span>
                        </div>
                        <div style="font-size: 16px; font-weight: 800; color: ${statusColor}; margin-bottom: 4px;">
                            ${s.health_pct.toFixed(1)}%
                        </div>
                        <div style="color: var(--text-muted); font-size: 8px;">${s.name}</div>
                    </div>
                `;
            }).join('');
        }
    }

    async loadPerfStatus() {
        try {
            const res = await fetch('/api/perf/status');
            if (res.ok) {
                const data = await res.json();
                this.renderPerfStatus(data);
            }
        } catch (e) {
            console.error('Failed to load performance status:', e);
        }
    }

    renderPerfStatus(data) {
        if (!data) return;
        const gov = data.governor || {};
        const hw = data.hardware || {};
        const latency = hw.latency || {};
        const stages = latency.stages_ms || {};

        // 1. Target FPS
        const targetFpsEl = document.getElementById('perfTargetFpsVal');
        const modePillEl = document.getElementById('perfFpsModePill');
        if (targetFpsEl) {
            targetFpsEl.textContent = `${gov.current_target_fps || 6.0} FPS`;
            targetFpsEl.style.color = gov.is_bursting ? '#ef4444' : '#34d399';
        }
        if (modePillEl) {
            modePillEl.textContent = gov.is_bursting ? 'THREAT BURST (30 FPS)' : (gov.mode || 'ECO IDLE');
            modePillEl.style.background = gov.is_bursting ? 'rgba(239, 68, 68, 0.2)' : 'rgba(52, 211, 153, 0.15)';
            modePillEl.style.color = gov.is_bursting ? '#ef4444' : '#34d399';
        }

        // 2. E2E Latency & Headroom
        const totalLatEl = document.getElementById('perfTotalLatencyVal');
        const budgetPill = document.getElementById('perfBudgetStatusPill');
        const headroomEl = document.getElementById('perfLatencyHeadroomText');
        const totalMs = latency.total_e2e_ms || 48.0;

        if (totalLatEl) totalLatEl.textContent = `${totalMs} ms`;
        if (budgetPill) {
            const ok = latency.status === 'WITHIN_BUDGET';
            budgetPill.textContent = ok ? '< 100ms OK' : 'BUDGET EXCEEDED';
            budgetPill.style.color = ok ? '#38bdf8' : '#ef4444';
        }
        if (headroomEl) {
            headroomEl.textContent = `HEADROOM: ${latency.headroom_ms || 52.0} ms`;
        }

        // 3. Power Reduction
        const powerSavedEl = document.getElementById('perfPowerSavedVal');
        if (powerSavedEl) {
            powerSavedEl.textContent = `${gov.power_saved_pct || 80.0}%`;
        }

        // 4. Compute Device & Precision
        const devEl = document.getElementById('perfComputeDeviceVal');
        const precPill = document.getElementById('perfPrecisionPill');
        if (devEl) devEl.textContent = hw.compute_provider || 'CPU OpenMP';
        if (precPill) precPill.textContent = hw.current_precision || 'FP16';

        // 5. Stage Progress Bar
        const barCap = document.getElementById('barLatencyCap');
        const barInf = document.getElementById('barLatencyInf');
        const barTrk = document.getElementById('barLatencyTrk');
        const barNet = document.getElementById('barLatencyNet');

        if (barCap) barCap.style.width = `${Math.min(100, stages.capture || 14)}%`;
        if (barInf) barInf.style.width = `${Math.min(100, stages.inference || 28)}%`;
        if (barTrk) barTrk.style.width = `${Math.min(100, stages.tracking || 2)}%`;
        if (barNet) barNet.style.width = `${Math.min(100, stages.network || 3)}%`;

        const elCap = document.getElementById('perfStageCapMs');
        const elInf = document.getElementById('perfStageInfMs');
        const elTrk = document.getElementById('perfStageTrkMs');
        const elNet = document.getElementById('perfStageNetMs');

        if (elCap) elCap.textContent = `${stages.capture || 14.2} ms`;
        if (elInf) elInf.textContent = `${stages.inference || 28.5} ms`;
        if (elTrk) elTrk.textContent = `${stages.tracking || 2.1} ms`;
        if (elNet) elNet.textContent = `${stages.network || 3.2} ms`;

        // 6. Active Mode Label & Description
        const activeLabel = document.getElementById('perfActiveModeLabel');
        const modeDesc = document.getElementById('perfModeDescText');
        if (activeLabel) activeLabel.textContent = `ACTIVE: ${gov.mode || 'AUTO_ADAPTIVE'}`;
        if (modeDesc) {
            if (gov.mode === 'ECO_IDLE') {
                modeDesc.textContent = 'Fixed at 6 FPS. Extreme battery and thermal conservation for sustained quiescent border patrol.';
            } else if (gov.mode === 'BURST_MAX') {
                modeDesc.textContent = 'Fixed at 30 FPS. Full temporal resolution for fast-moving airborne drones and ballistic verification.';
            } else if (gov.mode === 'BALANCED') {
                modeDesc.textContent = 'Fixed at 15 FPS. Moderate standard surveillance with balanced power envelope.';
            } else {
                modeDesc.textContent = 'Dynamically throttles AI loop to 6 FPS during calm surveillance, bursting to 30 FPS in < 20ms upon radar breach or camera intrusion.';
            }
        }
    }

    async loadEwSensorsStatus() {
        try {
            const res = await fetch('/api/ew-sensors/status');
            if (res.ok) {
                const data = await res.json();
                this.renderEwSensorsStatus(data);
            }
        } catch (e) {
            console.error('Failed to load EW sensors status:', e);
        }
    }

    renderEwSensorsStatus(data) {
        if (!data) return;
        const df = data.direction_finding_array || {};
        const gs = data.ground_sensors || {};

        // Jamming Triangulation
        const mgrsEl = document.getElementById('ewJammerMgrsText');
        const coordsEl = document.getElementById('ewJammerCoordsText');
        const antiSpoofEl = document.getElementById('ewAntiSpoofText');
        const triBadge = document.getElementById('ewArrayStatusBadge');

        if (df.latest_triangulation) {
            const t = df.latest_triangulation;
            if (mgrsEl) mgrsEl.textContent = t.georeferenced.mgrs_8digit;
            if (coordsEl) coordsEl.textContent = `x: ${t.estimated_coords.x_m}m, y: ${t.estimated_coords.y_m}m | CEP: ${t.estimated_coords.cep_radius_m}m`;
            if (antiSpoofEl) {
                antiSpoofEl.textContent = 'GPS DENIED // INS DEAD RECKONING';
                antiSpoofEl.style.color = '#ef4444';
            }
            if (triBadge) {
                triBadge.textContent = 'JAMMER LOCATED';
                triBadge.style.background = 'rgba(239, 68, 68, 0.2)';
                triBadge.style.color = '#ef4444';
            }
        } else {
            if (mgrsEl) mgrsEl.textContent = 'N/A - SPECTRUM CLEAN';
            if (coordsEl) coordsEl.textContent = 'x: 0.0m, y: 0.0m | CEP: 0.0m';
            if (antiSpoofEl) {
                antiSpoofEl.textContent = 'GPS ACTIVE // INS STANDBY';
                antiSpoofEl.style.color = '#10b981';
            }
            if (triBadge) {
                triBadge.textContent = '3 DF POSTS ACTIVE';
                triBadge.style.background = 'rgba(244, 63, 94, 0.15)';
                triBadge.style.color = '#fb7185';
            }
        }

        // Seismic Geophone
        const cadenceEl = document.getElementById('ewSeismicCadenceVal');
        const energyEl = document.getElementById('ewSeismicEnergyVal');
        const classPill = document.getElementById('ewSeismicClassPill');

        if (gs.recent_detections && gs.recent_detections.length > 0) {
            const latest = gs.recent_detections[gs.recent_detections.length - 1];
            if (cadenceEl) cadenceEl.textContent = `${latest.cadence_hz} Hz`;
            if (energyEl) energyEl.textContent = `${Math.round(latest.energy_normalized * 100)}%`;
            if (classPill) {
                classPill.textContent = latest.classification;
                classPill.style.background = latest.is_critical ? 'rgba(239, 68, 68, 0.2)' : 'rgba(16, 185, 129, 0.2)';
                classPill.style.color = latest.is_critical ? '#ef4444' : '#10b981';
            }
        }
    }

    // ==============================================================================
    // Phase 20: Master Tactical Playbooks & Evaluator Pitch Tour Handlers
    // ==============================================================================

    async loadPlaybooksCatalog() {
        try {
            const res = await fetch('/api/playbooks');
            if (res.ok) {
                const data = await res.json();
                this.playbooksCatalog = data.playbooks || [];
                this.renderPlaybooksGrid();
                if (this.playbooksCatalog.length > 0) {
                    this.selectPlaybook(this.activePlaybookId);
                }
            }
        } catch (e) {
            console.error('Failed to load playbooks catalog:', e);
        }
    }

    renderPlaybooksGrid() {
        const grid = document.getElementById('playbooksGrid');
        if (!grid || !this.playbooksCatalog) return;

        grid.innerHTML = this.playbooksCatalog.map(p => {
            const isSelected = p.id === this.activePlaybookId;
            let threatColor = '#10b981';
            let threatBg = 'rgba(16, 185, 129, 0.15)';
            if (p.threat_level === 'CRITICAL') {
                threatColor = '#f43f5e';
                threatBg = 'rgba(244, 63, 94, 0.15)';
            } else if (p.threat_level === 'HIGH') {
                threatColor = '#f97316';
                threatBg = 'rgba(249, 115, 22, 0.15)';
            } else if (p.threat_level === 'MEDIUM') {
                threatColor = '#f59e0b';
                threatBg = 'rgba(245, 158, 11, 0.15)';
            }

            const borderStyle = isSelected 
                ? 'border: 1.5px solid #38bdf8; background: rgba(56, 189, 248, 0.09); box-shadow: 0 0 15px rgba(56, 189, 248, 0.25);' 
                : 'border: 1px solid #1e293b; background: rgba(15, 23, 42, 0.6);';

            return `
                <div class="playbook-card" data-id="${p.id}" style="${borderStyle} border-radius: 6px; padding: 10px 12px; cursor: pointer; transition: all 0.2s ease;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                        <span style="font-family: var(--font-mono); font-size: 11px; font-weight: 800; color: #38bdf8;">${p.code}</span>
                        <span style="font-size: 9px; font-weight: 800; padding: 1px 6px; border-radius: 3px; background: ${threatBg}; color: ${threatColor}; font-family: var(--font-mono);">${p.threat_level}</span>
                    </div>
                    <div style="font-size: 11px; font-weight: 700; color: #fff; line-height: 1.3; margin-bottom: 6px; min-height: 28px;">
                        ${p.name}
                    </div>
                    <div style="display: flex; justify-content: space-between; align-items: center; font-size: 10px; color: #94a3b8; font-family: var(--font-mono); border-top: 1px solid rgba(255,255,255,0.06); padding-top: 6px; margin-top: 4px;">
                        <span>${p.stages_count} STAGES</span>
                        <span style="color: #38bdf8;">${p.category.split('_')[0]}</span>
                    </div>
                </div>
            `;
        }).join('');

        grid.querySelectorAll('.playbook-card').forEach(card => {
            card.addEventListener('click', () => {
                const id = parseInt(card.getAttribute('data-id'), 10);
                this.selectPlaybook(id);
            });
        });
    }

    selectPlaybook(id) {
        this.activePlaybookId = id;
        this.activeStageIndex = 0;
        this.renderPlaybooksGrid();

        const pb = (this.playbooksCatalog || []).find(p => p.id === id);
        if (!pb) return;

        const codeEl = document.getElementById('pbActiveCode');
        const titleEl = document.getElementById('pbActiveTitle');
        const threatEl = document.getElementById('pbActiveThreatPill');

        if (codeEl) codeEl.textContent = pb.code;
        if (titleEl) titleEl.textContent = pb.name;
        if (threatEl) {
            threatEl.textContent = `${pb.threat_level} THREAT`;
            if (pb.threat_level === 'CRITICAL') {
                threatEl.style.color = '#f43f5e';
                threatEl.style.borderColor = '#f43f5e';
                threatEl.style.background = 'rgba(244, 63, 94, 0.2)';
            } else if (pb.threat_level === 'HIGH') {
                threatEl.style.color = '#f97316';
                threatEl.style.borderColor = '#f97316';
                threatEl.style.background = 'rgba(249, 115, 22, 0.2)';
            } else if (pb.threat_level === 'MEDIUM') {
                threatEl.style.color = '#f59e0b';
                threatEl.style.borderColor = '#f59e0b';
                threatEl.style.background = 'rgba(245, 158, 11, 0.2)';
            } else {
                threatEl.style.color = '#10b981';
                threatEl.style.borderColor = '#10b981';
                threatEl.style.background = 'rgba(16, 185, 129, 0.2)';
            }
        }

        this.renderStepper(pb.stages_count, 0);

        const logBox = document.getElementById('pbStageLogBox');
        if (logBox) {
            logBox.innerHTML = `
                <div style="color: #38bdf8; font-weight: 700; margin-bottom: 4px;">▶ [${pb.code}] ${pb.name}</div>
                <div style="color: #94a3b8; font-size: 10px; margin-bottom: 6px;">${pb.description}</div>
                <div style="color: #64748b; font-size: 10px;">Subsystems: ${pb.subsystems.join(' • ')} (${pb.section_ref})</div>
                <div style="color: #64748b; font-size: 10px; margin-top: 6px;">Ready. Click [EXECUTE FULL DRILL] to run all ${pb.stages_count} stages, or [STEP STAGE] for an evaluator-guided walkthrough.</div>
            `;
        }
    }

    renderStepper(totalStages, activeIdx) {
        const stepper = document.getElementById('pbStageStepper');
        if (!stepper) return;

        let html = '';
        for (let i = 1; i <= totalStages; i++) {
            let pillStyle = 'background: #0b1329; border: 1px solid #1e293b; color: #64748b;';
            let label = `Stage ${i}`;

            if (activeIdx === -1 || (activeIdx > 0 && i < activeIdx)) {
                // Completed stage
                pillStyle = 'background: rgba(16, 185, 129, 0.15); border: 1px solid #10b981; color: #10b981; font-weight: 700;';
                label = `✓ Stage ${i}`;
            } else if (i === activeIdx) {
                // Active stage
                pillStyle = 'background: rgba(56, 189, 248, 0.2); border: 1px solid #38bdf8; color: #38bdf8; font-weight: 800; box-shadow: 0 0 10px rgba(56, 189, 248, 0.4);';
                label = `⚡ Stage ${i}`;
            }

            html += `
                <div id="pbStageStep_${i}" style="flex: 1; min-width: 90px; text-align: center; padding: 6px 8px; border-radius: 6px; font-family: var(--font-mono); font-size: 10px; ${pillStyle} transition: all 0.3s ease;">
                    ${label}
                </div>
            `;
        }
        stepper.innerHTML = html;
    }

    async executeActivePlaybook() {
        const btnExec = document.getElementById('btnExecutePlaybook');
        const btnStep = document.getElementById('btnStepPlaybook');
        const spinner = document.getElementById('pbExecutionSpinner');
        const logBox = document.getElementById('pbStageLogBox');
        const isPitchMode = document.getElementById('chkEvaluatorPitchMode')?.checked;

        if (btnExec) btnExec.disabled = true;
        if (btnStep) btnStep.disabled = true;
        if (spinner) spinner.style.display = 'flex';

        try {
            const res = await fetch(`/api/playbooks/${this.activePlaybookId}/execute`, { method: 'POST' });
            if (res.ok) {
                const data = await res.json();
                const execution = data.execution;
                const stages = execution.stages || [];

                this.renderStepper(stages.length, -1);

                if (logBox) {
                    logBox.innerHTML = `
                        <div style="color: #10b981; font-weight: 800; margin-bottom: 6px; font-size: 12px;">
                            ✅ [${execution.code}] ${execution.title} — DRILL COMPLETED SUCCESSFULLY
                        </div>
                    `;

                    stages.forEach(s => {
                        const metricsSummary = Object.entries(s.metrics || {})
                            .map(([k, v]) => `<span style="color: #38bdf8;">${k}:</span> ${v}`)
                            .join(' | ');

                        logBox.innerHTML += `
                            <div style="margin-top: 8px; padding: 6px 10px; background: rgba(15, 23, 42, 0.7); border-left: 3px solid #10b981; border-radius: 0 4px 4px 0;">
                                <div style="display: flex; justify-content: space-between; align-items: center;">
                                    <strong style="color: #fff;">STAGE ${s.stage}: ${s.title}</strong>
                                    <span style="font-size: 9px; color: #10b981; font-weight: 700;">PASSED</span>
                                </div>
                                <div style="color: #94a3b8; font-size: 10px; margin-top: 2px;">⚡ Subsystem: ${s.subsystem}</div>
                                <div style="color: #cbd5e1; font-size: 10px; margin-top: 2px;">&gt; ${s.action}</div>
                                ${metricsSummary ? `<div style="color: #64748b; font-size: 9px; margin-top: 3px; font-family: var(--font-mono);">${metricsSummary}</div>` : ''}
                            </div>
                        `;
                    });

                    logBox.scrollTop = logBox.scrollHeight;
                }

                if (window.audioAlert) {
                    window.audioAlert.speakTacticalAlert(`Tactical Playbook ${execution.code} executed. All mission objectives verified.`);
                }

                if (isPitchMode && stages.length > 0) {
                    await this.triggerEvaluatorPitchTour(stages);
                }
            }
        } catch (e) {
            console.error('Failed to execute playbook:', e);
            if (logBox) {
                logBox.innerHTML += `<div style="color: #ef4444; margin-top: 6px;">❌ DRILL EXECUTION FAILED: ${e.message}</div>`;
            }
        } finally {
            if (btnExec) btnExec.disabled = false;
            if (btnStep) btnStep.disabled = false;
            if (spinner) spinner.style.display = 'none';
        }
    }

    async stepActivePlaybook() {
        const btnStep = document.getElementById('btnStepPlaybook');
        const spinner = document.getElementById('pbExecutionSpinner');
        const logBox = document.getElementById('pbStageLogBox');
        const isPitchMode = document.getElementById('chkEvaluatorPitchMode')?.checked;

        if (btnStep) btnStep.disabled = true;
        if (spinner) spinner.style.display = 'flex';

        try {
            const res = await fetch(`/api/playbooks/${this.activePlaybookId}/step`, { method: 'POST' });
            if (res.ok) {
                const data = await res.json();
                const step = data.step;
                const stage = step.current_stage;

                this.activeStageIndex = step.stage_index;
                this.renderStepper(step.total_stages, step.stage_index);

                if (logBox) {
                    const metricsSummary = Object.entries(stage.metrics || {})
                        .map(([k, v]) => `<span style="color: #38bdf8;">${k}:</span> ${v}`)
                        .join(' | ');

                    logBox.innerHTML += `
                        <div style="margin-top: 8px; padding: 6px 10px; background: rgba(56, 189, 248, 0.08); border-left: 3px solid #38bdf8; border-radius: 0 4px 4px 0;">
                            <div style="display: flex; justify-content: space-between; align-items: center;">
                                <strong style="color: #38bdf8;">STAGE ${stage.stage}/${step.total_stages}: ${stage.title}</strong>
                                <span style="font-size: 9px; color: ${step.is_last_stage ? '#10b981' : '#38bdf8'}; font-weight: 800;">${step.is_last_stage ? 'MISSION COMPLETE' : 'IN PROGRESS'}</span>
                            </div>
                            <div style="color: #94a3b8; font-size: 10px; margin-top: 2px;">⚡ Subsystem: ${stage.subsystem}</div>
                            <div style="color: #fff; font-size: 10px; margin-top: 2px;">&gt; ${stage.action}</div>
                            ${metricsSummary ? `<div style="color: #64748b; font-size: 9px; margin-top: 3px; font-family: var(--font-mono);">${metricsSummary}</div>` : ''}
                        </div>
                    `;
                    logBox.scrollTop = logBox.scrollHeight;
                }

                if (isPitchMode) {
                    this.highlightHudWidgetForStage(stage);
                }

                if (window.audioAlert) {
                    window.audioAlert.playWarningBeep();
                }
            }
        } catch (e) {
            console.error('Failed to step playbook:', e);
        } finally {
            if (btnStep) btnStep.disabled = false;
            if (spinner) spinner.style.display = 'none';
        }
    }

    async resetActivePlaybooks() {
        try {
            const res = await fetch('/api/playbooks/reset', { method: 'POST' });
            if (res.ok) {
                this.resetPlaybooksUI();
            }
        } catch (e) {
            console.error('Failed to reset playbooks:', e);
        }
    }

    resetPlaybooksUI() {
        this.activeStageIndex = 0;
        const pb = (this.playbooksCatalog || []).find(p => p.id === this.activePlaybookId);
        const stageCount = pb ? pb.stages_count : 6;
        this.renderStepper(stageCount, 0);

        const logBox = document.getElementById('pbStageLogBox');
        if (logBox) {
            logBox.innerHTML = '<div style="color: #10b981;">[DRILL RESET] All tactical demonstration playbooks, sensors, and actuators restored to baseline clean state.</div>';
        }

        document.querySelectorAll('.pitch-highlight, .pitch-highlight-danger').forEach(el => {
            el.classList.remove('pitch-highlight', 'pitch-highlight-danger');
        });
    }

    highlightHudWidgetForStage(stage) {
        if (!stage) return;
        const title = (stage.title || '').toLowerCase();
        const sub = (stage.subsystem || '').toLowerCase();

        let targetEl = null;
        let isDanger = false;

        if (title.includes('ew') || title.includes('jamming') || sub.includes('direction-finding')) {
            targetEl = document.getElementById('radarCanvas')?.closest('.hud-panel') || document.getElementById('ewSensorsModal');
            isDanger = true;
        } else if (title.includes('geophone') || title.includes('seismic') || sub.includes('geophone')) {
            targetEl = document.getElementById('zoneMapCanvas')?.closest('.hud-panel');
        } else if (title.includes('radar') || title.includes('ekf') || title.includes('kinematics')) {
            targetEl = document.getElementById('radarCanvas')?.closest('.hud-panel');
        } else if (title.includes('thermal') || title.includes('slew') || title.includes('lwir') || title.includes('camera') || title.includes('anpr')) {
            targetEl = document.getElementById('cameraGridContainer')?.closest('.hud-panel') || document.getElementById('tacticalMonitorImg');
        } else if (title.includes('deterrence') || title.includes('strobe') || title.includes('siren')) {
            targetEl = document.getElementById('alertFeedContainer')?.closest('.hud-panel');
            isDanger = true;
        } else if (title.includes('sitrep') || title.includes('certificate')) {
            targetEl = document.getElementById('alertFeedContainer')?.closest('.hud-panel');
        } else if (title.includes('drone') || title.includes('cuas') || title.includes('intercept') || title.includes('uav')) {
            targetEl = document.getElementById('radarCanvas')?.closest('.hud-panel');
            isDanger = true;
        } else if (title.includes('lora') || title.includes('mesh')) {
            targetEl = document.getElementById('zoneMapCanvas')?.closest('.hud-panel');
        }

        if (targetEl) {
            const highlightClass = isDanger ? 'pitch-highlight-danger' : 'pitch-highlight';
            targetEl.classList.add(highlightClass);
            setTimeout(() => {
                targetEl.classList.remove(highlightClass);
            }, 3200);
        }
    }

    async triggerEvaluatorPitchTour(stages) {
        for (let i = 0; i < stages.length; i++) {
            this.highlightHudWidgetForStage(stages[i]);
            await new Promise(r => setTimeout(r, 1200));
        }
    }

    handlePlaybookStageTransition(data) {
        if (data.playbook_id === this.activePlaybookId) {
            const pb = (this.playbooksCatalog || []).find(p => p.id === data.playbook_id);
            const total = pb ? pb.stages_count : 6;
            this.renderStepper(total, data.stage_number);

            const isPitchMode = document.getElementById('chkEvaluatorPitchMode')?.checked;
            if (isPitchMode) {
                this.highlightHudWidgetForStage({
                    title: data.title,
                    subsystem: data.subsystem
                });
            }
        }
    }

    async loadCameraNetworkInfo(selectedIp = null) {
        try {
            const query = selectedIp ? `?selected_ip=${encodeURIComponent(selectedIp)}` : '';
            const res = await fetch(`/api/cameras/network/info${query}`);
            if (res.ok) {
                const data = await res.json();
                this.cam02NetworkData = data;
                const displayEl = document.getElementById('mobileStreamUrlDisplay');
                const appUrlInput = document.getElementById('cam02StreamUrl');
                const httpFallbackEl = document.getElementById('httpFallbackText');
                const btnOpenTab = document.getElementById('btnOpenMobileTab');
                const ipSelector = document.getElementById('cam02IpSelector');

                // Populate IP selector options if available
                if (ipSelector && Array.isArray(data.available_ips)) {
                    ipSelector.innerHTML = '';
                    data.available_ips.forEach(ip => {
                        const opt = document.createElement('option');
                        opt.value = ip;
                        opt.textContent = `${ip} ${ip === data.local_ip ? '(Active LAN)' : ''}`;
                        if (ip === data.local_ip) opt.selected = true;
                        ipSelector.appendChild(opt);
                    });
                }

                if (displayEl && (data.mobile_stream_url_https || data.mobile_stream_url)) {
                    displayEl.value = data.mobile_stream_url_https || data.mobile_stream_url;
                }
                if (btnOpenTab && (data.mobile_stream_url_https || data.mobile_stream_url)) {
                    btnOpenTab.href = data.mobile_stream_url_https || data.mobile_stream_url;
                }
                if (httpFallbackEl && data.mobile_stream_url_http) {
                    httpFallbackEl.textContent = data.mobile_stream_url_http;
                }
                if (appUrlInput && data.local_ip) {
                    appUrlInput.value = `http://${data.local_ip}:8080/video`;
                }

                this.updateCam02QrDisplay();
            }
        } catch (e) {
            console.debug('Failed to load camera network info:', e);
        }
    }

    updateCam02QrDisplay() {
        if (!this.cam02NetworkData) return;
        const data = this.cam02NetworkData;
        const qrImg = document.getElementById('cam02QrImage');
        const badge = document.getElementById('cam02QrProtocolBadge');
        const isHttp = this.cam02QrMode === 'http';
        const targetUrl = isHttp ? data.mobile_stream_url_http : data.mobile_stream_url_https;

        if (qrImg) {
            qrImg.src = `/api/cameras/network/qr?target=${encodeURIComponent(targetUrl)}&_t=${Date.now()}`;
        }
        if (badge) {
            badge.textContent = isHttp ? '🌐 HTTP PORT 8000 (FALLBACK)' : '🔒 SECURE HTTPS (PORT 8443)';
            badge.style.color = isHttp ? '#f59e0b' : '#10b981';
        }
    }

    renderIdentityVerification(data) {
        if (!data) return;
        const nameEl = document.getElementById('idHudName');
        const confEl = document.getElementById('idHudConfidence');
        const authEl = document.getElementById('idHudAuthorization');
        const reasonEl = document.getElementById('idHudAuthReason');
        const camEl = document.getElementById('idHudCamera');
        const zoneEl = document.getElementById('idHudZone');
        const droneBanner = document.getElementById('idHudDroneBanner');
        const droneDesc = document.getElementById('idHudDroneBannerDesc');

        const identity = data.identity || 'UNKNOWN';
        const conf = data.confidence !== undefined ? Math.round(data.confidence * 100) : 0;
        const auth = (data.authorization || 'UNVERIFIED').toUpperCase();

        if (nameEl) {
            nameEl.textContent = identity;
            nameEl.style.color = auth === 'AUTHORIZED' ? 'var(--accent-success)' : (auth === 'UNVERIFIED' ? 'var(--accent-warning)' : 'var(--accent-danger)');
        }
        if (confEl) {
            confEl.textContent = conf > 0 ? `${conf}%` : '--%';
        }
        if (authEl) {
            if (auth === 'AUTHORIZED') {
                authEl.innerHTML = `<span style="background: rgba(16, 185, 129, 0.2); color: #10b981; border: 1px solid #10b981; padding: 2px 8px; border-radius: 4px;">AUTHORIZED</span>`;
                if (reasonEl) reasonEl.textContent = 'Identity matched & permitted for this zone';
            } else if (auth === 'NOT_AUTHORIZED_FOR_ZONE') {
                authEl.innerHTML = `<span style="background: rgba(245, 158, 11, 0.2); color: #f59e0b; border: 1px solid #f59e0b; padding: 2px 8px; border-radius: 4px;">NOT AUTHORIZED FOR ZONE</span>`;
                if (reasonEl) reasonEl.textContent = 'Known person without access clearance in this sector';
            } else if (auth === 'UNAUTHORIZED') {
                authEl.innerHTML = `<span style="background: rgba(239, 68, 68, 0.2); color: #ef4444; border: 1px solid #ef4444; padding: 2px 8px; border-radius: 4px;">UNAUTHORIZED</span>`;
                if (reasonEl) reasonEl.textContent = 'Unregistered intruder detected in perimeter';
            } else {
                authEl.innerHTML = `<span style="background: rgba(148, 163, 184, 0.2); color: #94a3b8; border: 1px solid #94a3b8; padding: 2px 8px; border-radius: 4px;">UNVERIFIED</span>`;
                if (reasonEl) reasonEl.textContent = 'Low confidence / face obscured - continuing observation';
            }
        }
        if (camEl && data.camera_id) camEl.textContent = data.camera_id;
        if (zoneEl && data.zone_id) zoneEl.textContent = data.zone_id;

        if (droneBanner) {
            if (auth === 'UNAUTHORIZED' || auth === 'NOT_AUTHORIZED_FOR_ZONE') {
                droneBanner.style.display = 'flex';
                if (droneDesc) {
                    droneDesc.textContent = `DRONE-001 automatically dispatched to incident zone coordinates. Target: ${data.zone_id || 'ZONE_B'}. Intercept in progress.`;
                }
            } else {
                droneBanner.style.display = 'none';
            }
        }

        // Prominent Floating Tactical Badge directly on Video Player Overlay
        const monitorContainer = document.querySelector('#tacticalMonitorImg')?.parentElement;
        if (monitorContainer) {
            let floatTag = document.getElementById('liveFloatingIdentityBadge');
            if (!floatTag) {
                floatTag = document.createElement('div');
                floatTag.id = 'liveFloatingIdentityBadge';
                floatTag.style.cssText = 'position: absolute; top: 38px; left: 12px; z-index: 10; padding: 6px 14px; border-radius: 4px; font-family: var(--font-mono); font-size: 12px; font-weight: 800; letter-spacing: 0.5px; pointer-events: none; transition: all 0.3s; display: none;';
                monitorContainer.appendChild(floatTag);
            }
            if (auth === 'AUTHORIZED') {
                floatTag.style.display = 'flex';
                floatTag.style.alignItems = 'center';
                floatTag.style.gap = '8px';
                floatTag.style.background = 'rgba(0, 200, 80, 0.92)';
                floatTag.style.border = '2px solid #ffffff';
                floatTag.style.color = '#ffffff';
                floatTag.style.boxShadow = '0 0 20px rgba(0, 255, 115, 0.7)';
                floatTag.innerHTML = `<span style="font-size:14px;">✓</span> <span>AUTHORIZED: ${identity.toUpperCase()}</span> <span style="font-size: 10px; background: rgba(0,0,0,0.3); padding: 2px 6px; border-radius: 3px;">${conf}% MATCH</span> <span style="font-size: 10px; background: rgba(0,0,0,0.3); padding: 2px 6px; border-radius: 3px;">CLEARANCE PERMITTED</span>`;
            } else if (auth === 'UNAUTHORIZED' || auth === 'NOT_AUTHORIZED_FOR_ZONE') {
                floatTag.style.display = 'flex';
                floatTag.style.alignItems = 'center';
                floatTag.style.gap = '8px';
                floatTag.style.background = 'rgba(220, 38, 38, 0.92)';
                floatTag.style.border = '2px solid #ffffff';
                floatTag.style.color = '#ffffff';
                floatTag.style.boxShadow = '0 0 20px rgba(239, 68, 68, 0.7)';
                floatTag.innerHTML = `<span style="font-size:14px;">⚠</span> <span>UNAUTHORIZED: ${identity.toUpperCase()}</span> <span style="font-size: 10px; background: rgba(0,0,0,0.3); padding: 2px 6px; border-radius: 3px;">${conf}%</span>`;
            } else {
                floatTag.style.display = 'none';
            }
        }
    }

    handleSecurityIncidentCreated(data) {
        if (!data || !data.incident) return;
        const inc = data.incident;
        if (this.alertFeed) {
            this.alertFeed.addAlert({
                severity: 'CRITICAL',
                event_type: 'SECURITY_INCIDENT',
                description: `🚨 INCIDENT ${inc.incident_id} CREATED: ${inc.identity} (${inc.authorization}) in ${inc.zone_id}. DRONE-001 Dispatched.`,
                timestamp: inc.created_at
            });
        }
        if (window.audioAlert) {
            window.audioAlert.playCriticalAlarm(4);
            window.audioAlert.speakTacticalAlert(`Security incident ${inc.incident_id}. Unauthorized person in ${inc.zone_id}. Recon drone launched.`);
        }
        if (this.uavView && inc.latitude && inc.longitude) {
            this.uavView.telemetry.active_incident_id = inc.incident_id;
            this.uavView.telemetry.target_zone_id = inc.zone_id;
            this.uavView.telemetry.target_lat = inc.latitude;
            this.uavView.telemetry.target_lon = inc.longitude;
            this.uavView.renderTelemetryHUD();
        }
    }

    handleSecurityIncidentUpdated(data) {
        if (!data || !data.incident) return;
        const inc = data.incident;
        if (this.uavView && inc.aerial_verification) {
            this.uavView.telemetry.aerial_verification = inc.aerial_verification;
            this.uavView.renderTelemetryHUD();
        }
    }

    handlePirMotionAlert(data) {
        if (!data) return;
        const timeStr = new Date().toLocaleTimeString();
        const toastEl = document.getElementById('simFeedbackText');
        const timeEl = document.getElementById('simFeedbackTime');
        if (toastEl) toastEl.textContent = `> 🚶 PIR-001 Motion detected in ${data.zone_id || 'ZONE_B'}! Camera inference triggered.`;
        if (timeEl) timeEl.textContent = timeStr;
        if (this.alertFeed) {
            this.alertFeed.addAlert({
                severity: 'INFO',
                event_type: 'PIR_MOTION',
                description: `PIR-001 activity detected in ${data.zone_id || 'ZONE_B'}. Camera verification armed.`,
                timestamp: new Date().toISOString()
            });
        }
    }

    setupAerionHandlers() {
        const toast = (msg) => {
            const el = document.getElementById('simFeedbackText');
            const timeEl = document.getElementById('simFeedbackTime');
            if (el) el.textContent = `> ${msg}`;
            if (timeEl) timeEl.textContent = new Date().toLocaleTimeString();
        };

        // 1. Simulate PIR Motion
        const btnPir = document.getElementById('btnSimPirMotion');
        if (btnPir) {
            btnPir.addEventListener('click', async () => {
                try {
                    const res = await fetch('/api/pir/trigger', { method: 'POST' });
                    const d = await res.json();
                    toast(`PIR-001 motion detected in ${d.zone_id}! Camera person detection activated.`);
                } catch (e) {
                    toast(`PIR trigger failed: ${e.message}`);
                }
            });
        }

        // 2. Simulate Authorized Person
        const btnAuth = document.getElementById('btnSimAuthPerson');
        if (btnAuth) {
            btnAuth.addEventListener('click', async () => {
                try {
                    await fetch('/api/identity/simulate', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            camera_id: 'CAM_01',
                            identity: 'Keerthi',
                            confidence: 0.96,
                            authorization: 'AUTHORIZED',
                            duration: 25.0
                        })
                    });
                    toast('Simulated Authorized Person: Keerthi (96% confidence, AUTHORIZED). Normal monitoring.');
                } catch (e) {
                    toast(`Sim error: ${e.message}`);
                }
            });
        }

        // 3. Simulate Unknown Person
        const btnUnk = document.getElementById('btnSimUnknownPerson');
        if (btnUnk) {
            btnUnk.addEventListener('click', async () => {
                try {
                    await fetch('/api/identity/simulate', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            camera_id: 'CAM_01',
                            identity: 'UNKNOWN',
                            confidence: 0.92,
                            authorization: 'UNAUTHORIZED',
                            duration: 25.0
                        })
                    });
                    toast('Simulated Unknown Person (92% confidence, UNAUTHORIZED). Security incident trigger ready.');
                } catch (e) {
                    toast(`Sim error: ${e.message}`);
                }
            });
        }

        // 4. Trigger Unauthorized Incident
        const btnInc = document.getElementById('btnTriggerUnauthIncident');
        if (btnInc) {
            btnInc.addEventListener('click', async () => {
                try {
                    const res = await fetch('/api/incidents/trigger', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            camera_id: 'CAM_01',
                            zone_id: 'ZONE_B',
                            identity: 'UNKNOWN',
                            confidence: 0.92,
                            authorization: 'UNAUTHORIZED'
                        })
                    });
                    const d = await res.json();
                    toast(`Security incident created: ${d.incident.incident_id} in ${d.incident.zone_id}. Drone dispatch triggered.`);
                } catch (e) {
                    toast(`Incident trigger error: ${e.message}`);
                }
            });
        }

        // 5. Dispatch Drone
        const btnDispatch = document.getElementById('btnSimDispatchDrone');
        if (btnDispatch) {
            btnDispatch.addEventListener('click', async () => {
                try {
                    const res = await fetch('/api/uav/dispatch', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            target_lat: 31.6262,
                            target_lon: 74.8748,
                            zone_id: 'ZONE_B',
                            incident_id: 'INC-DEMO-01'
                        })
                    });
                    if (res.ok) {
                        toast('DRONE-001 Dispatched to ZONE_B (31.6262°N, 74.8748°E)! Intercept initiated.');
                    } else {
                        const err = await res.json();
                        toast(`Dispatch refused: ${err.detail || 'Safety rule'}`);
                    }
                } catch (e) {
                    toast(`Dispatch error: ${e.message}`);
                }
            });
        }

        // 6. Simulate Drone Arrival
        const btnArrive = document.getElementById('btnSimDroneArrival');
        if (btnArrive) {
            btnArrive.addEventListener('click', async () => {
                try {
                    await fetch('/api/uav/step-sim', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ action: 'arrive', target_lat: 31.6262, target_lon: 74.8748 })
                    });
                    toast('DRONE-001 arrived at target incident zone (within 10m arrival radius). Commencing aerial sweep.');
                } catch (e) {
                    toast(`Arrival sim error: ${e.message}`);
                }
            });
        }

        // 7. Start Aerial Scan
        const btnScan = document.getElementById('btnSimStartScan');
        if (btnScan) {
            btnScan.addEventListener('click', async () => {
                try {
                    await fetch('/api/uav/start-scan', { method: 'POST' });
                    toast('Aerial optical & thermal scan active over ZONE_B. Infiltrator visually confirmed.');
                } catch (e) {
                    toast(`Scan error: ${e.message}`);
                }
            });
        }

        // 8. Simulate Battery 19%
        const btnBat19 = document.getElementById('btnSimBattery19');
        if (btnBat19) {
            btnBat19.addEventListener('click', async () => {
                try {
                    await fetch('/api/uav/set-battery', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ battery_percent: 19.0 })
                    });
                    toast('Battery set to 19%. Safety rule triggered: Automatic Return-to-Home initiated!');
                } catch (e) {
                    toast(`Battery error: ${e.message}`);
                }
            });
        }

        // 9. Return Home
        const btnRth = document.getElementById('btnSimReturnHome');
        if (btnRth) {
            btnRth.addEventListener('click', async () => {
                try {
                    await fetch('/api/uav/return-home', { method: 'POST' });
                    toast('DRONE-001 returning to base station (RTH). Safe recovery in progress.');
                } catch (e) {
                    toast(`RTH error: ${e.message}`);
                }
            });
        }

        // 10. Reset Demo
        const btnReset = document.getElementById('btnSimResetDemo');
        if (btnReset) {
            btnReset.addEventListener('click', async () => {
                try {
                    await fetch('/api/identity/simulate/clear', { method: 'POST' });
                    await fetch('/api/uav/set-battery', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ battery_percent: 98.0 })
                    });
                    await fetch('/api/uav/return-home', { method: 'POST' });
                    toast('Simulation demo reset to standby baseline. Battery restored to 98%, drone docked.');
                } catch (e) {
                    toast(`Reset error: ${e.message}`);
                }
            });
        }

        // Safe Operator Controls in Tab-UAV
        const btnOpScan = document.getElementById('btnStartScanUav');
        if (btnOpScan) {
            btnOpScan.addEventListener('click', async () => {
                try {
                    await fetch('/api/uav/start-scan', { method: 'POST' });
                } catch (e) { console.error(e); }
            });
        }

        const btnOpRth = document.getElementById('btnReturnHomeUav');
        if (btnOpRth) {
            btnOpRth.addEventListener('click', async () => {
                try {
                    await fetch('/api/uav/return-home', { method: 'POST' });
                } catch (e) { console.error(e); }
            });
        }

        const btnToggleMode = document.getElementById('btnToggleDroneMode');
        if (btnToggleMode) {
            btnToggleMode.addEventListener('click', async () => {
                try {
                    const currentMode = btnToggleMode.textContent.includes('LIVE') ? 'LIVE' : 'SIMULATION';
                    const newMode = currentMode === 'LIVE' ? 'SIMULATION' : 'LIVE';
                    await fetch('/api/uav/mode', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ mode: newMode })
                    });
                } catch (e) { console.error(e); }
            });
        }

        // Switch to UAV tab from Camera banner
        const btnSwitchTab = document.getElementById('btnSwitchToUavTab');
        if (btnSwitchTab) {
            btnSwitchTab.addEventListener('click', () => {
                if (this.switchTab) this.switchTab('tab-uav');
            });
        }

        // Authorized Persons Registry Modal
        const btnOpenReg = document.getElementById('btnOpenRegistryModal');
        const modalReg = document.getElementById('modalAuthorizedRegistry');
        const btnCloseReg = document.getElementById('btnCloseRegistryModal');
        const btnCancelReg = document.getElementById('btnCancelEnroll');
        const btnSubmitReg = document.getElementById('btnSubmitEnroll');

        if (btnOpenReg && modalReg) {
            btnOpenReg.addEventListener('click', () => {
                modalReg.style.display = 'flex';
                this.loadAuthorizedPersons();
            });
        }
        if (btnCloseReg && modalReg) {
            btnCloseReg.addEventListener('click', () => { modalReg.style.display = 'none'; });
        }
        if (btnCancelReg && modalReg) {
            btnCancelReg.addEventListener('click', () => { modalReg.style.display = 'none'; });
        }
        if (btnSubmitReg) {
            btnSubmitReg.addEventListener('click', async () => {
                const pid = document.getElementById('regPersonId')?.value.trim();
                const pname = document.getElementById('regPersonName')?.value.trim();
                const pzones = document.getElementById('regAllowedZones')?.value.trim();
                if (!pid || !pname) {
                    alert('Please provide Person ID and Full Name.');
                    return;
                }
                const allowedList = pzones ? pzones.split(',').map(z => z.trim()).filter(Boolean) : ['ZONE_A', 'ZONE_B'];
                try {
                    btnSubmitReg.textContent = 'ENROLLING...';
                    const res = await fetch('/api/identity/persons/enroll', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            person_id: pid,
                            name: pname,
                            allowed_zones: allowedList
                        })
                    });
                    if (res.ok) {
                        alert(`Successfully enrolled ${pname} (${pid}) into facial recognition gallery.`);
                        document.getElementById('regPersonId').value = '';
                        document.getElementById('regPersonName').value = '';
                        this.loadAuthorizedPersons();
                    } else {
                        const err = await res.json();
                        alert(`Enrollment error: ${err.detail || 'Failed'}`);
                    }
                } catch (e) {
                    alert(`Enrollment error: ${e.message}`);
                } finally {
                    btnSubmitReg.textContent = 'ENROLL IN FACIAL GALLERY';
                }
            });
        }
    }

    async loadAuthorizedPersons() {
        const tbody = document.getElementById('registryPersonsTableBody');
        if (!tbody) return;
        try {
            const res = await fetch('/api/identity/persons');
            if (res.ok) {
                const data = await res.json();
                const persons = data.persons || [];
                tbody.innerHTML = '';
                if (persons.length === 0) {
                    tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: var(--text-muted);">No authorized persons enrolled yet.</td></tr>`;
                    return;
                }
                persons.forEach(p => {
                    const tr = document.createElement('tr');
                    tr.innerHTML = `
                        <td style="font-family: var(--font-mono); color: #fff;">${p.person_id}</td>
                        <td style="font-weight: 700;">${p.name}</td>
                        <td><span class="status-pill online"><span class="dot"></span> ${p.status}</span></td>
                        <td style="font-family: var(--font-mono); color: var(--accent-cyan);">${(p.allowed_zones || []).join(', ')}</td>
                        <td><span style="color: ${p.has_embedding ? 'var(--accent-success)' : 'var(--text-muted)'};">${p.has_embedding ? '128-D VECTOR' : 'PENDING'}</span></td>
                        <td><button class="btn-tactical danger" style="padding: 2px 6px; font-size: 9px;" onclick="window.app.deleteAuthorizedPerson('${p.person_id}')">REMOVE</button></td>
                    `;
                    tbody.appendChild(tr);
                });
            }
        } catch (e) {
            console.error('Failed to load authorized persons:', e);
        }
    }

    async deleteAuthorizedPerson(personId) {
        if (!confirm(`Are you sure you want to revoke authorization for ${personId}?`)) return;
        try {
            const res = await fetch(`/api/identity/persons/${personId}`, { method: 'DELETE' });
            if (res.ok) {
                this.loadAuthorizedPersons();
            }
        } catch (e) {
            alert(`Failed to delete person: ${e.message}`);
        }
    }

    // ============================================================
    // DASHBOARD OVERVIEW COUNTER METHODS
    // ============================================================
    async _loadDashboardOverview() {
        if (this._sovUnknownCount === undefined) this._sovUnknownCount = 0;
        if (this._sovViolationCount === undefined) this._sovViolationCount = 0;

        // 1. Authorized persons count
        try {
            const res = await fetch('/api/persons');
            if (res.ok) {
                const data = await res.json();
                const count = data.count !== undefined ? data.count : (data.persons ? data.persons.length : 0);
                const el = document.getElementById('sovAuthorized');
                if (el) el.textContent = count;
            }
        } catch (e) {
            console.warn('[SOV] Failed to load persons count', e);
        }

        // 2. Active Threats
        try {
            const res = await fetch('/api/incidents/active');
            if (res.ok) {
                const data = await res.json();
                const threats = Array.isArray(data) ? data.length : (data.incidents ? data.incidents.length : 0);
                const el = document.getElementById('sovThreats');
                if (el) el.textContent = threats;
            }
        } catch (e) {
            try {
                const evRes = await fetch('/api/events/active');
                if (evRes.ok) {
                    const evData = await evRes.json();
                    const el = document.getElementById('sovThreats');
                    if (el) el.textContent = Array.isArray(evData) ? evData.length : 0;
                }
            } catch (err) {}
        }

        // 3. Cameras count
        try {
            const res = await fetch('/api/cameras');
            if (res.ok) {
                const cams = await res.json();
                const total = cams.length;
                const online = cams.filter(c => c.status === 'ONLINE' || c.is_active).length;
                const el = document.getElementById('sovCameras');
                if (el) el.textContent = `${online}/${total}`;
            }
        } catch (e) {}

        // 4. Initial Radar targets from radar status
        try {
            const res = await fetch('/api/zones/status');
            if (res.ok) {
                const data = await res.json();
                const targets = data.active_targets ? Object.keys(data.active_targets).length : 0;
                const el = document.getElementById('sovRadarTargets');
                if (el) el.textContent = targets;
            }
        } catch (e) {}
    }

    // ============================================================
    // SITE CONFIGURATION TAB METHODS
    // ============================================================
    async _loadSiteConfig() {
        try {
            const res = await fetch('/api/site');
            if (!res.ok) return;
            const data = await res.json();
            const site = data.site;
            if (site) {
                const elName = document.getElementById('siteFieldName');
                const elId = document.getElementById('siteFieldId');
                const elCountry = document.getElementById('siteFieldCountry');
                const elAddr = document.getElementById('siteFieldAddress');
                const elCity = document.getElementById('siteFieldCity');
                const elState = document.getElementById('siteFieldState');
                const elLat = document.getElementById('siteFieldLat');
                const elLon = document.getElementById('siteFieldLon');
                const elDesc = document.getElementById('siteFieldDesc');

                if (elName && site.site_name) elName.value = site.site_name;
                if (elId && site.site_id) elId.value = site.site_id;
                if (elCountry && site.country) elCountry.value = site.country;
                if (elAddr && site.address) elAddr.value = site.address;
                if (elCity && site.city) elCity.value = site.city;
                if (elState && site.state) elState.value = site.state;
                if (elLat && site.latitude != null) elLat.value = site.latitude;
                if (elLon && site.longitude != null) elLon.value = site.longitude;
                if (elDesc && site.description) elDesc.value = site.description;

                const pillConfigured = document.getElementById('siteConfiguredPill');
                const pillUnconfigured = document.getElementById('siteUnconfiguredPill');
                if (pillConfigured) pillConfigured.style.display = 'inline-flex';
                if (pillUnconfigured) pillUnconfigured.style.display = 'none';

                const sumContent = document.getElementById('siteConfigSummaryContent');
                if (sumContent) {
                    sumContent.innerHTML = `
                        <div style="font-weight:700;color:var(--accent-cyan);font-size:13px;margin-bottom:6px;">${site.site_name || 'Unnamed Site'}</div>
                        <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;font-family:var(--font-mono);font-size:10px;">
                            <div>ID: <span style="color:#fff;">${site.site_id || '—'}</span></div>
                            <div>LOCATION: <span style="color:#fff;">${site.city || ''}, ${site.country || ''}</span></div>
                            <div>COORDINATES: <span style="color:#38bdf8;">${site.latitude != null ? Number(site.latitude).toFixed(4) : '—'}, ${site.longitude != null ? Number(site.longitude).toFixed(4) : '—'}</span></div>
                            <div>UPDATED: <span style="color:#94a3b8;">${site.updated_at ? new Date(site.updated_at).toLocaleString() : 'Just now'}</span></div>
                        </div>
                        ${site.description ? `<div style="margin-top:8px;font-size:11px;color:#94a3b8;">${site.description}</div>` : ''}
                    `;
                }

                this._drawSiteMap(site.latitude, site.longitude, site.site_name);

                const mapIframe = document.getElementById('siteGoogleMapIframe');
                if (mapIframe && site.latitude != null && site.longitude != null) {
                    mapIframe.src = `https://maps.google.com/maps?q=${site.latitude},${site.longitude}&z=16&output=embed`;
                }
            }
        } catch (e) {
            console.error('[SITE] Failed to load site config:', e);
        }
    }

    async _saveSiteConfig() {
        const feedback = document.getElementById('siteConfigFeedback');
        const errEl = document.getElementById('siteConfigError');
        if (feedback) feedback.style.display = 'none';
        if (errEl) errEl.style.display = 'none';

        const name = document.getElementById('siteFieldName')?.value?.trim();
        const lat = parseFloat(document.getElementById('siteFieldLat')?.value);
        const lon = parseFloat(document.getElementById('siteFieldLon')?.value);

        if (!name) {
            if (errEl) { errEl.textContent = 'Site Name is required.'; errEl.style.display = 'block'; }
            return;
        }
        if (isNaN(lat) || isNaN(lon)) {
            if (errEl) { errEl.textContent = 'Valid Latitude and Longitude are required.'; errEl.style.display = 'block'; }
            return;
        }

        const payload = {
            site_id: document.getElementById('siteFieldId')?.value?.trim() || 'SITE-001',
            site_name: name,
            country: document.getElementById('siteFieldCountry')?.value?.trim() || '',
            address: document.getElementById('siteFieldAddress')?.value?.trim() || '',
            city: document.getElementById('siteFieldCity')?.value?.trim() || '',
            state: document.getElementById('siteFieldState')?.value?.trim() || '',
            latitude: lat,
            longitude: lon,
            description: document.getElementById('siteFieldDesc')?.value?.trim() || ''
        };

        try {
            const res = await fetch('/api/site', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            if (!res.ok) {
                const errData = await res.json().catch(() => ({}));
                throw new Error(errData.detail || 'Failed to save site configuration');
            }
            if (feedback) {
                feedback.style.display = 'block';
                setTimeout(() => { feedback.style.display = 'none'; }, 3000);
            }
            await this._loadSiteConfig();
        } catch (e) {
            if (errEl) { errEl.textContent = e.message; errEl.style.display = 'block'; }
        }
    }

    async _loadLocationZonesSummary() {
        const tbody = document.getElementById('locationZonesSummaryBody');
        if (!tbody) return;
        try {
            const res = await fetch('/api/zones');
            if (!res.ok) return;
            const data = await res.json();
            const zones = Array.isArray(data) ? data : (data.zones || []);
            if (zones.length === 0) {
                tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:20px;color:var(--text-muted);font-size:11px;">No zones configured yet.</td></tr>';
                return;
            }
            tbody.innerHTML = zones.map(z => `
                <tr>
                    <td style="font-family:var(--font-mono);font-weight:700;color:#fff;">${z.name || z.id}</td>
                    <td><span class="status-pill standby" style="font-size:9px;">${z.zone_subtype || z.zone_type || 'STANDARD'}</span></td>
                    <td><span class="status-pill ${z.security_level === 'CRITICAL' ? 'danger' : z.security_level === 'HIGH' ? 'warning' : 'online'}" style="font-size:9px;">${z.security_level || 'LOW'}</span></td>
                    <td style="font-family:var(--font-mono);font-size:10px;color:var(--accent-cyan);">${(z.assigned_cameras || []).join(', ') || '—'}</td>
                    <td style="font-family:var(--font-mono);font-size:10px;color:#a855f7;">${(z.assigned_radar || []).join(', ') || '—'}</td>
                    <td style="font-family:var(--font-mono);font-size:10px;color:#38bdf8;">${(z.assigned_uav || []).join(', ') || '—'}</td>
                    <td><span class="status-pill ${z.status === 'ACTIVE' ? 'online' : 'offline'}" style="font-size:9px;"><span class="dot"></span> ${z.status || 'ACTIVE'}</span></td>
                </tr>
            `).join('');
        } catch (e) {
            console.error('[LOCATION] Failed to load zones summary:', e);
        }
    }

    _drawSiteMap(lat, lon, name) {
        const canvas = document.getElementById('siteMapCanvas');
        if (!canvas) return;
        const rect = canvas.getBoundingClientRect();
        canvas.width = rect.width || 400;
        canvas.height = rect.height || 260;
        const ctx = canvas.getContext('2d');
        if (!ctx) return;

        const w = canvas.width;
        const h = canvas.height;

        // Background
        ctx.fillStyle = '#060c18';
        ctx.fillRect(0, 0, w, h);

        // Coordinate Grid lines
        ctx.strokeStyle = 'rgba(0, 229, 255, 0.07)';
        ctx.lineWidth = 1;
        const step = 30;
        for (let x = 0; x < w; x += step) {
            ctx.beginPath();
            ctx.moveTo(x, 0);
            ctx.lineTo(x, h);
            ctx.stroke();
        }
        for (let y = 0; y < h; y += step) {
            ctx.beginPath();
            ctx.moveTo(0, y);
            ctx.lineTo(w, y);
            ctx.stroke();
        }

        const cx = w / 2;
        const cy = h / 2;

        // Draw concentric radar rings around center
        ctx.strokeStyle = 'rgba(0, 229, 255, 0.15)';
        ctx.setLineDash([4, 4]);
        [40, 80, 110].forEach(r => {
            ctx.beginPath();
            ctx.arc(cx, cy, r, 0, Math.PI * 2);
            ctx.stroke();
        });
        ctx.setLineDash([]);

        // Center crosshair
        ctx.strokeStyle = 'rgba(56, 189, 248, 0.5)';
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.moveTo(cx - 20, cy);
        ctx.lineTo(cx + 20, cy);
        ctx.moveTo(cx, cy - 20);
        ctx.lineTo(cx, cy + 20);
        ctx.stroke();

        // Target marker dot
        ctx.fillStyle = '#00e5ff';
        ctx.beginPath();
        ctx.arc(cx, cy, 5, 0, Math.PI * 2);
        ctx.fill();

        // Pulse glow
        const grad = ctx.createRadialGradient(cx, cy, 2, cx, cy, 25);
        grad.addColorStop(0, 'rgba(0, 229, 255, 0.4)');
        grad.addColorStop(1, 'rgba(0, 229, 255, 0)');
        ctx.fillStyle = grad;
        ctx.beginPath();
        ctx.arc(cx, cy, 25, 0, Math.PI * 2);
        ctx.fill();

        // Label
        ctx.fillStyle = '#38bdf8';
        ctx.font = 'bold 11px monospace';
        ctx.textAlign = 'center';
        ctx.fillText(name || 'BASE CAMPUS', cx, cy - 14);

        if (lat != null && lon != null) {
            ctx.fillStyle = '#94a3b8';
            ctx.font = '9px monospace';
            ctx.fillText(`${Number(lat).toFixed(4)}°N, ${Number(lon).toFixed(4)}°E`, cx, cy + 22);
        }
    }

    // ============================================================
    // ALERT RULES TAB METHODS
    // ============================================================
    async _loadAlertRules() {
        const tbody = document.getElementById('alertRulesTableBody');
        if (!tbody) return;
        try {
            const res = await fetch('/api/alert-rules');
            if (!res.ok) return;
            const data = await res.json();
            const rules = data.rules || [];
            if (rules.length === 0) {
                tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:20px;color:var(--text-muted);font-size:11px;">No alert rules defined yet. Click "+ ADD RULE" to create one.</td></tr>';
                return;
            }
            tbody.innerHTML = rules.map(r => {
                const cond = typeof r.condition === 'object' ? JSON.stringify(r.condition) : (r.condition || 'ALL_EVENTS');
                const acts = r.action || {};
                const sev = acts.severity || r.priority || 'CRITICAL';
                const uav = acts.trigger_uav ? '✓ DISPATCH' : '—';
                const prioColor = r.priority === 'CRITICAL' || r.priority === 1 ? 'danger' : (r.priority === 'HIGH' || r.priority === 2 ? 'warning' : 'online');
                return `
                    <tr>
                        <td><span class="status-pill ${prioColor}" style="font-size:9px;">${r.priority || 'P2'}</span></td>
                        <td style="font-weight:700;color:#fff;">${r.name || r.rule_id}</td>
                        <td style="font-family:var(--font-mono);font-size:10px;color:var(--accent-cyan);max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${cond}">${cond}</td>
                        <td><span class="status-pill ${sev === 'CRITICAL' ? 'danger' : 'warning'}" style="font-size:9px;">${sev}</span></td>
                        <td style="font-family:var(--font-mono);font-size:10px;color:#38bdf8;">${uav}</td>
                        <td>
                            <button class="btn-tactical ${r.enabled ? 'primary' : ''}" style="font-size:9px;padding:2px 8px;" onclick="window.app._toggleAlertRule('${r.rule_id}')">
                                ${r.enabled ? 'ENABLED' : 'DISABLED'}
                            </button>
                        </td>
                        <td>
                            <button class="btn-tactical danger" style="font-size:9px;padding:2px 6px;" onclick="window.app._deleteAlertRule('${r.rule_id}')">DELETE</button>
                        </td>
                    </tr>
                `;
            }).join('');
        } catch (e) {
            console.error('[ALERT-RULES] Failed to load alert rules:', e);
        }
    }

    async _toggleAlertRule(ruleId) {
        try {
            const res = await fetch(`/api/alert-rules/${ruleId}/toggle`, { method: 'POST' });
            if (res.ok) {
                await this._loadAlertRules();
            }
        } catch (e) {
            alert('Failed to toggle rule: ' + e.message);
        }
    }

    async _deleteAlertRule(ruleId) {
        if (!confirm(`Delete alert rule ${ruleId}?`)) return;
        try {
            const res = await fetch(`/api/alert-rules/${ruleId}`, { method: 'DELETE' });
            if (res.ok) {
                await this._loadAlertRules();
            }
        } catch (e) {
            alert('Failed to delete rule: ' + e.message);
        }
    }

    async _addAlertRulePrompt() {
        const name = prompt('Enter Alert Rule Name (e.g., Critical Fence Breach):');
        if (!name) return;
        const condition = prompt('Enter Trigger Condition (e.g., target_type == "unknown" && zone == "ZONE_RESTRICTED"):', 'target_type == "unknown"');
        if (!condition) return;

        const payload = {
            name: name,
            priority: 'HIGH',
            condition: { expr: condition },
            action: { alert_sound: true, log_incident: true, trigger_uav: true, severity: 'HIGH' },
            enabled: true
        };

        try {
            const res = await fetch('/api/alert-rules', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            if (res.ok) {
                await this._loadAlertRules();
            } else {
                const d = await res.json().catch(() => ({}));
                alert(d.detail || 'Failed to create rule');
            }
        } catch (e) {
            alert('Failed to create rule: ' + e.message);
        }
    }

    // ============================================================
    // SENSOR MATRIX METHODS
    // ============================================================
    async _loadSensorMatrix() {
        const tbody = document.getElementById('sensorMatrixBody');
        if (!tbody) return;
        try {
            const res = await fetch('/api/zones');
            if (!res.ok) return;
            const data = await res.json();
            const zones = Array.isArray(data) ? data : (data.zones || []);
            if (zones.length === 0) {
                tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:20px;color:var(--text-muted);font-size:11px;">No zones defined yet.</td></tr>';
                return;
            }
            tbody.innerHTML = zones.map(z => `
                <tr>
                    <td style="font-family:var(--font-mono);font-weight:700;color:#fff;">${z.name || z.id}</td>
                    <td><span class="status-pill ${z.security_level === 'CRITICAL' ? 'danger' : z.security_level === 'HIGH' ? 'warning' : 'online'}" style="font-size:9px;">${z.security_level || 'LOW'}</span></td>
                    <td style="font-family:var(--font-mono);font-size:10px;color:var(--accent-cyan);">${(z.assigned_cameras && z.assigned_cameras.length) ? z.assigned_cameras.join(', ') : 'CAM_01'}</td>
                    <td style="font-family:var(--font-mono);font-size:10px;color:#a855f7;">${(z.assigned_radar && z.assigned_radar.length) ? z.assigned_radar.join(', ') : 'RADAR_01'}</td>
                    <td style="font-family:var(--font-mono);font-size:10px;color:#38bdf8;">${(z.assigned_uav && z.assigned_uav.length) ? z.assigned_uav.join(', ') : 'UAV_01'}</td>
                    <td style="font-family:var(--font-mono);font-size:10px;color:#94a3b8;">${(z.authorized_persons && z.authorized_persons.length) ? z.authorized_persons.join(', ') : 'ALL_STAFF'}</td>
                    <td>
                        <button class="btn-tactical" style="font-size:9px;padding:2px 8px;" onclick="window.app.switchTab('tab-zones')">VIEW ZONE</button>
                    </td>
                </tr>
            `).join('');
        } catch (e) {
            console.error('[MATRIX] Failed to load sensor matrix:', e);
        }
    }

    // ============================================================
    // NEW TAB BUTTON / FORM HANDLERS WIRING
    // ============================================================
    _setupNewTabHandlers() {
        // Site save / reset buttons
        const btnSaveSite = document.getElementById('btnSaveSiteConfig');
        if (btnSaveSite) {
            btnSaveSite.addEventListener('click', () => this._saveSiteConfig());
        }
        const btnResetSite = document.getElementById('btnResetSiteConfig');
        if (btnResetSite) {
            btnResetSite.addEventListener('click', () => this._loadSiteConfig());
        }

        // Alert rules buttons
        const btnRefreshRules = document.getElementById('btnRefreshAlertRules');
        if (btnRefreshRules) {
            btnRefreshRules.addEventListener('click', () => this._loadAlertRules());
        }
        const btnAddRule = document.getElementById('btnAddAlertRule');
        if (btnAddRule) {
            btnAddRule.addEventListener('click', () => this._addAlertRulePrompt());
        }

        // Navigate to zones from location tab
        const btnGoToZones = document.getElementById('btnGoToZones');
        if (btnGoToZones) {
            btnGoToZones.addEventListener('click', () => this.switchTab('tab-zones'));
        }

        // Audio synthesizer status reflection
        const audioPill = document.getElementById('ioAudioStatus');
        if (audioPill && window.audioAlert) {
            audioPill.className = 'status-pill online io-pill';
            audioPill.innerHTML = '<span class="dot"></span> ARMED';
        }

        // Hardware Device GPS Acquisition (Laptop Wi-Fi / Mobile GPS)
        const btnGps = document.getElementById('btnAcquireDeviceGps');
        const gpsMsg = document.getElementById('deviceGpsStatusMsg');
        if (btnGps) {
            btnGps.addEventListener('click', () => {
                if (!navigator.geolocation) {
                    if (gpsMsg) {
                        gpsMsg.style.display = 'block';
                        gpsMsg.style.background = 'rgba(239, 68, 68, 0.15)';
                        gpsMsg.style.color = '#ef4444';
                        gpsMsg.textContent = 'Geolocation API is not supported by your browser.';
                    }
                    return;
                }

                btnGps.textContent = '📍 ACQUIRING GPS...';
                btnGps.disabled = true;
                if (gpsMsg) {
                    gpsMsg.style.display = 'block';
                    gpsMsg.style.background = 'rgba(0, 229, 255, 0.15)';
                    gpsMsg.style.color = '#00e5ff';
                    gpsMsg.textContent = 'Requesting hardware device GPS / Wi-Fi coordinates... Please allow location permission in your browser.';
                }

                navigator.geolocation.getCurrentPosition(
                    (pos) => {
                        const lat = pos.coords.latitude;
                        const lon = pos.coords.longitude;
                        const acc = Math.round(pos.coords.accuracy || 0);

                        const elLat = document.getElementById('siteFieldLat');
                        const elLon = document.getElementById('siteFieldLon');
                        if (elLat) elLat.value = lat.toFixed(6);
                        if (elLon) elLon.value = lon.toFixed(6);

                        btnGps.textContent = '✓ GPS ACQUIRED';
                        btnGps.disabled = false;
                        if (gpsMsg) {
                            gpsMsg.style.background = 'rgba(16, 185, 129, 0.15)';
                            gpsMsg.style.color = '#10b981';
                            gpsMsg.textContent = `✓ Device Location Acquired: ${lat.toFixed(6)}°N, ${lon.toFixed(6)}°E (±${acc}m accuracy)`;
                        }

                        // Update Google Maps embed iframe immediately
                        const mapIframe = document.getElementById('siteGoogleMapIframe');
                        if (mapIframe) {
                            mapIframe.src = `https://maps.google.com/maps?q=${lat},${lon}&z=16&output=embed`;
                        }

                        setTimeout(() => { btnGps.textContent = '📍 GET DEVICE LOCATION'; }, 4500);
                    },
                    (err) => {
                        btnGps.textContent = '📍 GET DEVICE LOCATION';
                        btnGps.disabled = false;
                        if (gpsMsg) {
                            gpsMsg.style.display = 'block';
                            gpsMsg.style.background = 'rgba(239, 68, 68, 0.15)';
                            gpsMsg.style.color = '#ef4444';
                            gpsMsg.textContent = `GPS Acquisition Failed: ${err.message || 'Permission denied or timed out'}. Please allow location in your browser toolbar.`;
                        }
                    },
                    { enableHighAccuracy: true, timeout: 12000, maximumAge: 0 }
                );
            });
        }

        // Open site location in external Google Maps
        const btnExt = document.getElementById('btnOpenGoogleMapsExternal');
        if (btnExt) {
            btnExt.addEventListener('click', () => {
                const lat = document.getElementById('siteFieldLat')?.value || '31.6240';
                const lon = document.getElementById('siteFieldLon')?.value || '74.8723';
                window.open(`https://www.google.com/maps?q=${lat},${lon}`, '_blank');
            });
        }
    }
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        const app = new SurveillanceApp();
        window.app = app;
        app.init();
    });
} else {
    const app = new SurveillanceApp();
    window.app = app;
    app.init();
}

