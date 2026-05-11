"""Geodesy helpers for AFC (great-circle distances).

Implements Haversine distance for AP→FS paths used to evaluate protection at the
FS receiver location (WINNF-TS-1014 9.1.1 evaluation point).
"""

import math


def haversine_distance_m(lat1_deg: float, lon1_deg: float, lat2_deg: float, lon2_deg: float) -> float:
    """Great-circle distance between two WGS-84 points in meters.

    Args:
        lat1_deg, lon1_deg: point 1 latitude/longitude in degrees
        lat2_deg, lon2_deg: point 2 latitude/longitude in degrees
    Returns:
        distance in meters
    """
    r_earth_m = 6371000.0
    lat1 = math.radians(lat1_deg)
    lon1 = math.radians(lon1_deg)
    lat2 = math.radians(lat2_deg)
    lon2 = math.radians(lon2_deg)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2.0) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return r_earth_m * c


def initial_bearing_deg(lat1_deg: float, lon1_deg: float, lat2_deg: float, lon2_deg: float) -> float:
    """Initial bearing from point 1 to point 2 (degrees 0..360).

    Useful to compute off-axis angle versus an antenna azimuth.
    """
    lat1 = math.radians(lat1_deg)
    lat2 = math.radians(lat2_deg)
    dlon = math.radians(lon2_deg - lon1_deg)
    x = math.sin(dlon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    brng = math.degrees(math.atan2(x, y))
    return (brng + 360.0) % 360.0


