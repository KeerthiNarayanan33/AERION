/**
 * System Telemetry & Hardware Utilization Dashboard
 */
export class MetricsMonitor {
    constructor() {
        this.cpuEl = document.getElementById('metricCpu');
        this.cpuBar = document.getElementById('metricCpuBar');
        this.ramEl = document.getElementById('metricRam');
        this.ramBar = document.getElementById('metricRamBar');
        this.gpuEl = document.getElementById('metricGpu');
        this.gpuBar = document.getElementById('metricGpuBar');
        this.vramEl = document.getElementById('metricVram');
        this.vramBar = document.getElementById('metricVramBar');
        this.aiFpsEl = document.getElementById('metricAiFps');
        this.camFpsEl = document.getElementById('metricCamFps');
    }

    update(metrics) {
        if (!metrics) return;

        // CPU
        if (metrics.cpu_percent !== undefined) {
            if (this.cpuEl) this.cpuEl.textContent = `${metrics.cpu_percent.toFixed(1)}%`;
            if (this.cpuBar) {
                this.cpuBar.style.width = `${Math.min(metrics.cpu_percent, 100)}%`;
                this.applyColorClass(this.cpuBar, metrics.cpu_percent);
            }
        }

        // RAM
        if (metrics.ram_percent !== undefined) {
            if (this.ramEl) this.ramEl.textContent = `${metrics.ram_percent.toFixed(1)}%`;
            if (this.ramBar) {
                this.ramBar.style.width = `${Math.min(metrics.ram_percent, 100)}%`;
                this.applyColorClass(this.ramBar, metrics.ram_percent);
            }
        }

        // GPU
        if (metrics.gpu && metrics.gpu.available) {
            const gpuUtil = metrics.gpu.gpu_utilization_percent || 0;
            if (this.gpuEl) this.gpuEl.textContent = `${gpuUtil.toFixed(1)}%`;
            if (this.gpuBar) {
                this.gpuBar.style.width = `${Math.min(gpuUtil, 100)}%`;
                this.applyColorClass(this.gpuBar, gpuUtil);
            }

            if (metrics.gpu.memory_total_mb > 0) {
                const vramPercent = (metrics.gpu.memory_used_mb / metrics.gpu.memory_total_mb) * 100;
                if (this.vramEl) this.vramEl.textContent = `${metrics.gpu.memory_used_mb.toFixed(0)} / ${metrics.gpu.memory_total_mb.toFixed(0)} MB`;
                if (this.vramBar) {
                    this.vramBar.style.width = `${Math.min(vramPercent, 100)}%`;
                    this.applyColorClass(this.vramBar, vramPercent);
                }
            }
        } else {
            if (this.gpuEl) this.gpuEl.textContent = 'CPU (Fallback)';
            if (this.vramEl) this.vramEl.textContent = 'Shared Memory';
        }

        // FPS
        if (metrics.target_ai_fps !== undefined && this.aiFpsEl) {
            this.aiFpsEl.textContent = `${metrics.target_ai_fps} FPS`;
        }
        if (metrics.camera_target_fps !== undefined && this.camFpsEl) {
            this.camFpsEl.textContent = `${metrics.camera_target_fps} FPS`;
        }
    }

    applyColorClass(barElement, value) {
        barElement.classList.remove('warn', 'danger');
        if (value > 85) {
            barElement.classList.add('danger');
        } else if (value > 65) {
            barElement.classList.add('warn');
        }
    }
}
