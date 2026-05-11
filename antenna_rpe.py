"""Antenna RPE utilities (simplified).

Radiation Pattern Envelope (RPE) describes off-axis antenna discrimination. We
support:
- Loading a simple (angle_deg, attenuation_db) table
- Interpolating attenuation for an angle
- Combining azimuth and elevation attenuations with floors

This is a placeholder to be replaced with manufacturer RPE tables or Annex E
interpolation from TS-1014.
"""

from typing import Iterable, List, Tuple


def _sorted_pts(pts: Iterable[Tuple[float, float]]) -> List[Tuple[float, float]]:
    out = sorted((float(a), float(d)) for a, d in pts)
    merged: List[Tuple[float, float]] = []
    for a, d in out:
        if merged and abs(merged[-1][0] - a) < 1e-9:
            merged[-1] = (a, d)
        else:
            merged.append((a, d))
    return merged


def interpolate_rpe_db(angle_deg: float, rpe_points: Iterable[Tuple[float, float]]) -> float:
    pts = _sorted_pts(rpe_points)
    if not pts:
        return 0.0
    x = abs(float(angle_deg))
    if x <= pts[0][0]:
        return pts[0][1]
    for (a0, d0), (a1, d1) in zip(pts, pts[1:]):
        if a0 <= x <= a1:
            if abs(a1 - a0) < 1e-12:
                return d0
            t = (x - a0) / (a1 - a0)
            return d0 + t * (d1 - d0)
    return pts[-1][1]


def combined_rpe_gain_dbi(g_max_dbi: float, az_off_deg: float, el_off_deg: float,
                          az_rpe_pts: Iterable[Tuple[float, float]],
                          el_rpe_pts: Iterable[Tuple[float, float]],
                          backlobe_floor_dbi: float = -10.0) -> float:
    az_att = interpolate_rpe_db(az_off_deg, az_rpe_pts)
    el_att = interpolate_rpe_db(el_off_deg, el_rpe_pts)
    g = g_max_dbi - (az_att + el_att)
    return max(g, backlobe_floor_dbi)


