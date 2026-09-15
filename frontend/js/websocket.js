/**
 * Real-time WebSocket Client for Border Surveillance HUD
 * Handles automatic reconnects, heartbeats, and message routing.
 */
class SurveillanceSocket {
    constructor() {
        this.socket = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 10;
        this.reconnectDelay = 2000;
        this.listeners = new Map();
        this.statusElement = null;
    }

    init() {
        this.statusElement = document.getElementById('wsStatus');
        this.connect();
    }

    connect() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/live`;
        
        console.log(`[WS] Connecting to ${wsUrl}...`);
        this.socket = new WebSocket(wsUrl);

        this.socket.onopen = () => {
            console.log('[WS] Connected successfully.');
            this.reconnectAttempts = 0;
            this.updateStatus(true);
        };

        this.socket.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                this.dispatch(data.type, data);
            } catch (err) {
                console.error('[WS] Error parsing message:', err, event.data);
            }
        };

        this.socket.onclose = () => {
            console.warn('[WS] Connection closed.');
            this.updateStatus(false);
            this.scheduleReconnect();
        };

        this.socket.onerror = (err) => {
            console.error('[WS] Socket error:', err);
            this.updateStatus(false);
        };
    }

    scheduleReconnect() {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            const delay = Math.min(this.reconnectDelay * Math.pow(1.5, this.reconnectAttempts - 1), 15000);
            console.log(`[WS] Reconnecting in ${Math.round(delay / 1000)}s (attempt ${this.reconnectAttempts})...`);
            setTimeout(() => this.connect(), delay);
        } else {
            console.error('[WS] Max reconnect attempts reached.');
        }
    }

    updateStatus(connected) {
        if (!this.statusElement) return;
        const dot = this.statusElement.querySelector('.dot');
        const text = this.statusElement.querySelector('.ws-label');
        if (connected) {
            this.statusElement.className = 'status-pill online';
            if (text) text.textContent = 'FEED: LIVE';
        } else {
            this.statusElement.className = 'status-pill offline';
            if (text) text.textContent = 'FEED: RECONNECTING';
        }
    }

    on(eventType, callback) {
        if (!this.listeners.has(eventType)) {
            this.listeners.set(eventType, []);
        }
        this.listeners.get(eventType).push(callback);
    }

    dispatch(eventType, data) {
        // Specific listeners
        if (this.listeners.has(eventType)) {
            this.listeners.get(eventType).forEach(cb => cb(data));
        }
        // Wildcard listeners
        if (this.listeners.has('*')) {
            this.listeners.get('*').forEach(cb => cb(data));
        }

        // Also trigger DOM custom event
        window.dispatchEvent(new CustomEvent('surveillance:event', { detail: data }));
    }

    send(data) {
        if (this.socket && this.socket.readyState === WebSocket.OPEN) {
            this.socket.send(typeof data === 'string' ? data : JSON.stringify(data));
        }
    }
}

export const wsClient = new SurveillanceSocket();
