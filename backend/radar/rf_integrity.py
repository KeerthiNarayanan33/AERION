import time
from typing import Dict, Any, Optional
from datetime import datetime, timezone

from backend.logger import logger

class RFIntegrityMonitor:
    """
    Defensive Electronic Warfare (EW) & RF Jamming Anomaly Monitor (Sections 61 & 62).
    Analyzes physical layer mmWave radar telemetry, ESP32 packet jitter,
    UART frame corruption, and RF noise floor shifts to detect barrage jamming,
    frequency hopping interference, or physical transmission line tampering.
    """

    def __init__(self):
        self.packet_loss_rate: float = 0.012  # Baseline 1.2% nominal packet loss
        self.rssi_dbm: float = -56.0           # Nominal Wi-Fi/LoRa RSSI
        self.noise_floor_dbm: float = -94.0    # Ambient thermal noise floor
        self.jitter_ms: float = 2.4            # Transmission jitter
        self.ew_state: str = "NORMAL"          # "NORMAL" | "SIGNAL_DEGRADATION" | "ACTIVE_RF_JAMMING"
        self.countermeasure_active: bool = False
        self.last_anomaly_timestamp: Optional[str] = None
        self.simulated_until: float = 0.0

    @property
    def snr_db(self) -> float:
        """Signal-to-Noise Ratio (dB) = RSSI - Noise Floor."""
        return round(self.rssi_dbm - self.noise_floor_dbm, 1)

    def evaluate_telemetry(
        self,
        packet_loss: Optional[float] = None,
        noise_floor: Optional[float] = None,
        jitter: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Updates RF metrics and evaluates electronic warfare threat levels.
        """
        now = time.time()
        # If simulated jamming has expired, auto-recover
        if self.ew_state == "ACTIVE_RF_JAMMING" and self.simulated_until > 0 and now > self.simulated_until:
            self.reset()

        if packet_loss is not None:
            self.packet_loss_rate = max(0.0, min(1.0, packet_loss))
        if noise_floor is not None:
            self.noise_floor_dbm = noise_floor
        if jitter is not None:
            self.jitter_ms = jitter

        # Threshold rules for Electronic Warfare detection
        if self.packet_loss_rate >= 0.45 or self.snr_db < 6.0 or self.noise_floor_dbm > -60.0:
            self.ew_state = "ACTIVE_RF_JAMMING"
            self.countermeasure_active = True
            self.last_anomaly_timestamp = datetime.now(timezone.utc).isoformat()
        elif self.packet_loss_rate >= 0.15 or self.snr_db < 18.0:
            self.ew_state = "SIGNAL_DEGRADATION"
            self.countermeasure_active = False
        else:
            if self.simulated_until <= now:
                self.ew_state = "NORMAL"
                self.countermeasure_active = False

        return self.get_telemetry()

    def simulate_jamming(self, severity: str = "HIGH", duration_seconds: float = 20.0) -> Dict[str, Any]:
        """
        Triggers an active RF Jamming barrage anomaly for live evaluator demonstration.
        """
        now = time.time()
        self.simulated_until = now + duration_seconds
        self.ew_state = "ACTIVE_RF_JAMMING"
        self.packet_loss_rate = 0.74
        self.noise_floor_dbm = -46.0  # Intense broadband noise injection
        self.rssi_dbm = -58.0
        self.jitter_ms = 48.6
        self.countermeasure_active = True
        self.last_anomaly_timestamp = datetime.now(timezone.utc).isoformat()

        logger.warning(
            f"[EW MONITOR] CRITICAL RF JAMMING DETECTED! Noise floor: {self.noise_floor_dbm} dBm, "
            f"Loss: {self.packet_loss_rate * 100:.1f}%. Activating autonomous optical lock countermeasure."
        )
        return self.get_telemetry()

    def reset(self) -> Dict[str, Any]:
        """Restores nominal RF and electronic propagation environment."""
        self.packet_loss_rate = 0.012
        self.rssi_dbm = -56.0
        self.noise_floor_dbm = -94.0
        self.jitter_ms = 2.4
        self.ew_state = "NORMAL"
        self.countermeasure_active = False
        self.simulated_until = 0.0
        logger.info("[EW MONITOR] Electronic spectrum restored to NORMAL clean baseline.")
        return self.get_telemetry()

    def get_telemetry(self) -> Dict[str, Any]:
        """Returns structured EW and RF spectrum telemetry."""
        return {
            "status": "HEALTHY",
            "ew_state": self.ew_state,
            "snr_db": self.snr_db,
            "rssi_dbm": self.rssi_dbm,
            "noise_floor_dbm": self.noise_floor_dbm,
            "packet_loss_rate": round(self.packet_loss_rate, 3),
            "packet_loss_percentage": round(self.packet_loss_rate * 100, 1),
            "jitter_ms": round(self.jitter_ms, 1),
            "countermeasure_active": self.countermeasure_active,
            "recommended_action": (
                "Deploy UAV for aerial line-of-sight visual confirmation and switch optical cameras to high-contrast mode."
                if self.ew_state == "ACTIVE_RF_JAMMING"
                else ("Monitor radar packet jitter." if self.ew_state == "SIGNAL_DEGRADATION" else "Spectrum clean.")
            ),
            "last_anomaly": self.last_anomaly_timestamp,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

rf_integrity_monitor = RFIntegrityMonitor()
