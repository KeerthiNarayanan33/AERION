/**
 * 2D Tactical Surveillance Map & Zone Visualizer
 */

/**
 * Converts a hex color string (#rrggbb or #rgb) to rgba() with given alpha.
 */
function hexToRgba(hex, alpha) {
    let h = hex.replace('#', '');
    if (h.length === 3) h = h[0]+h[0]+h[1]+h[1]+h[2]+h[2];
    const r = parseInt(h.substring(0,2), 16);
    const g = parseInt(h.substring(2,4), 16);
    const b = parseInt(h.substring(4,6), 16);
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

/**
 * Computes the centroid (average x, y) of a polygon coordinate array [[x,y],...].
 */
function polygonCentroid(coords) {
    if (!coords || coords.length === 0) return [0.5, 0.5];
    const sx = coords.reduce((s, p) => s + p[0], 0);
    const sy = coords.reduce((s, p) => s + p[1], 0);
    return [sx / coords.length, sy / coords.length];
}

export class ZoneMap {
    constructor(canvasId) {
        this.canvas = document.getElementById(canvasId);
        if (!this.canvas) return;
        this.ctx = this.canvas.getContext('2d');
        this.zones = [];
        this.targets = [];
        this.heatmapEnabled = false;
        this.heatmapData = null;
        this.init();
    }

    setHeatmapData(data) {
        this.heatmapData = data;
        if (this.heatmapEnabled) {
            this.draw();
        }
    }

    toggleHeatmap(forcedState) {
        this.heatmapEnabled = forcedState !== undefined ? forcedState : !this.heatmapEnabled;
        this.draw();
        return this.heatmapEnabled;
    }

    init() {
        const rect = this.canvas.getBoundingClientRect();
        const dpr = window.devicePixelRatio || 1;
        this.canvas.width = (rect.width || 600) * dpr;
        this.canvas.height = (rect.height || 400) * dpr;
        this.ctx.scale(dpr, dpr);
        this.width = rect.width || 600;
        this.height = rect.height || 400;

        window.addEventListener('resize', () => {
            const r = this.canvas.getBoundingClientRect();
            if (r.width > 0 && r.height > 0) {
                this.canvas.width = r.width * (window.devicePixelRatio || 1);
                this.canvas.height = r.height * (window.devicePixelRatio || 1);
                this.ctx.scale(window.devicePixelRatio || 1, window.devicePixelRatio || 1);
                this.width = r.width;
                this.height = r.height;
                this.draw();
            }
        });
    }

    setZones(zones) {
        this.zones = zones || [];
        this.draw();
    }

    setTargets(targets) {
        this.targets = targets || [];
        this.draw();
    }

    draw() {
        const { ctx, width, height } = this;
        ctx.clearRect(0, 0, width, height);

        // Tactical grid background
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.04)';
        ctx.lineWidth = 1;
        const gridSize = 30;
        for (let x = 0; x < width; x += gridSize) {
            ctx.beginPath();
            ctx.moveTo(x, 0);
            ctx.lineTo(x, height);
            ctx.stroke();
        }
        for (let y = 0; y < height; y += gridSize) {
            ctx.beginPath();
            ctx.moveTo(0, y);
            ctx.lineTo(width, y);
            ctx.stroke();
        }

        // Draw Heatmap Overlay if enabled
        if (this.heatmapEnabled && this.heatmapData) {
            this.drawHeatmapOverlay();
        }

        // Draw Zones
        this.zones.forEach(zone => {
            if (!zone.coordinates || zone.coordinates.length < 3) return;

            ctx.beginPath();
            const firstPt = zone.coordinates[0];
            ctx.moveTo(firstPt[0] * width, firstPt[1] * height);

            for (let i = 1; i < zone.coordinates.length; i++) {
                const pt = zone.coordinates[i];
                ctx.lineTo(pt[0] * width, pt[1] * height);
            }
            ctx.closePath();

            // Fill with zone-type-specific alpha and color
            let fillAlpha = 0.08;
            let strokeColor = zone.color || '#00e676';
            let lineWidth = 1.5;
            let dashPattern = [5, 4];

            if (zone.zone_type === 'RESTRICTED') {
                fillAlpha = 0.18;
                strokeColor = '#ff1744';
                lineWidth = 2.5;
                dashPattern = [8, 3];
            } else if (zone.zone_type === 'WARNING') {
                fillAlpha = 0.13;
                strokeColor = '#ffab00';
                lineWidth = 2;
                dashPattern = [6, 4];
            } else {
                // NORMAL zone
                strokeColor = zone.color || '#00e676';
                fillAlpha = 0.08;
            }

            // Safely convert any color (hex or rgb) to rgba
            const fillColor = strokeColor.startsWith('#')
                ? hexToRgba(strokeColor, fillAlpha)
                : strokeColor.replace(/rgb\(/, 'rgba(').replace(/\)$/, `, ${fillAlpha})`);

            ctx.fillStyle = fillColor;
            ctx.fill();

            ctx.strokeStyle = strokeColor;
            ctx.lineWidth = lineWidth;
            ctx.setLineDash(dashPattern);
            ctx.stroke();
            ctx.setLineDash([]);

            // Label positioned at polygon centroid for correct placement
            const [cx, cy] = polygonCentroid(zone.coordinates);
            const labelX = cx * width;
            const labelY = cy * height;

            // Zone label background pill for readability
            const labelText = `${zone.name.toUpperCase()}`;
            const typeText = `[${zone.zone_type}]`;
            ctx.font = 'bold 11px Outfit, sans-serif';
            const lw = ctx.measureText(labelText).width;
            ctx.fillStyle = 'rgba(7, 10, 17, 0.75)';
            ctx.beginPath();
            if (ctx.roundRect) {
                ctx.roundRect(labelX - lw / 2 - 6, labelY - 16, lw + 12, 22, 3);
            } else {
                ctx.rect(labelX - lw / 2 - 6, labelY - 16, lw + 12, 22);
            }
            ctx.fill();

            ctx.fillStyle = strokeColor;
            ctx.textAlign = 'center';
            ctx.fillText(labelText, labelX, labelY);

            ctx.fillStyle = 'rgba(255,255,255,0.55)';
            ctx.font = '9px JetBrains Mono, monospace';
            ctx.fillText(typeText, labelX, labelY + 13);

            if (zone.center_lat && zone.center_lon) {
                ctx.fillStyle = 'rgba(255, 255, 255, 0.6)';
                ctx.font = '8px JetBrains Mono, monospace';
                ctx.fillText(`📍 ${Number(zone.center_lat).toFixed(4)}°N, ${Number(zone.center_lon).toFixed(4)}°E`, labelX, labelY + 25);
            }
            ctx.textAlign = 'left';
        });

        // Draw Radar Station Icon & Coverage Frustum
        const radarX = width * 0.5;
        const radarY = height * 0.92;

        ctx.beginPath();
        ctx.arc(radarX, radarY, 8, 0, Math.PI * 2);
        ctx.fillStyle = '#00e5ff';
        ctx.fill();
        ctx.strokeStyle = '#fff';
        ctx.lineWidth = 2;
        ctx.stroke();

        ctx.fillStyle = '#fff';
        ctx.font = '10px Outfit, sans-serif';
        ctx.fillText('RADAR 01', radarX - 22, radarY + 20);

        // Draw Cameras Positions
        const cam1X = width * 0.25;
        const cam1Y = height * 0.90;
        ctx.beginPath();
        ctx.arc(cam1X, cam1Y, 6, 0, Math.PI * 2);
        ctx.fillStyle = '#00e676';
        ctx.fill();
        ctx.fillText('CAM 01 (CCTV)', cam1X - 35, cam1Y + 18);

        const cam2X = width * 0.75;
        const cam2Y = height * 0.90;
        ctx.beginPath();
        ctx.arc(cam2X, cam2Y, 6, 0, Math.PI * 2);
        ctx.fillStyle = '#ff5252';
        ctx.fill();
        ctx.fillText('CAM 02 (OFFLINE)', cam2X - 40, cam2Y + 18);

        // Draw Targets
        this.targets.forEach(t => {
            // Map normalized to map coordinates
            const px = radarX + (t.x * 25);
            const py = radarY - (t.y * 25);

            ctx.beginPath();
            ctx.arc(px, py, 6, 0, Math.PI * 2);
            ctx.fillStyle = '#ff1744';
            ctx.fill();
            ctx.strokeStyle = '#fff';
            ctx.lineWidth = 1.5;
            ctx.stroke();

            ctx.fillStyle = '#fff';
            ctx.font = '10px JetBrains Mono, monospace';
            ctx.fillText(`TARGET #${t.target_id}`, px + 10, py - 4);
        });
    }

    drawHeatmapOverlay() {
        const { ctx, width, height } = this;
        const grid = this.heatmapData.density_grid;
        if (!grid || grid.length === 0) return;

        const rows = grid.length;
        const cols = grid[0].length;
        const cellW = width / cols;
        const cellH = height / rows;

        ctx.save();
        // Render Gaussian density cells with soft radial blend
        for (let r = 0; r < rows; r++) {
            for (let c = 0; c < cols; c++) {
                const val = grid[r][c];
                if (val < 0.08) continue;
                const cx = (c + 0.5) * cellW;
                const cy = (r + 0.5) * cellH;
                const radius = Math.max(cellW, cellH) * 2.2;

                const radGrad = ctx.createRadialGradient(cx, cy, 2, cx, cy, radius);
                if (val > 0.7) {
                    radGrad.addColorStop(0, `rgba(255, 23, 68, ${val * 0.55})`);
                    radGrad.addColorStop(0.5, `rgba(255, 109, 0, ${val * 0.30})`);
                    radGrad.addColorStop(1, 'rgba(255, 23, 68, 0)');
                } else if (val > 0.35) {
                    radGrad.addColorStop(0, `rgba(255, 171, 0, ${val * 0.40})`);
                    radGrad.addColorStop(0.6, `rgba(255, 214, 0, ${val * 0.20})`);
                    radGrad.addColorStop(1, 'rgba(255, 171, 0, 0)');
                } else {
                    radGrad.addColorStop(0, `rgba(0, 243, 255, ${val * 0.30})`);
                    radGrad.addColorStop(0.7, `rgba(0, 229, 255, ${val * 0.12})`);
                    radGrad.addColorStop(1, 'rgba(0, 243, 255, 0)');
                }
                ctx.fillStyle = radGrad;
                ctx.beginPath();
                ctx.arc(cx, cy, radius, 0, Math.PI * 2);
                ctx.fill();
            }
        }

        // Hotspot Tactical Target Crosshairs & Labels
        if (this.heatmapData.hotspots) {
            this.heatmapData.hotspots.forEach(hs => {
                const hx = hs.x * width;
                const hy = hs.y * height;

                ctx.save();
                // Outer pulsating ring
                ctx.beginPath();
                ctx.arc(hx, hy, 16, 0, Math.PI * 2);
                ctx.strokeStyle = hs.risk_level === 'CRITICAL' ? 'rgba(255, 23, 68, 0.9)' : 'rgba(255, 171, 0, 0.9)';
                ctx.lineWidth = 1.5;
                ctx.setLineDash([4, 3]);
                ctx.stroke();

                // Crosshairs
                ctx.setLineDash([]);
                ctx.strokeStyle = hs.risk_level === 'CRITICAL' ? 'rgba(255, 23, 68, 0.7)' : 'rgba(255, 171, 0, 0.7)';
                ctx.beginPath();
                ctx.moveTo(hx - 20, hy);
                ctx.lineTo(hx + 20, hy);
                ctx.moveTo(hx, hy - 20);
                ctx.lineTo(hx, hy + 20);
                ctx.stroke();

                // Center core
                ctx.beginPath();
                ctx.arc(hx, hy, 4, 0, Math.PI * 2);
                ctx.fillStyle = hs.risk_level === 'CRITICAL' ? '#ff1744' : '#ffab00';
                ctx.fill();

                // HUD callout
                ctx.font = 'bold 10px JetBrains Mono, monospace';
                ctx.fillStyle = '#fff';
                ctx.fillText(`⚡ ${hs.id} [${Math.round(hs.intensity * 100)}% DENSITY]`, hx + 18, hy - 4);
                ctx.font = '9px Outfit, sans-serif';
                ctx.fillStyle = 'rgba(255, 255, 255, 0.75)';
                ctx.fillText(hs.name, hx + 18, hy + 8);
                ctx.restore();
            });
        }

        // Tactical HUD Header Badge
        ctx.fillStyle = 'rgba(15, 23, 42, 0.85)';
        ctx.strokeStyle = 'rgba(255, 23, 68, 0.6)';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.roundRect(10, 10, 310, 48, 4);
        ctx.fill();
        ctx.stroke();

        ctx.font = 'bold 10px JetBrains Mono, monospace';
        ctx.fillStyle = '#ff1744';
        ctx.fillText('🔴 PERIMETER THREAT DENSITY [2D KDE MATRIX]', 20, 28);
        ctx.font = '9px Outfit, sans-serif';
        ctx.fillStyle = 'rgba(255, 255, 255, 0.8)';
        ctx.fillText(`ANALYZED: ${this.heatmapData.total_incidents_analyzed || 25} INCIDENTS | PEAK: ${this.heatmapData.peak_risk_sector || 'ZONE_C'}`, 20, 44);

        ctx.restore();
    }
}
