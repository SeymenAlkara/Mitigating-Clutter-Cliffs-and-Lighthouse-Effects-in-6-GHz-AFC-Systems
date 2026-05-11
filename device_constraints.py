"""Device constraint helpers.

Apply minimum operational EIRP/PSD constraints to grant decisions so channels
with allowed EIRP below a device’s minimum are marked deny.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class DeviceConstraints:
    min_eirp_dbm: float = 0.0
    min_psd_dbm_per_mhz: float = -10.0
    power_basis: str = "EIRP"  # "EIRP" or "ERP"


def _to_eirp_dbm(value_dbm: float, basis: str) -> float:
    """Convert value in given power basis to EIRP dBm (ERP→EIRP adds 2.15 dB)."""
    if (basis or "EIRP").upper() == "ERP":
        return value_dbm + 2.15
    return value_dbm


def apply_constraints_to_decision(allowed_eirp_dbm: float, psd_dbm_per_mhz: float, cons: DeviceConstraints) -> bool:
    """Return True if both EIRP and PSD meet device minimums (basis-aware)."""
    thr_eirp_dbm = _to_eirp_dbm(cons.min_eirp_dbm, cons.power_basis)
    thr_psd_dbm = _to_eirp_dbm(cons.min_psd_dbm_per_mhz, cons.power_basis)
    if allowed_eirp_dbm < thr_eirp_dbm:
        return False
    if psd_dbm_per_mhz < thr_psd_dbm:
        return False
    return True


