"""
Digital Elevation Model (DEM) loader for SRTM and AW3D30 terrain data.

This module handles loading GeoTIFF terrain files and provides efficient
querying of elevation data at specific coordinates.
"""

import rasterio
from rasterio.transform import rowcol
from typing import Optional, Tuple, Dict
import os
from pathlib import Path


# Global cache for loaded DEM tiles
_dem_cache: Dict[str, Tuple[rasterio.DatasetReader, object]] = {}


def load_dem_tile(dem_file_path: str, cache: bool = True) -> Optional[rasterio.DatasetReader]:
    """
    Load a DEM tile from a GeoTIFF file.
    
    Args:
        dem_file_path: Path to the GeoTIFF DEM file
        cache: If True, cache the loaded tile for future queries
        
    Returns:
        rasterio DatasetReader object, or None if file not found
        
    Example:
        >>> dem = load_dem_tile("data/terrain/n41_e028_1arc_v3.tif")
        >>> print(dem.bounds)
    """
    if not os.path.exists(dem_file_path):
        raise FileNotFoundError(f"DEM file not found: {dem_file_path}")
    
    # Check cache first
    if cache and dem_file_path in _dem_cache:
        dataset, _ = _dem_cache[dem_file_path]
        return dataset
    
    # Load the DEM file
    dataset = rasterio.open(dem_file_path)
    
    # Cache it if requested
    if cache:
        _dem_cache[dem_file_path] = (dataset, None)
    
    return dataset


def query_elevation(
    lat: float,
    lon: float,
    dem_file_path: str,
    default_elevation: float = 0.0
) -> float:
    """
    Query terrain elevation at a specific latitude/longitude.
    
    Args:
        lat: Latitude in decimal degrees
        lon: Longitude in decimal degrees
        dem_file_path: Path to the DEM GeoTIFF file
        default_elevation: Return value if coordinates are out of bounds
        
    Returns:
        Elevation in meters above sea level
        
    Example:
        >>> # Query elevation at Taksim Square, Istanbul
        >>> elev = query_elevation(41.0370, 28.9854, "data/terrain/n41_e028_1arc_v3.tif")
        >>> print(f"Elevation: {elev:.1f} m")
    """
    try:
        dem = load_dem_tile(dem_file_path, cache=True)
        
        # Convert lat/lon to pixel row/col
        row, col = rowcol(dem.transform, lon, lat)
        
        # Check bounds
        if 0 <= row < dem.height and 0 <= col < dem.width:
            # Read the elevation value
            elevation_data = dem.read(1)
            elevation = float(elevation_data[row, col])
            
            # Handle no-data values
            if dem.nodata is not None and elevation == dem.nodata:
                return default_elevation
            
            return elevation
        else:
            # Out of bounds
            return default_elevation
            
    except FileNotFoundError:
        return default_elevation
    except Exception as e:
        print(f"Warning: Error querying elevation at ({lat}, {lon}): {e}")
        return default_elevation


def get_height_profile(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
    dem_file_path: str,
    num_points: int = 100
) -> list[Tuple[float, float, float, float]]:
    """
    Extract a terrain height profile between two points.
    
    This creates a simple linear path between the two points and samples
    elevations along that path.
    
    Args:
        lat1, lon1: Start point coordinates
        lat2, lon2: End point coordinates
        dem_file_path: Path to the DEM file
        num_points: Number of sample points along the profile
        
    Returns:
        List of tuples: (latitude, longitude, distance_m, elevation_m)
        where distance_m is cumulative distance from start point
        
    Example:
        >>> # Profile from Taksim to Bosphorus Bridge
        >>> profile = get_height_profile(
        ...     41.0370, 28.9854,  # Taksim
        ...     41.0428, 29.0278,  # Bosphorus Bridge
        ...     "data/terrain/n41_e028_1arc_v3.tif",
        ...     num_points=50
        ... )
        >>> for lat, lon, dist, elev in profile[:5]:
        ...     print(f"Distance: {dist:.0f}m, Elevation: {elev:.1f}m")
    """
    from .geodesy_utils import haversine_distance_m
    
    profile = []
    total_distance = haversine_distance_m(lat1, lon1, lat2, lon2)
    
    for i in range(num_points):
        # Linear interpolation between points
        fraction = i / (num_points - 1) if num_points > 1 else 0
        lat = lat1 + fraction * (lat2 - lat1)
        lon = lon1 + fraction * (lon2 - lon1)
        
        # Query elevation at this point
        elev = query_elevation(lat, lon, dem_file_path)
        
        # Calculate cumulative distance
        distance = fraction * total_distance
        
        profile.append((lat, lon, distance, elev))
    
    return profile


def get_dem_info(dem_file_path: str) -> dict:
    """
    Get metadata information about a DEM file.
    
    Args:
        dem_file_path: Path to the DEM file
        
    Returns:
        Dictionary with DEM metadata (bounds, CRS, resolution, etc.)
    """
    dem = load_dem_tile(dem_file_path, cache=True)
    
    return {
        "bounds": dem.bounds,
        "crs": str(dem.crs),
        "width": dem.width,
        "height": dem.height,
        "resolution": dem.res,
        "nodata": dem.nodata,
        "transform": dem.transform
    }


def clear_cache():
    """
    Clear the DEM tile cache to free memory.
    
    Call this if you've loaded many DEM tiles and want to release memory.
    """
    global _dem_cache
    
    # Close all open datasets
    for dem_file, (dataset, _) in _dem_cache.items():
        dataset.close()
    
    _dem_cache.clear()


# Utility function for finding DEM files
def find_dem_for_location(lat: float, lon: float, dem_dir: str) -> Optional[str]:
    """
    Find the appropriate DEM file for a given location.
    
    This assumes SRTM-style naming: N[lat]E[lon] or S[lat]W[lon]
    
    Args:
        lat: Latitude
        lon: Longitude  
        dem_dir: Directory containing DEM files
        
    Returns:
        Path to DEM file, or None if not found
    """
    # Determine tile coordinates
    lat_tile = int(lat) if lat >= 0 else int(lat) - 1
    lon_tile = int(lon) if lon >= 0 else int(lon) - 1
    
    lat_prefix = "N" if lat_tile >= 0 else "S"
    lon_prefix = "E" if lon_tile >= 0 else "W"
    
    # Common SRTM filename patterns
    patterns = [
        f"n{abs(lat_tile):02d}_e{abs(lon_tile):03d}_1arc_v3.tif",  # AW3D30/SRTM
        f"{lat_prefix}{abs(lat_tile):02d}{lon_prefix}{abs(lon_tile):03d}.tif",
        f"{lat_prefix}{abs(lat_tile):02d}{lon_prefix}{abs(lon_tile):03d}.hgt",
    ]
    
    dem_path = Path(dem_dir)
    
    for pattern in patterns:
        candidate = dem_path / pattern
        if candidate.exists():
            return str(candidate)
    
    return None
