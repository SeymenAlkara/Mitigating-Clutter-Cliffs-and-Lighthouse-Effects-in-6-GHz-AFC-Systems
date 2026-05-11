"""
Clutter module for loading and querying land cover data.

Now supports both Corine Land Cover (44 classes) and ESA WorldCover (11 classes).
"""

from .clc_loader import load_clc_raster, query_land_cover as query_clc, clear_cache
from .clc_mapping import (
    get_clutter_params as get_clc_params, 
    is_clutter_cliff_risk as is_clc_cliff_risk,
    get_clc_name
)

# Import WorldCover support
try:
    from .worldcover_mapping import (
        get_clutter_params as get_worldcover_params,
        is_clutter_cliff_risk as is_worldcover_cliff_risk,
        get_worldcover_name
    )
    _worldcover_available = True
except ImportError:
    _worldcover_available = False


def query_land_cover(lat: float, lon: float, data_file: str, dataset_type: str = "auto"):
    """
    Query land cover code at a location.
    
    Args:
        lat, lon: Coordinates
        data_file: Path to data file
        dataset_type: "corine", "worldcover", or "auto" (auto-detect from filename)
    
    Returns:
        Land cover code (integer)
    """
    # Auto-detect dataset type from filename
    if dataset_type == "auto":
        if "WorldCover" in data_file or "worldcover" in data_file.lower():
            dataset_type = "worldcover"
        else:
            dataset_type = "corine"
    
    # Use the same loader for both (both are GeoTIFF)
    return query_clc(lat, lon, data_file)


def get_clutter_params(code: int, dataset_type: str = "worldcover"):
    """
    Get ITU-R P.452 clutter parameters for a land cover code.
    
    Args:
        code: Land cover code
        dataset_type: "corine" or "worldcover"
    
    Returns:
        ClutterParams object
    """
    if dataset_type == "worldcover":
        return get_worldcover_params(code)
    else:
        return get_clc_params(code)


def is_clutter_cliff_risk(code: int, dataset_type: str = "worldcover"):
    """
    Check if a land cover code represents Clutter Cliff risk.
    
    Args:
        code: Land cover code
        dataset_type: "corine" or "worldcover"
    
    Returns:
        True if cliff risk
    """
    if dataset_type == "worldcover":
        return is_worldcover_cliff_risk(code)
    else:
        return is_clc_cliff_risk(code)


def get_land_cover_name(code: int, dataset_type: str = "worldcover"):
    """
    Get human-readable name for a land cover code.
    
    Args:
        code: Land cover code
        dataset_type: "corine" or "worldcover"
    
    Returns:
        Name string
    """
    if dataset_type == "worldcover":
        return get_worldcover_name(code)
    else:
        return get_clc_name(code)


__all__ = [
    "load_clc_raster",
    "query_land_cover",
    "get_clutter_params",
    "is_clutter_cliff_risk",
    "get_land_cover_name",
    "clear_cache"
]
