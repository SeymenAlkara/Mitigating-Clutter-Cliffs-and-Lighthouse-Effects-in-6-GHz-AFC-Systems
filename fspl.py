"""FSPL utilities.

This file implements core path-loss math used by the AIP (AFC Incumbent
Protection) flow.

WINNF-TS-1014 reference: 9.1.3 Propagation Models (FSPL per ITU-R P.525 used
as LoS baseline). This file supports those calculations.
"""

import math

_FOUR_PI = 4.0 * math.pi
_C = 2.99792458e8  # m/s


def fspl_db(distance_m: float, frequency_hz: float) -> float:
    """Free-space path loss in dB: 20 log10(4π d f / c).

    Args:
        distance_m: distance in meters (> 0)
        frequency_hz: frequency in Hz (> 0)
    """
    if distance_m <= 0 or frequency_hz <= 0:
        raise ValueError("distance and frequency must be positive")
    x = _FOUR_PI * distance_m * frequency_hz / _C
    return 20.0 * math.log10(x)


def invert_fspl_distance_m(fspl_db_value: float, frequency_hz: float) -> float:
    """Invert FSPL to distance: d = (c/(4π f)) · 10^{FSPL/20}.

    Args:
        fspl_db_value: FSPL in dB
        frequency_hz: frequency in Hz (> 0)
    """
    if frequency_hz <= 0:
        raise ValueError("frequency must be positive")
    return (_C / (_FOUR_PI * frequency_hz)) * (10.0 ** (fspl_db_value / 20.0))

