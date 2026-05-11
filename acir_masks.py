"""ACIR mask mapping utilities.

Goal: map regulatory or measured spectral masks (Tx out-of-band leakage and Rx
selectivity) into an effective ACIR(dB) at a given offset frequency.

Inputs are sparse "mask points" as (offset_MHz, attenuation_dB). We linearly
interpolate between points and extrapolate flat beyond the last point.

WINNF-TS-1014 references:
- R0-AIP-04 (adjacent-channel I/N) and R2-AIP-03 (consider first-adjacent and
  1.5× first-adjacent per 47 CFR 15.407(b)(7)).
"""

from typing import Iterable, List, Tuple, Dict

from .acir import acir_db


def _sorted_points(points: Iterable[Tuple[float, float]]) -> List[Tuple[float, float]]:
    pts = sorted((float(x), float(y)) for x, y in points)
    # Remove duplicates by last value wins
    cleaned: List[Tuple[float, float]] = []
    for x, y in pts:
        if cleaned and abs(cleaned[-1][0] - x) < 1e-9:
            cleaned[-1] = (x, y)
        else:
            cleaned.append((x, y))
    return cleaned


def interpolate_mask_db(offset_mhz: float, mask_points: Iterable[Tuple[float, float]]) -> float:
    """Linearly interpolate attenuation (dB) at offset (MHz) from mask points.

    If offset is below the first point, return the first point's attenuation.
    If above last, return the last point's attenuation (flat extrapolation).
    """
    pts = _sorted_points(mask_points)
    if not pts:
        raise ValueError("mask_points must not be empty")
    x = float(offset_mhz)
    if x <= pts[0][0]:
        return pts[0][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 <= x <= x1:
            if abs(x1 - x0) < 1e-12:
                return y0
            t = (x - x0) / (x1 - x0)
            return y0 + t * (y1 - y0)
    return pts[-1][1]


def acir_db_from_masks(
    offset_mhz: float,
    tx_mask_points: Iterable[Tuple[float, float]],
    rx_acs_points: Iterable[Tuple[float, float]],
) -> float:
    """Compute ACIR(dB) at a given offset from Tx and Rx masks.

    Args:
        offset_mhz: absolute offset in MHz between AP channel and FS center
        tx_mask_points: (offset_MHz, attenuation_dB) Tx out-of-band mask
        rx_acs_points: (offset_MHz, attenuation_dB) Rx selectivity mask
    """
    a_tx = interpolate_mask_db(offset_mhz, tx_mask_points)
    a_rx = interpolate_mask_db(offset_mhz, rx_acs_points)
    return acir_db(a_tx, a_rx)


def acir_profile_from_tables(
    tx_table: Dict[int, float],
    rx_table: Dict[int, float],
    offsets_mhz: Iterable[int] = (10, 20, 30, 40, 80, 120),
) -> List[Tuple[float, float]]:
    """Build an ACIR profile table (offset, ACIR_dB) from sparse ACLR/ACS entries.

    Helpful to inspect or cache ACIR across several offsets.
    """
    pts_tx = sorted((float(k), float(v)) for k, v in tx_table.items())
    pts_rx = sorted((float(k), float(v)) for k, v in rx_table.items())
    results: List[Tuple[float, float]] = []
    for off in offsets_mhz:
        a = acir_db_from_masks(float(off), pts_tx, pts_rx)
        results.append((float(off), a))
    return results


