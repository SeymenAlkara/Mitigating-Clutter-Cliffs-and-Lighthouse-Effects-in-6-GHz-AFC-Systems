"""UNII band/channel utilities.

Provides helpers to enumerate standard 6 GHz Wi‑Fi centers across UNII-5..8
for given bandwidths, and mapping to channel numbers.
"""

from typing import Iterable, List, Tuple


def centers_for_band(lower_mhz: float, upper_mhz: float, bandwidth_mhz: float) -> List[float]:
    centers: List[float] = []
    origin = 5955.0
    step = bandwidth_mhz
    n0 = int((lower_mhz - origin + step - 1e-9) // step)
    c = origin + n0 * step
    while c + bandwidth_mhz / 2.0 <= upper_mhz:
        lo = c - bandwidth_mhz / 2.0
        hi = c + bandwidth_mhz / 2.0
        if lo >= lower_mhz - 1e-9 and hi <= upper_mhz + 1e-9:
            centers.append(c)
        c += step
    return centers


def enumerate_bands(band_selector: str) -> List[Tuple[float, float]]:
    if band_selector == "unii5":
        return [(5925.0, 6425.0)]
    if band_selector == "unii7":
        return [(6525.0, 6875.0)]
    return [(5925.0, 6425.0), (6525.0, 6875.0)]


