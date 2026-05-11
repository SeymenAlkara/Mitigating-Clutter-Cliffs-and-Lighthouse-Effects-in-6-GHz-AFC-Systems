"""Multi-AP aggregate interference evaluation (scaffold).

Purpose: Given multiple AP sites and a Wi‑Fi channel, estimate aggregate
interference at each FS receiver and check the INR criterion (I/N ≤ −6 dB).

This implements a simplified TS‑1014 9.1.1 aggregate evaluation:
- Interference from each AP is computed using path loss (selectable model) and
  FS antenna discrimination (simple parabolic or RPE if provided via incumbents).
- Aggregate interference is the linear sum of AP contributions at the FS.
- INR is aggregate I minus FS noise; pass/fail is compared to the limit.

Notes:
- AP EIRP per site is an input (use the allowed EIRP granted earlier or a trial
  value). This module does not solve the joint allocation; it evaluates a given
  set.
"""

from dataclasses import dataclass
from typing import Iterable, Dict, Any, List, Tuple
import math

from .geodesy import haversine_distance_m, initial_bearing_deg
from .propagation import select_pathloss_db
from .itm import longley_rice_pathloss_db
from .antenna import AntennaPatternParams, off_axis_azimuth_deg, effective_gain_dbi
from .antenna_rpe import combined_rpe_gain_dbi
from .link_budget import noise_power_dbm
from .fs_bandwidth import determine_fs_noise_bw_hz


@dataclass
class APSite:
    lat: float
    lon: float
    eirp_dbm: float


def _path_loss(distance_m: float, f_hz: float, environment: str | None, path_model: str, rx_h_m: float | None) -> float:
    if path_model == "fspl":
        return select_pathloss_db(distance_m=distance_m, frequency_hz=f_hz, environment=environment, selector="fspl")
    if path_model == "winner":
        return select_pathloss_db(distance_m=distance_m, frequency_hz=f_hz, environment=environment, selector="winner2")
    if path_model == "two_slope":
        return select_pathloss_db(distance_m=distance_m, frequency_hz=f_hz, environment=environment)
    if path_model == "itm":
        return longley_rice_pathloss_db(distance_m=distance_m, frequency_hz=f_hz, tx_height_m=10.0, rx_height_m=rx_h_m, climate=environment)
    return select_pathloss_db(distance_m=distance_m, frequency_hz=f_hz, environment=environment)


def evaluate_aggregate_inr_for_channel(
    incumbents: Iterable[Dict[str, Any]],
    ap_sites: Iterable[APSite],
    center_mhz: float,
    bw_mhz: float,
    inr_limit_db: float = -6.0,
    environment: str | None = None,
    path_model: str = "auto",
) -> List[Dict[str, Any]]:
    """Return per-incumbent aggregate INR and pass/fail for a Wi‑Fi channel.

    Returns a list of dicts: {link_id, inr_db, pass, components: [(ap_idx, i_dbm), ...]}
    """
    f_hz = center_mhz * 1e6
    results: List[Dict[str, Any]] = []
    for inc in incumbents:
        rx_lat = float(inc.get("rx_lat", 0.0))
        rx_lon = float(inc.get("rx_lon", 0.0))
        rx_az = float(inc.get("rx_antenna_azimuth_deg", 0.0))
        rx_gain = float(inc.get("rx_antenna_gain_dbi", 30.0))
        rpe_az = inc.get("rx_rpe_az")
        rpe_el = inc.get("rx_rpe_el")
        rx_h_m = inc.get("rx_antenna_height_m")
        link_id = str(inc.get("link_id", "unknown"))

        # Noise with precedence: use incumbent bandwidth if provided
        n_bw = determine_fs_noise_bw_hz(spec=None, emission_designator=None, explicit_rx_bw_hz=float(inc.get("bandwidth_mhz", 20.0)) * 1e6, ul_bandwidth_hz=None)  # type: ignore[arg-type]
        n_dbm = noise_power_dbm(n_bw, nf_db=4.5)

        comps: List[Tuple[int, float]] = []
        for idx, ap in enumerate(ap_sites):
            d_m = haversine_distance_m(ap.lat, ap.lon, rx_lat, rx_lon)
            pl_db = _path_loss(d_m, f_hz, environment, path_model, float(rx_h_m) if rx_h_m else None)
            brg = initial_bearing_deg(ap.lat, ap.lon, rx_lat, rx_lon)
            delta_az = off_axis_azimuth_deg(rx_az, (brg + 180.0) % 360.0)
            if rpe_az and rpe_el:
                g_eff = combined_rpe_gain_dbi(rx_gain, delta_az, 0.0, rpe_az, rpe_el)
            else:
                g_eff = effective_gain_dbi(AntennaPatternParams(g_max_dbi=rx_gain), delta_az, 0.0)
            i_dbm = ap.eirp_dbm - pl_db + g_eff
            comps.append((idx, i_dbm))

        # Aggregate
        total_mw = sum(10 ** (i_dbm / 10.0) for _, i_dbm in comps)
        i_agg_dbm = -math.inf if total_mw <= 0 else 10.0 * math.log10(total_mw)
        inr_db = i_agg_dbm - n_dbm
        results.append({
            "link_id": link_id,
            "inr_db": inr_db,
            "pass": inr_db <= inr_limit_db,
            "components": comps,
        })
    return results


def evaluate_aggregate_inr_across(
    incumbents: Iterable[Dict[str, Any]],
    ap_sites: Iterable[APSite],
    channels: Iterable[Tuple[float, float]],  # (center_mhz, bw_mhz)
    inr_limit_db: float = -6.0,
    environment: str | None = None,
    path_model: str = "auto",
) -> List[Dict[str, Any]]:
    """Evaluate aggregate INR for multiple channels.

    Returns a list of dicts per channel with per-incumbent results and a summary.
    """
    summary: List[Dict[str, Any]] = []
    for center_mhz, bw_mhz in channels:
        per_inc = evaluate_aggregate_inr_for_channel(
            incumbents=incumbents,
            ap_sites=ap_sites,
            center_mhz=center_mhz,
            bw_mhz=bw_mhz,
            inr_limit_db=inr_limit_db,
            environment=environment,
            path_model=path_model,
        )
        worst = max(per_inc, key=lambda r: r["inr_db"]) if per_inc else None
        summary.append({
            "center_mhz": center_mhz,
            "bw_mhz": bw_mhz,
            "per_inc": per_inc,
            "worst_inr_db": worst["inr_db"] if worst else None,
            "worst_link_id": worst["link_id"] if worst else None,
            "all_pass": all(r["pass"] for r in per_inc) if per_inc else True,
        })
    return summary


