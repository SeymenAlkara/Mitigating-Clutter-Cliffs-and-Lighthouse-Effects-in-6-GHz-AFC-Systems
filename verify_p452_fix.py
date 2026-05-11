"""
VERIFICATION TEST: ITU-R P.452-17 Clutter Loss Implementation

This test verifies that the new formula is working correctly by directly
testing the clutter loss calculations.
"""

import sys
sys.path.insert(0, '.')

print("=" * 80)
print("VERIFICATION TEST: ITU-R P.452-17 CLUTTER IMPLEMENTATION")
print("=" * 80)

# Test 1: Direct formula test
print("\n" + "=" * 80)
print("TEST 1: Direct ITU-R P.452-17 Formula")
print("=" * 80)

from clutter.p452_clutter import compute_p452_clutter_loss_db

# Test dense urban
frequency = 6000  # MHz
distance = 5.0    # km
ap_height = 10.0  # m
rx_height = 30.0  # m

print(f"\nTest Parameters:")
print(f"  Frequency: {frequency} MHz")
print(f"  Distance: {distance} km")
print(f"  AP height: {ap_height} m")
print(f"  RX height: {rx_height} m")

test_cases = [
    ("Dense Urban", 20.0, 0.050),
    ("Park (Grassland)", 1.0, 0.0),
]

print(f"\n{'Scenario':<20} {'Clutter H':<12} {'Nom Dist':<12} {'TX Loss':<12} {'RX Loss':<12}")
print("-" * 80)

for name, clutter_h, nom_dist_km in test_cases:
    loss_tx, loss_rx = compute_p452_clutter_loss_db(
        frequency, distance, ap_height, rx_height, clutter_h, nom_dist_km
    )
    print(f"{name:<20} {clutter_h:<12.1f} {nom_dist_km*1000:<12.0f} {loss_tx:<12.1f} {loss_rx:<12.1f}")

print("\n✓ Expected: Urban ~18 dB, Park ~0 dB, Difference ~18 dB")

# Test 2: Test hybrid_clutter module
print("\n" + "=" * 80)
print("TEST 2: Hybrid Clutter Module Integration")
print("=" * 80)

from algorithms.hybrid_clutter import get_site_specific_clutter_loss_db
from terrain.geodesy_utils import haversine_distance_m

# Fake data for test
rx_lat, rx_lon = 41.0, 29.0
ap_locations = [
    ("AP in Dense Urban", 41.05, 29.0),
    ("AP in Park", 41.11, 29.055),
]

# Synthetic test since we might not have real file
print("\nNote: This requires WorldCover file. Testing with synthetic WorldCover codes...")

# Create a minimal mock test
print("\nDirect WorldCover code test:")
from clutter.worldcover_mapping import get_clutter_params

codes = [50, 30]  # Urban, Grassland
names = ["Dense Urban", "Grassland (Park)"]

for code, name in zip(codes, names):
    params = get_clutter_params(code)
    
    # Calculate loss using the formula directly
    loss_tx, loss_rx = compute_p452_clutter_loss_db(
        6000,  # 6 GHz
        5.0,   # 5 km
        10.0,  # AP height
        30.0,  # RX height
        params.height_m,
        params.nominal_distance_m / 1000
    )
    
    print(f"\n  {name} (Code {code}):")
    print(f"    Clutter height: {params.height_m} m")
    print(f"    Nominal distance: {params.nominal_distance_m} m")
    print(f"    Calculated loss: {loss_tx:.1f} dB")

# Test 3: Check if old formula is still being used somewhere
print("\n" + "=" * 80)
print("TEST 3: Verifying Module Import")
print("=" * 80)

import inspect
from algorithms import hybrid_clutter

# Get the source code of get_site_specific_clutter_loss_db
source = inspect.getsource(hybrid_clutter.get_site_specific_clutter_loss_db)

if "compute_p452_clutter_loss_db" in source:
    print("\n✓ CORRECT: hybrid_clutter is importing compute_p452_clutter_loss_db")
    print("✓ The new ITU-R P.452-17 formula IS being used")
else:
    print("\n✗ ERROR: hybrid_clutter is NOT using the new formula!")
    print("✗ Still using old approximation")

if "height_m / 10" in source:
    print("✗ ERROR: Old formula 'height_m / 10' still present!")
else:
    print("✓ CORRECT: Old formula 'height_m / 10' has been removed")

# Test 4: Compare old vs new
print("\n" + "=" * 80)
print("TEST 4: Formula Comparison")
print("=" * 80)

urban_height = 20.0
park_height = 1.0

# Old formula (wrong)
old_urban = urban_height / 10.0  # Wrong!
old_park = park_height / 10.0    # Wrong!

# New formula (correct)
new_urban, _ = compute_p452_clutter_loss_db(6000, 5.0, 10.0, 30.0, urban_height, 0.050)
new_park, _ = compute_p452_clutter_loss_db(6000, 5.0, 10.0, 30.0, park_height, 0.0)

print(f"\n{'Scenario':<20} {'Old Formula':<15} {'New P.452-17':<15} {'Difference'}")
print("-" * 70)
print(f"{'Dense Urban':<20} {old_urban:<15.1f} {new_urban:<15.1f} {new_urban - old_urban:>10.1f} dB")
print(f"{'Park':<20} {old_park:<15.1f} {new_park:<15.1f} {new_park - old_park:>10.1f} dB")

print("\n" + "=" * 80)
print("SUMMARY")
print("=" * 80)

if new_urban > 15.0 and new_park < 2.0:
    print("\n✅ SUCCESS: New formula is working correctly!")
    print(f"   Urban: {new_urban:.1f} dB (should be ~18 dB)")
    print(f"   Park: {new_park:.1f} dB (should be ~0 dB)")
    print(f"   Clutter Cliff: {new_urban - new_park:.1f} dB difference")
    print("\n   The formula fix is WORKING!")
    print("\n   If notebook still shows 13.8 dB, the issue is:")
    print("   → Jupyter kernel needs restart (Kernel → Restart)")
    print("   → Or notebook is calculating clutter differently")
else:
    print("\n❌ PROBLEM: Formula not giving expected results")
    print(f"   Urban: {new_urban:.1f} dB (expected ~18 dB)")
    print(f"   Park: {new_park:.1f} dB (expected ~0 dB)")

print("\n" + "=" * 80)
input("\nPress Enter to exit...")
