import math
from typing import Dict, Any, Tuple

class NavigationService:
    """
    Geospatial Navigation & Flight Vector Service (Sections 22, 23, 24).
    Provides Haversine distance, initial true bearing, and arrival radius detection.
    Never calculates geographic distance using naive lat/lon subtraction.
    """
    EARTH_RADIUS_M: float = 6371000.0  # WGS-84 mean radius in meters

    @staticmethod
    def calculate_haversine_distance(
        lat1: float, lon1: float,
        lat2: float, lon2: float
    ) -> float:
        """
        Computes accurate great-circle distance between two GPS coordinates in meters.
        """
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lon2 - lon1)

        a = (
            math.sin(delta_phi / 2.0) ** 2
            + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
        )
        c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))
        return NavigationService.EARTH_RADIUS_M * c

    @staticmethod
    def calculate_initial_bearing(
        lat1: float, lon1: float,
        lat2: float, lon2: float
    ) -> float:
        """
        Computes initial true bearing in degrees (0° - 360°, clockwise from True North)
        from point 1 to point 2.
        """
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_lambda = math.radians(lon2 - lon1)

        y = math.sin(delta_lambda) * math.cos(phi2)
        x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(delta_lambda)

        bearing_rad = math.atan2(y, x)
        bearing_deg = (math.degrees(bearing_rad) + 360.0) % 360.0
        return round(bearing_deg, 1)

    @staticmethod
    def format_distance(distance_m: float) -> str:
        """Formats distance in meters or kilometers."""
        if distance_m < 1000.0:
            return f"{int(round(distance_m))} m"
        return f"{distance_m / 1000.0:.2f} km"

    @staticmethod
    def format_bearing(bearing_deg: float) -> str:
        """Formats bearing in degrees."""
        return f"{int(round(bearing_deg))}°"

    @classmethod
    def evaluate_navigation(
        cls,
        current_lat: float,
        current_lon: float,
        target_lat: float,
        target_lon: float,
        current_heading: float = 0.0,
        arrival_radius_m: float = 10.0
    ) -> Dict[str, Any]:
        """
        Evaluates navigation telemetry from drone current location to target.
        Returns distance, bearing, formatted strings, and arrival status.
        """
        dist_m = cls.calculate_haversine_distance(current_lat, current_lon, target_lat, target_lon)
        bearing_deg = cls.calculate_initial_bearing(current_lat, current_lon, target_lat, target_lon)
        has_arrived = dist_m <= arrival_radius_m

        cardinal_dirs = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
        idx = int((bearing_deg + 11.25) / 22.5) % 16
        cardinal = cardinal_dirs[idx]

        return {
            "distance_m": round(dist_m, 1),
            "distance_formatted": cls.format_distance(dist_m),
            "bearing_deg": bearing_deg,
            "bearing_formatted": cls.format_bearing(bearing_deg),
            "cardinal_direction": cardinal,
            "arrival_radius_m": arrival_radius_m,
            "has_arrived": has_arrived,
            "navigation_status": "ARRIVED" if has_arrived else "NAVIGATING"
        }

navigation_service = NavigationService()
