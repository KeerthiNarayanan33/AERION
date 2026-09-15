/**
 * PersonsManager — Authorized People Management Module
 * Handles CRUD operations, table rendering, search/filter, and modal logic.
 */
export class PersonsManager {
    constructor() {
        this.persons = [];
        this.filteredPersons = [];
        this.searchQuery = '';
        this.filterStatus = '';
        this.editingPersonId = null;
        this.imageBase64 = null;
        this._zones = [];
    }

    async init() {
        if (!this._eventsBound) {
            this._bindEvents();
            this._eventsBound = true;
        }
        await this.loadZones();
        await this.loadPersons();
    }

    async loadZones() {
        try {
            const res = await fetch('/api/zones');
            if (res.ok) {
                const data = await res.json();
                this._zones = Array.isArray(data) ? data : (data.zones || []);
            }
        } catch (e) { this._zones = []; }
    }

    async loadPersons() {
        try {
            const params = new URLSearchParams();
            if (this.searchQuery) params.set('search', this.searchQuery);
            if (this.filterStatus) params.set('status', this.filterStatus);
            const res = await fetch(`/api/persons?${params}`);
            if (!res.ok) throw new Error('Failed to fetch persons');
            const data = await res.json();
            this.persons = data.persons || [];
            this.filteredPersons = this.persons;
            this._renderTable();
            this._renderSummaryBadges();
        } catch (e) {
            console.error('[PERSONS] Load error:', e);
        }
    }

    _renderSummaryBadges() {
        const authorized = this.persons.filter(p => p.status === 'AUTHORIZED').length;
        const disabled = this.persons.filter(p => p.status === 'DISABLED').length;
        const expired = this.persons.filter(p => {
            if (!p.valid_until) return false;
            return new Date(p.valid_until) < new Date();
        }).length;

        const el = (id, val) => { const e = document.getElementById(id); if (e) e.textContent = val; };
        el('personsCountTotal', this.persons.length);
        el('personsCountAuthorized', authorized);
        el('personsCountDisabled', disabled);
        el('personsCountExpired', expired);

        // Update dashboard counter
        const dashUnauth = document.getElementById('dashUnknownPersons');
        if (dashUnauth && window._surveillanceState) {
            // keep from WS state
        }
    }

    _statusBadge(p) {
        const now = new Date();
        let status = p.status;
        if (status === 'AUTHORIZED' && p.valid_until && new Date(p.valid_until) < now) {
            status = 'EXPIRED';
        }
        const map = {
            AUTHORIZED: { cls: 'badge-auth-ok', label: '● AUTHORIZED' },
            DISABLED: { cls: 'badge-auth-disabled', label: '○ DISABLED' },
            EXPIRED: { cls: 'badge-auth-expired', label: '⚠ EXPIRED' },
            SUSPENDED: { cls: 'badge-auth-warn', label: '⚠ SUSPENDED' },
            REVOKED: { cls: 'badge-auth-bad', label: '✕ REVOKED' },
        };
        const { cls, label } = map[status] || map.DISABLED;
        return `<span class="person-status-badge ${cls}">${label}</span>`;
    }

    _accessBadge(level) {
        const map = {
            VISITOR: '#64748b',
            STANDARD: '#38bdf8',
            ELEVATED: '#f59e0b',
            ADMIN: '#a855f7',
        };
        const color = map[level] || '#64748b';
        return `<span style="font-size:9px;font-weight:700;color:${color};font-family:var(--font-mono);padding:1px 6px;border:1px solid ${color};border-radius:3px;">${level || 'STANDARD'}</span>`;
    }

    _formatDate(d) {
        if (!d) return '—';
        try { return new Date(d).toLocaleDateString('en-IN', { year: 'numeric', month: 'short', day: 'numeric' }); }
        catch { return d; }
    }

    _formatDetectedAt(d) {
        if (!d) return '—';
        try {
            const dt = new Date(d);
            const now = new Date();
            const diffMs = now - dt;
            if (diffMs < 60000) return 'Just now';
            if (diffMs < 3600000) return `${Math.floor(diffMs / 60000)}m ago`;
            if (diffMs < 86400000) return `${Math.floor(diffMs / 3600000)}h ago`;
            return dt.toLocaleDateString('en-IN', { month: 'short', day: 'numeric' });
        } catch { return d; }
    }

    _renderTable() {
        const tbody = document.getElementById('personsTableBody');
        if (!tbody) return;

        if (this.filteredPersons.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="9" style="text-align:center;padding:40px;color:var(--text-muted);">
                        <div style="font-size:13px;margin-bottom:8px;">No authorized persons found.</div>
                        <div style="font-size:11px;">Add your first authorized person using the button above.</div>
                    </td>
                </tr>`;
            return;
        }

        tbody.innerHTML = this.filteredPersons.map(p => {
            const zones = (p.allowed_zones || []).slice(0, 3).join(', ') || '—';
            const moreZones = (p.allowed_zones || []).length > 3 ? ` +${p.allowed_zones.length - 3}` : '';
            const imgHtml = p.reference_image_path
                ? `<img src="${p.reference_image_path}" style="width:28px;height:28px;border-radius:50%;object-fit:cover;border:1px solid rgba(255,255,255,0.2);" onerror="this.src='';this.style.display='none';">`
                : `<div style="width:28px;height:28px;border-radius:50%;background:rgba(56,189,248,0.2);border:1px solid #38bdf8;display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:700;color:#38bdf8;">${(p.name||'?')[0].toUpperCase()}</div>`;

            return `
            <tr class="person-table-row" data-person-id="${p.person_id}">
                <td>
                    <div style="display:flex;align-items:center;gap:8px;">
                        ${imgHtml}
                        <div>
                            <div style="font-weight:600;color:#fff;font-size:11px;">${p.name}</div>
                            <div style="font-size:9px;color:var(--text-muted);font-family:var(--font-mono);">${p.employee_id || '—'}</div>
                        </div>
                    </div>
                </td>
                <td style="font-family:var(--font-mono);font-size:10px;color:var(--accent-cyan);">${p.person_id}</td>
                <td style="font-size:10px;">${p.role || '—'}</td>
                <td style="font-size:10px;">${p.department || '—'}</td>
                <td>${this._accessBadge(p.access_level)}</td>
                <td style="font-size:9px;color:var(--text-secondary);font-family:var(--font-mono);">${zones}${moreZones}</td>
                <td>${this._statusBadge(p)}</td>
                <td style="font-size:9px;color:var(--text-muted);">
                    <div>${this._formatDetectedAt(p.last_detected_at)}</div>
                    <div style="color:#64748b;">${p.last_detected_zone || '—'}</div>
                </td>
                <td>
                    <div style="display:flex;gap:4px;flex-wrap:wrap;">
                        <button class="btn-person-action btn-view" data-id="${p.person_id}" title="View Profile">👁</button>
                        <button class="btn-person-action btn-edit" data-id="${p.person_id}" title="Edit">✏️</button>
                        ${p.status === 'AUTHORIZED'
                            ? `<button class="btn-person-action btn-disable" data-id="${p.person_id}" title="Disable">⊘</button>`
                            : `<button class="btn-person-action btn-enable" data-id="${p.person_id}" title="Enable">✓</button>`}
                        <button class="btn-person-action btn-activity" data-id="${p.person_id}" title="Activity">📋</button>
                        <button class="btn-person-action btn-delete" data-id="${p.person_id}" title="Delete" style="color:#ef4444;">🗑</button>
                    </div>
                </td>
            </tr>`;
        }).join('');

        // Bind row action buttons
        tbody.querySelectorAll('.btn-view').forEach(b => b.addEventListener('click', () => this._showProfile(b.dataset.id)));
        tbody.querySelectorAll('.btn-edit').forEach(b => b.addEventListener('click', () => this._openEditModal(b.dataset.id)));
        tbody.querySelectorAll('.btn-disable').forEach(b => b.addEventListener('click', () => this._disablePerson(b.dataset.id)));
        tbody.querySelectorAll('.btn-enable').forEach(b => b.addEventListener('click', () => this._enablePerson(b.dataset.id)));
        tbody.querySelectorAll('.btn-delete').forEach(b => b.addEventListener('click', () => this._deletePerson(b.dataset.id)));
        tbody.querySelectorAll('.btn-activity').forEach(b => b.addEventListener('click', () => this._showActivity(b.dataset.id)));
    }

    _buildZoneCheckboxes(selectedZones = []) {
        if (!this._zones.length) return '<div style="color:var(--text-muted);font-size:10px;">No zones configured yet.</div>';
        return this._zones.map(z => `
            <label style="display:flex;align-items:center;gap:6px;font-size:11px;color:var(--text-secondary);cursor:pointer;padding:3px 0;">
                <input type="checkbox" value="${z.id}" class="zone-checkbox" ${selectedZones.includes(z.id) ? 'checked' : ''}
                    style="accent-color:var(--accent-cyan);">
                <span style="width:8px;height:8px;border-radius:50%;background:${z.color || '#00e676'};display:inline-block;"></span>
                ${z.name} <span style="color:#475569;font-size:9px;">(${z.id})</span>
            </label>`).join('');
    }

    _openAddModal() {
        this.editingPersonId = null;
        this.imageBase64 = null;
        this._populateModal(null);
        const modal = document.getElementById('personModal');
        if (modal) { modal.style.display = 'flex'; }
    }

    async _openEditModal(personId) {
        const p = this.persons.find(x => x.person_id === personId);
        if (!p) return;
        this.editingPersonId = personId;
        this.imageBase64 = null;
        this._populateModal(p);
        const modal = document.getElementById('personModal');
        if (modal) { modal.style.display = 'flex'; }
    }

    _populateModal(p) {
        const title = document.getElementById('personModalTitle');
        if (title) title.textContent = p ? 'EDIT AUTHORIZED PERSON' : 'ADD AUTHORIZED PERSON';

        const val = (id, v) => { const e = document.getElementById(id); if (e) e.value = v || ''; };
        val('pmPersonId', p?.person_id || '');
        val('pmName', p?.name || '');
        val('pmEmployeeId', p?.employee_id || '');
        val('pmDepartment', p?.department || '');
        val('pmRole', p?.role || '');
        val('pmPhone', p?.phone || '');
        val('pmEmail', p?.email || '');
        val('pmAccessLevel', p?.access_level || 'STANDARD');
        val('pmStatus', p?.status || 'AUTHORIZED');
        val('pmValidFrom', p?.valid_from ? p.valid_from.split('T')[0] : '');
        val('pmValidUntil', p?.valid_until ? p.valid_until.split('T')[0] : '');
        val('pmNotes', p?.notes || '');

        // Disable person_id field if editing
        const idField = document.getElementById('pmPersonId');
        if (idField) idField.disabled = !!p;

        // Zone checkboxes
        const zoneContainer = document.getElementById('pmZoneCheckboxes');
        if (zoneContainer) zoneContainer.innerHTML = this._buildZoneCheckboxes(p?.allowed_zones || []);

        // Image preview
        const preview = document.getElementById('pmImagePreview');
        if (preview) {
            if (p?.reference_image_path) {
                preview.innerHTML = `<img src="${p.reference_image_path}" style="max-width:100px;max-height:100px;border-radius:4px;border:1px solid rgba(255,255,255,0.2);" onerror="this.parentElement.innerHTML='<span style=color:var(--text-muted);font-size:10px;>No image</span>'">`;
            } else {
                preview.innerHTML = '<span style="color:var(--text-muted);font-size:10px;">No image uploaded</span>';
            }
        }
    }

    _closeModal() {
        const modal = document.getElementById('personModal');
        if (modal) { modal.style.display = 'none'; }
        this.editingPersonId = null;
        this.imageBase64 = null;
    }

    _getFormData() {
        const get = (id) => { const e = document.getElementById(id); return e ? e.value.trim() : ''; };
        const zones = Array.from(document.querySelectorAll('#pmZoneCheckboxes .zone-checkbox:checked')).map(c => c.value);
        return {
            person_id: get('pmPersonId'),
            name: get('pmName'),
            employee_id: get('pmEmployeeId') || null,
            department: get('pmDepartment') || null,
            role: get('pmRole') || null,
            phone: get('pmPhone') || null,
            email: get('pmEmail') || null,
            access_level: get('pmAccessLevel') || 'STANDARD',
            status: get('pmStatus') || 'AUTHORIZED',
            allowed_zones: zones,
            valid_from: get('pmValidFrom') ? get('pmValidFrom') + 'T00:00:00Z' : null,
            valid_until: get('pmValidUntil') ? get('pmValidUntil') + 'T23:59:59Z' : null,
            notes: get('pmNotes') || null,
            image_base64: this.imageBase64 || null,
        };
    }

    async _submitPerson() {
        const data = this._getFormData();
        if (!data.name) { this._showModalError('Name is required.'); return; }
        if (!this.editingPersonId && !data.person_id) { this._showModalError('Person ID is required.'); return; }
        if (!this.editingPersonId && data.person_id.length < 3) { this._showModalError('Person ID must be at least 3 characters.'); return; }

        const url = this.editingPersonId ? `/api/persons/${this.editingPersonId}` : '/api/persons';
        const method = this.editingPersonId ? 'PUT' : 'POST';

        try {
            const res = await fetch(url, {
                method,
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });
            const body = await res.json();
            if (!res.ok) {
                this._showModalError(body.detail || 'Failed to save person.');
                return;
            }
            this._closeModal();
            await this.loadPersons();
            this._showToast(`Person ${this.editingPersonId ? 'updated' : 'created'} successfully.`, 'success');
        } catch (e) {
            this._showModalError('Network error. Please try again.');
        }
    }

    async _disablePerson(id) {
        if (!confirm(`Disable person ${id}? They will no longer be recognized as authorized.`)) return;
        await fetch(`/api/persons/${id}/disable`, { method: 'POST' });
        await this.loadPersons();
        this._showToast(`Person ${id} disabled.`, 'warn');
    }

    async _enablePerson(id) {
        await fetch(`/api/persons/${id}/enable`, { method: 'POST' });
        await this.loadPersons();
        this._showToast(`Person ${id} re-enabled.`, 'success');
    }

    async _deletePerson(id) {
        if (!confirm(`Permanently delete person ${id}? This cannot be undone.`)) return;
        await fetch(`/api/persons/${id}`, { method: 'DELETE' });
        await this.loadPersons();
        this._showToast(`Person ${id} removed from registry.`, 'warn');
    }

    _showProfile(id) {
        const p = this.persons.find(x => x.person_id === id);
        if (!p) return;

        const now = new Date();
        const expired = p.valid_until && new Date(p.valid_until) < now;
        const status = expired ? 'EXPIRED' : p.status;
        const statusColors = { AUTHORIZED: '#10b981', DISABLED: '#64748b', EXPIRED: '#f59e0b', SUSPENDED: '#f59e0b', REVOKED: '#ef4444' };
        const color = statusColors[status] || '#64748b';
        const imgHtml = p.reference_image_path
            ? `<img src="${p.reference_image_path}" style="width:72px;height:72px;border-radius:50%;object-fit:cover;border:2px solid ${color};" onerror="this.outerHTML='<div style=width:72px;height:72px;border-radius:50%;background:rgba(56,189,248,0.2);border:2px solid #38bdf8;display:flex;align-items:center;justify-content:center;font-size:24px;font-weight:700;color:#38bdf8;>${(p.name||'?')[0].toUpperCase()}</div>'">`
            : `<div style="width:72px;height:72px;border-radius:50%;background:rgba(56,189,248,0.2);border:2px solid #38bdf8;display:flex;align-items:center;justify-content:center;font-size:24px;font-weight:700;color:#38bdf8;">${(p.name||'?')[0].toUpperCase()}</div>`;

        const zoneList = (p.allowed_zones || []).map(z => {
            const zoneObj = this._zones.find(x => x.id === z);
            return `<span style="font-size:10px;background:rgba(56,189,248,0.1);border:1px solid rgba(56,189,248,0.3);padding:2px 8px;border-radius:3px;color:#38bdf8;">• ${zoneObj?.name || z}</span>`;
        }).join(' ');

        const overlay = document.getElementById('personProfileModal');
        const content = document.getElementById('personProfileContent');
        if (!overlay || !content) return;

        content.innerHTML = `
            <div style="display:flex;gap:20px;align-items:flex-start;margin-bottom:20px;">
                <div>${imgHtml}</div>
                <div style="flex:1;">
                    <div style="font-size:18px;font-weight:800;color:#fff;margin-bottom:4px;">${p.name}</div>
                    <div style="font-size:11px;color:var(--text-muted);font-family:var(--font-mono);margin-bottom:8px;">ID: ${p.person_id} ${p.employee_id ? '| ' + p.employee_id : ''}</div>
                    <div style="font-size:12px;color:var(--text-secondary);margin-bottom:4px;">${p.role || 'No role assigned'}</div>
                    <div style="font-size:11px;color:var(--text-muted);">${p.department || ''}</div>
                    <div style="margin-top:8px;">
                        <span style="font-weight:800;color:${color};font-size:12px;font-family:var(--font-mono);background:${color}20;padding:3px 10px;border:1px solid ${color};border-radius:4px;">● ${status}</span>
                    </div>
                </div>
                <div style="text-align:right;font-size:10px;color:var(--text-muted);">
                    <div>Access: <strong style="color:#a855f7;">${p.access_level || 'STANDARD'}</strong></div>
                    <div>Detections: <strong style="color:#fff;">${p.detection_count || 0}</strong></div>
                </div>
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px;">
                <div style="background:var(--bg-primary);border:1px solid var(--border-subtle);border-radius:6px;padding:10px;">
                    <div style="font-size:9px;color:var(--text-muted);margin-bottom:4px;">LAST DETECTED</div>
                    <div style="font-size:12px;color:#fff;font-weight:600;">${this._formatDetectedAt(p.last_detected_at)}</div>
                    <div style="font-size:10px;color:var(--text-secondary);">${p.last_detected_zone || '—'}</div>
                </div>
                <div style="background:var(--bg-primary);border:1px solid var(--border-subtle);border-radius:6px;padding:10px;">
                    <div style="font-size:9px;color:var(--text-muted);margin-bottom:4px;">VALID UNTIL</div>
                    <div style="font-size:12px;color:${expired ? '#f59e0b' : '#10b981'};font-weight:600;">${this._formatDate(p.valid_until)}</div>
                </div>
            </div>
            <div style="margin-bottom:14px;">
                <div style="font-size:10px;color:var(--text-muted);margin-bottom:6px;font-weight:600;">AUTHORIZED ZONES</div>
                <div style="display:flex;gap:6px;flex-wrap:wrap;">${zoneList || '<span style="color:var(--text-muted);font-size:10px;">No zones assigned</span>'}</div>
            </div>
            ${p.notes ? `<div style="background:var(--bg-primary);border:1px solid var(--border-subtle);border-radius:6px;padding:10px;font-size:11px;color:var(--text-secondary);">${p.notes}</div>` : ''}
            ${p.has_face_embedding ? '<div style="margin-top:10px;font-size:10px;color:#10b981;font-family:var(--font-mono);">✓ Face embedding registered in recognition gallery</div>' : '<div style="margin-top:10px;font-size:10px;color:#f59e0b;font-family:var(--font-mono);">⚠ No face embedding — recognition not available</div>'}
        `;

        overlay.style.display = 'flex';
    }

    async _showActivity(id) {
        try {
            const res = await fetch(`/api/persons/${id}/activity`);
            if (!res.ok) return;
            const data = await res.json();
            const overlay = document.getElementById('personActivityModal');
            const content = document.getElementById('personActivityContent');
            if (!overlay || !content) return;

            const actHtml = data.activity.length === 0
                ? '<div style="text-align:center;padding:24px;color:var(--text-muted);font-size:12px;">No detection events recorded yet.</div>'
                : data.activity.map(e => {
                    const sev = { CRITICAL: '#ef4444', HIGH: '#f59e0b', MEDIUM: '#3b82f6', LOW: '#10b981', INFO: '#64748b' }[e.severity] || '#64748b';
                    return `<div style="display:flex;justify-content:space-between;align-items:flex-start;padding:8px 0;border-bottom:1px solid var(--border-subtle);">
                        <div>
                            <span style="font-size:9px;font-weight:700;color:${sev};background:${sev}20;padding:1px 6px;border-radius:3px;border:1px solid ${sev};">${e.severity}</span>
                            <span style="font-size:11px;color:#fff;margin-left:8px;">${e.event_type}</span>
                            <div style="font-size:10px;color:var(--text-muted);margin-top:2px;">Zone: ${e.zone_id || '—'} | Camera: ${e.camera_id || '—'}</div>
                        </div>
                        <div style="font-size:10px;color:var(--text-muted);text-align:right;">${this._formatDate(e.timestamp)}</div>
                    </div>`;
                }).join('');

            content.innerHTML = `
                <div style="margin-bottom:14px;display:flex;gap:20px;">
                    <div><div style="font-size:10px;color:var(--text-muted);">PERSON</div><div style="font-size:14px;font-weight:700;color:#fff;">${data.name}</div></div>
                    <div><div style="font-size:10px;color:var(--text-muted);">TOTAL DETECTIONS</div><div style="font-size:14px;font-weight:700;color:var(--accent-cyan);">${data.detection_count}</div></div>
                    <div><div style="font-size:10px;color:var(--text-muted);">LAST SEEN</div><div style="font-size:14px;font-weight:700;color:#fff;">${this._formatDetectedAt(data.last_detected_at)}</div></div>
                    <div><div style="font-size:10px;color:var(--text-muted);">LAST ZONE</div><div style="font-size:14px;font-weight:700;color:#fff;">${data.last_detected_zone || '—'}</div></div>
                </div>
                <div style="max-height:320px;overflow-y:auto;">${actHtml}</div>`;
            overlay.style.display = 'flex';
        } catch (e) { console.error('[PERSONS] Activity error:', e); }
    }

    _showModalError(msg) {
        const el = document.getElementById('personModalError');
        if (el) { el.textContent = msg; el.style.display = 'block'; }
    }

    _showToast(msg, type = 'info') {
        const colors = { success: '#10b981', warn: '#f59e0b', error: '#ef4444', info: '#38bdf8' };
        const toast = document.createElement('div');
        toast.style.cssText = `position:fixed;bottom:20px;right:20px;background:#0b1329;border:1px solid ${colors[type]};color:${colors[type]};padding:10px 18px;border-radius:6px;font-size:11px;font-family:var(--font-mono);z-index:99999;`;
        toast.textContent = msg;
        document.body.appendChild(toast);
        setTimeout(() => toast.remove(), 3000);
    }

    _bindEvents() {
        // Add person button
        const addBtn = document.getElementById('btnAddPerson');
        if (addBtn) addBtn.addEventListener('click', () => this._openAddModal());

        // Refresh button
        const refreshBtn = document.getElementById('btnRefreshPersons');
        if (refreshBtn) refreshBtn.addEventListener('click', () => this.loadPersons());

        // Search
        const searchEl = document.getElementById('personsSearch');
        if (searchEl) {
            searchEl.addEventListener('input', (e) => {
                this.searchQuery = e.target.value;
                this.loadPersons();
            });
        }

        // Status filter
        const filterEl = document.getElementById('personsStatusFilter');
        if (filterEl) {
            filterEl.addEventListener('change', (e) => {
                this.filterStatus = e.target.value;
                this.loadPersons();
            });
        }

        // Modal close
        document.getElementById('btnClosePersonModal')?.addEventListener('click', () => this._closeModal());
        document.getElementById('btnCancelPersonModal')?.addEventListener('click', () => this._closeModal());
        document.getElementById('personModal')?.addEventListener('click', (e) => {
            if (e.target === e.currentTarget) this._closeModal();
        });

        // Modal submit
        document.getElementById('btnSubmitPerson')?.addEventListener('click', () => this._submitPerson());

        // Profile modal close
        document.getElementById('btnClosePersonProfile')?.addEventListener('click', () => {
            const m = document.getElementById('personProfileModal');
            if (m) m.style.display = 'none';
        });
        document.getElementById('personProfileModal')?.addEventListener('click', (e) => {
            if (e.target === e.currentTarget) { e.target.style.display = 'none'; }
        });

        // Activity modal close
        document.getElementById('btnClosePersonActivity')?.addEventListener('click', () => {
            const m = document.getElementById('personActivityModal');
            if (m) m.style.display = 'none';
        });
        document.getElementById('personActivityModal')?.addEventListener('click', (e) => {
            if (e.target === e.currentTarget) { e.target.style.display = 'none'; }
        });

        // Image upload
        const imgInput = document.getElementById('pmImageInput');
        if (imgInput) {
            imgInput.addEventListener('change', (e) => {
                const file = e.target.files[0];
                if (!file) return;
                if (file.size > 5 * 1024 * 1024) { this._showModalError('Image must be under 5MB.'); return; }
                const reader = new FileReader();
                reader.onload = (ev) => {
                    this.imageBase64 = ev.target.result;
                    const preview = document.getElementById('pmImagePreview');
                    if (preview) preview.innerHTML = `<img src="${ev.target.result}" style="max-width:100px;max-height:100px;border-radius:4px;border:1px solid rgba(255,255,255,0.2);">`;
                };
                reader.readAsDataURL(file);
            });
        }

        // Image clear button
        document.getElementById('btnClearPersonImage')?.addEventListener('click', () => {
            this.imageBase64 = null;
            const preview = document.getElementById('pmImagePreview');
            if (preview) preview.innerHTML = '<span style="color:var(--text-muted);font-size:10px;">No image uploaded</span>';
            const inp = document.getElementById('pmImageInput');
            if (inp) inp.value = '';
        });
    }

    // Called by WebSocket updates
    onPersonEvent(event) {
        if (['PERSON_ENROLLED', 'PERSON_UPDATED', 'PERSON_DISABLED', 'PERSON_ENABLED', 'PERSON_DELETED'].includes(event.type)) {
            this.loadPersons();
        }
    }
}
