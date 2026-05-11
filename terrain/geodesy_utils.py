"""
Geodesy utilities for distance and coordinate calculations.
"""

import math


def haversine_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate great-circle distance between two points on Earth using Haversine formula.
    
    Args:
        lat1, lon1: First point coordinates (decimal degrees)
        lat2, lon2: Second point coordinates (decimal degrees)
        
    Returns:
        Distance in meters
        
    Example:
        >>> # Distance from Taksim to Bosphorus Bridge
        >>> dist = haversine_distance_m(41.0370, 28.9854, 41.0428, 29.0278)
        >>> print(f"Distance: {dist/1000:.2f} km")
    """
    R = 6371000  # Earth radius in meters
    
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    
    a = (math.sin(delta_phi/2)**2 + 
         math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda/2)**2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    
    return R * c


def azimuth_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the bearing/azimuth from point 1 to point 2.
    
    Args:
        lat1, lon1: Start point coordinates (decimal degrees)
        lat2, lon2: End point coordinates (decimal degrees)
        
    Returns:
        Azimuth in degrees (0-360, where 0 = North, 90 = East)
    """
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_lambda = math.radians(lon2 - lon1)
    
    y = math.sin(delta_lambda) * math.cos(phi2)
    x = (math.cos(phi1) * math.sin(phi2) - 
         math.sin(phi1) * math.cos(phi2) * math.cos(delta_lambda))
    
    azimuth_rad = math.atan2(y, x)
    azimuth_degrees = math.degrees(azimuth_rad)
    
    # Normalize to 0-360
    return (azimuth_degrees + 360) % 360
