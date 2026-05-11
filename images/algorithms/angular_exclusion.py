"""
Angular Exclusion Algorithm - Lighthouse Effect Mitigation

The Lighthouse Effect occurs when aggregate interference is dominated by distant 
devices aligned with an incumbent antenna's high-gain boresight. Standard circular 
exclusion zones are inefficient.

This module implements:
1. Off-axis angle calculation between AP and incumbent boresight
2. ITU-R F.1245 and F.699 antenna radiation patterns
3. Angular-aware EIRP limits (lower power in boresight direction)

Reference: Ph.D. Dissertation Defense Steps, Section 2.1
"""

import math
from typing import Tuple, Optional
from dataclasses import dataclass


@dataclass
class IncumbentAntenna:
    """
    Fixed Service incumbent antenna parameters.
    
    Attributes:
        lat, lon: Antenna location (degrees)
        height_m: Height above ground level
        boresight_azimuth_deg: Main beam direction (0° = North, 90° = East)
        boresight_elevation_deg: Elevation angle (0° = horizon)
        max_gain_dbi: Peak antenna gain
        beamwidth_3db_deg: 3 dB beamwidth
        pattern_type: "ITU-R_F.1245" or "ITU-R_F.699"
    """
    lat: float
    lon: float
    height_m: float = 30.0
    boresight_azimuth_deg: float = 0.0
    boresight_elevation_deg: float = 0.0
    max_gain_dbi: float = 38.8  # Typical 6-foot dish at 6 GHz
    beamwidth_3db_deg: float = 1.8
    pattern_type: str = "ITU-R_F.1245"


def compute_off_axis_angle_deg(
    ap_lat: float,
    ap_lon: float,
    ap_height_m: float,
    incumbent: IncumbentAntenna
) -> Tuple[float, float, float]:
    """
    Calculate the 3D off-axis angle of an AP relative to incumbent antenna boresight.
    
    This is the KEY calculation for the Lighthouse Effect mitigation!
    
    Args:
        ap_lat, ap_lon: AP coordinates
        ap_height_m: AP height above ground
        incumbent: Incumbent antenna parameters
        
    Returns:
        (off_axis_angle_deg, azimuth_from_rx_deg, elevation_from_rx_deg)
        - off_axis_angle_deg: Total angular separation from boresight
        - azimuth_from_rx_deg: Azimuth from RX to AP (0-360)
        - elevation_from_rx_deg: Elevation angle from RX to AP
        
    Example:
        >>> incumbent = IncumbentAntenna(41.0, 29.0, 30.0, boresight_azimuth_deg=90.0)
        >>> off_axis, az, el = compute_off_axis_angle_deg(41.0, 29.1, 10.0, incumbent)
        >>> print(f"Off-axis: {off_axis:.2f}°")
    """
    from terrain.geodesy_utils import haversine_distance_m, azimuth_deg as calc_azimuth
    
    # 1. Calculate horizontal distance and azimuth from RX to AP
    distance_m = haversine_distance_m(incumbent.lat, incumbent.lon, ap_lat, ap_lon)
    azimuth_rx_to_ap = calc_azimuth(incumbent.lat, incumbent.lon, ap_lat, ap_lon)
    
    # 2. Calculate elevation angle from RX to AP
    height_diff_m = ap_height_m - incumbent.height_m
    elevation_rx_to_ap = math.degrees(math.atan2(height_diff_m, distance_m))
    
    # 3. Calculate azimuth difference from boresight
    azimuth_diff = azimuth_rx_to_ap - incumbent.boresight_azimuth_deg
    
    # Normalize to [-180, 180]
    while azimuth_diff > 180:
        azimuth_diff -= 360
    while azimuth_diff < -180:
        azimuth_diff += 360
    
    # 4. Calculate elevation difference from boresight
    elevation_diff = elevation_rx_to_ap - incumbent.boresight_elevation_deg
    
    # 5. Calculate 3D off-axis angle using spherical geometry
    # off_axis = arccos(cos(Δaz) * cos(Δel))
    # This gives the total angular separation on the celestial sphere
    
    cos_off_axis = (math.cos(math.radians(azimuth_diff)) * 
                    math.cos(math.radians(elevation_diff)))
    
    # Clamp to valid range for arccos
    cos_off_axis = max(-1.0, min(1.0, cos_off_axis))
    
    off_axis_angle = math.degrees(math.acos(cos_off_axis))
    
    return off_axis_angle, azimuth_rx_to_ap, elevation_rx_to_ap


def get_antenna_gain_at_angle_itu_f1245(
    off_axis_deg: float,
    max_gain_dbi: float,
    beamwidth_3db_deg: float
) -> float:
    """
    Calculate antenna gain at off-axis angle using ITU-R F.1245 pattern.
    
    This is the standard pattern for Fixed Service microwave antennas.
    
    Reference: ITU-R Recommendation F.1245
    
    Args:
        off_axis_deg: Angular offset from boresight (0-180)
        max_gain_dbi: Peak antenna gain
        beamwidth_3db_deg: 3 dB beamwidth
        
    Returns:
        Gain in dBi at the specified off-axis angle
        
    Pattern formula:
        G(θ) = Gmax - 12*(θ/θ3dB)^2   for θ <= θm
        G(θ) = Gmax - Xm              for θm < θ <= θr
        G(θ) = Gmax - X1 - 25*log10(θ) for θ > θr
        
    where θm and θr are pattern transition angles
    """
    theta = abs(off_axis_deg)
    theta_3db = beamwidth_3db_deg
    
    # Calculate transition angles
    # θm: angle where main lobe meets first side-lobe
    theta_m = theta_3db * math.sqrt(12 * (max_gain_dbi - 10) / max_gain_dbi)
    
    # θr: angle where far side-lobe formula starts
    theta_r = 15.85 * (max_gain_dbi ** (-0.6))
    
    # Main lobe (Gaussian-like)
    if theta <= theta_m:
        gain = max_gain_dbi - 12 * (theta / theta_3db) ** 2
    
    # Near side-lobes
    elif theta <= theta_r:
        Xm = 12 * (theta_m / theta_3db) ** 2
        gain = max_gain_dbi - Xm
    
    # Far side-lobes
    else:
        X1 = 12 * (theta_m / theta_3db) ** 2
        gain = max_gain_dbi - X1 - 25 * math.log10(theta)
    
    # Minimum gain floor (typically -10 dBi for back lobe)
    min_gain = -10.0
    
    return max(gain, min_gain)


def get_antenna_gain_at_angle_itu_f699(
    off_axis_deg: float,
    max_gain_dbi: float,
    diameter_wavelengths: float = 100.0
) -> float:
    """
    Calculate antenna gain using ITU-R F.699 pattern (alternative to F.1245).
    
    This pattern is based on antenna diameter in wavelengths.
    
    Reference: ITU-R Recommendation F.699
    
    Args:
        off_axis_deg: Angular offset from boresight
        max_gain_dbi: Peak antenna gain
        diameter_wavelengths: Antenna diameter / wavelength (D/λ)
        
    Returns:
        Gain in dBi
    """
    theta = abs(off_axis_deg)
    D_lambda = diameter_wavelengths
    
    # Pattern parameters
    theta_1 = 100 / D_lambda  # First null
    
    if theta < theta_1:
        # Main lobe
        gain = max_gain_dbi - 2.5e-3 * (D_lambda * theta) ** 2
    else:
        # Side lobes
        gain = 32 - 25 * math.log10(theta)
    
    return max(gain, -10.0)


def compute_angular_eirp_limit_dbm(
    ap_lat: float,
    ap_lon: float,
    ap_height_m: float,
    incumbent: IncumbentAntenna,
    path_loss_db: float,
    target_inr_db: float = -6.0,
    noise_power_dbm: float = -104.0
) -> Tuple[float, float]:
    """
    Calculate maximum allowed AP EIRP considering angular antenna discrimination.
    
    This is the CORE of the Angular Exclusion algorithm!
    
    The key insight: APs in the boresight direction get MUCH lower EIRP limits
    than APs in the side-lobes, maximizing spectrum efficiency.
    
    Formula:
        EIRP_max = I_threshold + L_path - G_rx(θ)
        
    where:
        I_threshold = target I/N ratio + noise power
        L_path = path loss between AP and RX
        G_rx(θ) = RX antenna gain at off-axis angle θ
    
    Args:
        ap_lat, ap_lon, ap_height_m: AP location
        incumbent: Incumbent antenna
        path_loss_db: Path loss from AP to incumbent RX
        target_inr_db: Target interference-to-noise ratio (typically -6 dB)
        noise_power_dbm: RX noise power
        
    Returns:
        (eirp_max_dbm, off_axis_angle_deg)
        
    Example:
        >>> incumbent = IncumbentAntenna(41.0, 29.0, 30.0, boresight_azimuth_deg=90.0)
        >>> # AP in boresight (low EIRP allowed)
        >>> eirp1, angle1 = compute_angular_eirp_limit_dbm(41.0, 29.2, 10, incumbent, 120.0)
        >>> # AP in side-lobe (higher EIRP allowed)
        >>> eirp2, angle2 = compute_angular_eirp_limit_dbm(41.2, 29.0, 10, incumbent, 120.0)
        >>> print(f"Boresight EIRP: {eirp1:.1f} dBm, Side-lobe EIRP: {eirp2:.1f} dBm")
    """
    # 1. Calculate off-axis angle
    off_axis_angle, _, _ = compute_off_axis_angle_deg(
        ap_lat, ap_lon, ap_height_m, incumbent
    )
    
    # 2. Get antenna gain at this angle
    if incumbent.pattern_type == "ITU-R_F.1245":
        rx_gain_dbi = get_antenna_gain_at_angle_itu_f1245(
            off_axis_angle, 
            incumbent.max_gain_dbi,
            incumbent.beamwidth_3db_deg
        )
    else:  # F.699
        rx_gain_dbi = get_antenna_gain_at_angle_itu_f699(
            off_axis_angle,
            incumbent.max_gain_dbi
        )
    
    # 3. Calculate interference threshold
    interference_threshold_dbm = noise_power_dbm + target_inr_db
    
    # 4. Calculate max allowed EIRP
    # EIRP_max = I_threshold + L_path - G_rx
    eirp_max_dbm = interference_threshold_dbm + path_loss_db - rx_gain_dbi
    
    return eirp_max_dbm, off_axis_angle


def demonstrate_lighthouse_effect():
    """
    Demonstrate the Lighthouse Effect and how Angular Exclusion mitigates it.
    """
    print("=" * 80)
    print("LIGHTHOUSE EFFECT DEMONSTRATION")
    print("=" * 80)
    
    # Create incumbent at Istanbul with boresight pointing East
    incumbent = IncumbentAntenna(
        lat=41.0,
        lon=29.0,
        height_m=30.0,
        boresight_azimuth_deg=90.0,  # Pointing East
        max_gain_dbi=38.8,
        beamwidth_3db_deg=1.8
    )
    
    print(f"\nIncumbent RX:")
    print(f"  Location: {incumbent.lat}°N, {incumbent.lon}°E, {incumbent.height_m}m")
    print(f"  Boresight: {incumbent.boresight_azimuth_deg}° (East)")
    print(f"  Max gain: {incumbent.max_gain_dbi} dBi")
    print(f"  Beamwidth: {incumbent.beamwidth_3db_deg}°")
    
    # Test APs at different positions
    test_aps = [
        ("AP in boresight (East)", 41.0, 29.2, 10),     # Directly in boresight
        ("AP slightly off boresight", 41.01, 29.2, 10), # 1° off
        ("AP in side-lobe (North)", 41.2, 29.0, 10),    # 90° off (North)
        ("AP in back-lobe (West)", 41.0, 28.8, 10),     # 180° off (West)
    ]
    
    path_loss = 120.0  # Assume same path loss for comparison
    
    print(f"\n{'Location':<30} {'Off-axis':<12} {'RX Gain':<12} {'Max EIRP'}")
    print("-" * 80)
    
    for name, lat, lon, height in test_aps:
        eirp_max, off_axis = compute_angular_eirp_limit_dbm(
            lat, lon, height, incumbent, path_loss
        )
        
        # Also get the RX gain for display
        rx_gain = get_antenna_gain_at_angle_itu_f1245(
            off_axis, incumbent.max_gain_dbi, incumbent.beamwidth_3db_deg
        )
        
        print(f"{name:<30} {off_axis:>10.2f}° {rx_gain:>10.1f} dBi {eirp_max:>10.1f} dBm")
    
    print("\n" + "=" * 80)
    print("KEY INSIGHT:")
    print("  APs in the boresight get MUCH LOWER EIRP limits!")
    print("  This prevents the 'Lighthouse Effect' where distant boresight APs")
    print("  dominate aggregate interference.")
    print("  Side-lobe APs can use higher power → better spectrum efficiency!")
    print("=" * 80)


if __name__ == "__main__":
    # Run demonstration
    demonstrate_lighthouse_effect()
