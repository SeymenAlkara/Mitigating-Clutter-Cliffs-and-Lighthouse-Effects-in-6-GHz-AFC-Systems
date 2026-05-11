"""
Test script for terrain and clutter modules.

This tests the newly created terrain and clutter integration modules.
"""

import sys
sys.path.insert(0, '.')  # Add current directory to path

from terrain.dem_loader import query_elevation, get_height_profile, get_dem_info
from terrain.geodesy_utils import haversine_distance_m, azimuth_deg
from clutter.clc_loader import query_land_cover
from clutter.clc_mapping import get_clutter_params, is_clutter_cliff_risk, get_clc_name


def test_terrain_module():
    """Test the terrain module functions."""
    print("=" * 70)
    print("TEST 1: Terrain Module")
    print("=" * 70)
    
    dem_file = r"data\terrain\n41_e028_1arc_v3.tif"
    
    # Test DEM info
    print("\nDEM Information:")
    info = get_dem_info(dem_file)
    print(f"  Bounds: {info['bounds']}")
    print(f"  Size: {info['width']} x {info['height']} pixels")
    print(f"  Resolution: {info['resolution']}")
    
    # Test elevation query
    print("\nElevation Queries:")
    locations = [
        ("Taksim Square", 41.0370, 28.9854),
        ("Bosphorus Bridge", 41.0428, 29.0278),
    ]
    
    for name, lat, lon in locations:
        elev = query_elevation(lat, lon, dem_file)
        print(f"  {name}: {elev:.1f} m")
    
    # Test height profile
    print("\nHeight Profile (Taksim to Bosphorus):")
    lat1, lon1 = 41.0370, 28.9854
    lat2, lon2 = 41.0428, 29.0278
    
    profile = get_height_profile(lat1, lon1, lat2, lon2, dem_file, num_points=10)
    print(f"  Points: {len(profile)}")
    print(f"  Elevation range: {min(p[3] for p in profile):.1f}m to {max(p[3] for p in profile):.1f}m")
    
    print("✓ Terrain module test passed!\n")


def test_geodesy_module():
    """Test geodesy utility functions."""
    print("=" * 70)
    print("TEST 2: Geodesy Module")
    print("=" * 70)
    
    lat1, lon1 = 41.0370, 28.9854  # Taksim
    lat2, lon2 = 41.0428, 29.0278  # Bosphorus Bridge
    
    dist = haversine_distance_m(lat1, lon1, lat2, lon2)
    az = azimuth_deg(lat1, lon1, lat2, lon2)
    
    print(f"\nFrom Taksim to Bosphorus Bridge:")
    print(f"  Distance: {dist/1000:.2f} km")
    print(f"  Azimuth: {az:.1f}° (0° = North, 90° = East)")
    
    print("✓ Geodesy module test passed!\n")


def test_clutter_module():
    """Test the clutter module functions."""
    print("=" * 70)
    print("TEST 3: Clutter Module")
    print("=" * 70)
    
    clc_file = r"data\clutter\u2018_clc2018_v2020_20u1_raster100m\DATA\U2018_CLC2018_V2020_20u1.tif"
    
    print("\nLand Cover Queries:")
    locations = [
        ("Taksim Square", 41.0370, 28.9854),
        ("Bosphorus Bridge", 41.0428, 29.0278),
        ("Emirgan Park (expected: park)", 41.1100, 29.0550),
    ]
    
    for name, lat, lon in locations:
        code = query_land_cover(lat, lon, clc_file)
        if code > 0:
            clc_name = get_clc_name(code)
            params = get_clutter_params(code)
            cliff_risk = is_clutter_cliff_risk(code)
            
            print(f"\n  {name}:")
            print(f"    CLC Code: {code}")
            print(f"    Type: {clc_name}")
            print(f"    Clutter Height: {params.height_m} m")
            print(f"    Nominal Distance: {params.nominal_distance_m} m")
            if cliff_risk:
                print(f"    ⚠️  CLUTTER CLIFF RISK DETECTED!")
        else:
            print(f"\n  {name}: No data")
    
    print("\n✓ Clutter module test passed!\n")


def test_clc_mapping():
    """Test the CLC mapping table."""
    print("=" * 70)
    print("TEST 4: CLC Code Mapping Table")
    print("=" * 70)
    
    print("\nSample CLC Codes and Parameters:")
    sample_codes = [111, 112, 141, 142, 311, 512]
    
    for code in sample_codes:
        params = get_clutter_params(code)
        cliff = "⚠️ CLIFF RISK" if params.is_cliff_risk else ""
        print(f"  {code}: {params.name}")
        print(f"      Height={params.height_m}m, Distance={params.nominal_distance_m}m {cliff}")
    
    print("\n✓ CLC mapping test passed!\n")


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("Testing Terrain and Clutter Integration Modules")
    print("=" * 70)
    print()
    
    try:
        test_terrain_module()
        test_geodesy_module()
        test_clutter_module()
        test_clc_mapping()
        
        print("=" * 70)
        print("🎉 ALL TESTS PASSED!")
        print("=" * 70)
        print("\nThe terrain and clutter modules are working correctly.")
        print("Ready to proceed with:")
        print("  - Angular Exclusion algorithm (Lighthouse Effect mitigation)")
        print("  - Hybrid Clutter algorithm implementation")
        print("  - pycraf integration for P.452 propagation")
        print("=" * 70)
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n")
    input("Press Enter to exit...")
