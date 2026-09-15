/**
 * Top-Down 2D Radar Canvas HUD Renderer
 * Visualizes LD2450 mmWave targets, sweep beam, and surveillance zones.
 */
export class RadarView {
    constructor(canvasId) {
        this.canvas = document.getElementById(canvasId);
        if (!this.canvas) return;
        this.ctx = this.canvas.getContext('2d');
        this.targets = [];
        this.sweepAngle = 0;
        this.maxRangeMeters = 8.0; // LD2450 typical tracking range
        this.fovAngle = 120; // LD2450 ~120 degree azimuth
        this.animationFrameId = null;

        this.initCanvas();
        this.startRenderLoop();
    }

    initCanvas() {
        // High DPI canvas scaling
        const rect = this.canvas.getBoundingClientRect();
        const dpr = window.devicePixelRatio || 1;
        this.canvas.width = (rect.width || 400) * dpr;
        this.canvas.height = (rect.height || 400) * dpr;
        this.ctx.scale(dpr, dpr);
        this.width = rect.width || 400;
        this.height = rect.height || 400;

        window.addEventListener('resize', () => {
            const r = this.canvas.getBoundingClientRect();
            if (r.width > 0 && r.height > 0) {
                this.canvas.width = r.width * (window.devicePixelRatio || 1);
                this.canvas.height = r.height * (window.devicePixelRatio || 1);
                this.ctx.scale(window.devicePixelRatio || 1, window.devicePixelRatio || 1);
                this.width = r.width;
                this.height = r.height;
            }
        });
    }

    setTargets(targets) {
        this.targets = targets || [];
    }

    startRenderLoop() {
        const render = () => {
            this.draw();
            this.sweepAngle = (this.sweepAngle + 0.035) % (Math.PI * 2);
            this.animationFrameId = requestAnimationFrame(render);
        };
        this.animationFrameId = requestAnimationFrame(render);
    }

    draw() {
        const { ctx, width, height } = this;
        ctx.clearRect(0, 0, width, height);

        const centerX = width / 2;
        const centerY = height - 30; // Radar antenna stationed at bottom center
        const radius = Math.min(centerX - 20, centerY - 20);

        // 1. Draw Range Rings (2m, 4m, 6m, 8m)
        const rings = [0.25, 0.5, 0.75, 1.0];
        ctx.lineWidth = 1;
        ctx.strokeStyle = 'rgba(0, 229, 255, 0.15)';
        ctx.fillStyle = 'rgba(0, 229, 255, 0.5)';
        ctx.font = '9px JetBrains Mono, monospace';

        rings.forEach((ratio, idx) => {
            const r = radius * ratio;
            ctx.beginPath();
            // Arc for 120 degree cone (-60 deg to +60 deg from vertical)
            ctx.arc(centerX, centerY, r, -Math.PI * 5/6, -Math.PI * 1/6);
            ctx.stroke();

            // Distance label
            const distLabel = `${(this.maxRangeMeters * ratio).toFixed(1)}m`;
            ctx.fillText(distLabel, centerX + 6, centerY - r + 10);
        });

        // 2. Azimuth Angle Rays (-60°, -30°, 0°, +30°, +60°)
        const angles = [-Math.PI/3, -Math.PI/6, 0, Math.PI/6, Math.PI/3];
        angles.forEach(ang => {
            const x = centerX + radius * Math.sin(ang);
            const y = centerY - radius * Math.cos(ang);
            ctx.beginPath();
            ctx.moveTo(centerX, centerY);
            ctx.lineTo(x, y);
            ctx.strokeStyle = ang === 0 ? 'rgba(0, 229, 255, 0.3)' : 'rgba(0, 229, 255, 0.1)';
            ctx.stroke();

            const degLabel = `${Math.round(ang * 180 / Math.PI)}°`;
            ctx.fillText(degLabel, x - 8, y - 6);
        });

        // 3. Radar Sweep Line (oscillating across FOV cone)
        const sweepOscillation = Math.sin(this.sweepAngle) * (Math.PI / 3); // -60 to +60 degrees
        const sweepX = centerX + radius * Math.sin(sweepOscillation);
        const sweepY = centerY - radius * Math.cos(sweepOscillation);

        const sweepGradient = ctx.createLinearGradient(centerX, centerY, sweepX, sweepY);
        sweepGradient.addColorStop(0, 'rgba(0, 230, 118, 0.8)');
        sweepGradient.addColorStop(1, 'rgba(0, 229, 255, 0.2)');

        ctx.beginPath();
        ctx.moveTo(centerX, centerY);
        ctx.lineTo(sweepX, sweepY);
        ctx.strokeStyle = sweepGradient;
        ctx.lineWidth = 2;
        ctx.stroke();

        // Sweep cone shadow trail
        ctx.beginPath();
        ctx.moveTo(centerX, centerY);
        ctx.arc(centerX, centerY, radius, -Math.PI/2 + sweepOscillation - 0.2, -Math.PI/2 + sweepOscillation);
        ctx.closePath();
        ctx.fillStyle = 'rgba(0, 230, 118, 0.04)';
        ctx.fill();

        // 4. Radar Origin Node (LD2450 Station)
        ctx.beginPath();
        ctx.arc(centerX, centerY, 6, 0, Math.PI * 2);
        ctx.fillStyle = '#00e5ff';
        ctx.fill();
        ctx.strokeStyle = '#fff';
        ctx.lineWidth = 1.5;
        ctx.stroke();

        ctx.fillStyle = 'rgba(255, 255, 255, 0.7)';
        ctx.font = '10px Outfit, sans-serif';
        ctx.fillText('LD2450 RADAR', centerX - 36, centerY + 18);

        // 5. Render Detected Targets
        this.targets.forEach((t) => {
            // Coordinate mapping: x (left/right meters), y (forward distance meters)
            const targetX = centerX + (t.x / (this.maxRangeMeters / 2)) * (radius / 2);
            const targetY = centerY - (t.y / this.maxRangeMeters) * radius;

            // Target color based on distance/threat
            let targetColor = '#00e676';
            if (t.y < 3.0) targetColor = '#ff1744'; // Close intrusion
            else if (t.y < 5.0) targetColor = '#ffab00'; // Warning zone

            // Blip glow halo
            ctx.beginPath();
            ctx.arc(targetX, targetY, 10, 0, Math.PI * 2);
            ctx.fillStyle = targetColor === '#ff1744' ? 'rgba(255, 23, 68, 0.25)' : 'rgba(0, 230, 118, 0.2)';
            ctx.fill();

            // Core Blip
            ctx.beginPath();
            ctx.arc(targetX, targetY, 4, 0, Math.PI * 2);
            ctx.fillStyle = targetColor;
            ctx.fill();
            ctx.strokeStyle = '#fff';
            ctx.lineWidth = 1.5;
            ctx.stroke();

            // Target Label
            const targetLabel = (t.name || t.identity) ? `T#${t.target_id} (${t.name || t.identity})` : `T#${t.target_id}`;
            ctx.fillStyle = '#fff';
            ctx.font = 'bold 9px JetBrains Mono, monospace';
            ctx.fillText(targetLabel, targetX + 8, targetY - 4);
            ctx.fillStyle = 'rgba(255, 255, 255, 0.7)';
            ctx.font = '8px JetBrains Mono, monospace';
            ctx.fillText(`${t.distance || (Math.sqrt(t.x**2 + t.y**2)).toFixed(1)}m | ${t.speed || 0}m/s`, targetX + 8, targetY + 6);


            // Velocity Vector Line
            if (t.speed > 0.1) {
                ctx.beginPath();
                ctx.moveTo(targetX, targetY);
                ctx.lineTo(targetX, targetY - (t.speed * 8));
                ctx.strokeStyle = targetColor;
                ctx.lineWidth = 1.5;
                ctx.stroke();
            }
        });
    }

    destroy() {
        if (this.animationFrameId) {
            cancelAnimationFrame(this.animationFrameId);
        }
    }
}
