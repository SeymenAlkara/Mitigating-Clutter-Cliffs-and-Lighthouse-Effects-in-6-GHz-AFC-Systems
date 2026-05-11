"""Adjacent-channel interference ratio (ACIR) helpers.

Functions:
- acir_db: combine Tx leakage (ACLR-like) and Rx selectivity (ACS-like) into ACIR.
- adjacent_channel_interference_dbm: apply ACIR to co-channel interference to estimate adjacent.
- acir_db_from_spec: compute ACIR based on parsed spec tables for a given channel offset.

WINNF-TS-1014 references:
- R0-AIP-04: adjacent-channel interference protection criterion I/N ≤ −6 dB
- R2-AIP-03: account for out-of-channel emission limits (47 CFR 15.407(b)(7)) up to 1.5× first adjacent
"""

import math
from typing import Dict

from .spec_params import ACIRSpec


def acir_db(a_tx_db: float, a_rx_db: float) -> float:
    """ACIR [dB] from Tx leakage (A_tx) and Rx selectivity (A_rx).

    ACIR_lin = 1 / (10^{−A_tx/10} + 10^{−A_rx/10})
    ACIR_dB = 10 log10(ACIR_lin)
    """
    a_tx_lin = 10.0 ** (-a_tx_db / 10.0)
    a_rx_lin = 10.0 ** (-a_rx_db / 10.0)
    denom = a_tx_lin + a_rx_lin
    if denom <= 0:
        raise ValueError("Invalid ACIR inputs")
    acir_lin = 1.0 / denom
    return 10.0 * math.log10(acir_lin)


def adjacent_channel_interference_dbm(i_co_dbm: float, a_tx_db: float, a_rx_db: float) -> float:
    """I_adj [dBm] = I_cochannel − ACIR [dB]."""
    return i_co_dbm - acir_db(a_tx_db, a_rx_db)


def _nearest_key(d: Dict[int, float], key: int) -> int:
    if key in d:
        return key
    if not d:
        raise ValueError("Empty dictionary for ACIR lookup")
    return min(d.keys(), key=lambda k: abs(k - key))


def acir_db_from_spec(acir_spec: ACIRSpec, offset_mhz: int) -> float:
    """Compute ACIR [dB] for a given channel offset using parsed spec tables.

    Uses nearest-neighbor lookup on the provided ACLR/ACS tables, then combines them
    via acir_db().
    """
    k_tx = _nearest_key(acir_spec.a_tx_db_by_offset_mhz, offset_mhz)
    k_rx = _nearest_key(acir_spec.a_rx_db_by_offset_mhz, offset_mhz)
    a_tx = acir_spec.a_tx_db_by_offset_mhz[k_tx]
    a_rx = acir_spec.a_rx_db_by_offset_mhz[k_rx]
    return acir_db(a_tx, a_rx)

