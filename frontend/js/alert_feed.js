/**
 * Real-time Security Alert Feed Controller with Continuous Deduplication & In-Place Lifecycle
 */
export class AlertFeed {
    constructor(containerId, countBadgeId) {
        this.container = document.getElementById(containerId);
        this.badge = document.getElementById(countBadgeId);
        this.alerts = [];
        this.maxAlerts = 40;
    }

    addAlert(alertData) {
        this.upsertAlert(alertData);
    }

    upsertAlert(eventData) {
        if (!eventData) return;
        const id = eventData.id || eventData.event_id;
        const existingIdx = this.alerts.findIndex(a => (a.id === id || (id && a.event_id === id)));

        if (existingIdx !== -1) {
            // Update in-place to avoid duplicate card spam
            const existing = this.alerts[existingIdx];
            existing.severity = eventData.severity || existing.severity;
            existing.description = eventData.description || existing.description;
            existing.status = eventData.status || existing.status;
            existing.duration_seconds = eventData.duration_seconds ?? existing.duration_seconds;
            existing.update_count = eventData.update_count ?? (existing.update_count + 1);
            existing.trajectory_points = eventData.trajectory_points ?? existing.trajectory_points;
            existing.is_acknowledged = eventData.is_acknowledged ?? existing.is_acknowledged;
            existing.timestamp = eventData.timestamp || eventData.updated_time || existing.timestamp;
            // Bump to top if escalated to CRITICAL
            if (eventData.severity === 'CRITICAL' && existingIdx > 0) {
                const [item] = this.alerts.splice(existingIdx, 1);
                this.alerts.unshift(item);
            }
        } else {
            // New alert card
            this.alerts.unshift({
                id: id,
                event_type: eventData.event_type || 'INTRUSION_ALERT',
                severity: eventData.severity || 'LOW',
                status: eventData.status || 'ACTIVE',
                description: eventData.description || 'Target activity detected',
                zone_id: eventData.zone_id,
                zone_name: eventData.zone_name,
                camera_id: eventData.camera_id,
                radar_id: eventData.radar_id,
                target_id: eventData.target_id,
                confidence: eventData.confidence,
                duration_seconds: eventData.duration_seconds || 0,
                trajectory_points: eventData.trajectory_points || 1,
                timestamp: eventData.timestamp || eventData.start_time || new Date().toISOString(),
                is_simulated: eventData.is_simulated || false,
                is_acknowledged: eventData.is_acknowledged || false
            });

            if (this.alerts.length > this.maxAlerts) {
                this.alerts.pop();
            }
        }

        this.render();
        this.updateBadge();
    }

    resolveAlert(eventData) {
        if (!eventData) return;
        const id = eventData.id || eventData.event_id;
        const alert = this.alerts.find(a => a.id === id);
        if (alert) {
            alert.status = 'RESOLVED';
            alert.severity = 'LOW';
            alert.resolved_at = eventData.resolved_at || new Date().toISOString();
            this.render();
            this.updateBadge();
        }
    }

    async acknowledgeAlert(eventId) {
        try {
            const res = await fetch(`/api/events/${eventId}/acknowledge`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ operator_name: 'Command Operator' })
            });
            if (res.ok) {
                const alert = this.alerts.find(a => a.id === eventId);
                if (alert) {
                    alert.status = 'ACKNOWLEDGED';
                    alert.is_acknowledged = true;
                    this.render();
                }
            }
        } catch (e) {
            console.error('Failed to acknowledge alert:', e);
        }
    }

    async manualResolveAlert(eventId) {
        try {
            const res = await fetch(`/api/events/${eventId}/resolve`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ operator_name: 'Command Operator' })
            });
            if (res.ok) {
                this.resolveAlert({ id: eventId });
            }
        } catch (e) {
            console.error('Failed to resolve alert:', e);
        }
    }

    async loadInitialAlerts() {
        try {
            const res = await fetch('/api/events?limit=20');
            if (res.ok) {
                const raw = await res.json();
                const list = Array.isArray(raw) ? raw : (raw && Array.isArray(raw.events) ? raw.events : []);
                list.forEach(evt => {
                    this.upsertAlert({
                        id: evt.id,
                        event_type: evt.event_type,
                        severity: evt.severity,
                        status: evt.status,
                        description: evt.description || `${evt.event_type} in ${evt.zone_id || 'sector'}`,
                        zone_id: evt.zone_id,
                        camera_id: evt.camera_id,
                        radar_id: evt.radar_id,
                        timestamp: evt.start_time || evt.created_at,
                        is_simulated: evt.is_simulated
                    });
                });
            }
        } catch (e) {
            console.debug('[ALERTS] Failed to load initial events:', e);
        }
    }

    updateBadge() {
        if (this.badge) {
            const activeAlerts = this.alerts.filter(a => a.status === 'ACTIVE' || a.status === 'ACKNOWLEDGED');
            const criticalCount = activeAlerts.filter(a => a.severity === 'CRITICAL' || a.severity === 'HIGH').length;

            if (criticalCount > 0) {
                this.badge.textContent = `${criticalCount} CRITICAL THREAT${criticalCount === 1 ? '' : 'S'}`;
                this.badge.style.background = 'var(--accent-danger)';
                this.badge.style.color = '#fff';
            } else if (activeAlerts.length > 0) {
                this.badge.textContent = `${activeAlerts.length} ACTIVE`;
                this.badge.style.background = 'var(--accent-warning)';
                this.badge.style.color = '#000';
            } else {
                this.badge.textContent = '0 ALERTS';
                this.badge.style.background = 'var(--bg-tertiary)';
                this.badge.style.color = 'var(--text-muted)';
            }
        }
    }

    render() {
        if (!this.container) return;
        if (this.alerts.length === 0) {
            this.container.innerHTML = `
                <div style="text-align: center; color: var(--text-muted); padding: 24px; font-size: 12px;">
                    ALL SECTORS SECURE • NO ACTIVE THREATS
                </div>
            `;
            return;
        }

        this.container.innerHTML = this.alerts.map(a => {
            const sev = (a.severity || 'LOW').toLowerCase();
            const isResolved = a.status === 'RESOLVED';
            const isAck = a.status === 'ACKNOWLEDGED';
            const timeStr = a.timestamp ? new Date(a.timestamp).toLocaleTimeString() : new Date().toLocaleTimeString();

            return `
                <div class="alert-card ${isResolved ? 'resolved' : sev}" id="alert-card-${a.id}" style="${isResolved ? 'opacity: 0.65; border-color: rgba(255,255,255,0.1);' : ''}">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                        <span class="alert-severity-badge ${sev}">
                            ${isResolved ? 'RESOLVED' : (isAck ? 'ACKNOWLEDGED' : a.severity)}
                        </span>
                        <div style="display: flex; gap: 6px; align-items: center;">
                            ${a.duration_seconds > 0 ? `
                                <span style="font-family: var(--font-mono); font-size: 10px; color: var(--accent-cyan); background: rgba(0,229,255,0.12); padding: 1px 6px; border-radius: 2px;">
                                    ⏱️ ${a.duration_seconds.toFixed(1)}s
                                </span>
                            ` : ''}
                            ${a.trajectory_points > 1 ? `
                                <span style="font-family: var(--font-mono); font-size: 10px; color: var(--text-secondary);">
                                    📍 ${a.trajectory_points}pts
                                </span>
                            ` : ''}
                        </div>
                    </div>
                    <div class="alert-content">
                        <div class="alert-title">
                            <span style="font-weight: 700;">${a.event_type}</span>
                            <span class="alert-time">${timeStr}</span>
                        </div>
                        <div class="alert-desc">${a.description}</div>
                        <div class="alert-meta">
                            ${a.zone_id ? `ZONE: <strong>${a.zone_id}</strong>` : ''} 
                            ${a.camera_id ? `• CAM: ${a.camera_id}` : ''} 
                            ${a.radar_id ? `• RADAR: ${a.radar_id}` : ''}
                            ${a.target_id ? `• TRK: ${a.target_id}` : ''}
                            ${a.is_simulated ? ' • <span style="color:var(--accent-warning);">[SIM]</span>' : ''}
                        </div>

                        ${!isResolved ? `
                            <div style="display: flex; gap: 6px; margin-top: 8px;">
                                ${!isAck ? `
                                    <button class="btn-tactical btn-ack-alert" data-event-id="${a.id}" style="padding: 2px 8px; font-size: 10px; background: rgba(255, 179, 0, 0.15); border-color: var(--accent-warning); color: var(--accent-warning);">
                                        ACKNOWLEDGE
                                    </button>
                                ` : `
                                    <span style="font-size: 10px; font-family: var(--font-mono); color: var(--accent-warning);">✓ ACKNOWLEDGED</span>
                                `}
                                <button class="btn-tactical btn-resolve-alert" data-event-id="${a.id}" style="padding: 2px 8px; font-size: 10px;">
                                    RESOLVE
                                </button>
                            </div>
                        ` : ''}
                    </div>
                </div>
            `;
        }).join('');

        // Attach action handlers for Acknowledge and Resolve
        this.container.querySelectorAll('.btn-ack-alert').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const evtId = btn.getAttribute('data-event-id');
                btn.textContent = 'ACKING...';
                this.acknowledgeAlert(evtId);
            });
        });

        this.container.querySelectorAll('.btn-resolve-alert').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const evtId = btn.getAttribute('data-event-id');
                btn.textContent = 'RESOLVING...';
                this.manualResolveAlert(evtId);
            });
        });
    }

    clear() {
        this.alerts = [];
        this.render();
        this.updateBadge();
    }
}
