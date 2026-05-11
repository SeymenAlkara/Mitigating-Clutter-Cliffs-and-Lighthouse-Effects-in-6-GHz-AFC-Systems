"""
Fast WorldCover data reader - uses windowed reading instead of point-by-point queries.

This is MUCH faster than querying individual points!
"""

import rasterio
from rasterio.windows import from_bounds
import numpy as np


def read_worldcover_region(worldcover_file, lat_min, lat_max, lon_min, lon_max, target_size=500):
    """
    Read a region of WorldCover data efficiently.
    
    Instead of querying 160,000 points individually (which takes forever!),
    this reads the entire region at once and resamples.
    
    Args:
        worldcover_file: Path to WorldCover GeoTIFF
        lat_min, lat_max: Latitude bounds
        lon_min, lon_max: Longitude bounds
        target_size: Desired output grid size (default 500x500)
        
    Returns:
        grid: numpy array of WorldCover codes
        lats: latitude array for grid
        lons: longitude array for grid
    """
    print(f"Reading WorldCover region: {lat_min:.2f}-{lat_max:.2f}°N, {lon_min:.2f}-{lon_max:.2f}°E")
    
    with rasterio.open(worldcover_file) as src:
        # Get window for the specified bounds
        window = from_bounds(lon_min, lat_min, lon_max, lat_max, src.transform)
        
        # Read the data within the window
        print(f"  Reading window: {window.width} x {window.height} pixels...")
        data = src.read(1, window=window)
        
        print(f"  Data shape: {data.shape}")
        print(f"  Resampling to {target_size}x{target_size}...")
        
        # Resample to target size using nearest neighbor
        from scipy.ndimage import zoom
        
        zoom_factor_y = target_size / data.shape[0]
        zoom_factor_x = target_size / data.shape[1]
        
        resampled = zoom(data, (zoom_factor_y, zoom_factor_x), order=0)  # order=0 = nearest neighbor
        
        # Create coordinate arrays
        lats = np.linspace(lat_max, lat_min, target_size)  # Note: reversed for image orientation
        lons = np.linspace(lon_min, lon_max, target_size)
        
        print(f"  ✓ Done! Final grid: {resampled.shape}")
        
        return resampled, lats, lons


if __name__ == "__main__":
    # Test the fast reader
    worldcover_file = r"data\clutter\ESA_WorldCover_10m_2021_V200_N39E027_Map.tif"
    
    # Istanbul region
    lat_min, lat_max = 40.9, 41.2
    lon_min, lon_max = 28.8, 29.2
    
    print("Testing fast WorldCover reader...")
    print("=" * 70)
    
    import time
    start = time.time()
    
    grid, lats, lons = read_worldcover_region(worldcover_file, lat_min, lat_max, lon_min, lon_max, target_size=400)
    
    elapsed = time.time() - start
    
    print("=" * 70)
    print(f"✓ Fast read completed in {elapsed:.1f} seconds!")
    print(f"  (vs. the old method which would take 30+ minutes)")
    print(f"\nGrid statistics:")
    print(f"  Unique codes: {len(np.unique(grid))}")
    print(f"  Codes present: {sorted([int(c) for c in np.unique(grid) if c > 0])}")
    print("=" * 70)
