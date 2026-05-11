"""Link budget utilities for AFC interference calculations.

Implements (WINNF-TS-1014 mapping): 9.1.1 Interference Protection Criteria (I/N)
and evaluation point arithmetic used throughout AIP calculations.

Functions:
- compute_eirp_dbm: compute EIRP from Tx power, antenna gain, and losses.
- noise_power_dbm: compute receiver noise power from bandwidth and NF.
- interference_dbm: compute interference at the incumbent receiver terminals.
- inr_db: compute I/N in dB.
- i_threshold_dbm: compute allowed interference level given INR limit.
- interference_margin_db: margin between threshold and computed interference.
"""

import math


def compute_eirp_dbm(p_tx_dbm: float, g_tx_dbi: float, l_tx_losses_db: float) -> float:
    """Compute EIRP in dBm.

    EIRP [dBm] = P_tx + G_tx − L_tx_losses.
    """
    return p_tx_dbm + g_tx_dbi - l_tx_losses_db


def noise_power_dbm(b_rx_hz: float, nf_db: float, t0_noise_dbmhz: float = -174.0) -> float:
    """Compute receiver noise power in dBm.

    Thermal noise: N [dBm] = -174 + 10 log10(B_Rx) + NF.

    Args:
        b_rx_hz: receiver noise bandwidth in Hz
        nf_db: receiver noise figure in dB
        t0_noise_dbmhz: thermal noise density at 290K in dBm/Hz (default -174)
    """
    if b_rx_hz <= 0:
        raise ValueError("Bandwidth must be positive")
    return t0_noise_dbmhz + 10.0 * math.log10(b_rx_hz) + nf_db


def interference_dbm(
    eirp_dbm: float,
    path_loss_db: float,
    g_rx_dbi: float,
    l_rx_losses_db: float,
    l_polarization_db: float = 0.0,
) -> float:
    """Compute interference at incumbent receiver terminals in dBm.

    I [dBm] = EIRP − PL + G_rx − L_rx_losses − L_polarization
    """
    return eirp_dbm - path_loss_db + g_rx_dbi - l_rx_losses_db - l_polarization_db


def inr_db(i_dbm: float, n_dbm: float) -> float:
    """Compute I/N in dB (simple difference)."""
    return i_dbm - n_dbm


def i_threshold_dbm(n_dbm: float, inr_limit_db: float = -6.0) -> float:
    """Compute allowed interference threshold in dBm.

    I_thresh = N + INR_limit (e.g., -6 dB).
    """
    return n_dbm + inr_limit_db


def interference_margin_db(i_dbm: float, i_thresh_dbm: float) -> float:
    """Interference margin in dB.

    IM = I_thresh − I. Positive means protected.
    """
    return i_thresh_dbm - i_dbm

