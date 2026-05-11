"""
Script to find which WorldCover tiles we have and check if Turkey is covered.
"""

import os
from pathlib import Path

clutter_dir = r"data\clutter"

print("=" * 70)
print("WORLDCOVER TILE INVENTORY")
print("=" * 70)

# Find all TIF files
tif_files = []
for root, dirs, files in os.walk(clutter_dir):
    for file in files:
        if file.endswith('_Map.tif'):
            full_path = os.path.join(root, file)
            tif_files.append((file, full_path))

print(f"\nFound {len(tif_files)} WorldCover tiles")
print("\n" + "-" * 70)

# Parse tile coordinates
tiles = []
for filename, path in tif_files:
    # Extract coordinates from filename like "ESA_WorldCover_10m_2021_V200_N42E000_Map.tif"
    parts = filename.split('_')
    for part in parts:
        if part.startswith('N') and 'E' in part:
            # Parse N42E000 format
            try:
                lat_str = part.split('E')[0]
                lon_str = part.split('E')[1]
                
                lat = int(lat_str[1:])  # Remove 'N'
                lon = int(lon_str)
                
                tiles.append({
                    'filename': filename,
                    'path': path,
                    'lat': lat,
                    'lon': lon,
                    'coords': part
                })
                print(f"Tile: {part:<12} (Lat={lat}°N, Lon={lon}°E)")
            except:
                pass

print("\n" + "=" * 70)
print("CHECKING ISTANBUL COVERAGE")
print("=" * 70)

# Istanbul coordinates
istanbul_lat = 41
istanbul_lon = 29

print(f"\nIstanbul location: ~41°N, ~29°E")
print(f"Need tiles covering: 39-42°N and 27-30°E")

# Find tiles that cover Istanbul
istanbul_tiles = []
for tile in tiles:
    # WorldCover tiles are 3° x 3° 
    # Tile N39E027 covers 39-42°N, 27-30°E
    lat_match = tile['lat'] <= istanbul_lat < tile['lat'] + 3
    lon_match = tile['lon'] <= istanbul_lon < tile['lon'] + 3
    
    if lat_match and lon_match:
        istanbul_tiles.append(tile)
        print(f"\n✅ FOUND: {tile['coords']} covers Istanbul!")
        print(f"   File: {tile['filename']}")
        print(f"   Path: {tile['path']}")

if not istanbul_tiles:
    print("\n❌ NO TILES FOUND covering Istanbul (41°N, 29°E)")
    print("\nTiles needed for Turkey:")
    print("  - N39E027 (covers 39-42°N, 27-30°E) ← Istanbul area")
    print("  - N39E030 (covers 39-42°N, 30-33°E)")
    print("  - N39E033 (covers 39-42°N, 33-36°E)")
    print("\nYou may need to download Turkey-specific tiles!")

print("\n" + "=" * 70)
input("Press Enter to exit...")
