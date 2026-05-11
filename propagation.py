"""Propagation models and selector.

Provides a simple selector between FSPL, a WINNER II-style log-distance placeholder,
and an ITM-like placeholder to be replaced with proper bindings. We also support
simple environment presets that add extra loss.

WINNF-TS-1014 reference:
- 9.1.3 Propagation Models — this file provides the hooks and placeholders.
"""

import math
from typing import Literal, Optional

from .fspl import fspl_db
from .itm import longley_rice_pathloss_db
from .p452_adapter import p452_basic_pathloss_db


PathlossModel = Literal["fspl", "winner2", "itm", "p452"]
Environment = Literal["urban", "suburban", "rural", "indoor"]


def winner2_pathloss_db(
    distance_m: float,
    frequency_hz: float,
    pathloss_exponent: float = 2.1,
    reference_distance_m: float = 1.0,
    additional_loss_db: float = 0.0,
) -> float:
    """Simplified WINNER II-style log-distance model placeholder.

    PL(d) = PL(d0) + 10 n log10(d/d0) + L_add
    with PL(d0) taken as FSPL at reference distance.
    """
    if distance_m <= 0 or frequency_hz <= 0:
        raise ValueError("distance and frequency must be positive")
    pl_d0 = fspl_db(max(reference_distance_m, 1e-3), frequency_hz)
    return pl_d0 + 10.0 * pathloss_exponent * math.log10(max(distance_m, reference_distance_m) / reference_distance_m) + additional_loss_db


def two_slope_pathloss_db(
    distance_m: float,
    frequency_hz: float,
    breakpoint_m: float = 100.0,
    n1: float = 2.0,
    n2: float = 3.5,
    additional_loss_db: float = 0.0,
) -> float:
    """Simple two-slope model: FSPL at d0, then n1 up to breakpoint, n2 beyond.

    PL(d) = PL(d0) + 10 n1 log10(d/d0) for d <= bp
          = PL(bp) + 10 n2 log10(d/bp) for d > bp
    """
    if distance_m <= 0 or frequency_hz <= 0:
        raise ValueError("distance and frequency must be positive")
    d0 = 1.0
    pl_d0 = fspl_db(d0, frequency_hz)
    if distance_m <= breakpoint_m:
        return pl_d0 + 10.0 * n1 * math.log10(max(distance_m, d0) / d0) + additional_loss_db
    pl_bp = pl_d0 + 10.0 * n1 * math.log10(breakpoint_m / d0)
    return pl_bp + 10.0 * n2 * math.log10(distance_m / breakpoint_m) + additional_loss_db


def itm_pathloss_db(
    distance_m: float,
    frequency_hz: float,
    terrain_profile: Optional[object] = None,
    rx_tx_heights_m: Optional[tuple[float, float]] = None,
    climate: Optional[str] = None,
    reliability_pct: float = 50.0,
) -> float:
    """ITM (Longley–Rice) path loss via adapter.

    Uses `afc_new.itm.longley_rice_pathloss_db` which invokes pyitm if available,
    otherwise falls back to a conservative heuristic.
    """
    tx_h = rx_tx_heights_m[0] if rx_tx_heights_m else None
    rx_h = rx_tx_heights_m[1] if rx_tx_heights_m else None
    return longley_rice_pathloss_db(
        distance_m=distance_m,
        frequency_hz=frequency_hz,
        tx_height_m=tx_h,
        rx_height_m=rx_h,
        climate=climate,
        reliability_pct=reliability_pct,
    )


def p452_pathloss_db(
    distance_m: float,
    frequency_hz: float,
    tx_height_m: float = 10.0,
    rx_height_m: float = 10.0,
    tx_lon_deg: float = 0.0,
    tx_lat_deg: float = 0.0,
    rx_lon_deg: float = 0.0,
    rx_lat_deg: float = 0.0,
    polarization: int = 1,
    time_percentage: float = 50.0,
) -> float:
    """ITU-R P.452-18 via Py452 wrapper (flat profile fallback).

    For high-fidelity results provide real profiles through a higher-level
    adapter; this is a minimal integration to enable parity checks.
    """
    return p452_basic_pathloss_db(
        distance_m=distance_m,
        frequency_hz=frequency_hz,
        tx_height_m_agl=tx_height_m,
        rx_height_m_agl=rx_height_m,
        tx_lon_deg=tx_lon_deg,
        tx_lat_deg=tx_lat_deg,
        rx_lon_deg=rx_lon_deg,
        rx_lat_deg=rx_lat_deg,
        polarization=polarization,
        time_percentage=time_percentage,
    )


def environment_extra_loss_db(env: Environment) -> float:
    """Environment/clutter presets (simple).

    These values approximate additional median excess loss beyond free space.
    Replace with a validated clutter model for production (e.g., Hata‑like or
    site‑specific classes). Kept small and conservative.
    """
    return {
        "urban": 8.0,
        "suburban": 4.0,
        "rural": 1.0,
        "indoor": 12.0,
    }[env]


def building_penetration_loss_db(indoor: bool = False, penetration_db: Optional[float] = None) -> float:
    """Simple building penetration loss model.

    If `penetration_db` is provided, use it. Otherwise, if `indoor` is True,
    apply a typical 12 dB indoor loss placeholder; else 0 dB.
    """
    if penetration_db is not None:
        return max(0.0, float(penetration_db))
    return 12.0 if indoor else 0.0


def select_pathloss_db(
    distance_m: float,
    frequency_hz: float,
    selector: PathlossModel | None = None,
    winner_threshold_m: float = 1000.0,
    environment: Environment | None = None,
    indoor: bool = False,
    penetration_db: Optional[float] = None,
) -> float:
    """Select a pathloss model by distance or explicit selector.

    Notes:
    - In `selector=None` (aka "auto") mode, we follow the same *distance regime* used
      by our openafc_py parity engine:
        - FSPL for very short links (<= 30 m)
        - Mid-range log-distance ("WINNER2-like") for 30 m .. winner_threshold_m
        - ITM for >= winner_threshold_m
    - To avoid artificial discontinuities at the model boundary, we *calibrate* the
      mid-range curve so it matches FSPL at 30 m and ITM at winner_threshold_m.
    """
    if selector == "fspl":
        pl = fspl_db(distance_m, frequency_hz)
    elif selector == "winner2":
        pl = winner2_pathloss_db(distance_m, frequency_hz)
    elif selector == "itm":
        pl = itm_pathloss_db(distance_m, frequency_hz)
    elif selector == "p452":
        pl = p452_pathloss_db(distance_m, frequency_hz)
    elif selector is None:
        # Auto selector with continuity:
        # - FSPL at <=30 m
        # - Calibrated mid-range log-distance between 30 m and threshold
        # - ITM beyond threshold
        if distance_m <= 30.0:
            pl = fspl_db(distance_m, frequency_hz)
        elif distance_m >= winner_threshold_m:
            pl = itm_pathloss_db(distance_m, frequency_hz)
        else:
            d0 = 30.0
            d1 = float(winner_threshold_m)
            pl0 = fspl_db(d0, frequency_hz)
            pl1 = itm_pathloss_db(d1, frequency_hz)
            denom = 10.0 * math.log10(d1 / d0)
            # Effective exponent that matches the two endpoints
            n_eff = (pl1 - pl0) / denom if abs(denom) > 1e-12 else 2.0
            pl = pl0 + 10.0 * n_eff * math.log10(distance_m / d0)
    else:
        raise ValueError("Unknown pathloss selector")

    if environment is not None:
        pl += environment_extra_loss_db(environment)
    # Add optional building penetration loss (e.g., indoor FS or AP)
    pl += building_penetration_loss_db(indoor=indoor, penetration_db=penetration_db)
    return pl

