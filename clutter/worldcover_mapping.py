"""
ESA WorldCover land cover classification mapping to ITU-R P.452 clutter parameters.

This replaces the Corine 44-class system with WorldCover's simpler 11-class system.

WorldCover is global coverage at 10m resolution - much better for Turkey than Corine!

Reference: https://esa-worldcover.org/
"""

from typing import NamedTuple


class ClutterParams(NamedTuple):
    """
    ITU-R P.452 clutter parameters for a land cover type.
    
    Attributes:
        code: WorldCover code (10-100)
        name: Human-readable name
        height_m: Nominal clutter height in meters
        nominal_distance_m: Nominal distance parameter for P.452 (0 for open areas)
        is_cliff_risk: True if this is a low-clutter zone within urban areas (Clutter Cliff risk)
    """
    code: int
    name: str
    height_m: float
    nominal_distance_m: float
    is_cliff_risk: bool = False


# ESA WorldCover 11-class system mapped to ITU-R P.452 parameters
# Updated to use ITU-R P.452-17 recommended nominal distances
WORLDCOVER_TO_CLUTTER = {
    10: ClutterParams(10, "Tree cover (Forest)", 18.0, 40.0, False),
    20: ClutterParams(20, "Shrubland", 4.0, 20.0, False),
    30: ClutterParams(30, "Grassland", 1.0, 0.0, True),  # Can be Clutter Cliff if near urban!
    40: ClutterParams(40, "Cropland", 2.0, 5.0, False),
    50: ClutterParams(50, "Built-up (Urban)", 20.0, 20.0, False),  # ITU-R P.452-17: h=20m, d=20m
    60: ClutterParams(60, "Bare / sparse vegetation", 0.5, 0.0, False),
    70: ClutterParams(70, "Snow and ice", 0.0, 0.0, False),
    80: ClutterParams(80, "Permanent water bodies", 0.0, 0.0, False),
    90: ClutterParams(90, "Herbaceous wetland", 1.5, 5.0, False),
    95: ClutterParams(95, "Mangroves", 8.0, 30.0, False),
    100: ClutterParams(100, "Moss and lichen", 0.3, 0.0, False),
}


def get_clutter_params(worldcover_code: int) -> ClutterParams:
    """
    Get ITU-R P.452 clutter parameters for a WorldCover code.
    
    Args:
        worldcover_code: ESA WorldCover code (10-100)
        
    Returns:
        ClutterParams object with height, nominal distance, etc.
        Returns default "open area" parameters for unknown codes.
        
    Example:
        >>> params = get_clutter_params(50)  # Built-up
        >>> print(f"Height: {params.height_m}m, Distance: {params.nominal_distance_m}m")
    """
    if worldcover_code in WORLDCOVER_TO_CLUTTER:
        return WORLDCOVER_TO_CLUTTER[worldcover_code]
    else:
        # Default to open area for unknown codes
        return ClutterParams(worldcover_code, f"Unknown (code {worldcover_code})", 0.0, 0.0, False)


def is_clutter_cliff_risk(worldcover_code: int, context_codes: list = None) -> bool:
    """
    Check if a WorldCover code represents a "Clutter Cliff" risk scenario.
    
    Clutter Cliff occurs when a location has low clutter (e.g., grassland, park)
    but is surrounded by urban areas. Statistical models may assume high urban 
    clutter (~20 dB), but actual clutter is low (~1 dB), leading to large errors.
    
    Args:
        worldcover_code: WorldCover code
        context_codes: Optional list of nearby codes to check for urban context
        
    Returns:
        True if this is a cliff risk location
        
    Example:
        >>> is_clutter_cliff_risk(30)  # Grassland - potential risk
        True
        >>> is_clutter_cliff_risk(50)  # Built-up - not a risk
        False
    """
    params = get_clutter_params(worldcover_code)
    
    # Grassland (30) is inherently a cliff risk if in urban context
    if worldcover_code == 30:
        # If we have context and it's mostly urban, definite cliff risk
        if context_codes:
            urban_nearby = sum(1 for c in context_codes if c == 50) / len(context_codes)
            if urban_nearby > 0.3:  # More than 30% urban nearby
                return True
        # Even without context, grassland is a potential risk
        return True
    
    return params.is_cliff_risk


def get_worldcover_name(code: int) -> str:
    """
    Get human-readable name for a WorldCover code.
    
    Args:
        code: WorldCover code
        
    Returns:
        Descriptive name string
    """
    params = get_clutter_params(code)
    return params.name


def summarize_worldcover_mapping():
    """
    Print a summary of the WorldCover clutter mapping for documentation.
    """
    print("ESA WorldCover to ITU-R P.452 Clutter Mapping")
    print("=" * 80)
    print(f"{'Code':<6} {'Name':<35} {'Height':<8} {'Dist':<8} {'Cliff?'}")
    print("-" * 80)
    
    for code in sorted(WORLDCOVER_TO_CLUTTER.keys()):
        params = WORLDCOVER_TO_CLUTTER[code]
        cliff_flag = "⚠️ YES" if params.is_cliff_risk else ""
        print(f"{code:<6} {params.name:<35} {params.height_m:<8.1f} {params.nominal_distance_m:<8.0f} {cliff_flag}")
    
    print("=" * 80)
    print(f"\nTotal classes: {len(WORLDCOVER_TO_CLUTTER)} (much simpler than Corine's 44!)")
    print("\nClutter Cliff Risk:")
    print("  - Code 30 (Grassland) can be a cliff risk when in urban context")
    print("  - Parks, sports fields, open urban spaces show as grassland")
    print("  - Same 18 dB error risk as Corine system!")


if __name__ == "__main__":
    # Print the mapping table when run as a script
    summarize_worldcover_mapping()
