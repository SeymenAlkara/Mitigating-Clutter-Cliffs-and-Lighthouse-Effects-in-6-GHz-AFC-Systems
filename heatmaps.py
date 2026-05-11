"""SINR and throughput heatmap generators (client-side view).

This module computes simple client-side SINR and throughput maps for a set of
AP sites over a geographic grid around a given center. It is intended for
visualization and sanity-checking rather than detailed PHY/MAC simulation.

Assumptions (kept explicit for clarity):
- Client bandwidth: user-specified (e.g., 20/40/80 MHz)
- Client NF: 7 dB (configurable)
- Client antenna gain: 0 dBi (configurable)
- No building penetration by default (can be passed via propagation selector)
- Interference from other APs is summed in linear power domain

Outputs:
- Saves PNG figures per AP (SINR and throughput) and returns the grids
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Tuple

import numpy as np
import matplotlib.pyplot as plt

from .propagation import select_pathloss_db
from .phy_mcs import phy_rate_bps_from_snr_db


@dataclass(frozen=True)
class APSiteClient:
    lat: float
    lon: float
    eirp_dbm: float
    name: str | None = None


def _meters_to_deg(lat_deg: float, dx_m: float, dy_m: float) -> Tuple[float, float]:
    dlat = dy_m / 111_320.0
    dlon = dx_m / (111_320.0 * np.cos(np.radians(lat_deg)) + 1e-12)
    return dlon, dlat


def _noise_dbm(bw_hz: float, nf_db: float) -> float:
    return -174.0 + 10.0 * np.log10(bw_hz) + nf_db


def _generate_ap_heatmaps_core(
    ap_sites: Iterable[APSiteClient],
    center_lat: float,
    center_lon: float,
    center_mhz: float,
    bw_mhz: float,
    radius_km: float = 2.0,
    step_m: float = 20.0,
    environment: str | None = "urban",
    path_model: str = "auto",
    client_nf_db: float = 7.0,
    client_rx_gain_dbi: float = 0.0,
    mac_efficiency: float = 0.85,
    out_dir: str | Path = "simulation_results_enhanced",
) -> dict:
    """Compute and save SINR/throughput heatmaps for each AP.

    Returns a dict with entries {ap_name: {"sinr_db": grid, "tp_mbps": grid}}
    where grids are 2D numpy arrays.
    """
    ap_list = list(ap_sites)
    outp = Path(out_dir)
    outp.mkdir(parents=True, exist_ok=True)

    bw_hz = bw_mhz * 1e6
    noise_dbm = _noise_dbm(bw_hz, client_nf_db)

    R = radius_km * 1000.0
    nx = int(2 * R / step_m) + 1
    xs = np.linspace(-R, R, nx)
    ys = np.linspace(-R, R, nx)

    # Precompute client grid lat/lon
    lons = np.zeros((nx, nx))
    lats = np.zeros((nx, nx))
    for iy, dy in enumerate(ys):
        for ix, dx in enumerate(xs):
            dlon, dlat = _meters_to_deg(center_lat, dx, dy)
            lons[iy, ix] = center_lon + dlon
            lats[iy, ix] = center_lat + dlat

    # Path loss and received powers per AP
    results: dict = {}
    f_hz = center_mhz * 1e6

    # Compute received power grids from each AP at the client grid
    pr_dbm_all = []  # list of 2D arrays per AP
    for ap in ap_list:
        pr = np.zeros((nx, nx))
        for iy in range(nx):
            for ix in range(nx):
                # great-circle approx via local meters conversion; acceptable for small areas
                dx_m = (lons[iy, ix] - ap.lon) * (111_320.0 * np.cos(np.radians(center_lat)))
                dy_m = (lats[iy, ix] - ap.lat) * 111_320.0
                d_m = np.hypot(dx_m, dy_m)
                d_m = max(d_m, 1.0)
                if path_model == "fspl":
                    pl_db = select_pathloss_db(d_m, f_hz, environment=environment, selector="fspl")
                elif path_model == "winner":
                    pl_db = select_pathloss_db(d_m, f_hz, environment=environment, selector="winner2")
                else:
                    pl_db = select_pathloss_db(d_m, f_hz, environment=environment)
                pr[iy, ix] = ap.eirp_dbm - pl_db + client_rx_gain_dbi
        pr_dbm_all.append(pr)

    # For each AP, compute SINR and throughput with other APs as interference
    for idx, ap in enumerate(ap_list):
        s_dbm = pr_dbm_all[idx]
        # Sum interference from others in linear mW
        i_mw = np.zeros_like(s_dbm)
        for jdx, pr in enumerate(pr_dbm_all):
            if jdx == idx:
                continue
            i_mw += 10.0 ** (pr / 10.0)
        n_mw = 10.0 ** (noise_dbm / 10.0)
        s_mw = 10.0 ** (s_dbm / 10.0)
        sinr_lin = s_mw / (i_mw + n_mw)
        sinr_db = 10.0 * np.log10(np.maximum(sinr_lin, 1e-12))

        # Throughput using PHY mapping (single spatial stream assumed)
        tp_mbps = np.zeros_like(sinr_db)
        for iy in range(nx):
            for ix in range(nx):
                mcs, per, rate_bps = phy_rate_bps_from_snr_db(
                    float(sinr_db[iy, ix]), bw_hz, spatial_streams=1, mac_efficiency=mac_efficiency
                )
                tp_mbps[iy, ix] = rate_bps / 1e6

        name = ap.name or f"AP_{idx+1}"
        results[name] = {"sinr_db": sinr_db, "tp_mbps": tp_mbps}

        # Save figures similar to the provided examples
        fig, axes = plt.subplots(1, 2, figsize=(10, 4), dpi=140)
        im0 = axes[0].imshow(sinr_db, origin="lower", extent=[0, nx - 1, 0, nx - 1], cmap="RdYlGn")
        axes[0].set_title(f"SINR – {name} (dB)")
        fig.colorbar(im0, ax=axes[0])
        im1 = axes[1].imshow(tp_mbps, origin="lower", extent=[0, nx - 1, 0, nx - 1], cmap="turbo")
        axes[1].set_title(f"Throughput – {name} (Mbps)")
        fig.colorbar(im1, ax=axes[1])
        fig.tight_layout()
        fig.savefig(outp / f"heatmap_{name}.png")
        plt.close(fig)

    return results


def generate_ap_heatmaps(
    ap_sites: Iterable[APSiteClient] | None = None,
    *,
    # Runbook-friendly aliases
    aps: Iterable[APSiteClient] | None = None,
    grid_center: Tuple[float, float] | None = None,
    grid_size_m: float | None = None,
    resolution_m: float | None = None,
    center_mhz: float | None = None,
    bandwidth_mhz: float | None = None,
    # Original names (optional)
    center_lat: float | None = None,
    center_lon: float | None = None,
    bw_mhz: float | None = None,
    radius_km: float | None = None,
    step_m: float | None = None,
    environment: str | None = "urban",
    path_model: str = "auto",
    client_nf_db: float = 7.0,
    client_rx_gain_dbi: float = 0.0,
    mac_efficiency: float = 0.85,
    out_dir: str | Path = "simulation_results_enhanced",
) -> dict:
    """Wrapper that accepts both the original and runbook parameter names.

    - aps (runbook) or ap_sites (original) supply the AP list
    - grid_center (lat, lon), grid_size_m, resolution_m map to center/radius/step
    - bandwidth_mhz maps to bw_mhz
    """
    ap_list = list(aps if aps is not None else (ap_sites or []))
    if not ap_list:
        raise ValueError("No AP sites provided (aps/ap_sites is empty)")

    if grid_center is not None:
        center_lat = grid_center[0]
        center_lon = grid_center[1]
    if center_lat is None or center_lon is None:
        raise ValueError("center_lat/center_lon or grid_center must be provided")

    if bandwidth_mhz is not None:
        bw_mhz = bandwidth_mhz
    if bw_mhz is None:
        raise ValueError("bandwidth_mhz/bw_mhz must be provided")

    if center_mhz is None:
        raise ValueError("center_mhz must be provided")

    # Map grid size and resolution
    if grid_size_m is not None:
        radius_km = (grid_size_m / 2.0) / 1000.0
    if radius_km is None:
        radius_km = 2.0
    if resolution_m is not None:
        step_m = resolution_m
    if step_m is None:
        step_m = 20.0

    return _generate_ap_heatmaps_core(
        ap_sites=ap_list,
        center_lat=float(center_lat),
        center_lon=float(center_lon),
        center_mhz=float(center_mhz),
        bw_mhz=float(bw_mhz),
        radius_km=float(radius_km),
        step_m=float(step_m),
        environment=environment,
        path_model=path_model,
        client_nf_db=float(client_nf_db),
        client_rx_gain_dbi=float(client_rx_gain_dbi),
        mac_efficiency=float(mac_efficiency),
        out_dir=out_dir,
    )


