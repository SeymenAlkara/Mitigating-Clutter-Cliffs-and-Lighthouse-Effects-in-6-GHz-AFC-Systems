"""
Investigation: Why aren't we getting 18 dB for urban areas?
"""

import sys
sys.path.insert(0, '.')

from clutter.p452_clutter import compute_p452_clutter_loss_db
from clutter.worldcover_mapping import get_clutter_params, WORLDCOVER_TO_CLUTTER

print("=" * 80)
print("INVESTIGATION: Urban Clutter Loss Values")
print("=" * 80)

# Check WorldCover mapping for urban
print("\n1. WorldCover Code 50 (Built-up/Urban) Parameters:")
print("-" * 80)
params_urban = get_clutter_params(50)
print(f"   Code: {params_urban.code}")
print(f"   Name: {params_urban.name}")
print(f"   Height: {params_urban.height_m} m")
print(f"   Nominal Distance: {params_urban.nominal_distance_m} m")

# Calculate what loss this gives
print("\n2. Calculated Loss with Current Parameters:")
print("-" * 80)
loss_tx, loss_rx = compute_p452_clutter_loss_db(
    6000,  # 6 GHz
    5.0,   # 5 km
    10.0,  # AP height
    30.0,  # RX height
    params_urban.height_m,
    params_urban.nominal_distance_m / 1000  # Convert to km
)
print(f"   TX loss (at AP): {loss_tx:.1f} dB")
print(f"   RX loss (at incumbent): {loss_rx:.1f} dB")

# Test different nominal distances to see effect
print("\n3. Effect of Nominal Distance on Loss:")
print("-" * 80)
print(f"{'Nom Dist (m)':<15} {'TX Loss (dB)':<15} {'Effect'}")
print("-" * 80)

nom_dists = [10, 20, 30, 40, 50, 75, 100]
for nd in nom_dists:
    loss, _ = compute_p452_clutter_loss_db(6000, 5.0, 10.0, 30.0, 15.0, nd/1000)
    print(f"{nd:<15} {loss:<15.1f}")

# Check what we SHOULD use for dense urban
print("\n4. ITU-R P.452-17 Standard Clutter Categories:")
print("-" * 80)
print("   From ITU-R P.452-17 documentation:")
print("   - Dense Urban:  h=25m, d_nom=20m")
print("   - Urban:        h=20m, d_nom=20m") 
print("   - Suburban:     h=9m,  d_nom=25m")
print("   - Rural:        h=4m,  d_nom=50m")

# Test with ITU recommended values
print("\n5. Loss with ITU-R Recommended Values:")
print("-" * 80)
itu_dense = compute_p452_clutter_loss_db(6000, 5.0, 10.0, 30.0, 25.0, 0.020)
itu_urban = compute_p452_clutter_loss_db(6000, 5.0, 10.0, 30.0, 20.0, 0.020)
itu_suburban = compute_p452_clutter_loss_db(6000, 5.0, 10.0, 30.0, 9.0, 0.025)

print(f"   Dense Urban (h=25m, d=20m): {itu_dense[0]:.1f} dB")
print(f"   Urban (h=20m, d=20m):       {itu_urban[0]:.1f} dB")
print(f"   Suburban (h=9m, d=25m):     {itu_suburban[0]:.1f} dB")

print("\n6. Grassland/Park Parameters:")
print("-" * 80)
params_grass = get_clutter_params(30)
loss_grass, _ = compute_p452_clutter_loss_db(
    6000, 5.0, 10.0, 30.0, 
    params_grass.height_m, 
    params_grass.nominal_distance_m / 1000
)
print(f"   Grassland: h={params_grass.height_m}m, d={params_grass.nominal_distance_m}m")
print(f"   Loss: {loss_grass:.1f} dB")

print("\n" + "=" * 80)
print("CONCLUSION:")
print("=" * 80)
print(f"Current urban loss: {loss_tx:.1f} dB")
print(f"Current park loss: {loss_grass:.1f} dB")
print(f"Current Clutter Cliff: {loss_tx - loss_grass:.1f} dB")
print("")
print(f"With ITU values: Urban {itu_urban[0]:.1f} dB - Park {loss_grass:.1f} dB = {itu_urban[0] - loss_grass:.1f} dB Cliff")
print("=" * 80)

input("\nPress Enter to exit...")
