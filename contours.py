"""Exclusion contour rendering (PNG) for co/adjacent channel zones around one FS.

Approach (simple grid sampler):
- Choose an FS (by index in the incumbents list) and a Wi‑Fi channel (center/bw).
- Sample a lat/lon grid around the FS within a given radius (km).
- For each grid point (candidate AP site), run the grant evaluator against THIS FS
  only and record grant/deny for the channel.
- Render a colored mask (green=grant, red=deny), overlay the FS point, and save PNG.

This avoids extra dependencies (Shapely/GeoPandas); output is a static image.
"""

from pathlib import Path
from typing import Iterable, Tuple

import numpy as np
import matplotlib.pyplot as plt

from .spec_params import SpecParameters
from .grant_table import build_grant_table_with_incumbents


def _meters_to_deg(lat_deg: float, dx_m: float, dy_m: float) -> Tuple[float, float]:
    # Rough conversions near latitude
    dlat = dy_m / 111_320.0
    dlon = dx_m / (111_320.0 * np.cos(np.radians(lat_deg)) + 1e-12)
    return dlon, dlat


def render_exclusion_map(
    spec: SpecParameters,
    incumbents: list[dict],
    fs_index: int,
    center_mhz: float,
    bw_mhz: float,
    environment: str = "urban",
    path_model: str = "auto",
    protection_margin_db: float = 0.0,
    device_constraints=None,
    grid_radius_km: float = 10.0,
    grid_step_m: float = 200.0,
    outfile: str | Path = "exclusion_map.png",
) -> Path:
    assert 0 <= fs_index < len(incumbents), "fs_index out of range"
    fs = incumbents[fs_index]
    rx_lat = float(fs["rx_lat"]) if "rx_lat" in fs else 0.0
    rx_lon = float(fs["rx_lon"]) if "rx_lon" in fs else 0.0

    # Build grid around FS
    R = grid_radius_km * 1000.0
    step = max(50.0, float(grid_step_m))
    half = int(np.ceil(R / step))
    xs = np.arange(-half, half + 1) * step
    ys = np.arange(-half, half + 1) * step
    grid = np.zeros((ys.size, xs.size), dtype=np.uint8)

    # Evaluate per grid point
    for iy, dy in enumerate(ys):
        for ix, dx in enumerate(xs):
            dlon, dlat = _meters_to_deg(rx_lat, dx, dy)
            ap_lat = rx_lat + dlat
            ap_lon = rx_lon + dlon
            rows = build_grant_table_with_incumbents(
                spec=spec,
                incumbents=[fs],
                distance_m=None,
                ap_lat=ap_lat,
                ap_lon=ap_lon,
                lower_mhz=center_mhz - 0.5 * bw_mhz,
                upper_mhz=center_mhz + 0.5 * bw_mhz,
                bandwidths_mhz=(bw_mhz,),
                inr_limit_db=-6.0,
                environment=environment,
                path_model=path_model,
                device_constraints=device_constraints,
                indoor=False,
                penetration_db=None,
                protection_margin_db=protection_margin_db,
            )
            decision = rows[0].decision.lower() if rows else "grant"
            grid[iy, ix] = 0 if decision == "grant" else 1

    # Render
    fig, ax = plt.subplots(figsize=(6, 6), dpi=150)
    extent = [rx_lon + _meters_to_deg(rx_lat, xs[0], 0)[0],
              rx_lon + _meters_to_deg(rx_lat, xs[-1], 0)[0],
              rx_lat + _meters_to_deg(rx_lat, 0, ys[0])[1],
              rx_lat + _meters_to_deg(rx_lat, 0, ys[-1])[1]]
    cmap = plt.matplotlib.colors.ListedColormap([[0.2, 0.8, 0.4, 1.0], [0.85, 0.3, 0.3, 1.0]])
    ax.imshow(grid, origin="lower", extent=extent, cmap=cmap, alpha=0.6)
    ax.scatter([rx_lon], [rx_lat], c="k", s=30, marker="s", label="FS Rx")
    ax.set_title(f"Exclusion map (FS idx {fs_index}, {center_mhz:.1f} MHz / {bw_mhz:.0f} MHz)")
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.legend(loc="upper right")
    outp = Path(outfile)
    outp.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(outp)
    plt.close(fig)
    return outp


