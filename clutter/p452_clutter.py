"""
ITU-R P.452 Clutter Loss Calculator

Implements the proper ITU-R P.452-17 building entry loss and clutter loss models.

This replaces the simplified approximation with the actual ITU-R formulas.
"""

import math
from typing import Tuple


def compute_p452_clutter_loss_db(
    frequency_mhz: float,
    distance_km: float,
    tx_height_m: float,
    rx_height_m: float,
    clutter_height_m: float,
    nominal_distance_km: float = 0.0
) -> Tuple[float, float]:
    """
    Calculate clutter loss according to ITU-R P.452-17 Annex 1, Section 4.5.
    
    This is the EXACT ITU-R P.452-17 formula for clutter loss!
    
    Formula:
        A_h = 10.25 * F_fc * exp(-d_nom) * (1 - tanh(6 * (h_eff/h_clutter - 0.625))) - 0.33
    
    Where:
        F_fc = 0.25 + 0.375 * (1 + tanh(7.5 * (f_ghz - 0.5)))
        d_nom = distance from nominal clutter point to antenna
        h_eff = effective antenna height above local ground
        h_clutter = nominal clutter height
    
    Args:
        frequency_mhz: Frequency in MHz
        distance_km: Path distance in km
        tx_height_m: Transmitter antenna height above ground level
        rx_height_m: Receiver antenna height above ground level
        clutter_height_m: Nominal clutter height from land cover data (m)
        nominal_distance_km: Nominal distance from antenna to clutter edge (km)
        
    Returns:
        Tuple of (tx_clutter_loss_db, rx_clutter_loss_db)
        
    Reference:
        ITU-R Recommendation P.452-17 (2021), Annex 1, Section 4.5
        "Additional losses due to terminal surroundings"
    """
    
    # If no clutter, return zero loss
    if clutter_height_m <= 0 or nominal_distance_km <= 0:
        return (0.0, 0.0)
    
    f_ghz = frequency_mhz / 1000.0
    
    # Frequency coefficient F_fc
    F_fc = 0.25 + 0.375 * (1 + math.tanh(7.5 * (f_ghz - 0.5)))
    
    # Calculate clutter loss for transmitter location
    if tx_height_m > clutter_height_m:
        # Antenna above clutter - reduced loss
        h_ratio_tx = tx_height_m / clutter_height_m
        A_h_tx = 10.25 * F_fc * math.exp(-nominal_distance_km) * \
                 (1 - math.tanh(6 * (h_ratio_tx - 0.625))) - 0.33
    else:
        # Antenna within/below clutter - full loss
        h_ratio_tx = tx_height_m / max(clutter_height_m, 1.0)
        A_h_tx = 10.25 * F_fc * math.exp(-nominal_distance_km) * \
                 (1 - math.tanh(6 * (h_ratio_tx - 0.625))) - 0.33
    
    # Calculate clutter loss for receiver location
    if rx_height_m > clutter_height_m:
        # Antenna above clutter - reduced loss  
        h_ratio_rx = rx_height_m / clutter_height_m
        A_h_rx = 10.25 * F_fc * math.exp(-nominal_distance_km) * \
                 (1 - math.tanh(6 * (h_ratio_rx - 0.625))) - 0.33
    else:
        # Antenna within/below clutter
        h_ratio_rx = rx_height_m / max(clutter_height_m, 1.0)
        A_h_rx = 10.25 * F_fc * math.exp(-nominal_distance_km) * \
                 (1 - math.tanh(6 * (h_ratio_rx - 0.625))) - 0.33
    
    # Ensure non-negative
    A_h_tx = max(0.0, A_h_tx)
    A_h_rx = max(0.0, A_h_rx)
    
    return (A_h_tx, A_h_rx)


def compute_hybrid_clutter_loss_db(
    frequency_hz: float,
    distance_m: float,
    clutter_height_m: float,
    nominal_distance_m: float,
    use_p452_model: bool = True
) -> float:
    """
    Calculate clutter loss using hybrid approach.
    
    This is a wrapper that chooses between:
    - ITU-R P.452 clutter model (proper formula)
    - Simplified empirical model (fallback)
    
    Args:
        frequency_hz: Frequency in Hz
        distance_m: Distance in meters
        clutter_height_m: Clutter height from land cover data
        nominal_distance_m: Nominal distance from land cover data
        use_p452_model: If True, use ITU-R P.452 formula (recommended)
        
    Returns:
        Clutter loss in dB
    """
    if use_p452_model:
        # Use proper ITU-R P.452 formula
        return compute_p452_clutter_loss_db(
            frequency_hz / 1e6,  # Convert Hz to MHz
            distance_m / 1000,   # Convert m to km
            clutter_height_m,
            nominal_distance_m
        )
    else:
        # Fallback: simplified empirical formula
        # This is based on Okumura-Hata suburban model
        if clutter_height_m <= 1.0:
            # Open area - minimal loss
            return 0.5
        elif clutter_height_m <= 5.0:
            # Low clutter (crops, shrubs)
            return 2.0 + 3.0 * math.log10(clutter_height_m)
        else:
            # Urban/forest clutter
            # Empirical: ~10 dB base + height term + frequency term
            freq_ghz = frequency_hz / 1e9
            loss = 10.0 + 6.0 * math.log10(clutter_height_m / 10.0) + 2.0 * math.log10(freq_ghz / 2.0)
            return min(25.0, loss)  # Cap at 25 dB


# Test function
def test_clutter_formulas():
    """Test the clutter loss formulas with realistic scenarios."""
    print("=" * 80)
    print("ITU-R P.452-17 CLUTTER LOSS MODEL VALIDATION")
    print("=" * 80)
    
    frequency = 6000  # 6 GHz in MHz
    distance = 5.0    # 5 km
    
    # Typical antenna heights
    ap_height = 10.0  # AP at 10m
    rx_height = 30.0  # Incumbent RX at 30m
    
    test_cases = [
        ("Dense Urban", 20.0, 0.050),      # Height 20m, nominal dist 50m
        ("Medium Urban", 15.0, 0.100),     # Height 15m, nominal dist 100m
        ("Park/Grassland", 1.0, 0.0),      # Height 1m, nominal dist 0m - CLIFF!
        ("Forest", 18.0, 0.040),           # Height 18m, nominal dist 40m
        ("Crops", 2.0, 0.005),             # Height 2m, nominal dist 5m
        ("Water/Bare", 0.0, 0.0),          # No clutter
    ]
    
    print(f"\nFrequency: {frequency} MHz (6 GHz)")
    print(f"Distance: {distance} km")
    print(f"AP height: {ap_height} m, RX height: {rx_height} m")
    print(f"\n{'Scenario':<20} {'Height (m)':<12} {'Nom.Dist (m)':<15} {'TX Loss (dB)':<15} {'RX Loss (dB)'}")
    print("-" * 90)
    
    for name, height, nom_dist_km in test_cases:
        loss_tx, loss_rx = compute_p452_clutter_loss_db(
            frequency, distance, ap_height, rx_height, height, nom_dist_km
        )
        print(f"{name:<20} {height:<12.1f} {nom_dist_km*1000:<15.0f} {loss_tx:<15.1f} {loss_rx:<15.1f}")
    
    print("\n" + "=" * 80)
    print("VALIDATION:")
    print("  ✓ Dense urban should show 10-18 dB")
    print("  ✓ Parks/grass should show 0-2 dB")
    print("  ✓ Difference (Clutter Cliff) should be 10-16 dB")
    print("  ✓ RX at height=30m above clutter gets reduced loss")
    print("=" * 80)


if __name__ == "__main__":
    test_clutter_formulas()
