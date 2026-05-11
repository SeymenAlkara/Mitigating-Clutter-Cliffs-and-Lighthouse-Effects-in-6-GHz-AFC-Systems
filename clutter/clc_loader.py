"""
Corine Land Cover (CLC) data loader and query functions.
"""

import rasterio
from rasterio.transform import rowcol
from typing import Optional, Dict, Tuple
import os


# Global cache for loaded CLC rasters
_clc_cache: Dict[str, rasterio.DatasetReader] = {}


def load_clc_raster(clc_file_path: str, cache: bool = True) -> Optional[rasterio.DatasetReader]:
    """
    Load a Corine Land Cover raster file.
    
    Args:
        clc_file_path: Path to the CLC GeoTIFF file
        cache: If True, cache the loaded raster
        
    Returns:
        rasterio DatasetReader object
    """
    if not os.path.exists(clc_file_path):
        raise FileNotFoundError(f"CLC file not found: {clc_file_path}")
    
    # Check cache
    if cache and clc_file_path in _clc_cache:
        return _clc_cache[clc_file_path]
    
    # Load the raster
    dataset = rasterio.open(clc_file_path)
    
    # Cache it
    if cache:
        _clc_cache[clc_file_path] = dataset
    
    return dataset


def query_land_cover(
    lat: float,
    lon: float,
    clc_file_path: str,
    default_code: int = 0
) -> int:
    """
    Query Corine Land Cover code at a specific location.
    
    Args:
        lat: Latitude in decimal degrees
        lon: Longitude in decimal degrees
        clc_file_path: Path to CLC GeoTIFF file
        default_code: Return value if out of bounds (0 = no data)
        
    Returns:
        Corine Land Cover code (integer, 1-44, or 0 for no data)
        
    Example:
        >>> code = query_land_cover(41.0370, 28.9854, "data/clutter/clc_turkey.tif")
        >>> print(f"Land cover code: {code}")
    """
    try:
        clc = load_clc_raster(clc_file_path, cache=True)
        
        # Convert lat/lon to pixel coordinates
        row, col = rowcol(clc.transform, lon, lat)
        
        # Check bounds
        if 0 <= row < clc.height and 0 <= col < clc.width:
            clc_data = clc.read(1)
            code = int(clc_data[row, col])
            
            # Handle no-data values
            if clc.nodata is not None and code == clc.nodata:
                return default_code
            
            return code
        else:
            return default_code
            
    except FileNotFoundError:
        return default_code
    except Exception as e:
        print(f"Warning: Error querying land cover at ({lat}, {lon}): {e}")
        return default_code


def clear_cache():
    """Clear the CLC raster cache to free memory."""
    global _clc_cache
    
    for clc_file, dataset in _clc_cache.items():
        dataset.close()
    
    _clc_cache.clear()
