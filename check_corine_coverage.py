"""
Quick diagnostic script to check if Corine Land Cover data covers Turkey.
"""

import rasterio

clc_file = r"data\clutter\u2018_clc2018_v2020_20u1_raster100m\DATA\U2018_CLC2018_V2020_20u1.tif"

print("=" * 70)
print("CORINE LAND COVER DATA DIAGNOSTIC")
print("=" * 70)

try:
    with rasterio.open(clc_file) as src:
        print(f"\n✓ File opened successfully")
        print(f"\nFile Information:")
        print(f"  Size: {src.width} x {src.height} pixels")
        print(f"  CRS: {src.crs}")
        print(f"  Bounds:")
        print(f"    Left (West):   {src.bounds.left:.2f}°")
        print(f"    Right (East):  {src.bounds.right:.2f}°")
        print(f"    Bottom (South): {src.bounds.bottom:.2f}°")
        print(f"    Top (North):    {src.bounds.top:.2f}°")
        
        # Istanbul coordinates
        istanbul_lat = 41.0370
        istanbul_lon = 28.9854
        
        print(f"\n📍 Istanbul Location:")
        print(f"  Latitude:  {istanbul_lat}°N")
        print(f"  Longitude: {istanbul_lon}°E")
        
        # Check if Istanbul is within bounds
        within_bounds = (src.bounds.left <= istanbul_lon <= src.bounds.right and
                        src.bounds.bottom <= istanbul_lat <= src.bounds.top)
        
        print(f"\n🔍 Coverage Check:")
        if within_bounds:
            print(f"  ✅ Istanbul IS within Corine data bounds!")
            
            # Try to read actual value
            from rasterio.transform import rowcol
            row, col = rowcol(src.transform, istanbul_lon, istanbul_lat)
            
            if 0 <= row < src.height and 0 <= col < src.width:
                data = src.read(1)
                value = data[row, col]
                print(f"  Sample value at Istanbul: {value}")
                
                # Check for unique values in a small region
                sample_data = data[max(0, row-100):min(src.height, row+100), 
                                  max(0, col-100):min(src.width, col+100)]
                unique_values = set(sample_data.flatten())
                print(f"  Unique values in Istanbul region: {len(unique_values)}")
                print(f"  Sample values: {list(unique_values)[:10]}")
                
                if len(unique_values) <= 2:
                    print(f"\n  ⚠️ WARNING: Very few unique values detected!")
                    print(f"  This suggests the data may be empty or no-data for Turkey.")
            else:
                print(f"  ❌ Pixel coordinates out of range!")
        else:
            print(f"  ❌ Istanbul is NOT within Corine data bounds!")
            print(f"\n  The Corine 2018 dataset you downloaded may be:")
            print(f"  - Only for Western/Central Europe (EU countries)")
            print(f"  - Not including Turkey")
            
        # Check if it's actually European coverage only
        print(f"\n🌍 Geographic Coverage Analysis:")
        if src.bounds.right < 30:  # Istanbul is at ~29°E
            print(f"  This appears to be Western/Central Europe only")
            print(f"  Eastern boundary: {src.bounds.right:.2f}°E")
            print(f"  Turkey starts at ~26°E and extends to ~45°E")
            print(f"\n  ❌ PROBLEM IDENTIFIED: Dataset does NOT include Turkey!")
        
except FileNotFoundError:
    print(f"❌ File not found: {clc_file}")
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 70)
input("Press Enter to exit...")
