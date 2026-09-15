/**
 * Autonomous UAV (UAV_01) Reconnaissance Tactical HUD and Waypoint Tracker
 * Renders real-time flight telemetry, waypoint map, and FLIR optical HUD overlay.
 */

export class UAVView {
    constructor() {
        this.mapCanvas = document.getElementById('uavWaypointCanvas');
        this.hudCanvas = document.getElementById('uavHudCanvas');
        this.mapCtx = this.mapCanvas ? this.mapCanvas.getContext('2d') : null;
        this.hudCtx = this.hudCanvas ? this.hudCanvas.getContext('2d') : null;

        this.telemetry = {
            uav_id: 'UAV_01',
            state: 'UAV_STANDBY',
            current_zone: 'BASE',
            battery_percent: 100.0,
            altitude_m: 0.0,
            speed_mps: 0.0,
            latitude: 31.6240,
            longitude: 74.8723,
            reason: 'Standby at Base Station'
        };

        this.baseCoords = { lat: 31.6240, lon: 74.8723 };
        this.waypoints = {
            'BASE': { lat: 31.6240, lon: 74.8723, label: 'BASE OUTPOST' },
            'ZONE_A': { lat: 31.6248, lon: 74.8735, label: 'ZONE_A (OUTER)' },
            'ZONE_B': { lat: 31.6262, lon: 74.8748, label: 'ZONE_B (WARNING)' },
            'ZONE_C': { lat: 31.6280, lon: 74.8765, label: 'ZONE_C (RESTRICTED)' }
        };

        this.flightTrail = [];
        this.pitchOffset = 0;
        this.targetLockBlink = 0;

        this.initCanvases();
        this.startRenderLoops();
    }

    initCanvases() {
        if (this.mapCanvas) {
            const r = this.mapCanvas.getBoundingClientRect();
            const dpr = window.devicePixelRatio || 1;
            this.mapCanvas.width = (r.width || 450) * dpr;
            this.mapCanvas.height = (r.height || 260) * dpr;
            if (this.mapCtx) this.mapCtx.scale(dpr, dpr);
            this.mapWidth = r.width || 450;
            this.mapHeight = r.height || 260;
        }

        if (this.hudCanvas) {
            const r = this.hudCanvas.getBoundingClientRect();
            const dpr = window.devicePixelRatio || 1;
            this.hudCanvas.width = (r.width || 450) * dpr;
            this.hudCanvas.height = (r.height || 240) * dpr;
            if (this.hudCtx) this.hudCtx.scale(dpr, dpr);
            this.hudWidth = r.width || 450;
            this.hudHeight = r.height || 240;
        }

        window.addEventListener('resize', () => {
            if (this.mapCanvas) {
                const r = this.mapCanvas.getBoundingClientRect();
                if (r.width > 0 && r.height > 0) {
                    this.mapCanvas.width = r.width * (window.devicePixelRatio || 1);
                    this.mapCanvas.height = r.height * (window.devicePixelRatio || 1);
                    this.mapCtx.scale(window.devicePixelRatio || 1, window.devicePixelRatio || 1);
                    this.mapWidth = r.width;
                    this.mapHeight = r.height;
                }
            }
            if (this.hudCanvas) {
                const r = this.hudCanvas.getBoundingClientRect();
                if (r.width > 0 && r.height > 0) {
                    this.hudCanvas.width = r.width * (window.devicePixelRatio || 1);
                    this.hudCanvas.height = r.height * (window.devicePixelRatio || 1);
                    this.hudCtx.scale(window.devicePixelRatio || 1, window.devicePixelRatio || 1);
                    this.hudWidth = r.width;
                    this.hudHeight = r.height;
                }
            }
        });
    }

    updateTelemetry(t) {
        if (!t) return;
        const prevState = this.telemetry.state;
        this.telemetry = { ...this.telemetry, ...t };

        // Save flight trail point
        if (this.telemetry.state !== 'UAV_STANDBY') {
            this.flightTrail.push({ lat: this.telemetry.latitude, lon: this.telemetry.longitude });
            if (this.flightTrail.length > 50) this.flightTrail.shift();
        } else {
            this.flightTrail = [];
        }

        this.renderTelemetryHUD();

        if (prevState !== this.telemetry.state) {
            this.logFlightEvent(`State transition: ${prevState} -> ${this.telemetry.state}`);
        }
    }

    renderTelemetryHUD() {
        const t = this.telemetry;

        // Battery (Sections 34 & 35)
        const batVal = document.getElementById('uavBatteryVal');
        const batBar = document.getElementById('uavBatteryBar');
        const batStatus = document.getElementById('uavBatteryStatus');
        const batEst = document.getElementById('uavBatteryEst');

        const batPercent = t.battery_percent !== undefined ? t.battery_percent : 100.0;
        if (batVal) batVal.textContent = `${batPercent.toFixed(1)}%`;
        if (batBar) {
            batBar.style.width = `${Math.max(0, Math.min(100, batPercent))}%`;
            batBar.style.background = batPercent > 30 ? 'var(--accent-success)' : (batPercent > 20 ? 'var(--accent-warning)' : 'var(--accent-danger)');
        }
        if (batStatus) {
            if (batPercent <= 20) {
                batStatus.textContent = 'CRITICAL LOW (<20%) -> RTH MANDATED';
                batStatus.style.color = 'var(--accent-danger)';
            } else if (t.state === 'UAV_STANDBY' || t.state === 'STANDBY' || t.state === 'CHARGING') {
                batStatus.textContent = 'DOCKED / CHARGING';
                batStatus.style.color = 'var(--accent-cyan)';
            } else {
                batStatus.textContent = 'AIRBORNE (DISCHARGING)';
                batStatus.style.color = 'var(--accent-warning)';
            }
        }
        if (batEst) {
            const minutesLeft = Math.round((batPercent / 100) * 28);
            batEst.textContent = `${minutesLeft} MIN`;
        }

        // Flight & GPS metrics (Sections 19-21)
        const altEl = document.getElementById('uavAltVal');
        const spdEl = document.getElementById('uavSpeedVal');
        const hdgEl = document.getElementById('uavHeadingVal');
        const satsEl = document.getElementById('uavSatsVal');
        const latEl = document.getElementById('uavLatVal');
        const lonEl = document.getElementById('uavLonVal');
        const fixEl = document.getElementById('uavFixVal');
        const phsEl = document.getElementById('uavPhaseVal');

        if (altEl) altEl.textContent = `${(t.altitude_m || 0).toFixed(1)} m`;
        if (spdEl) spdEl.textContent = `${(t.speed_mps || 0).toFixed(1)} m/s`;
        if (hdgEl) hdgEl.textContent = `${Math.round(t.heading_deg || 0)}°`;
        if (satsEl) satsEl.textContent = `${t.satellites || 12} SATS`;
        if (latEl) latEl.textContent = (t.latitude || 31.6240).toFixed(6);
        if (lonEl) lonEl.textContent = (t.longitude || 74.8723).toFixed(6);
        if (fixEl) {
            const fix = t.gps_fix || '3D DGPS FIX';
            fixEl.textContent = fix;
            fixEl.style.color = fix.includes('NO FIX') ? 'var(--accent-danger)' : 'var(--accent-success)';
        }

        const cleanState = (t.state || 'STANDBY').replace('UAV_', '');
        if (phsEl) phsEl.textContent = cleanState;

        // GPS Source Pill & Mode Toggle
        const gpsPill = document.getElementById('uavGpsPill');
        const gpsText = document.getElementById('uavGpsText');
        const modeBtn = document.getElementById('btnToggleDroneMode');
        const isSim = (t.mode || 'SIMULATION').toUpperCase() === 'SIMULATION';
        if (gpsText) gpsText.textContent = isSim ? 'GPS: 3D FIX (SIM)' : 'GPS: 3D FIX (LIVE)';
        if (gpsPill) gpsPill.className = isSim ? 'status-pill standby' : 'status-pill online';
        if (modeBtn) modeBtn.textContent = isSim ? 'MODE: SIMULATION' : 'MODE: LIVE (NEO-6M)';

        // Mission & Geospatial Intercept Card (Sections 17, 18, 22, 23)
        const incBadge = document.getElementById('uavIncidentBadge');
        const tgtZoneVal = document.getElementById('uavTargetZoneVal');
        const distVal = document.getElementById('uavDistanceVal');
        const brgVal = document.getElementById('uavBearingVal');

        if (incBadge) {
            if (t.active_incident_id) {
                incBadge.textContent = `MISSION: ${t.active_incident_id}`;
                incBadge.style.background = 'rgba(239, 68, 68, 0.2)';
                incBadge.style.color = '#f87171';
            } else {
                incBadge.textContent = 'MISSION: STANDBY';
                incBadge.style.background = 'rgba(14, 165, 233, 0.2)';
                incBadge.style.color = '#38bdf8';
            }
        }
        if (tgtZoneVal) {
            const zName = t.target_zone_id || t.current_zone || 'ZONE_B';
            tgtZoneVal.textContent = `${zName} (${(t.target_lat || 31.6262).toFixed(4)}, ${(t.target_lon || 74.8748).toFixed(4)})`;
        }
        if (distVal) {
            const d = t.distance_to_target_m !== undefined ? t.distance_to_target_m : 0;
            distVal.textContent = d > 1000 ? `${(d / 1000).toFixed(2)} km` : `${Math.round(d)} m`;
        }
        if (brgVal) {
            brgVal.textContent = `${Math.round(t.bearing_deg || 0)}°`;
        }

        // Aerial Verification Card (Section 32)
        const aLock = document.getElementById('aerialLockBadge');
        const aTgt = document.getElementById('aerialTargetVal');
        const aSub = document.getElementById('aerialSubjectVal');
        const aConf = document.getElementById('aerialConfVal');
        const aStat = document.getElementById('aerialStatusVal');

        if (t.aerial_verification) {
            const av = t.aerial_verification;
            if (aLock) {
                aLock.textContent = 'AERIAL LOCK ACTIVE';
                aLock.style.background = 'rgba(239, 68, 68, 0.2)';
                aLock.style.color = '#f87171';
            }
            if (aTgt) aTgt.textContent = av.target_zone || t.target_zone_id || 'ZONE_B';
            if (aSub) aSub.textContent = av.identity || 'UNKNOWN';
            if (aConf) aConf.textContent = `${Math.round((av.confidence || 0.91) * 100)}%`;
            if (aStat) aStat.textContent = av.status || 'INCIDENT CONFIRMED';
        } else if (cleanState === 'AERIAL_SCAN' || cleanState === 'VERIFICATION' || cleanState === 'ARRIVED') {
            if (aLock) {
                aLock.textContent = 'SCANNING INCIDENT ZONE';
                aLock.style.background = 'rgba(245, 158, 11, 0.2)';
                aLock.style.color = '#fbbf24';
            }
            if (aTgt) aTgt.textContent = t.target_zone_id || 'ZONE_B';
            if (aSub) aSub.textContent = 'ACQUIRING SUBJECT...';
            if (aConf) aConf.textContent = '--%';
            if (aStat) aStat.textContent = 'OPTICAL SWEEP ACTIVE';
        } else {
            if (aLock) {
                aLock.textContent = 'SCAN INACTIVE';
                aLock.style.background = 'rgba(255, 255, 255, 0.05)';
                aLock.style.color = 'var(--text-muted)';
            }
        }

        // Safe Operator Control States (Section 37)
        const btnDispatch = document.getElementById('btnDispatchUav');
        const btnStartScan = document.getElementById('btnStartScanUav');
        const btnReturnHome = document.getElementById('btnReturnHomeUav');
        const btnAbort = document.getElementById('btnAbortUav');

        const isStandby = ['STANDBY', 'CHARGING', 'DOCKED', 'OFFLINE'].includes(cleanState);
        const isInFlight = !isStandby;

        if (btnDispatch) {
            btnDispatch.disabled = isInFlight || batPercent <= 20;
            btnDispatch.style.opacity = (isInFlight || batPercent <= 20) ? '0.6' : '1';
            btnDispatch.style.cursor = (isInFlight || batPercent <= 20) ? 'not-allowed' : 'pointer';
        }
        if (btnStartScan) {
            const canScan = ['ARRIVED', 'SEARCHING', 'CONFIRMED', 'EN_ROUTE', 'DISPATCHED', 'NAVIGATING', 'STANDBY'].includes(cleanState);
            btnStartScan.disabled = !canScan;
            btnStartScan.style.opacity = canScan ? '1' : '0.6';
            btnStartScan.style.cursor = canScan ? 'pointer' : 'not-allowed';
        }
        if (btnReturnHome) {
            btnReturnHome.disabled = isStandby;
            btnReturnHome.style.opacity = isStandby ? '0.6' : '1';
            btnReturnHome.style.cursor = isStandby ? 'not-allowed' : 'pointer';
        }
        if (btnAbort) {
            btnAbort.disabled = isStandby;
            btnAbort.style.opacity = isStandby ? '0.6' : '1';
            btnAbort.style.cursor = isStandby ? 'not-allowed' : 'pointer';
        }

        // Status Pill in Tab Header
        const pill = document.getElementById('uavTabStatusPill');
        const text = document.getElementById('uavTabStatusText');
        if (pill && text) {
            text.textContent = cleanState;
            if (isStandby) {
                pill.className = 'status-pill standby';
            } else if (cleanState === 'AERIAL_SCAN' || cleanState === 'VERIFICATION') {
                pill.className = 'status-pill critical';
            } else {
                pill.className = 'status-pill online';
            }
        }

        // Overlay status in HUD
        const ovSec = document.getElementById('uavHudOverlaySector');
        if (ovSec) ovSec.textContent = `SECTOR: ${t.target_zone_id || t.current_zone || 'ZONE_B'}`;
    }

    logFlightEvent(msg) {
        const log = document.getElementById('uavFlightLogContainer');
        if (!log) return;
        const timeStr = new Date().toLocaleTimeString();
        const div = document.createElement('div');
        div.innerHTML = `<span style="color: var(--accent-cyan);">[${timeStr}]</span> ${msg}`;
        log.appendChild(div);
        log.scrollTop = log.scrollHeight;
    }

    startRenderLoops() {
        const render = () => {
            this.drawWaypointMap();
            this.drawOpticalHUD();
            this.targetLockBlink = (this.targetLockBlink + 0.05) % (Math.PI * 2);
            requestAnimationFrame(render);
        };
        requestAnimationFrame(render);
    }

    // Projects (lat, lon) to Tactical Waypoint Map Canvas (X, Y)
    projectToMap(lat, lon) {
        const minLat = 31.6235;
        const maxLat = 31.6290;
        const minLon = 74.8715;
        const maxLon = 74.8775;

        const w = this.mapWidth || 450;
        const h = this.mapHeight || 260;

        // Lon -> X (left to right)
        const x = ((lon - minLon) / (maxLon - minLon)) * (w - 80) + 40;
        // Lat -> Y (bottom to top: higher latitude is further north / top of map)
        const y = h - (((lat - minLat) / (maxLat - minLat)) * (h - 70) + 35);

        return { x, y };
    }

    drawWaypointMap() {
        if (!this.mapCtx || !this.mapWidth) return;
        const ctx = this.mapCtx;
        const w = this.mapWidth;
        const h = this.mapHeight;

        ctx.clearRect(0, 0, w, h);

        // 1. Grid Background
        ctx.strokeStyle = 'rgba(0, 229, 255, 0.08)';
        ctx.lineWidth = 1;
        for (let x = 0; x < w; x += 40) {
            ctx.beginPath();
            ctx.moveTo(x, 0);
            ctx.lineTo(x, h);
            ctx.stroke();
        }
        for (let y = 0; y < h; y += 40) {
            ctx.beginPath();
            ctx.moveTo(0, y);
            ctx.lineTo(w, y);
            ctx.stroke();
        }

        // 2. Flight Path Waypoint lines
        const basePt = this.projectToMap(this.waypoints['BASE'].lat, this.waypoints['BASE'].lon);
        const zAPt = this.projectToMap(this.waypoints['ZONE_A'].lat, this.waypoints['ZONE_A'].lon);
        const zBPt = this.projectToMap(this.waypoints['ZONE_B'].lat, this.waypoints['ZONE_B'].lon);
        const zCPt = this.projectToMap(this.waypoints['ZONE_C'].lat, this.waypoints['ZONE_C'].lon);

        ctx.setLineDash([4, 4]);
        ctx.strokeStyle = 'rgba(0, 229, 255, 0.3)';
        ctx.beginPath();
        ctx.moveTo(basePt.x, basePt.y);
        ctx.lineTo(zAPt.x, zAPt.y);
        ctx.lineTo(zBPt.x, zBPt.y);
        ctx.lineTo(zCPt.x, zCPt.y);
        ctx.stroke();
        ctx.setLineDash([]);

        // 3. Draw Waypoint Nodes
        const drawNode = (pt, label, color, isBase = false) => {
            ctx.fillStyle = color;
            ctx.beginPath();
            if (isBase) {
                ctx.rect(pt.x - 7, pt.y - 7, 14, 14);
            } else {
                ctx.arc(pt.x, pt.y, 6, 0, Math.PI * 2);
            }
            ctx.fill();

            // Label
            ctx.fillStyle = '#fff';
            ctx.font = '9px JetBrains Mono, monospace';
            ctx.fillText(label, pt.x + 10, pt.y + 3);
        };

        drawNode(basePt, 'BASE HQ', 'rgba(0, 229, 255, 0.8)', true);
        drawNode(zAPt, 'WP-A', 'rgba(0, 230, 118, 0.8)');
        drawNode(zBPt, 'WP-B (WARNING)', 'rgba(255, 179, 0, 0.8)');
        drawNode(zCPt, 'WP-C (BORDER FENCE)', 'rgba(255, 23, 68, 0.8)');

        // 4. Draw Flight Trail
        if (this.flightTrail.length > 1) {
            ctx.strokeStyle = 'rgba(0, 229, 255, 0.6)';
            ctx.lineWidth = 2;
            ctx.beginPath();
            const start = this.projectToMap(this.flightTrail[0].lat, this.flightTrail[0].lon);
            ctx.moveTo(start.x, start.y);
            for (let i = 1; i < this.flightTrail.length; i++) {
                const pt = this.projectToMap(this.flightTrail[i].lat, this.flightTrail[i].lon);
                ctx.lineTo(pt.x, pt.y);
            }
            ctx.stroke();
        }

        // 5. Draw UAV Position
        const uavPt = this.projectToMap(this.telemetry.latitude, this.telemetry.longitude);

        // Pulse ring when active
        if (this.telemetry.state !== 'UAV_STANDBY') {
            const pulse = (Math.sin(this.targetLockBlink * 2) + 1) * 6 + 10;
            ctx.strokeStyle = this.telemetry.state === 'UAV_CONFIRMED' ? 'rgba(255, 23, 68, 0.6)' : 'rgba(0, 229, 255, 0.5)';
            ctx.lineWidth = 1.5;
            ctx.beginPath();
            ctx.arc(uavPt.x, uavPt.y, pulse, 0, Math.PI * 2);
            ctx.stroke();
        }

        // Drone Body (Delta wing chevron)
        ctx.fillStyle = this.telemetry.state === 'UAV_CONFIRMED' ? '#ff1744' : '#00e5ff';
        ctx.beginPath();
        ctx.moveTo(uavPt.x, uavPt.y - 10);
        ctx.lineTo(uavPt.x + 8, uavPt.y + 8);
        ctx.lineTo(uavPt.x, uavPt.y + 4);
        ctx.lineTo(uavPt.x - 8, uavPt.y + 8);
        ctx.closePath();
        ctx.fill();

        // Drone ID tag
        ctx.fillStyle = '#fff';
        ctx.font = 'bold 9px JetBrains Mono, monospace';
        ctx.fillText('UAV_01', uavPt.x + 12, uavPt.y - 4);
        ctx.fillStyle = 'rgba(0, 229, 255, 0.8)';
        ctx.fillText(`${this.telemetry.altitude_m.toFixed(0)}m AGL`, uavPt.x + 12, uavPt.y + 6);
    }

    drawOpticalHUD() {
        if (!this.hudCtx || !this.hudWidth) return;
        const ctx = this.hudCtx;
        const w = this.hudWidth;
        const h = this.hudHeight;
        const cx = w / 2;
        const cy = h / 2;

        ctx.clearRect(0, 0, w, h);

        ctx.strokeStyle = 'rgba(0, 229, 255, 0.4)';
        ctx.fillStyle = 'rgba(0, 229, 255, 0.7)';
        ctx.lineWidth = 1;
        ctx.font = '9px JetBrains Mono, monospace';

        // 1. Center Reticle
        ctx.beginPath();
        ctx.arc(cx, cy, 22, 0, Math.PI * 2);
        ctx.stroke();

        ctx.beginPath();
        ctx.moveTo(cx - 32, cy); ctx.lineTo(cx - 10, cy);
        ctx.moveTo(cx + 10, cy); ctx.lineTo(cx + 32, cy);
        ctx.moveTo(cx, cy - 32); ctx.lineTo(cx, cy - 10);
        ctx.moveTo(cx, cy + 10); ctx.lineTo(cx, cy + 32);
        ctx.stroke();

        // 2. Artificial Horizon Ladder Bars
        const pitchBars = [-30, -15, 15, 30];
        pitchBars.forEach(p => {
            const yOffset = cy + (p * 1.5);
            ctx.beginPath();
            ctx.moveTo(cx - 40, yOffset); ctx.lineTo(cx - 15, yOffset);
            ctx.moveTo(cx + 15, yOffset); ctx.lineTo(cx + 40, yOffset);
            ctx.stroke();
            ctx.fillText(`${Math.abs(p)}`, cx + 45, yOffset + 3);
        });

        // 3. Airspeed Tape (Left)
        ctx.beginPath();
        ctx.moveTo(25, 40); ctx.lineTo(25, h - 40);
        ctx.stroke();
        ctx.fillText('IAS m/s', 8, 35);
        ctx.font = 'bold 12px JetBrains Mono, monospace';
        ctx.fillStyle = 'var(--accent-cyan)';
        ctx.fillText(this.telemetry.speed_mps.toFixed(1), 10, cy + 4);

        // 4. Altitude Tape (Right)
        ctx.font = '9px JetBrains Mono, monospace';
        ctx.fillStyle = 'rgba(0, 229, 255, 0.7)';
        ctx.beginPath();
        ctx.moveTo(w - 25, 40); ctx.lineTo(w - 25, h - 40);
        ctx.stroke();
        ctx.fillText('ALT m', w - 42, 35);
        ctx.font = 'bold 12px JetBrains Mono, monospace';
        ctx.fillStyle = 'var(--accent-cyan)';
        ctx.fillText(this.telemetry.altitude_m.toFixed(1), w - 46, cy + 4);

        // 5. Target Optical Lock Box when in SEARCHING or CONFIRMED state
        const placeholder = document.getElementById('uavFeedPlaceholder');
        const targetText = document.getElementById('uavTargetAcquiredText');
        const feedStatus = document.getElementById('uavFeedStatus');

        if (this.telemetry.state === 'UAV_SEARCHING') {
            if (placeholder) placeholder.style.display = 'block';
            if (feedStatus) {
                feedStatus.textContent = '● RECON OPTICAL SWEEP IN PROGRESS';
                feedStatus.style.color = 'var(--accent-warning)';
            }
            if (targetText) targetText.textContent = 'Scanning sector perimeter coordinates...';

            // Searching scan box
            ctx.strokeStyle = 'rgba(255, 179, 0, 0.8)';
            ctx.lineWidth = 1.5;
            ctx.strokeRect(cx - 50, cy - 35, 100, 70);
            ctx.fillStyle = 'rgba(255, 179, 0, 0.9)';
            ctx.font = '9px JetBrains Mono, monospace';
            ctx.fillText('SEARCHING...', cx - 45, cy - 40);

        } else if (this.telemetry.state === 'UAV_CONFIRMED') {
            if (placeholder) placeholder.style.display = 'block';
            if (feedStatus) {
                feedStatus.textContent = '● INTRUDER CONFIRMED BY AERIAL RECON';
                feedStatus.style.color = 'var(--accent-danger)';
            }
            if (targetText) targetText.textContent = 'Target verified at sector coordinates';

            // Solid or flashing target box
            const alpha = Math.sin(this.targetLockBlink * 3) > 0 ? 1.0 : 0.4;
            ctx.strokeStyle = `rgba(255, 23, 68, ${alpha})`;
            ctx.lineWidth = 2;
            const bx = cx - 45;
            const by = cy - 40;
            const bw = 90;
            const bh = 80;

            // Corner brackets
            const clen = 15;
            ctx.beginPath();
            // Top-left
            ctx.moveTo(bx, by + clen); ctx.lineTo(bx, by); ctx.lineTo(bx + clen, by);
            // Top-right
            ctx.moveTo(bx + bw - clen, by); ctx.lineTo(bx + bw, by); ctx.lineTo(bx + bw, by + clen);
            // Bottom-left
            ctx.moveTo(bx, by + bh - clen); ctx.lineTo(bx, by + bh); ctx.lineTo(bx + clen, by + bh);
            // Bottom-right
            ctx.moveTo(bx + bw - clen, by + bh); ctx.lineTo(bx + bw, by + bh); ctx.lineTo(bx + bw, by + bh - clen);
            ctx.stroke();

            ctx.fillStyle = '#ff1744';
            ctx.font = 'bold 9px JetBrains Mono, monospace';
            ctx.fillText('TARGET VERIFIED [INTRUDER]', bx - 10, by - 8);
            ctx.fillText('CONFIDENCE: 96% | RNG: 38m', bx - 5, by + bh + 14);

        } else if (this.telemetry.state === 'UAV_RETURNING') {
            if (feedStatus) {
                feedStatus.textContent = '● RECON COMPLETE - RETURNING TO BASE';
                feedStatus.style.color = 'var(--accent-cyan)';
            }
            if (targetText) targetText.textContent = 'Navigating to Outpost docking station';
        } else {
            if (feedStatus) {
                feedStatus.textContent = '● UAV_01 RECON CAMERA GIMBAL DOCKED';
                feedStatus.style.color = 'var(--accent-cyan)';
            }
            if (targetText) targetText.textContent = 'Awaiting mission authorization';
        }
    }
}
