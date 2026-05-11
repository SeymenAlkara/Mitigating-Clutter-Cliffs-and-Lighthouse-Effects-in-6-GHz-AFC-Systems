"""ITM (Longley–Rice) adapter with graceful fallback.

This module provides a thin adapter function that calls a certified Longley–Rice
implementation (pyitm) when available, and otherwise falls back to a conservative
heuristic on top of FSPL. Keeping the adapter surface small allows us to swap in
other ITM bindings without touching call sites.

WINNF-TS-1014: 9.1.3 Propagation Models — binding location for ITM.
"""

from typing import Optional
import math

from .fspl import fspl_db

# Prefer the numerically-validated openafc_py ITM median if available
try:  # pragma: no cover — optional cross-package dependency
	from openafc_py.propagation_itm import pathloss_itm_median_db as _ofa_itm_median
except Exception:  # pragma: no cover
	_ofa_itm_median = None  # type: ignore

try:
    # pyitm installed by user (pip install pyitm)
    import pyitm  # type: ignore
    _HAS_PYITM = True
except Exception:  # pragma: no cover — optional dependency
    pyitm = None  # type: ignore
    _HAS_PYITM = False


def longley_rice_pathloss_db(
    distance_m: float,
    frequency_hz: float,
    tx_height_m: Optional[float] = None,
    rx_height_m: Optional[float] = None,
    climate: Optional[str] = None,
    reliability_pct: float = 20.0,
) -> float:
    """Compute ITM path loss using pyitm when available; otherwise fallback.

    Args:
        distance_m: path distance in meters
        frequency_hz: frequency in Hz
        tx_height_m: Tx antenna height above ground (m)
        rx_height_m: Rx antenna height above ground (m)
        climate: optional climate string ("continental", "maritime", ...)
        reliability_pct: time/rare-event reliability (50/90/99)

    Returns:
        Path loss in dB between sites at the given distance/frequency.
    """
    if distance_m <= 0 or frequency_hz <= 0:
        raise ValueError("distance and frequency must be positive")

    # If pyitm is present, use it. We defensively handle API differences by
    # checking common entry points and falling back if needed.
    if _HAS_PYITM:
        try:
            # Common patterns seen in pyitm variants. We attempt a simple smooth
            # Earth path with specified heights and reliability. Frequency is in MHz.
            f_mhz = float(frequency_hz) / 1e6
            h_tx = float(tx_height_m) if tx_height_m is not None else 10.0
            h_rx = float(rx_height_m) if rx_height_m is not None else 10.0
            rel = float(reliability_pct)
            clim = (climate or "continental")

            # Try attribute-style access first
            if hasattr(pyitm, "itm"):  # type: ignore[attr-defined]
                # Expected signature variants vary; we pass a minimal set.
                result = pyitm.itm(
                    d_km=distance_m / 1000.0,
                    f_mhz=f_mhz,
                    tx_h_m=h_tx,
                    rx_h_m=h_rx,
                    reliability=rel,
                    climate=clim,
                )
            elif hasattr(pyitm, "longley_rice"):  # type: ignore[attr-defined]
                result = pyitm.longley_rice(
                    distance_km=distance_m / 1000.0,
                    frequency_mhz=f_mhz,
                    tx_height_m=h_tx,
                    rx_height_m=h_rx,
                    reliability=rel,
                    climate=clim,
                )
            else:
                result = None

            if result is not None:
                # Many implementations return path loss dB directly.
                if isinstance(result, (int, float)):
                    val = float(result)
                    if math.isfinite(val):
                        return val
                    # Non-finite -> fall through to heuristic
                # Or a dict/object with 'pl_db' key/attribute
                if isinstance(result, dict) and "pl_db" in result:
                    try:
                        val = float(result["pl_db"])  # type: ignore[index]
                        if math.isfinite(val):
                            return val
                    except Exception:
                        pass
                if hasattr(result, "pl_db"):
                    try:
                        val = float(result.pl_db)  # type: ignore[attr-defined]
                        if math.isfinite(val):
                            return val
                    except Exception:
                        pass
        except Exception:
            # If anything goes wrong with pyitm, fall through to heuristic.
            pass

    # Prefer openafc_py smooth‑earth ITM median if available
    if _ofa_itm_median is not None:
        try:
            return float(_ofa_itm_median(
                distance_m=distance_m,
                frequency_hz=frequency_hz,
                tx_height_m=(tx_height_m or 10.0),
                rx_height_m=(rx_height_m or 10.0),
            ))
        except Exception:
            pass

    # Fallback heuristic: FSPL plus conservative excess loss terms
    base = fspl_db(distance_m, frequency_hz)
    h_tx = max(1.0, (tx_height_m or 10.0))
    h_rx = max(1.0, (rx_height_m or 10.0))
    height_term = -2.0 * math.log10(h_tx * h_rx)
    dist_term = 6.0 * math.log10(max(distance_m, 1.0) / 1000.0)
    climate_term = 0.0
    if climate:
        c = climate.lower()
        if "mar" in c:
            climate_term = 2.0
        elif "tropic" in c:
            climate_term = 1.0
        else:
            climate_term = 3.0
    rel_term = 0.0 if reliability_pct <= 50.0 else (reliability_pct - 50.0) * 0.05
    return base + max(0.0, dist_term + climate_term + rel_term + height_term)


