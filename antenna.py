"""Simple antenna pattern helpers (placeholders for RPE models).

Goal: provide utilities to estimate how antenna gain drops when looking away
from the main beam (boresight).

Supports:
1. ITU-R F.699 / F.1245 (via openafc_py if available, or internal fallback)
2. Simple Parabolic Model (deprecated but kept for backward compat)
"""

from dataclasses import dataclass
import math

# Try to import rigorous ITU models from openafc_py
try:
    from openafc_py.antenna_itu import calc_itu699_gain
    _HAS_OPENAFC_ITU = True
except ImportError:
    _HAS_OPENAFC_ITU = False


@dataclass(frozen=True)
class AntennaPatternParams:
    """Defines a very simple pattern by beamwidths and limits.

    g_max_dbi: main beam (boresight) gain in dBi
    hpbw_az_deg: 3 dB beamwidth in azimuth (degrees)
    hpbw_el_deg: 3 dB beamwidth in elevation (degrees)
    sidelobe_floor_db: max attenuation (dB) per plane before sidelobes (default 20 dB)
    backlobe_floor_dbi: minimum gain anywhere (e.g., -10 dBi)
    """

    g_max_dbi: float = 30.0
    hpbw_az_deg: float = 3.0
    hpbw_el_deg: float = 3.0
    sidelobe_floor_db: float = 20.0
    backlobe_floor_dbi: float = -10.0


def off_axis_azimuth_deg(antenna_azimuth_deg: float, bearing_to_target_deg: float) -> float:
    """Absolute azimuth off-axis angle between antenna boresight and target bearing."""
    d = abs(((bearing_to_target_deg - antenna_azimuth_deg + 180.0) % 360.0) - 180.0)
    return d


def _attenuation_parabolic(delta_deg: float, hpbw_deg: float, sidelobe_floor_db: float) -> float:
    if hpbw_deg <= 0:
        return sidelobe_floor_db
    att = 12.0 * (delta_deg / hpbw_deg) ** 2
    return min(att, sidelobe_floor_db)


def effective_gain_dbi(
    pattern: AntennaPatternParams,
    azimuth_offaxis_deg: float,
    elevation_offaxis_deg: float,
    use_itu_f699: bool = True,  # Default to high-fidelity model
) -> float:
    """Compute effective gain at given off-axis angles.

    Args:
        pattern: antenna pattern parameters
        azimuth_offaxis_deg: |Δ_az| from boresight (degrees)
        elevation_offaxis_deg: |Δ_el| from boresight (degrees)
        use_itu_f699: if True, try to use ITU-R F.699 model (requires openafc_py or implementation).
                      If False or unavailable, falls back to simple parabolic.

    Returns:
        gain in dBi
    """
    # 1. Try ITU-R F.699 (Rigorous)
    if use_itu_f699 and _HAS_OPENAFC_ITU:
        # F.699 defines discrimination based on total off-axis angle usually,
        # but here we combine Az/El. A common approximation for FS is:
        # phi = sqrt(az^2 + el^2)
        phi = math.sqrt(azimuth_offaxis_deg**2 + elevation_offaxis_deg**2)
        
        # OpenAFC Python clone signature: calc_itu699_gain(off_axis_deg, g_max_dbi, d_lambda=None)
        return calc_itu699_gain(phi, pattern.g_max_dbi)

    # 2. Fallback: Parabolic
    a_az = _attenuation_parabolic(abs(azimuth_offaxis_deg), pattern.hpbw_az_deg, pattern.sidelobe_floor_db)
    a_el = _attenuation_parabolic(abs(elevation_offaxis_deg), pattern.hpbw_el_deg, pattern.sidelobe_floor_db)
    g = pattern.g_max_dbi - (a_az + a_el)
    return max(g, pattern.backlobe_floor_dbi)
