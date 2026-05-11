"""Default ACIR/ACLR/ACS tables for 6 GHz (placeholders).

These are conservative example values to be used when explicit masks are not
provided. Replace with jurisdiction/device-specific masks as needed (e.g.,
47 CFR 15.407(b)(7)).
"""

from typing import Dict


def default_tx_mask_db_by_offset_mhz() -> Dict[int, float]:
    # offset MHz : attenuation dB (Tx ACLR-like)
    return {10: 20.0, 20: 30.0, 30: 33.0, 40: 35.0, 80: 45.0, 120: 50.0}


def default_rx_acs_db_by_offset_mhz() -> Dict[int, float]:
    # offset MHz : attenuation dB (Rx ACS-like)
    return {10: 18.0, 20: 30.0, 30: 32.0, 40: 35.0, 80: 43.0, 120: 48.0}


def ensure_defaults(a_tx: Dict[int, float], a_rx: Dict[int, float]) -> tuple[Dict[int, float], Dict[int, float]]:
    """Merge provided masks with defaults (fill missing offsets)."""
    tx = dict(default_tx_mask_db_by_offset_mhz())
    rx = dict(default_rx_acs_db_by_offset_mhz())
    tx.update(a_tx or {})
    rx.update(a_rx or {})
    return tx, rx


