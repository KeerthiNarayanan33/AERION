import time
import math
import threading
from typing import Dict, Any, Optional, List
from abc import ABC, abstractmethod

from backend.config import get_settings
from backend.logger import logger

settings = get_settings()

class GPSProvider(ABC):
    """Abstract interface for GPS sensor telemetry (Section 19)."""

    @abstractmethod
    def get_latitude(self) -> float:
        pass

    @abstractmethod
    def get_longitude(self) -> float:
        pass

    @abstractmethod
    def get_altitude(self) -> float:
        pass

    @abstractmethod
    def get_speed(self) -> float:
        pass

    @abstractmethod
    def get_heading(self) -> float:
        pass

    @abstractmethod
    def get_fix_status(self) -> str:
        pass

    @abstractmethod
    def get_satellites(self) -> int:
        pass

    @abstractmethod
    def is_valid_fix(self) -> bool:
        pass

    @abstractmethod
    def get_telemetry(self) -> Dict[str, Any]:
        pass

class SimulatedGPSProvider(GPSProvider):
    """
    Simulated GPS Telemetry Provider (Section 21).
    Explicitly flags data source as SIMULATION.
    """
    def __init__(
        self,
        base_lat: float = 31.6240,
        base_lon: float = 74.8723,
        base_alt: float = 0.0
    ):
        self.latitude = base_lat
        self.longitude = base_lon
        self.altitude = base_alt
        self.speed = 0.0
        self.heading = 0.0
        self.satellites = 10
        self.fix_status = "3D FIX"
        self.last_update = time.time()
        self._lock = threading.Lock()

    def update_position(
        self,
        lat: float,
        lon: float,
        alt: float = 0.0,
        speed: float = 0.0,
        heading: float = 0.0
    ) -> None:
        """Called by drone flight controller to update simulated coordinate."""
        with self._lock:
            self.latitude = lat
            self.longitude = lon
            self.altitude = alt
            self.speed = speed
            self.heading = heading
            self.last_update = time.time()

    def get_latitude(self) -> float:
        with self._lock:
            return round(self.latitude, 6)

    def get_longitude(self) -> float:
        with self._lock:
            return round(self.longitude, 6)

    def get_altitude(self) -> float:
        with self._lock:
            return round(self.altitude, 1)

    def get_speed(self) -> float:
        with self._lock:
            return round(self.speed, 1)

    def get_heading(self) -> float:
        with self._lock:
            return round(self.heading, 1)

    def get_fix_status(self) -> str:
        with self._lock:
            return self.fix_status

    def get_satellites(self) -> int:
        with self._lock:
            return self.satellites

    def is_valid_fix(self) -> bool:
        return self.fix_status in ("3D FIX", "2D FIX")

    def get_telemetry(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "source": "SIMULATION",
                "latitude": round(self.latitude, 6),
                "longitude": round(self.longitude, 6),
                "altitude_m": round(self.altitude, 1),
                "speed_mps": round(self.speed, 1),
                "heading_deg": round(self.heading, 1),
                "satellites": self.satellites,
                "fix_status": self.fix_status,
                "is_valid": True,
                "last_update": self.last_update
            }

class Neo6mGPSProvider(GPSProvider):
    """
    Live NEO-6M GNSS receiver interface over UART/Serial port (Section 20).
    Parses NMEA $GPGGA and $GPRMC sentences with checksum and fix quality validation.
    """
    def __init__(
        self,
        port: str = "COM4",
        baud_rate: int = 9600
    ):
        self.port = port
        self.baud_rate = baud_rate
        self.latitude: Optional[float] = None
        self.longitude: Optional[float] = None
        self.altitude: float = 0.0
        self.speed: float = 0.0
        self.heading: float = 0.0
        self.satellites: int = 0
        self.fix_status: str = "NO FIX"
        self.last_valid_lat: Optional[float] = None
        self.last_valid_lon: Optional[float] = None
        self.last_update: float = 0.0
        self.is_connected = False
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def start(self) -> None:
        """Starts background serial reader thread."""
        with self._lock:
            if self._running:
                return
            self._running = True
            self._thread = threading.Thread(target=self._serial_loop, daemon=True, name="NEO6M-Reader")
            self._thread.start()
            logger.info(f"[NEO-6M] Serial reader initiated for port {self.port} @ {self.baud_rate} baud.")

    def stop(self) -> None:
        """Stops background serial reader."""
        with self._lock:
            self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.5)

    def _parse_nmea_coord(self, raw_coord: str, direction: str) -> Optional[float]:
        """Converts NMEA ddmm.mmmm format to decimal degrees."""
        try:
            if not raw_coord or not direction:
                return None
            dot_idx = raw_coord.find('.')
            if dot_idx < 2:
                return None
            deg_chars = dot_idx - 2
            degrees = float(raw_coord[:deg_chars])
            minutes = float(raw_coord[deg_chars:])
            dec = degrees + (minutes / 60.0)
            if direction in ('S', 'W'):
                dec = -dec
            return dec
        except Exception:
            return None

    def _parse_nmea_sentence(self, sentence: str) -> None:
        """Parses $GPGGA and $GPRMC sentences."""
        sentence = sentence.strip()
        if not sentence.startswith('$'):
            return

        parts = sentence.split(',')
        msg_type = parts[0]

        now = time.time()

        with self._lock:
            # $GPGGA: Global Positioning System Fix Data
            if msg_type in ('$GPGGA', '$GNGGA') and len(parts) >= 10:
                try:
                    fix_quality = int(parts[6]) if parts[6] else 0
                    sat_count = int(parts[7]) if parts[7] else 0
                    alt = float(parts[9]) if parts[9] else 0.0

                    self.satellites = sat_count
                    self.altitude = alt

                    if fix_quality in (1, 2):
                        lat = self._parse_nmea_coord(parts[2], parts[3])
                        lon = self._parse_nmea_coord(parts[4], parts[5])
                        if lat is not None and lon is not None:
                            self.latitude = lat
                            self.longitude = lon
                            self.last_valid_lat = lat
                            self.last_valid_lon = lon
                            self.fix_status = "3D FIX" if sat_count >= 4 else "2D FIX"
                            self.last_update = now
                    else:
                        self.fix_status = "NO FIX"
                except Exception as ex:
                    logger.debug(f"[NEO-6M] Error parsing GGA: {ex}")

            # $GPRMC: Recommended Minimum Specific GNSS Data
            elif msg_type in ('$GPRMC', '$GNRMC') and len(parts) >= 9:
                try:
                    status = parts[2]
                    if status == 'A':
                        lat = self._parse_nmea_coord(parts[3], parts[4])
                        lon = self._parse_nmea_coord(parts[5], parts[6])
                        # Speed in knots -> convert to m/s
                        knots = float(parts[7]) if parts[7] else 0.0
                        self.speed = knots * 0.514444
                        # Course over ground
                        self.heading = float(parts[8]) if parts[8] else self.heading

                        if lat is not None and lon is not None:
                            self.latitude = lat
                            self.longitude = lon
                            self.last_valid_lat = lat
                            self.last_valid_lon = lon
                            if self.fix_status == "NO FIX":
                                self.fix_status = "2D FIX"
                            self.last_update = now
                    else:
                        self.fix_status = "NO FIX"
                except Exception as ex:
                    logger.debug(f"[NEO-6M] Error parsing RMC: {ex}")

    def _serial_loop(self) -> None:
        """Reads raw NMEA lines from USB serial interface."""
        try:
            import serial
        except ImportError:
            logger.warning("[NEO-6M] pyserial is not installed; NEO-6M live port disabled.")
            with self._lock:
                self.fix_status = "NO FIX (pyserial missing)"
            return

        while self._running:
            ser = None
            try:
                ser = serial.Serial(self.port, self.baud_rate, timeout=1.0)
                with self._lock:
                    self.is_connected = True
                logger.info(f"[NEO-6M] Connected to physical receiver on {self.port}.")

                while self._running:
                    line = ser.readline().decode('ascii', errors='ignore')
                    if line:
                        self._parse_nmea_sentence(line)

            except Exception as e:
                with self._lock:
                    self.is_connected = False
                    self.fix_status = "NO FIX (Disconnected)"
                logger.debug(f"[NEO-6M] Serial read idle or port unavailable ({self.port}): {e}")
                time.sleep(3.0)
            finally:
                if ser and ser.is_open:
                    ser.close()

    def get_latitude(self) -> float:
        with self._lock:
            return self.latitude if self.latitude is not None else (self.last_valid_lat or 0.0)

    def get_longitude(self) -> float:
        with self._lock:
            return self.longitude if self.longitude is not None else (self.last_valid_lon or 0.0)

    def get_altitude(self) -> float:
        with self._lock:
            return self.altitude

    def get_speed(self) -> float:
        with self._lock:
            return self.speed

    def get_heading(self) -> float:
        with self._lock:
            return self.heading

    def get_fix_status(self) -> str:
        with self._lock:
            # If no fresh update within 5 seconds, flag stale fix
            if time.time() - self.last_update > 5.0:
                return "NO FIX"
            return self.fix_status

    def get_satellites(self) -> int:
        with self._lock:
            return self.satellites

    def is_valid_fix(self) -> bool:
        return self.get_fix_status() in ("3D FIX", "2D FIX")

    def get_telemetry(self) -> Dict[str, Any]:
        with self._lock:
            valid = self.is_valid_fix()
            return {
                "source": "LIVE NEO-6M",
                "port": self.port,
                "is_connected": self.is_connected,
                "latitude": round(self.latitude, 6) if self.latitude is not None else None,
                "longitude": round(self.longitude, 6) if self.longitude is not None else None,
                "last_valid_latitude": round(self.last_valid_lat, 6) if self.last_valid_lat is not None else None,
                "last_valid_longitude": round(self.last_valid_lon, 6) if self.last_valid_lon is not None else None,
                "altitude_m": round(self.altitude, 1),
                "speed_mps": round(self.speed, 1),
                "heading_deg": round(self.heading, 1),
                "satellites": self.satellites,
                "fix_status": self.get_fix_status(),
                "is_valid": valid,
                "last_update": self.last_update
            }

class GPSManager:
    """
    Central GPS Management Service (Section 19).
    Orchestrates active provider (Live NEO-6M or Simulation).
    """
    _instance: Optional['GPSManager'] = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(GPSManager, cls).__new__(cls)
                cls._instance.sim_provider = SimulatedGPSProvider(
                    base_lat=settings.UAV_HOME_LAT,
                    base_lon=settings.UAV_HOME_LON
                )
                cls._instance.live_provider = Neo6mGPSProvider(
                    port=settings.GPS_SERIAL_PORT,
                    baud_rate=settings.GPS_BAUD_RATE
                )
                cls._instance.mode = settings.GPS_MODE
                cls._instance._initialized = False
            return cls._instance

    def initialize(self) -> None:
        with self._lock:
            if self._initialized:
                return
            if self.mode == "LIVE":
                self.live_provider.start()
            self._initialized = True
            logger.info(f"[GPS] GPSManager initialized in {self.mode} mode.")

    def set_mode(self, mode: str) -> None:
        with self._lock:
            m = mode.upper()
            if m not in ("SIMULATION", "LIVE"):
                raise ValueError("Mode must be 'SIMULATION' or 'LIVE'")
            self.mode = m
            if self.mode == "LIVE":
                self.live_provider.start()
            else:
                self.live_provider.stop()
            logger.info(f"[GPS] GPS mode switched to {self.mode}.")

    @property
    def active_provider(self) -> GPSProvider:
        if self.mode == "LIVE":
            return self.live_provider
        return self.sim_provider

    def get_position(self) -> tuple[float, float]:
        """Returns (latitude, longitude) of current drone position."""
        p = self.active_provider
        return p.get_latitude(), p.get_longitude()

    def get_latitude(self) -> float:
        return self.active_provider.get_latitude()

    def get_longitude(self) -> float:
        return self.active_provider.get_longitude()

    def get_altitude(self) -> float:
        return self.active_provider.get_altitude()

    def get_speed(self) -> float:
        return self.active_provider.get_speed()

    def get_heading(self) -> float:
        return self.active_provider.get_heading()

    def get_fix_status(self) -> str:
        return self.active_provider.get_fix_status()

    def get_satellites(self) -> int:
        return self.active_provider.get_satellites()

    def is_valid_fix(self) -> bool:
        return self.active_provider.is_valid_fix()

    def get_telemetry(self) -> Dict[str, Any]:
        t = self.active_provider.get_telemetry()
        t["mode"] = self.mode
        return t

gps_manager = GPSManager()
