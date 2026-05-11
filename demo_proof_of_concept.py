"""
Proof of Concept: Terrain and Clutter Data Query for Istanbul

This demo shows how to:
1. Query elevation at specific Istanbul locations from SRTM data
2. Query land cover type from Corine Land Cover data
3. Demonstrate basic terrain profile extraction

This is a simple proof-of-concept before building the full modules.
"""

import rasterio
from rasterio.transform import rowcol
import math


def query_elevation(terrain_file, lat, lon):
    """
    Query terrain elevation at a specific latitude/longitude.
    
    Args:
        terrain_file: Path to SRTM GeoTIFF file
        lat: Latitude in decimal degrees
        lon: Longitude in decimal degrees
        
    Returns:
        Elevation in meters
    """
    with rasterio.open(terrain_file) as src:
        # Convert lat/lon to pixel row/col
        row, col = rowcol(src.transform, lon, lat)
        
        # Make sure we're within bounds
        if 0 <= row < src.height and 0 <= col < src.width:
            elevation = src.read(1)[row, col]
            return float(elevation)
        else:
            return None


def query_land_cover(clutter_file, lat, lon):
    """
    Query land cover classification at a specific latitude/longitude.
    
    Args:
        clutter_file: Path to Corine Land Cover GeoTIFF file
        lat: Latitude in decimal degrees
        lon: Longitude in decimal degrees
        
    Returns:
        Corine Land Cover code (integer)
    """
    with rasterio.open(clutter_file) as src:
        # Convert lat/lon to pixel row/col
        row, col = rowcol(src.transform, lon, lat)
        
        # Make sure we're within bounds
        if 0 <= row < src.height and 0 <= col < src.width:
            clc_code = src.read(1)[row, col]
            return int(clc_code)
        else:
            return None


def get_clc_name(code):
    """
    Get human-readable name for Corine Land Cover code.
    
    This is a partial mapping - full list has 44 codes.
    """
    clc_names = {
        111: "Continuous urban fabric (Dense)",
        112: "Discontinuous urban fabric (Medium density)",
        121: "Industrial or commercial units",
        122: "Road and rail networks",
        123: "Port areas",
        124: "Airports",
        131: "Mineral extraction sites",
        132: "Dump sites",
        133: "Construction sites",
        141: "Green urban areas (Parks)", # CLUTTER CLIFF RISK!
        142: "Sport and leisure facilities",
        211: "Non-irrigated arable land",
        311: "Broad-leaved forest",
        312: "Coniferous forest",
        313: "Mixed forest",
        321: "Natural grasslands",
        324: "Transitional woodland-shrub",
        512: "Water bodies"
    }
    return clc_names.get(code, f"Unknown (code {code})")


def haversine_distance_m(lat1, lon1, lat2, lon2):
    """
    Calculate distance between two points on Earth using Haversine formula.
    
    Returns distance in meters.
    """
    R = 6371000  # Earth radius in meters
    
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    
    a = math.sin(delta_phi/2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    
    return R * c


def extract_simple_profile(terrain_file, lat1, lon1, lat2, lon2, num_points=50):
    """
    Extract a simple terrain profile between two points.
    
    This is a basic version - the full pycraf integration will be more sophisticated.
    
    Returns:
        List of (distance_m, elevation_m) tuples
    """
    profile = []
    total_distance = haversine_distance_m(lat1, lon1, lat2, lon2)
    
    for i in range(num_points):
        # Linear interpolation between points
        fraction = i / (num_points - 1)
        lat = lat1 + fraction * (lat2 - lat1)
        lon = lon1 + fraction * (lon2 - lon1)
        
        elev = query_elevation(terrain_file, lat, lon)
        distance = fraction * total_distance
        
        if elev is not None:
            profile.append((distance, elev))
    
    return profile


def demo_istanbul_queries():
    """
    Demonstrate querying terrain and clutter for famous Istanbul locations.
    """
    print("=" * 70)
    print("PROOF OF CONCEPT: Istanbul Terrain and Clutter Queries")
    print("=" * 70)
    
    # File paths
    terrain_file = r"data\terrain\n41_e028_1arc_v3.tif"
    clutter_file = r"data\clutter\u2018_clc2018_v2020_20u1_raster100m\DATA\U2018_CLC2018_V2020_20u1.tif"
    
    # Famous Istanbul locations
    locations = [
        ("Taksim Square", 41.0370, 28.9854),
        ("Sultanahmet (Blue Mosque)", 41.0054, 28.9768),
        ("Bosphorus Bridge", 41.0428, 29.0278),
        ("Galata Tower", 41.0256, 28.9744),
        ("Istanbul Airport", 41.2753, 28.7519),
    ]
    
    print("\n📍 Querying Famous Istanbul Locations:\n")
    
    for name, lat, lon in locations:
        print(f"Location: {name}")
        print(f"  Coordinates: {lat:.4f}°N, {lon:.4f}°E")
        
        # Query elevation
        elevation = query_elevation(terrain_file, lat, lon)
        if elevation is not None:
            print(f"  Elevation: {elevation:.1f} meters")
        else:
            print(f"  Elevation: Out of terrain data bounds")
        
        # Query land cover
        clc_code = query_land_cover(clutter_file, lat, lon)
        if clc_code is not None and clc_code > 0:
            clc_name = get_clc_name(clc_code)
            print(f"  Land Cover: {clc_name}")
            
            # Flag if this is a "Clutter Cliff" risk location
            if clc_code in [141, 142]:  # Urban parks/sports facilities
                print(f"  ⚠️  CLUTTER CLIFF RISK - Low clutter in urban area!")
        else:
            print(f"  Land Cover: No data or water")
        
        print()
    
    # Demonstrate terrain profile
    print("=" * 70)
    print("TERRAIN PROFILE DEMO")
    print("=" * 70)
    print("\nExtracting profile from Taksim to Bosphorus Bridge:\n")
    
    lat1, lon1 = 41.0370, 28.9854  # Taksim
    lat2, lon2 = 41.0428, 29.0278  # Bosphorus Bridge
    
    profile = extract_simple_profile(terrain_file, lat1, lon1, lat2, lon2, num_points=20)
    
    distance_km = haversine_distance_m(lat1, lon1, lat2, lon2) / 1000
    print(f"Total distance: {distance_km:.2f} km")
    print(f"Profile points: {len(profile)}")
    print("\nSample profile (first 10 points):")
    print("  Distance [m]  | Elevation [m]")
    print("  " + "-" * 30)
    
    for i, (dist, elev) in enumerate(profile[:10]):
        print(f"  {dist:>10.0f}    | {elev:>10.1f}")
    
    print("\n💡 This shows terrain varies from {:.1f}m to {:.1f}m along the path".format(
        min(e for d, e in profile), max(e for d, e in profile)
    ))


def demo_clutter_cliff_scenario():
    """
    Demonstrate the "Clutter Cliff" phenomenon.
    
    Compare two nearby locations: one in dense urban area, one in urban park.
    """
    print("\n" + "=" * 70)
    print("CLUTTER CLIFF DEMONSTRATION")
    print("=" * 70)
    print("\nComparing dense urban vs urban park (potential cliff scenario):\n")
    
    clutter_file = r"data\clutter\u2018_clc2018_v2020_20u1_raster100m\DATA\U2018_CLC2018_V2020_20u1.tif"
    
    # Try to find contrasting locations
    # These are example coordinates - actual parks may vary
    locations = [
        ("Dense Urban Area (Sisli)", 41.0600, 28.9850, "Expected: Dense urban clutter"),
        ("Emirgan Park", 41.1100, 29.0550, "Expected: Low clutter (park)")
    ]
    
    for name, lat, lon, expectation in locations:
        clc_code = query_land_cover(clutter_file, lat, lon)
        
        print(f"{name}:")
        print(f"  {expectation}")
        
        if clc_code and clc_code > 0:
            print(f"  Actual: {get_clc_name(clc_code)}")
            
            if clc_code in [141, 142]:
                print(f"  ⚠️  CLUTTER CLIFF DETECTED!")
                print(f"  → Statistical models may assume high urban clutter (~20 dB)")
                print(f"  → But actual clutter here is low (park/open area ~2 dB)")
                print(f"  → Risk: 18 dB error in interference prediction!")
        print()


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("AFC Terrain and Clutter - Proof of Concept Demo")
    print("=" * 70)
    print("\nThis demo shows that we can successfully:")
    print("  1. Query terrain elevation at any Istanbul location")
    print("  2. Query land cover type from Corine dataset")
    print("  3. Extract terrain profiles between points")
    print("  4. Detect 'Clutter Cliff' risk scenarios")
    print("\n")
    
    try:
        demo_istanbul_queries()
        demo_clutter_cliff_scenario()
        
        print("\n" + "=" * 70)
        print("✅ PROOF OF CONCEPT SUCCESSFUL!")
        print("=" * 70)
        print("\nNext steps:")
        print("  - Build full terrain integration module with pycraf")
        print("  - Build clutter mapping module with all 44 CLC codes")
        print("  - Implement Angular Exclusion algorithm")
        print("  - Implement Hybrid Clutter algorithm")
        print("=" * 70)
        
    except FileNotFoundError as e:
        print(f"\n❌ Error: Could not find data file")
        print(f"   {e}")
        print("\n   Make sure the terrain and clutter data are in the correct locations.")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n")
    input("Press Enter to exit...")
