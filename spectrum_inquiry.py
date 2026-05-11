"""Spectrum inquiry helper (single entry point).

This provides a simple, testable function that takes:
- AP coordinates (lat/lon)
- Incumbent records (ULS-like dicts)
- Basic environment and constraints
and returns a grant table over a requested band and bandwidth set.

WINNF-TS-1014 alignment: wraps 9.1.1 evaluation with co/adjacent handling and
the FS parameter precedence implemented elsewhere.
"""

from typing import Iterable, Tuple, List, Dict, Any

from .spec_params import SpecParameters
from .grant_table import build_grant_table_with_incumbents
from .device_constraints import DeviceConstraints
from .grant_table import grant_rows_to_table


def spectrum_inquiry(
    spec: SpecParameters,
    incumbents: Iterable[Dict[str, Any]],
    ap_lat: float,
    ap_lon: float,
    band_ranges_mhz: Iterable[Tuple[float, float]] = ((5925.0, 6425.0),),
    bandwidths_mhz: Iterable[float] = (20.0, 40.0, 80.0, 160.0),
    inr_limit_db: float = -6.0,
    environment: str | None = None,
    path_model: str = "auto",
    device_constraints: DeviceConstraints | None = None,
    indoor: bool = False,
    penetration_db: float | None = None,
    protection_margin_db: float = 0.0,
):
    """Return combined grant rows (list) for the given AP and bands.

    Computes per-incumbent distances and antenna discrimination automatically.
    """
    all_rows = []
    for lo, hi in band_ranges_mhz:
        rows = build_grant_table_with_incumbents(
            spec=spec,
            incumbents=incumbents,
            distance_m=None,
            ap_lat=ap_lat,
            ap_lon=ap_lon,
            lower_mhz=lo,
            upper_mhz=hi,
            bandwidths_mhz=bandwidths_mhz,
            inr_limit_db=inr_limit_db,
            environment=environment,
            path_model=path_model,
            device_constraints=device_constraints,
            indoor=indoor,
            penetration_db=penetration_db,
            protection_margin_db=protection_margin_db,
        )
        all_rows.extend(rows)
    return all_rows


