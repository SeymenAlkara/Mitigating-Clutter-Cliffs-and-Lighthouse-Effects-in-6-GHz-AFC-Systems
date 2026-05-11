"""
Terrain module for loading and querying Digital Elevation Models (DEM).

This module provides functions to:
- Load SRTM/AW3D30 terrain data (GeoTIFF format)
- Query elevation at specific coordinates
- Extract height profiles between points
- Cache loaded terrain tiles for performance
"""

__all__ = [
    "load_dem_tile",
    "query_elevation",
    "get_height_profile",
    "clear_cache"
]
