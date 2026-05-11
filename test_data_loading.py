"""
Test script to verify that the downloaded terrain and clutter data can be read.

This is a simple test to make sure the data files are valid before we build
the full integration modules.
"""

def test_terrain_data():
    """Test reading the SRTM terrain data."""
    print("=" * 60)
    print("Testing Terrain Data (SRTM)")
    print("=" * 60)
    
    try:
        import rasterio
        print("✓ rasterio library is installed")
    except ImportError:
        print("✗ rasterio library is NOT installed")
        print("  → Need to install: pip install rasterio")
        return False
    
    terrain_file = r"data\terrain\n41_e028_1arc_v3.tif"
    
    try:
        with rasterio.open(terrain_file) as src:
            print(f"✓ Successfully opened: {terrain_file}")
            print(f"  - Size: {src.width} x {src.height} pixels")
            print(f"  - Coordinate system: {src.crs}")
            print(f"  - Bounds: {src.bounds}")
            
            # Read a small sample
            data = src.read(1, window=((0, 100), (0, 100)))
            print(f"  - Sample elevation range: {data.min():.1f}m to {data.max():.1f}m")
            print("✓ Terrain data is valid!")
            return True
            
    except FileNotFoundError:
        print(f"✗ File not found: {terrain_file}")
        print("  → Check that the file exists in the data/terrain/ folder")
        return False
    except Exception as e:
        print(f"✗ Error reading file: {e}")
        return False


def test_clutter_data():
    """Test reading the Corine Land Cover clutter data."""
    print("\n" + "=" * 60)
    print("Testing Clutter Data (Corine Land Cover)")
    print("=" * 60)
    
    try:
        import rasterio
        print("✓ rasterio library is installed")
    except ImportError:
        print("✗ rasterio library is NOT installed")
        print("  → Need to install: pip install rasterio")
        return False
    
    clutter_file = r"data\clutter\u2018_clc2018_v2020_20u1_raster100m\DATA\U2018_CLC2018_V2020_20u1.tif"
    
    try:
        with rasterio.open(clutter_file) as src:
            print(f"✓ Successfully opened clutter data")
            print(f"  - Size: {src.width} x {src.height} pixels")
            print(f"  - Coordinate system: {src.crs}")
            print(f"  - Bounds: {src.bounds}")
            
            # Read a small sample
            data = src.read(1, window=((0, 100), (0, 100)))
            unique_codes = list(set(data.flatten()))[:10]  # First 10 unique codes
            print(f"  - Sample land cover codes: {unique_codes}")
            print("✓ Clutter data is valid!")
            return True
            
    except FileNotFoundError:
        print(f"✗ File not found: {clutter_file}")
        print("  → Check that the file exists in the clutter folder")
        return False
    except Exception as e:
        print(f"✗ Error reading file: {e}")
        return False


def test_specific_location():
    """Test querying elevation at a specific location (Istanbul)."""
    print("\n" + "=" * 60)
    print("Testing Location Query (Istanbul coordinates)")
    print("=" * 60)
    
    try:
        import rasterio
        from rasterio.transform import rowcol
    except ImportError:
        print("✗ rasterio not installed, skipping this test")
        return False
    
    terrain_file = r"data\terrain\n41_e028_1arc_v3.tif"
    
    # Istanbul coordinates (Taksim Square approximately)
    istanbul_lat = 41.0370
    istanbul_lon = 28.9854
    
    try:
        with rasterio.open(terrain_file) as src:
            # Convert lat/lon to pixel coordinates
            row, col = rowcol(src.transform, istanbul_lon, istanbul_lat)
            
            # Read the elevation value
            elevation = src.read(1)[row, col]
            
            print(f"✓ Query successful for Istanbul (lat={istanbul_lat}, lon={istanbul_lon})")
            print(f"  - Elevation: {elevation:.1f} meters")
            print("✓ Location query works!")
            return True
            
    except Exception as e:
        print(f"✗ Error querying location: {e}")
        return False


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("AFC Data Loading Test")
    print("=" * 60)
    print("\nThis script tests whether we can read the downloaded data files.")
    print("You need to install 'rasterio' first if you haven't already.\n")
    
    # Run tests
    terrain_ok = test_terrain_data()
    clutter_ok = test_clutter_data()
    location_ok = test_specific_location()
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Terrain data: {'✓ PASS' if terrain_ok else '✗ FAIL'}")
    print(f"Clutter data: {'✓ PASS' if clutter_ok else '✗ FAIL'}")
    print(f"Location query: {'✓ PASS' if location_ok else '✗ FAIL'}")
    
    if terrain_ok and clutter_ok:
        print("\n🎉 All tests passed! Your data is ready to use!")
    else:
        print("\n⚠️ Some tests failed. We may need to install libraries or check file paths.")
    
    print("\n" + "=" * 60)
    input("\nPress Enter to exit...")
