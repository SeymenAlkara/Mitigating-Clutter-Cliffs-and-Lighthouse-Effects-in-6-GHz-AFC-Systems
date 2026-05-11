"""FS receiver bandwidth determination per R2-AIP-19 (WINNF-TS-1014).

Implements:
- parse_emission_designator_bw_hz: extract necessary bandwidth from ULS emission
  designator strings like '25M0F7W' (25.0 MHz), '200K0F3E' (200 kHz), etc.
- determine_fs_noise_bw_hz: apply precedence to choose FS receiver noise bandwidth:
  a) If emission designator present -> use its necessary bandwidth
  b) Else if explicit FS Rx noise bandwidth provided -> use it
  c) Else fallback to spec default (e.g., 20 MHz)

This supports 9.1.2.2 R2-AIP-19 a & b from WINNF-TS-1014.

"Precedence" here means "which source of truth wins when multiple bandwidth
values are available?" The order is:
1) Emission designator (necessary bandwidth encoded by the license)
2) Explicit FS Rx bandwidth if provided from data
3) Project/spec default if neither is available
"""

import re
from typing import Optional

from .spec_params import SpecParameters


_UNIT_SCALE = {
    "H": 1.0,    # Hertz
    "K": 1e3,    # kHz
    "M": 1e6,    # MHz
    "G": 1e9,    # GHz
}


def parse_emission_designator_bw_hz(designator: str) -> Optional[float]:
    """Parse the necessary bandwidth from an emission designator.

    Examples:
        '25M0F7W' -> 25.0 MHz -> 25e6 Hz
        '200K0F3E' -> 200.0 kHz -> 200e3 Hz
        '5M50D7W' -> 5.50 MHz -> 5.5e6 Hz

    We look for a pattern like: <digits><unit><digit> where unit in {H,K,M,G}
    with optional embedded decimal encoded as a digit before the unit and a digit
    after. We then convert to Hz.
    """
    if not designator:
        return None
    m = re.search(r"([0-9]{1,3})([HKMG])([0-9])", designator, re.IGNORECASE)
    if not m:
        return None
    whole = int(m.group(1))
    unit = m.group(2).upper()
    frac_digit = int(m.group(3))
    scale = _UNIT_SCALE.get(unit)
    if scale is None:
        return None
    value = (whole + frac_digit / 10.0) * scale
    return value


def determine_fs_noise_bw_hz(
    spec: SpecParameters,
    emission_designator: Optional[str] = None,
    explicit_rx_bw_hz: Optional[float] = None,
    ul_bandwidth_hz: Optional[float] = None,
) -> float:
    """Apply precedence to determine FS receiver noise bandwidth (Hz).

    Order:
      1) Emission designator (if parseable)
      2) Explicit FS Rx noise bandwidth (if provided)
      3) ULS/recorded channel bandwidth (if provided)
      4) Spec default incumbent bandwidth
    """
    bw_from_ed = parse_emission_designator_bw_hz(emission_designator) if emission_designator else None
    if bw_from_ed and bw_from_ed > 0:
        return bw_from_ed
    if explicit_rx_bw_hz and explicit_rx_bw_hz > 0:
        return explicit_rx_bw_hz
    if ul_bandwidth_hz and ul_bandwidth_hz > 0:
        return ul_bandwidth_hz
    return spec.incumbent.bandwidth_hz


