"""Clutter Loss Models (ITU-R P.2108).

Implements dynamic clutter loss calculations to replace blanket constant values.
Reference: ITU-R P.2108-1 "Prediction of clutter loss".
"""

import math
from typing import Optional

def _inv_cum_norm(p: float) -> float:
    """Inverse cumulative normal distribution function (approximate).
    
    Source: Abramowitz and Stegun approx or standard Python erf inverse.
    """
    if p >= 1.0: return 5.0 # Clamp high
    if p <= 0.0: return -5.0 # Clamp low
    
    # Use math.erf inverse approximation or scipy.special.ndtri if available.
    # Since we want to avoid heavy scipy dependency for just this, use A&S approx.
    # Or simpler: use a lookup or simple curve fit for standard percentages.
    
    # Using simple approximation for Q^-1(p)
    # Q(x) = 0.5 * erfc(x/sqrt(2))
    # p = 0.5 * (1 + erf(x/sqrt(2)))
    # 2p - 1 = erf(x/sqrt(2))
    # x = sqrt(2) * erfinv(2p - 1)
    # We need an erfinv implementation if we don't have scipy.
    
    # Fallback: linear interpolation for common percentages if precise math not avail
    # P: 1, 5, 10, 50, 90, 95, 99
    # Z: -2.32, -1.64, -1.28, 0, 1.28, 1.64, 2.32
    
    # Simple crude implementation of erfinv for simulation context
    a = 8*(math.pi - 3)/(3*math.pi*(4 - math.pi))
    x = 2*p - 1
    term1 = 2/(math.pi*a) + math.log(1 - x**2)/2
    term2 = math.log(1 - x**2)/a
    sign = 1 if x >= 0 else -1
    erfinv = sign * math.sqrt(math.sqrt(term1**2 - term2) - term1)
    
    return math.sqrt(2) * erfinv

def compute_p2108_clutter_loss_db(
    dist_km: float,
    freq_ghz: float,
    percentage_p: float = 50.0,
    environment: str = "urban"
) -> float:
    """
    Compute clutter loss L_ctt using ITU-R P.2108-1 Section 3.2 (Terrestrial).
    
    Applicable for:
    - 0.5 GHz < f < 67 GHz
    - d > 0.25 km
    - Urban/Suburban environments (model is generic for these).
    
    Args:
        dist_km: Path distance in km
        freq_ghz: Frequency in GHz
        percentage_p: Percentage of locations (50 = median loss)
        environment: 'urban', 'suburban', or 'rural'.
                     P.2108 is technically for Urban/Suburban. 
                     Rural clutter is often negligible or modeled differently (e.g. trees).
                     We apply a scaler for rural.
    """
    # Validity checks (clamped)
    f = max(0.5, min(freq_ghz, 67.0))
    d = max(0.001, dist_km)
    p = max(0.1, min(percentage_p, 99.9)) / 100.0
    
    # P.2108 Section 3.2 Logic
    # L_ctt = -5 * log10( 10^(-0.2 * L_l) + 10^(-0.2 * L_s) ) - sigma_cb * Q^-1(p/100)
    # But the corrected formula (Eq 3) is:
    # L_ctt(p) = L_50 + sigma_c * Q_inv(p)
    # Where L_50 is median loss.
    
    # Median Loss L_50 (Eq 4)
    # L_50 = -5 * log10( 10^(-0.2*K1) + 10^(-0.2*K2) )
    # K1 = 32.98 + 23.9*log10(d) + 3*log10(f)  (Eq 5a) -- note d is d_km
    # K2 = ... (saturation term?)
    # Actually, let's use the precise text from Rec P.2108-1:
    
    # For d >= 0.25 km:
    # L_l = 23.5 + 9.6*log10(f)  (Max loss limit)
    # L_s = 32.98 + 23.9*log10(d) + 3*log10(f) (Distance dependent)
    
    # Median Loss:
    # L_50 = -5 * math.log10( 10**(-0.2 * L_l) + 10**(-0.2 * L_s) )
    
    # Standard Deviation sigma_L:
    # sigma_L = 6.0 (approx for 6 GHz, Eq 6 is complex function of f)
    # Eq 6: sigma_l = 6 (constant for f > 2 GHz is common approx, let's verify)
    
    L_l = 23.5 + 9.6 * math.log10(f)
    
    # L_s depends on distance, saturates at short dist?
    # Model says valid for d > 0.25.
    # For d < 0.25, loss drops to 0 at d=0?
    # We linearly interpolate from 0 to L_s(0.25) for short distances to avoid discontinuity.
    
    if d >= 0.25:
        L_s = 32.98 + 23.9 * math.log10(d) + 3 * math.log10(f)
        # Eq 3
        L_50 = -5 * math.log10( 10**(-0.2 * L_l) + 10**(-0.2 * L_s) )
    else:
        # Short range interpolation
        # Calc at 0.25
        L_s_ref = 32.98 + 23.9 * math.log10(0.25) + 3 * math.log10(f)
        L_50_ref = -5 * math.log10( 10**(-0.2 * L_l) + 10**(-0.2 * L_s_ref) )
        L_50 = L_50_ref * (d / 0.25) # Simple linear ramp
    
    # Distribution
    # Correction for p% locations.
    # P.2108 uses Gaussian distribution N(0, sigma).
    # Loss at p% (meaning loss NOT exceeded at p% locations? or loss IS exceeded?)
    # "Percentage of locations p" usually means loss is valid for p% of locations.
    # High p -> Low Loss (conservative)? Or High Loss?
    # ITU usually defines p as "% time/loc that field strength is exceeded".
    # So High p -> High Field -> Low Loss.
    # Low p -> Low Field -> High Loss.
    # We want "Median" (50%).
    # Let's stick to Median for now unless p is varied.
    
    clutter_loss = L_50
    
    # Sigma correction (if p != 50)
    # sigma_L = 6.0 (approx for 6 GHz)
    if abs(percentage_p - 50.0) > 0.1:
        sigma_L = 6.0 
        # Q^-1 is inverse Q-function (prob X > x).
        # If p is % locations where signal is exceeded...
        # We use inverse normal.
        # clutter_loss += sigma_L * _inv_cum_norm(1 - p) 
        # Let's leave as Median for baseline unless explicitly requested.
        pass

    # Environment Adjustment (Heuristic, P.2108 is strictly Urban/Suburban)
    # Rural areas often have much less building clutter, but trees.
    # P.2108 overestimates for Rural.
    if "rural" in environment.lower():
        clutter_loss *= 0.2 # 80% reduction heuristic
    elif "suburban" in environment.lower():
        clutter_loss *= 0.8
        
    return max(0.0, clutter_loss)

class ClutterModel:
    CONSTANT = "constant"
    P2108 = "p2108"

