"""AFC EIRP allocation utilities.

This module provides helpers to compute the maximum allowed EIRP for a given path
subject to an I/N constraint, handle adjacent-channel via ACIR, and convert between
PSD and total EIRP. It also includes a verifier to check compliance for a candidate
EIRP value.

WINNF TS-1014 references (informative):
- 9.1.1 Interference Protection Criteria and Evaluation Point (I/N ≤ −6 dB)
- R0-AIP-04 (adjacent-channel I/N criterion) and R2-AIP-03 (use 47 CFR 15.407(b)(7))
- 9.1.2.2 R2-AIP-19 (FS receiver bandwidth precedence) – supported via override hooks
"""

import math
from typing import Optional

from .link_budget import (
    i_threshold_dbm,
    interference_dbm,
)
from .acir import acir_db_from_spec
from .spec_params import SpecParameters


def allowed_eirp_dbm_for_path(
    n_dbm: float,
    inr_limit_db: float,
    path_loss_db: float,
    g_rx_dbi: float,
    l_rx_losses_db: float,
    l_polarization_db: float = 0.0,
    acir_db_value: Optional[float] = None,
    eirp_regulatory_max_dbm: Optional[float] = None,
) -> float:
    """Compute the maximum allowed EIRP [dBm] that satisfies I/N ≤ limit over a given path.

    For co-channel: I = EIRP − PL + G_rx − L_rx − L_pol ≤ I_thresh
    ⇒ EIRP_allowed = I_thresh + PL − G_rx + L_rx + L_pol.

    For adjacent channel, I_adj = I_co − ACIR ⇒ I_co ≤ I_thresh + ACIR.
    If a regulatory cap is provided, the result is min(calculated, regulatory cap).
    """
    i_thr_dbm = i_threshold_dbm(n_dbm=n_dbm, inr_limit_db=inr_limit_db)
    effective_i_thresh = i_thr_dbm
    if acir_db_value is not None:
        effective_i_thresh = i_thr_dbm + acir_db_value

    eirp_allowed = (
        effective_i_thresh
        + path_loss_db
        - g_rx_dbi
        + l_rx_losses_db
        + l_polarization_db
    )

    if eirp_regulatory_max_dbm is not None:
        eirp_allowed = min(eirp_allowed, eirp_regulatory_max_dbm)

    return eirp_allowed


def psd_dbm_per_mhz_from_eirp(eirp_total_dbm: float, bandwidth_mhz: float) -> float:
    """Convert total EIRP to PSD.

    PSD [dBm/MHz] from total EIRP [dBm] over bandwidth in MHz.
    EIRP_total_dBm = PSD_dBm_per_MHz + 10 log10(B_MHz)
    """
    if bandwidth_mhz <= 0:
        raise ValueError("bandwidth_mhz must be positive")
    return eirp_total_dbm - 10.0 * math.log10(bandwidth_mhz)


def eirp_total_dbm_from_psd(psd_dbm_per_mhz: float, bandwidth_mhz: float) -> float:
    """Convert PSD to total EIRP.

    Total EIRP [dBm] from PSD [dBm/MHz] and bandwidth [MHz].
    """
    if bandwidth_mhz <= 0:
        raise ValueError("bandwidth_mhz must be positive")
    return psd_dbm_per_mhz + 10.0 * math.log10(bandwidth_mhz)


def allowed_eirp_dbm_with_spec(
    n_dbm: float,
    inr_limit_db: float,
    path_loss_db: float,
    spec: SpecParameters,
    channel_offset_mhz: Optional[int] = None,
    eirp_regulatory_max_dbm: Optional[float] = None,
    l_polarization_db: Optional[float] = None,
    override_g_rx_dbi: Optional[float] = None,
) -> float:
    """Wrapper that uses SpecParameters to compute allowed EIRP.

    Args:
        n_dbm: receiver noise power (incumbent) in dBm
        inr_limit_db: protection limit (e.g., -6 dB)
        path_loss_db: path loss from AP to FS receiver in dB
        spec: parsed spec parameters (incumbent gains/losses and ACIR tables)
        channel_offset_mhz: None for co-channel; otherwise positive offset (e.g., 20, 40)
        eirp_regulatory_max_dbm: optional cap (defaults to spec.wifi_limits.max_eirp_dbm)
        l_polarization_db: optional override polarization mismatch (defaults from spec)
        override_g_rx_dbi: optional override for incumbent receiver antenna gain (dBi)
    """
    if eirp_regulatory_max_dbm is None:
        eirp_regulatory_max_dbm = spec.wifi_limits.max_eirp_dbm
    if l_polarization_db is None:
        l_polarization_db = spec.incumbent.polarization_mismatch_db

    acir_val = None
    if channel_offset_mhz is not None and channel_offset_mhz > 0:
        acir_val = acir_db_from_spec(spec.acir, channel_offset_mhz)

    return allowed_eirp_dbm_for_path(
        n_dbm=n_dbm,
        inr_limit_db=inr_limit_db,
        path_loss_db=path_loss_db,
        g_rx_dbi=(override_g_rx_dbi if override_g_rx_dbi is not None else spec.incumbent.antenna_gain_dbi),
        l_rx_losses_db=spec.incumbent.rx_losses_db,
        l_polarization_db=l_polarization_db,
        acir_db_value=acir_val,
        eirp_regulatory_max_dbm=eirp_regulatory_max_dbm,
    )


def allowed_eirp_dbm_with_spec_multi(
    n_dbm: float,
    inr_limit_db: float,
    path_loss_db: float,
    spec: SpecParameters,
    offsets_mhz: list[int] | tuple[int, ...],
    eirp_regulatory_max_dbm: Optional[float] = None,
    l_polarization_db: Optional[float] = None,
    override_g_rx_dbi: Optional[float] = None,
) -> float:
    """Compute allowed EIRP enforcing multiple offset constraints; return the minimum.

    This implements the spirit of "EIRP is set such that both in-band and adjacent
    channel interference are met across SPD’s channel +/- first adjacent channel".
    We accept a set of offsets (in MHz) to check simultaneously.
    """
    if eirp_regulatory_max_dbm is None:
        eirp_regulatory_max_dbm = spec.wifi_limits.max_eirp_dbm
    if l_polarization_db is None:
        l_polarization_db = spec.incumbent.polarization_mismatch_db

    best = eirp_regulatory_max_dbm
    for off in offsets_mhz:
        acir_val = None
        if off is not None and off > 0:
            acir_val = acir_db_from_spec(spec.acir, off)
        eirp = allowed_eirp_dbm_for_path(
            n_dbm=n_dbm,
            inr_limit_db=inr_limit_db,
            path_loss_db=path_loss_db,
            g_rx_dbi=(override_g_rx_dbi if override_g_rx_dbi is not None else spec.incumbent.antenna_gain_dbi),
            l_rx_losses_db=spec.incumbent.rx_losses_db,
            l_polarization_db=l_polarization_db,
            acir_db_value=acir_val,
            eirp_regulatory_max_dbm=eirp_regulatory_max_dbm,
        )
        if eirp < best:
            best = eirp
    return best


def verify_interference_meets_limit(
    eirp_dbm: float,
    path_loss_db: float,
    g_rx_dbi: float,
    l_rx_losses_db: float,
    l_polarization_db: float,
    n_dbm: float,
    inr_limit_db: float,
    acir_db_value: Optional[float] = None,
) -> bool:
    """Check if a given EIRP meets I/N ≤ limit (with optional ACIR).

    Returns True if compliant.
    """
    i_co_dbm = interference_dbm(
        eirp_dbm=eirp_dbm,
        path_loss_db=path_loss_db,
        g_rx_dbi=g_rx_dbi,
        l_rx_losses_db=l_rx_losses_db,
        l_polarization_db=l_polarization_db,
    )
    i_thr_dbm = i_threshold_dbm(n_dbm=n_dbm, inr_limit_db=inr_limit_db)
    if acir_db_value is not None:
        i_co_limit = i_thr_dbm + acir_db_value
        return i_co_dbm <= i_co_limit + 1e-9
    return i_co_dbm <= i_thr_dbm + 1e-9

