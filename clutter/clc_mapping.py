"""
Mapping of Corine Land Cover codes to ITU-R P.452 clutter parameters.

This module implements the "Hybrid Clutter" approach from the dissertation,
mapping the 44 Corine Land Cover classes to specific clutter heights and
nominal distances for use in ITU-R P.452 propagation calculations.

The mapping is based on Table 2 from the Ph.D. Dissertation Defense Steps document.
"""

from typing import Dict, NamedTuple


class ClutterParams(NamedTuple):
    """
    ITU-R P.452 clutter parameters for a land cover type.
    
    Attributes:
        clc_code: Corine Land Cover code (1-44)
        name: Human-readable name
        height_m: Nominal clutter height in meters
        nominal_distance_m: Nominal distance parameter for P.452 (0 for open areas)
        is_cliff_risk: True if this is a low-clutter zone within urban areas (Clutter Cliff risk)
    """
    clc_code: int
    name: str
    height_m: float
    nominal_distance_m: float
    is_cliff_risk: bool = False


# Complete mapping of all 44 Corine Land Cover codes to clutter parameters
# Based on dissertation Table 2 and ITU-R P.452 clutter model
CLC_TO_CLUTTER: Dict[int, ClutterParams] = {
    # Urban fabric (codes 111-112)
    111: ClutterParams(111, "Continuous urban fabric (Dense)", 20.0, 50.0, False),
    112: ClutterParams(112, "Discontinuous urban fabric (Medium)", 15.0, 100.0, False),
    
    # Industrial, commercial and transport units (codes 121-124)
    121: ClutterParams(121, "Industrial or commercial units", 12.0, 80.0, False),
    122: ClutterParams(122, "Road and rail networks", 3.0, 20.0, False),
    123: ClutterParams(123, "Port areas", 8.0, 50.0, False),
    124: ClutterParams(124, "Airports", 2.0, 10.0, True),  # Airports are open - cliff risk!
    
    # Mine, dump and construction sites (codes 131-133)
    131: ClutterParams(131, "Mineral extraction sites", 5.0, 30.0, False),
    132: ClutterParams(132, "Dump sites", 6.0, 40.0, False),
    133: ClutterParams(133, "Construction sites", 8.0, 50.0, False),
    
    # Artificial, non-agricultural vegetated areas (codes 141-142)
    141: ClutterParams(141, "Green urban areas (Parks)", 2.0, 0.0, True),  # CRITICAL: Clutter Cliff!
    142: ClutterParams(142, "Sport and leisure facilities", 1.0, 0.0, True),  # CRITICAL: Clutter Cliff!
    
    # Arable land (codes 211-213)
    211: ClutterParams(211, "Non-irrigated arable land", 1.5, 0.0, False),
    212: ClutterParams(212, "Permanently irrigated land", 2.0, 0.0, False),
    213: ClutterParams(213, "Rice fields", 1.0, 0.0, False),
    
    # Permanent crops (codes 221-223)
    221: ClutterParams(221, "Vineyards", 2.5, 10.0, False),
    222: ClutterParams(222, "Fruit trees and berry plantations", 4.0, 15.0, False),
    223: ClutterParams(223, "Olive groves", 5.0, 20.0, False),
    
    # Pastures (code 231)
    231: ClutterParams(231, "Pastures", 0.5, 0.0, False),
    
    # Heterogeneous agricultural areas (codes 241-244)
    241: ClutterParams(241, "Annual crops with permanent crops", 3.0, 10.0, False),
    242: ClutterParams(242, "Complex cultivation patterns", 3.5, 15.0, False),
    243: ClutterParams(243, "Agriculture with natural vegetation", 4.0, 20.0, False),
    244: ClutterParams(244, "Agro-forestry areas", 8.0, 30.0, False),
    
    # Forests (codes 311-313)
    311: ClutterParams(311, "Broad-leaved forest", 18.0, 40.0, False),
    312: ClutterParams(312, "Coniferous forest", 20.0, 45.0, False),
    313: ClutterParams(313, "Mixed forest", 19.0, 42.0, False),
    
    # Scrub and/or herbaceous vegetation (codes 321-324)
    321: ClutterParams(321, "Natural grasslands", 0.8, 0.0, False),
    322: ClutterParams(322, "Moors and heathland", 2.0, 5.0, False),
    323: ClutterParams(323, "Sclerophyllous vegetation", 3.0, 10.0, False),
    324: ClutterParams(324, "Transitional woodland-shrub", 6.0, 25.0, False),
    
    # Open spaces with little or no vegetation (codes 331-335)
    331: ClutterParams(331, "Beaches, dunes, sands", 0.0, 0.0, False),
    332: ClutterParams(332, "Bare rocks", 0.0, 0.0, False),
    333: ClutterParams(333, "Sparsely vegetated areas", 0.5, 0.0, False),
    334: ClutterParams(334, "Burnt areas", 0.2, 0.0, False),
    335: ClutterParams(335, "Glaciers and perpetual snow", 0.0, 0.0, False),
    
    # Wetlands (codes 411-423)
    411: ClutterParams(411, "Inland marshes", 1.5, 5.0, False),
    412: ClutterParams(412, "Peat bogs", 1.0, 0.0, False),
    421: ClutterParams(421, "Salt marshes", 1.2, 5.0, False),
    422: ClutterParams(422, "Salines", 0.5, 0.0, False),
    423: ClutterParams(423, "Intertidal flats", 0.0, 0.0, False),
    
    # Water bodies (codes 511-523)
    511: ClutterParams(511, "Water courses", 0.0, 0.0, False),
    512: ClutterParams(512, "Water bodies", 0.0, 0.0, False),
    521: ClutterParams(521, "Coastal lagoons", 0.0, 0.0, False),
    522: ClutterParams(522, "Estuaries", 0.0, 0.0, False),
    523: ClutterParams(523, "Sea and ocean", 0.0, 0.0, False),
}


def get_clutter_params(clc_code: int) -> ClutterParams:
    """
    Get ITU-R P.452 clutter parameters for a Corine Land Cover code.
    
    Args:
        clc_code: Corine Land Cover code (1-44)
        
    Returns:
        ClutterParams object with height, nominal distance, etc.
        Returns default "open area" parameters for unknown codes.
        
    Example:
        >>> params = get_clutter_params(111)  # Continuous urban fabric
        >>> print(f"Height: {params.height_m}m, Distance: {params.nominal_distance_m}m")
    """
    if clc_code in CLC_TO_CLUTTER:
        return CLC_TO_CLUTTER[clc_code]
    else:
        # Default to open area for unknown codes
        return ClutterParams(clc_code, f"Unknown (code {clc_code})", 0.0, 0.0, False)


def is_clutter_cliff_risk(clc_code: int) -> bool:
    """
    Check if a Corine Land Cover code represents a "Clutter Cliff" risk scenario.
    
    Clutter Cliff occurs when a location is classified as urban but actually
    has low clutter (e.g., urban parks, sports facilities, airports).
    Statistical models may assume high urban clutter (~20 dB), but the actual
    clutter is low (~2 dB), leading to large errors in interference prediction.
    
    Args:
        clc_code: Corine Land Cover code
        
    Returns:
        True if this is a cliff risk location
        
    Example:
        >>> is_clutter_cliff_risk(141)  # Green urban areas (parks)
        True
        >>> is_clutter_cliff_risk(111)  # Dense urban
        False
    """
    params = get_clutter_params(clc_code)
    return params.is_cliff_risk


def get_clc_name(clc_code: int) -> str:
    """
    Get human-readable name for a Corine Land Cover code.
    
    Args:
        clc_code: Corine Land Cover code
        
    Returns:
        Descriptive name string
    """
    params = get_clutter_params(clc_code)
    return params.name


def summarize_clutter_mapping():
    """
    Print a summary of the clutter mapping for documentation.
    
    Useful for generating tables for the dissertation.
    """
    print("Corine Land Cover to ITU-R P.452 Clutter Mapping")
    print("=" * 80)
    print(f"{'Code':<6} {'Name':<40} {'Height':<8} {'Dist':<8} {'Cliff?'}")
    print("-" * 80)
    
    for code in sorted(CLC_TO_CLUTTER.keys()):
        params = CLC_TO_CLUTTER[code]
        cliff_flag = "⚠️ YES" if params.is_cliff_risk else ""
        print(f"{code:<6} {params.name:<40} {params.height_m:<8.1f} {params.nominal_distance_m:<8.0f} {cliff_flag}")
    
    print("=" * 80)
    print(f"\nTotal codes mapped: {len(CLC_TO_CLUTTER)}")
    cliff_codes = [c for c in CLC_TO_CLUTTER.keys() if is_clutter_cliff_risk(c)]
    print(f"Clutter Cliff risk codes: {cliff_codes}")


if __name__ == "__main__":
    # Print the mapping table when run as a script
    summarize_clutter_mapping()
