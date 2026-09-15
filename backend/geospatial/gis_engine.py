"""
SENTINEL-AI: Offline Tactical GIS Vector Mapping Engine
Sections 37, 51, & 67: High-Resolution Offline Vector Map Layers,
MGRS Tactical Grid Matrices, International Border Fencing, and Sensor FOV Cones.

100% offline-first execution: Produces standard GeoJSON / Vector Feature Collections
with zero external internet map tile dependencies (OpenStreetMap, Google Maps, Mapbox).
"""

from typing import Dict, Any, List
from backend.geospatial.coordinates import geospatial_engine

class TacticalGISEngine:
    """
    Generates structured tactical GIS vector layers covering perimeter fencing,
    border pillars, polygonal defense sectors, terrain dead zones, and sensor FOV cones.
    """
    def __init__(self):
        self.anchor = geospatial_engine.anchor

    def get_tactical_vector_layers(self) -> Dict[str, Any]:
        """
        Returns an exhaustive collection of georeferenced vector features
        formatted as standard GeoJSON FeatureCollections.
        """
        lat0 = self.anchor.latitude
        lon0 = self.anchor.longitude

        # 1. Border Pillars (Point Features)
        pillars = [
            {
                "type": "Feature",
                "properties": {
                    "id": "BP-743",
                    "name": "Border Pillar 743 (Riverbed Sentry)",
                    "type": "BORDER_PILLAR",
                    "mgrs": "43R FU 8762 9845",
                    "elevation_m": 214.0
                },
                "geometry": {
                    "type": "Point",
                    "coordinates": [round(lon0 - 0.0035, 6), round(lat0 - 0.0028, 6)]
                }
            },
            {
                "type": "Feature",
                "properties": {
                    "id": "BP-744",
                    "name": "Border Pillar 744 (FOB Alpha Command Mast)",
                    "type": "BASE_STATION",
                    "mgrs": "43R FU 8785 9912",
                    "elevation_m": 218.5
                },
                "geometry": {
                    "type": "Point",
                    "coordinates": [round(lon0, 6), round(lat0, 6)]
                }
            },
            {
                "type": "Feature",
                "properties": {
                    "id": "BP-745",
                    "name": "Border Pillar 745 (Ridge Outpost)",
                    "type": "BORDER_PILLAR",
                    "mgrs": "43R FU 8812 9975",
                    "elevation_m": 223.2
                },
                "geometry": {
                    "type": "Point",
                    "coordinates": [round(lon0 + 0.0038, 6), round(lat0 + 0.0032, 6)]
                }
            }
        ]

        # 2. International Border Zero Line (LineString)
        zero_line = {
            "type": "Feature",
            "properties": {
                "name": "International Border (Zero Line)",
                "classification": "INTERNATIONAL_BOUNDARY",
                "stroke": "#ff1744",
                "stroke_width": 3,
                "stroke_dasharray": "6,4"
            },
            "geometry": {
                "type": "LineString",
                "coordinates": [
                    [round(lon0 - 0.0060, 6), round(lat0 - 0.0050, 6)],
                    [round(lon0 - 0.0035, 6), round(lat0 - 0.0028, 6)],
                    [round(lon0, 6), round(lat0 + 0.0005, 6)],
                    [round(lon0 + 0.0038, 6), round(lat0 + 0.0032, 6)],
                    [round(lon0 + 0.0065, 6), round(lat0 + 0.0058, 6)]
                ]
            }
        }

        # 3. Perimeter Smart Fencing (Double Wire with 10m Patrol Track)
        bsf_fence = {
            "type": "Feature",
            "properties": {
                "name": "High-Tensile Barbed Wire Security Fence",
                "classification": "BSF_SECURITY_FENCE",
                "stroke": "#f59e0b",
                "stroke_width": 2.5
            },
            "geometry": {
                "type": "LineString",
                "coordinates": [
                    [round(lon0 - 0.0058, 6), round(lat0 - 0.0052, 6)],
                    [round(lon0 - 0.0033, 6), round(lat0 - 0.0030, 6)],
                    [round(lon0 + 0.0002, 6), round(lat0 + 0.0003, 6)],
                    [round(lon0 + 0.0040, 6), round(lat0 + 0.0030, 6)],
                    [round(lon0 + 0.0067, 6), round(lat0 + 0.0056, 6)]
                ]
            }
        }

        # 4. Polygonal Surveillance Zones (A, B, C)
        zones = [
            {
                "type": "Feature",
                "properties": {
                    "id": "ZONE_C",
                    "name": "Restricted Border Fence (Zero Tolerance)",
                    "threat_level": "CRITICAL",
                    "fill": "rgba(239, 68, 68, 0.25)",
                    "stroke": "#ef4444"
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [round(lon0 - 0.0015, 6), round(lat0 + 0.0002, 6)],
                        [round(lon0 + 0.0020, 6), round(lat0 + 0.0002, 6)],
                        [round(lon0 + 0.0022, 6), round(lat0 + 0.0018, 6)],
                        [round(lon0 - 0.0013, 6), round(lat0 + 0.0018, 6)],
                        [round(lon0 - 0.0015, 6), round(lat0 + 0.0002, 6)]
                    ]]
                }
            },
            {
                "type": "Feature",
                "properties": {
                    "id": "ZONE_B",
                    "name": "Warning Approach Sector",
                    "threat_level": "HIGH",
                    "fill": "rgba(245, 158, 11, 0.18)",
                    "stroke": "#f59e0b"
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [round(lon0 - 0.0022, 6), round(lat0 - 0.0008, 6)],
                        [round(lon0 + 0.0028, 6), round(lat0 - 0.0008, 6)],
                        [round(lon0 + 0.0020, 6), round(lat0 + 0.0002, 6)],
                        [round(lon0 - 0.0015, 6), round(lat0 + 0.0002, 6)],
                        [round(lon0 - 0.0022, 6), round(lat0 - 0.0008, 6)]
                    ]]
                }
            },
            {
                "type": "Feature",
                "properties": {
                    "id": "ZONE_A",
                    "name": "Outer Patrol Sector",
                    "threat_level": "NORMAL",
                    "fill": "rgba(0, 229, 255, 0.12)",
                    "stroke": "#00e5ff"
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [round(lon0 - 0.0030, 6), round(lat0 - 0.0020, 6)],
                        [round(lon0 + 0.0035, 6), round(lat0 - 0.0020, 6)],
                        [round(lon0 + 0.0028, 6), round(lat0 - 0.0008, 6)],
                        [round(lon0 - 0.0022, 6), round(lat0 - 0.0008, 6)],
                        [round(lon0 - 0.0030, 6), round(lat0 - 0.0020, 6)]
                    ]]
                }
            }
        ]

        # 5. Sensor FOV Coverage Cones
        sensor_fov = [
            {
                "type": "Feature",
                "properties": {
                    "sensor_id": "RADAR_01",
                    "name": "24GHz FMCW Radar Sweep (120° FOV, 8m Range)",
                    "fill": "rgba(0, 229, 255, 0.08)",
                    "stroke": "rgba(0, 229, 255, 0.4)",
                    "fov_deg": 120
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [round(lon0, 6), round(lat0, 6)],
                        [round(lon0 - 0.0018, 6), round(lat0 + 0.0015, 6)],
                        [round(lon0 - 0.0008, 6), round(lat0 + 0.0022, 6)],
                        [round(lon0 + 0.0008, 6), round(lat0 + 0.0022, 6)],
                        [round(lon0 + 0.0018, 6), round(lat0 + 0.0015, 6)],
                        [round(lon0, 6), round(lat0, 6)]
                    ]]
                }
            }
        ]

        # 6. Terrain Ravine Shadow (Blind Zone)
        ravine_shadow = {
            "type": "Feature",
            "properties": {
                "name": "Terrain Ravine Shadow Pocket (-0.85m Dead Zone)",
                "threat_level": "RADAR_BLIND_SPOT",
                "fill": "rgba(168, 85, 247, 0.25)",
                "stroke": "#a855f7",
                "stroke_dasharray": "4,2"
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [round(lon0 + 0.0005, 6), round(lat0 + 0.0009, 6)],
                    [round(lon0 + 0.0014, 6), round(lat0 + 0.0009, 6)],
                    [round(lon0 + 0.0015, 6), round(lat0 + 0.0013, 6)],
                    [round(lon0 + 0.0006, 6), round(lat0 + 0.0013, 6)],
                    [round(lon0 + 0.0005, 6), round(lat0 + 0.0009, 6)]
                ]]
            }
        }

        # 7. 100-Meter MGRS Tactical Grid Matrix
        mgrs_squares = []
        for i in range(-2, 3):
            for j in range(-2, 3):
                g_lon = round(lon0 + i * 0.0010, 6)
                g_lat = round(lat0 + j * 0.0009, 6)
                mgrs_squares.append({
                    "type": "Feature",
                    "properties": {
                        "grid_id": f"43R-FU-{(87 + i):02d}-{(99 + j):02d}",
                        "type": "MGRS_100M_CELL"
                    },
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[
                            [g_lon, g_lat],
                            [round(g_lon + 0.0010, 6), g_lat],
                            [round(g_lon + 0.0010, 6), round(g_lat + 0.0009, 6)],
                            [g_lon, round(g_lat + 0.0009, 6)],
                            [g_lon, g_lat]
                        ]]
                    }
                })

        return {
            "status": "LAYERS_COMPILED",
            "geodetic_datum": "WGS-84 / UTM Zone 43N",
            "base_station": self.anchor.to_dict(),
            "layers": {
                "border_pillars": {"type": "FeatureCollection", "features": pillars},
                "zero_line": zero_line,
                "bsf_fence": bsf_fence,
                "surveillance_zones": {"type": "FeatureCollection", "features": zones},
                "sensor_fov": {"type": "FeatureCollection", "features": sensor_fov},
                "terrain_ravine_shadow": ravine_shadow,
                "mgrs_grid": {"type": "FeatureCollection", "features": mgrs_squares}
            }
        }

# Global singleton
tactical_gis_engine = TacticalGISEngine()
