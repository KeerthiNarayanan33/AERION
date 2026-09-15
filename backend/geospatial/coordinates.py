"""
SENTINEL-AI: Georeferenced Geographic & Tactical Grid Coordinate Engine
Sections 34 & 75: WGS-84, UTM Zone 43N, MGRS, and QRT Mission Dispatch Generator.

Converts local sensor Cartesian (x,y) and radar polar (R, theta) into global
georeferenced coordinates (Latitude/Longitude, MGRS 8-digit military grid, UTM).
Generates standardized BSF/CAPF Quick Reaction Team (QRT) tactical mission orders.
"""

import math
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, asdict

# WGS-84 Ellipsoid constants
WGS84_A = 6378137.0         # semi-major axis in meters
WGS84_F = 1.0 / 298.257223563  # flattening
WGS84_B = WGS84_A * (1.0 - WGS84_F)  # semi-minor axis
WGS84_E2 = WGS84_F * (2.0 - WGS84_F)  # first eccentricity squared

@dataclass
class GeodeticAnchor:
    """Base station / forward operating base reference datum."""
    site_id: str = "FOB_ALPHA"
    site_name: str = "Forward Operating Base Alpha (Border Pillar BP-744)"
    latitude: float = 31.623400     # Decimal degrees North
    longitude: float = 74.872100    # Decimal degrees East
    elevation_amsl_m: float = 218.5 # Meters Above Mean Sea Level
    mast_height_m: float = 10.0     # Mast height above ground
    mast_azimuth_deg: float = 0.0   # Sensor boresight offset from True North (0° = North)
    utm_zone: str = "43N"
    mgrs_100k_square: str = "FU"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

def decimal_to_dms(deg: float, is_latitude: bool) -> str:
    """Converts decimal degrees to formatted degrees/minutes/seconds string."""
    direction = ""
    if is_latitude:
        direction = "N" if deg >= 0 else "S"
    else:
        direction = "E" if deg >= 0 else "W"
    
    abs_deg = abs(deg)
    d = int(abs_deg)
    rem = (abs_deg - d) * 60.0
    m = int(rem)
    s = (rem - m) * 60.0
    return f"{d}°{m:02d}'{s:04.1f}\"{direction}"

def latlon_to_utm_zone_43n(lat: float, lon: float) -> Tuple[float, float]:
    """
    Computes Universal Transverse Mercator (UTM) Easting and Northing in meters
    for UTM Zone 43N (central meridian 75°E, covering western border sectors).
    Uses high-precision conformal map projection equations.
    """
    lon_rad = math.radians(lon)
    lat_rad = math.radians(lat)
    
    # Central meridian for Zone 43 is 75° E
    lon0 = math.radians(75.0)
    k0 = 0.9996  # UTM scale factor
    
    e_prime2 = WGS84_E2 / (1.0 - WGS84_E2)
    n = WGS84_A / math.sqrt(1.0 - WGS84_E2 * (math.sin(lat_rad) ** 2))
    t = math.tan(lat_rad) ** 2
    c = e_prime2 * (math.cos(lat_rad) ** 2)
    a = math.cos(lat_rad) * (lon_rad - lon0)
    
    # Meridional arc
    m = WGS84_A * (
        (1.0 - WGS84_E2 / 4.0 - 3.0 * (WGS84_E2 ** 2) / 64.0 - 5.0 * (WGS84_E2 ** 3) / 256.0) * lat_rad
        - (3.0 * WGS84_E2 / 8.0 + 3.0 * (WGS84_E2 ** 2) / 32.0 + 45.0 * (WGS84_E2 ** 3) / 1024.0) * math.sin(2.0 * lat_rad)
        + (15.0 * (WGS84_E2 ** 2) / 256.0 + 45.0 * (WGS84_E2 ** 3) / 1024.0) * math.sin(4.0 * lat_rad)
        - (35.0 * (WGS84_E2 ** 3) / 3072.0) * math.sin(6.0 * lat_rad)
    )
    
    # Easting (False Easting = 500,000m)
    easting = 500000.0 + k0 * n * (
        a + (1.0 - t + c) * (a ** 3) / 6.0
        + (5.0 - 18.0 * t + t ** 2 + 72.0 * c - 58.0 * e_prime2) * (a ** 5) / 120.0
    )
    
    # Northing (Equator = 0m)
    northing = k0 * (
        m + n * math.tan(lat_rad) * (
            (a ** 2) / 2.0
            + (5.0 - t + 9.0 * c + 4.0 * (c ** 2)) * (a ** 4) / 24.0
            + (61.0 - 58.0 * t + t ** 2 + 600.0 * c - 330.0 * e_prime2) * (a ** 6) / 720.0
        )
    )
    
    return easting, northing

def utm_to_mgrs_8digit(easting: float, northing: float, gzd: str = "43R", sq_100k: str = "FU") -> str:
    """
    Encodes UTM coordinates into standard military 8-digit MGRS (10m precision):
    e.g., '43R FU 8785 9912'
    """
    # 100k square offset remainder
    e_100k = int(easting) % 100000
    n_100k = int(northing) % 100000
    
    # 4-digit easting and northing (10-meter resolution)
    e_4digit = (e_100k // 10) % 10000
    n_4digit = (n_100k // 10) % 10000
    
    return f"{gzd} {sq_100k} {e_4digit:04d} {n_4digit:04d}"

class GeospatialEngine:
    """
    Central coordinate transformation and tactical dispatch service.
    Singleton instance accessible across backend pipelines.
    """
    def __init__(self, anchor: Optional[GeodeticAnchor] = None):
        self.anchor = anchor or GeodeticAnchor()
        # Precompute anchor UTM
        self.anchor_easting, self.anchor_northing = latlon_to_utm_zone_43n(
            self.anchor.latitude, self.anchor.longitude
        )
        self.anchor_mgrs = utm_to_mgrs_8digit(
            self.anchor_easting, self.anchor_northing,
            gzd="43R", sq_100k=self.anchor.mgrs_100k_square
        )

    def get_anchor_info(self) -> Dict[str, Any]:
        """Returns metadata of the current base station geodetic anchor."""
        return {
            "site_id": self.anchor.site_id,
            "site_name": self.anchor.site_name,
            "latitude": self.anchor.latitude,
            "longitude": self.anchor.longitude,
            "latitude_dms": decimal_to_dms(self.anchor.latitude, is_latitude=True),
            "longitude_dms": decimal_to_dms(self.anchor.longitude, is_latitude=False),
            "elevation_amsl_m": self.anchor.elevation_amsl_m,
            "mast_height_m": self.anchor.mast_height_m,
            "mast_azimuth_deg": self.anchor.mast_azimuth_deg,
            "utm_easting": round(self.anchor_easting, 2),
            "utm_northing": round(self.anchor_northing, 2),
            "utm_zone": self.anchor.utm_zone,
            "mgrs_grid": self.anchor_mgrs,
            "geodetic_datum": "WGS-84"
        }

    def local_xy_to_georeferenced(
        self, x_east_m: float, y_north_m: float, elevation_offset_m: float = 0.0
    ) -> Dict[str, Any]:
        """
        Converts local Cartesian offsets in meters (x = East, y = North from mast)
        into exact WGS-84 Lat/Lon, UTM Zone 43N, and 8-digit MGRS military grid.
        """
        lat_rad = math.radians(self.anchor.latitude)
        
        # Radii of curvature for accurate geodesic displacement
        m_per_deg_lat = 111132.954 - 559.822 * math.cos(2 * lat_rad) + 1.175 * math.cos(4 * lat_rad)
        m_per_deg_lon = (math.pi / 180.0) * WGS84_A * math.cos(lat_rad) / math.sqrt(1.0 - WGS84_E2 * (math.sin(lat_rad) ** 2))
        
        d_lat = y_north_m / m_per_deg_lat
        d_lon = x_east_m / m_per_deg_lon
        
        target_lat = self.anchor.latitude + d_lat
        target_lon = self.anchor.longitude + d_lon
        target_elev = self.anchor.elevation_amsl_m + elevation_offset_m
        
        target_easting, target_northing = latlon_to_utm_zone_43n(target_lat, target_lon)
        target_mgrs = utm_to_mgrs_8digit(
            target_easting, target_northing,
            gzd="43R", sq_100k=self.anchor.mgrs_100k_square
        )
        
        # Range & True Azimuth Bearing from mast
        range_m = math.sqrt(x_east_m ** 2 + y_north_m ** 2)
        bearing_rad = math.atan2(x_east_m, y_north_m)
        bearing_deg = (math.degrees(bearing_rad) + 360.0) % 360.0
        
        return {
            "local_x_m": round(x_east_m, 2),
            "local_y_m": round(y_north_m, 2),
            "range_m": round(range_m, 2),
            "bearing_deg": round(bearing_deg, 1),
            "latitude": round(target_lat, 7),
            "longitude": round(target_lon, 7),
            "latitude_dms": decimal_to_dms(target_lat, is_latitude=True),
            "longitude_dms": decimal_to_dms(target_lon, is_latitude=False),
            "elevation_amsl_m": round(target_elev, 2),
            "utm_easting": round(target_easting, 2),
            "utm_northing": round(target_northing, 2),
            "utm_zone": self.anchor.utm_zone,
            "mgrs_8digit": target_mgrs,
            "datum": "WGS-84"
        }

    def radar_polar_to_georeferenced(self, range_m: float, azimuth_deg: float) -> Dict[str, Any]:
        """
        Converts radar polar coordinates (range in meters, azimuth relative to boresight)
        into georeferenced coordinates.
        """
        total_azimuth_deg = (azimuth_deg + self.anchor.mast_azimuth_deg) % 360.0
        azimuth_rad = math.radians(total_azimuth_deg)
        x_east_m = range_m * math.sin(azimuth_rad)
        y_north_m = range_m * math.cos(azimuth_rad)
        return self.local_xy_to_georeferenced(x_east_m, y_north_m)

    def camera_pixel_to_georeferenced(
        self,
        norm_u: float,
        norm_v: float,
        camera_height_m: float = 4.5,
        optical_tilt_deg: float = 20.0,
        hfov_deg: float = 70.0,
        vfov_deg: float = 45.0
    ) -> Dict[str, Any]:
        """
        Transforms normalized camera pixel coordinates [0.0 - 1.0] to estimated
        ground plane Cartesian coordinates and georeferenced coordinates.
        """
        # Pixel angles relative to optical principal axis
        pan_angle_deg = (norm_u - 0.5) * hfov_deg
        tilt_from_horiz_deg = optical_tilt_deg + (norm_v - 0.5) * vfov_deg
        
        # Avoid division by zero or upward rays
        tilt_clamped = max(5.0, min(85.0, tilt_from_horiz_deg))
        ground_distance_y = camera_height_m / math.tan(math.radians(tilt_clamped))
        ground_offset_x = ground_distance_y * math.tan(math.radians(pan_angle_deg))
        
        return self.local_xy_to_georeferenced(ground_offset_x, ground_distance_y)

    def generate_qrt_dispatch_order(
        self,
        event_id: str,
        target_id: str,
        classification: str,
        severity: str,
        local_x_m: float,
        local_y_m: float,
        speed_mps: float = 1.4,
        threat_zone: str = "ZONE_C",
        operator_callsign: str = "WATCH_OFFICER_01"
    ) -> Dict[str, Any]:
        """
        Generates a formalized Quick Reaction Team (QRT) Tactical Mission Dispatch Order
        formatted for BSF / CAPF tactical communications and field GPS entry.
        """
        geo = self.local_xy_to_georeferenced(local_x_m, local_y_m)
        now = datetime.now(timezone.utc)
        dispatch_id = f"QRT-ORD-{now.strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
        
        # Estimate intercept time for standard 5 m/s (18 km/h) QRT tactical all-terrain vehicle
        intercept_speed_mps = 5.0
        eta_seconds = int(geo["range_m"] / intercept_speed_mps) + 15
        
        cardinal_dirs = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
        idx = int((geo["bearing_deg"] + 11.25) / 22.5) % 16
        cardinal = cardinal_dirs[idx]

        return {
            "dispatch_id": dispatch_id,
            "timestamp": now.isoformat(),
            "fob_anchor": self.anchor.site_name,
            "origin_callsign": operator_callsign,
            "target_id": target_id,
            "event_id": event_id,
            "threat_classification": classification.upper(),
            "severity": severity.upper(),
            "threat_zone": threat_zone,
            "target_tactical_position": {
                "mgrs_8digit": geo["mgrs_8digit"],
                "latitude_dms": geo["latitude_dms"],
                "longitude_dms": geo["longitude_dms"],
                "latitude_decimal": geo["latitude"],
                "longitude_decimal": geo["longitude"],
                "utm": f"{geo['utm_zone']} E:{geo['utm_easting']} N:{geo['utm_northing']}",
                "range_from_fob_m": geo["range_m"],
                "bearing_azimuth": f"{geo['bearing_deg']}° ({cardinal})",
                "estimated_speed_mps": speed_mps
            },
            "intercept_assessment": {
                "eta_seconds": eta_seconds,
                "recommended_approach": f"Advance along patrol vector {cardinal} bearing {geo['bearing_deg']}°",
                "recommended_unit": "QRT-TEAM-BRAVO (Mobile Interceptor)",
                "rules_of_engagement": "Deploy high-intensity dazzler & acoustic hail; secure perimeter boundary; prevent fence breach."
            },
            "status": "DISPATCH_AUTHORIZED"
        }

# Global singleton
geospatial_engine = GeospatialEngine()
