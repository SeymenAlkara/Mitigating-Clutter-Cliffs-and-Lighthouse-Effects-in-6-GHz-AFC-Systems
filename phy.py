"""PHY utilities: SINR, capacity and OFDMA helpers.

This module currently implements:
- sinr_db: compute SINR in dB from S/I/N in dBm.
- capacity_bps_hz_from_sinr_db: Shannon capacity per Hz.
- ofdma_sum_capacity_bps: sum capacity over resource units.

Upcoming: Wi‑Fi 6E MCS↔SNR thresholds and a simple PER model.
"""

import math
from typing import Iterable, Tuple


def sinr_db(signal_dbm: float, interference_dbm: float, noise_dbm: float) -> float:
    """Compute SINR in dB from S, I, N given in dBm.

    SINR_dB = 10 log10( S_lin / (I_lin + N_lin) ).
    """
    s_lin = 10.0 ** (signal_dbm / 10.0)
    i_lin = 10.0 ** (interference_dbm / 10.0)
    n_lin = 10.0 ** (noise_dbm / 10.0)
    denom = i_lin + n_lin
    if denom <= 0:
        return float("inf")
    sinr_lin = s_lin / denom
    return 10.0 * math.log10(sinr_lin)


def capacity_bps_hz_from_sinr_db(sinr_db_value: float) -> float:
    """Shannon: log2(1 + SINR)."""
    sinr_lin = 10.0 ** (sinr_db_value / 10.0)
    return math.log2(1.0 + sinr_lin)


def ofdma_sum_capacity_bps(
    ru_sinr_db: Iterable[Tuple[float, float]]
) -> float:
    """Sum capacity over RUs.

    Args:
        ru_sinr_db: iterable of tuples (delta_f_hz, sinr_db)
    Returns:
        capacity in bits/s
    """
    total = 0.0
    for delta_f_hz, sinr_db_value in ru_sinr_db:
        total += delta_f_hz * capacity_bps_hz_from_sinr_db(sinr_db_value)
    return total

