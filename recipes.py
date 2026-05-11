"""Recipes: one-shot workflows to reproduce common studies.

Includes:
- cap_ap_eirp_and_run_aggregate: compute per-channel grants for an AP position,
  cap AP EIRP to allowed values for the chosen channel, then run aggregate INR
  time-series and save KPIs/CSV outputs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Dict, Any, Tuple, List, Optional
import json
import csv
import math
import random
from datetime import datetime

from .spec_params import SpecParameters
from .spectrum_inquiry import spectrum_inquiry
from .grant_table import GrantRow, build_grant_table_with_incumbents, channel_number_from_center_mhz
from .kpi import inr_violation_probability, grant_stats, ipc_violation_probability_from_grants
from .aggregate import (
    evaluate_aggregate_inr_for_channel,
    evaluate_aggregate_inr_for_assignments,
)
from .acir_loader import apply_acir_to_spec, load_acir_from_json
from .audit import make_run_manifest, write_manifest, sha256_json, verify_files_exist


def _pick_allowed_eirp_for_channel(rows: Iterable[GrantRow], center_mhz: float, bw_mhz: float) -> float | None:
    for r in rows:
        if abs(r.center_mhz - center_mhz) < 1e-6 and abs(r.bandwidth_mhz - bw_mhz) < 1e-6:
            return float(r.allowed_eirp_dbm)
    return None


def generate_poisson_ap_field(
    *,
    center_lat: float,
    center_lon: float,
    radius_km: float,
    intensity_per_km2: Optional[float] = None,
    fixed_num_aps: Optional[int] = None,
    seed: int = 42,
) -> List[Dict[str, float]]:
    """Generate AP sites uniformly in a disk via Poisson count or fixed N.

    Args:
        center_lat/center_lon: disk center in degrees
        radius_km: disk radius
        intensity_per_km2: if provided and fixed_num_aps is None, draw N~Poisson(lambda*A)
        fixed_num_aps: if provided, use exactly this many APs
    Returns: list of {'lat': ..., 'lon': ...}
    """
    rng = random.Random(seed)
    area_km2 = math.pi * (radius_km ** 2)
    if fixed_num_aps is not None:
        n = int(max(0, fixed_num_aps))
    else:
        lam = float(intensity_per_km2 or 0.0) * area_km2
        # Poisson by Knuth's algorithm for moderate lam, fallback to normal approx when large
        if lam < 30.0:
            L = math.exp(-lam)
            k = 0
            p = 1.0
            while p > L:
                k += 1
                p *= rng.random()
            n = max(0, k - 1)
        else:
            # Normal approximation N(lam, lam)
            n = max(0, int(rng.gauss(lam, math.sqrt(lam)) + 0.5))

    def jitter_deg(meters: float) -> float:
        # ~1e-5 deg ≈ 1.11 m at these latitudes
        return meters * 1e-5 / 1.11

    sites: List[Dict[str, float]] = []
    for _ in range(n):
        # Uniform in disk: r = R * sqrt(u), theta ~ U[0,2pi)
        u = rng.random()
        r_km = radius_km * math.sqrt(u)
        theta = 2.0 * math.pi * rng.random()
        dx_m = r_km * 1000.0 * math.cos(theta)
        dy_m = r_km * 1000.0 * math.sin(theta)
        lat = center_lat + jitter_deg(dy_m)
        lon = center_lon + jitter_deg(dx_m)
        sites.append({'lat': lat, 'lon': lon})
    return sites


def cap_ap_eirp_and_run_aggregate(
    *,
    spec: SpecParameters,
    incumbents: Iterable[Dict[str, Any]],
    ap_lat: float,
    ap_lon: float,
    aps: Iterable[Dict[str, float]],
    center_mhz: float,
    bandwidth_mhz: float,
    out_dir: str | Path,
    inr_limit_db: float = -6.0,
    environment: str | None = None,
    path_model: str = "auto",
    duration_s: int = 300,
    sample_rate_hz: int = 1,
) -> Dict[str, Any]:
    """Cap AP EIRP to channel grants, run aggregate INR time-series, and save KPIs.

    Saves CSV `kpi_inr_timeseries.csv` and returns a small summary dict.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1) Compute grants for the AP position across UNII-5; use those to find allowed EIRP
    rows = build_grant_table_with_incumbents(
        spec=spec,
        incumbents=incumbents,
        lower_mhz=5925.0,
        upper_mhz=6425.0,
        bandwidths_mhz=(20.0, 40.0, 80.0, 160.0),
        inr_limit_db=inr_limit_db,
        environment=environment,
        path_model=path_model,
        ap_lat=ap_lat,
        ap_lon=ap_lon,
        protection_margin_db=0.0,
    )

    allowed = _pick_allowed_eirp_for_channel(rows, center_mhz=center_mhz, bw_mhz=bandwidth_mhz)
    if allowed is None:
        allowed = 0.0

    # 2) Cap AP EIRP to the allowed value
    capped_aps: List[Dict[str, float]] = []
    for ap in aps:
        nominal = float(ap.get("eirp_dbm", 0.0))
        capped_aps.append({**ap, "eirp_dbm": min(nominal, allowed)})

    # 3) Time-series INR with small jitter
    num_samples = duration_s * sample_rate_hz
    rng = random.Random(42)
    inr_series: List[float] = []
    for _ in range(num_samples):
        inst_aps = []
        for ap in capped_aps:
            jitter = (rng.random() - 0.5) * 2.0  # ±1 dB
            inst_aps.append({**ap, 'eirp_dbm': ap['eirp_dbm'] + jitter})
        res = evaluate_aggregate_inr_for_channel(
            spec=spec, incumbents=incumbents, aps=inst_aps,
            center_mhz=center_mhz, bandwidth_mhz=bandwidth_mhz,
            inr_limit_db=inr_limit_db, environment=environment, path_model=path_model,
        )
        worst = max(res['details'], key=lambda r: r['inr_db']) if res.get('details') else {'inr_db': float('-inf')}
        inr_series.append(worst['inr_db'])

    ipc_prob_time = inr_violation_probability(inr_series, inr_limit_db)

    # 4) Save CSV
    csv_path = out_dir / 'kpi_inr_timeseries.csv'
    with csv_path.open('w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['t_sec', 'inr_db'])
        for t, v in enumerate(inr_series):
            w.writerow([t, f"{v:.4f}"])

    return {
        "allowed_eirp_dbm": allowed,
        "ipc_violation_probability_time": ipc_prob_time,
        "csv_path": str(csv_path.resolve()),
    }


def cap_ap_eirp_and_run_aggregate_across_unii5(
    *,
    spec: SpecParameters,
    incumbents: Iterable[Dict[str, Any]],
    ap_lat: float,
    ap_lon: float,
    aps: Iterable[Dict[str, float]],
    bandwidths_mhz: Iterable[float] = (20.0, 40.0, 80.0, 160.0),
    inr_limit_db: float = -6.0,
    environment: str | None = None,
    path_model: str = "auto",
    duration_s: int = 120,
    sample_rate_hz: int = 1,
    out_dir: str | Path = "simulation_results_enhanced",
) -> Path:
    """Evaluate per-channel aggregate INR across UNII-5 with per-channel caps.

    For each (center,bw) channel in 5925–6425, we:
      1) compute allowed EIRP at AP location (min across incumbents),
      2) cap APs to that allowed EIRP for that channel,
      3) run a short INR time-series and record violation probability.

    Saves a CSV with columns: center_mhz,bw_mhz,allowed_eirp_dbm,ipc_violation_probability_time.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Precompute all grant rows once for UNII-5
    rows = build_grant_table_with_incumbents(
        spec=spec,
        incumbents=incumbents,
        lower_mhz=5925.0,
        upper_mhz=6425.0,
        bandwidths_mhz=bandwidths_mhz,
        inr_limit_db=inr_limit_db,
        environment=environment,
        path_model=path_model,
        ap_lat=ap_lat,
        ap_lon=ap_lon,
        protection_margin_db=0.0,
    )

    # Channel list from rows
    ch_list = sorted({(r.center_mhz, r.bandwidth_mhz) for r in rows})

    rng = random.Random(42)
    results: List[Tuple[float, float, float, float]] = []
    for center_mhz, bw_mhz in ch_list:
        allowed = _pick_allowed_eirp_for_channel(rows, center_mhz, bw_mhz)
        if allowed is None:
            allowed = 0.0

        # Cap APs for this channel
        capped_aps: List[Dict[str, float]] = []
        for ap in aps:
            nominal = float(ap.get("eirp_dbm", 0.0))
            capped_aps.append({**ap, "eirp_dbm": min(nominal, allowed)})

        # Time-series INR (shorter to iterate across channels)
        num_samples = duration_s * sample_rate_hz
        inr_series: List[float] = []
        for _ in range(num_samples):
            inst_aps = []
            for ap in capped_aps:
                jitter = (rng.random() - 0.5) * 2.0
                inst_aps.append({**ap, 'eirp_dbm': ap['eirp_dbm'] + jitter})
            res = evaluate_aggregate_inr_for_channel(
                spec=spec, incumbents=incumbents, aps=inst_aps,
                center_mhz=center_mhz, bandwidth_mhz=bw_mhz,
                inr_limit_db=inr_limit_db, environment=environment, path_model=path_model,
            )
            worst = max(res['details'], key=lambda r: r['inr_db']) if res.get('details') else {'inr_db': float('-inf')}
            inr_series.append(worst['inr_db'])
        ipc_prob_time = inr_violation_probability(inr_series, inr_limit_db)
        results.append((center_mhz, bw_mhz, allowed, ipc_prob_time))

    # Save summary
    csv_path = out_dir / 'aggregate_unii5_per_channel_kpi.csv'
    with csv_path.open('w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['center_mhz', 'bw_mhz', 'allowed_eirp_dbm', 'ipc_violation_probability_time'])
        for c, b, a, p in results:
            w.writerow([f"{c:.1f}", f"{b:.0f}", f"{a:.2f}", f"{p:.4f}"])
    return csv_path


def monte_carlo_multi_ap_unii5(
    *,
    spec: SpecParameters,
    incumbents: Iterable[Dict[str, Any]],
    ap_sites: Iterable[Dict[str, float]],  # per-AP lat/lon
    ap_nominal_eirp_dbm: float = 30.0,
    trials: int = 200,
    bandwidth_mhz: float = 20.0,
    inr_limit_db: float = -6.0,
    environment: str | None = None,
    path_model: str = "auto",
    out_dir: str | Path = "simulation_results_enhanced",
    base_name: str = "mc_unii5",
    run_tag: str | None = None,
) -> Path:
    """Monte Carlo: each AP randomly picks a UNII-5 channel allowed by its cap, then aggregate INR.

    Steps per trial:
      - Build per-AP grant rows at its location (UNII-5, given bandwidth)
      - Randomly select a channel from those with decision=grant (uniform)
      - Cap EIRP to that channel’s allowed EIRP
      - Evaluate aggregate INR with per-AP assignments
    Writes CSV with per-trial worst INR and selected channels.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Precompute per-AP grant tables
    per_ap_rows: List[List[GrantRow]] = []
    for ap in ap_sites:
        rows = build_grant_table_with_incumbents(
            spec=spec,
            incumbents=incumbents,
            lower_mhz=5925.0,
            upper_mhz=6425.0,
            bandwidths_mhz=(bandwidth_mhz,),
            inr_limit_db=inr_limit_db,
            environment=environment,
            path_model=path_model,
            ap_lat=float(ap['lat']),
            ap_lon=float(ap['lon']),
        )
        per_ap_rows.append(rows)

    # Extract granted channels per AP
    per_ap_granted: List[List[Tuple[float, float, float]]] = []  # (center, bw, allowed_eirp)
    for rows in per_ap_rows:
        granted = [(r.center_mhz, r.bandwidth_mhz, r.allowed_eirp_dbm) for r in rows if getattr(r, 'decision', '').lower() == 'grant']
        per_ap_granted.append(granted)

    rng = random.Random(123)
    tag = (run_tag or datetime.now().strftime('%H%M'))
    csv_path = out_dir / f'{base_name}_trials_{tag}.csv'
    csv_details_path = out_dir / f'{base_name}_trials_per_incumbent_{tag}.csv'
    csv_summary_path = out_dir / f'{base_name}_summary_per_incumbent_{tag}.csv'

    # Stable incumbent id order
    inc_ids: List[str] = []
    for inc in incumbents:
        lid = str(inc.get('link_id') or inc.get('fs_id') or inc.get('id') or 'unknown')
        inc_ids.append(lid)

    viol_counts = {lid: 0 for lid in inc_ids}

    with csv_path.open('w', newline='', encoding='utf-8') as f_main, \
         csv_details_path.open('w', newline='', encoding='utf-8') as f_det:
        w = csv.writer(f_main)
        wd = csv.writer(f_det)
        # Per-trial summary: worst INR and, for each AP, chosen channel, bw and capped EIRP
        header = ['trial', 'worst_inr_db', 'limiting_incumbent']
        for i in range(len(per_ap_granted)):
            header += [f'ap{i+1}_center_mhz', f'ap{i+1}_channel', f'ap{i+1}_bw_mhz', f'ap{i+1}_eirp_dbm']
        w.writerow(header)
        # Per-incumbent details: INR and pass flag
        wd.writerow(['trial'] + [f'inr_db_{lid}' for lid in inc_ids] + [f'pass_{lid}' for lid in inc_ids])

        for t in range(trials):
            assignments: List[Dict[str, float]] = []
            for ap_idx, ap in enumerate(ap_sites):
                choices = per_ap_granted[ap_idx]
                if not choices:
                    continue
                center, bw, allowed = rng.choice(choices)
                assignments.append({
                    'lat': float(ap['lat']),
                    'lon': float(ap['lon']),
                    'eirp_dbm': min(ap_nominal_eirp_dbm, float(allowed)),
                    'center_mhz': float(center),
                    'bw_mhz': float(bw),
                })
            res = evaluate_aggregate_inr_for_assignments(
                spec=spec,
                incumbents=incumbents,
                aps=assignments,
                inr_limit_db=inr_limit_db,
                environment=environment,
                path_model=path_model,
            )
            worst = float(res.get('worst_inr_db', 0.0))
            lim = res.get('limiting_incumbent')
            row_summary = [t, f"{worst:.3f}", (lim if lim is not None else '')]
            for a in assignments:
                c = float(a.get('center_mhz', float('nan')))
                bw = float(a.get('bw_mhz', float('nan')))
                e = float(a.get('eirp_dbm', float('nan')))
                try:
                    ch = channel_number_from_center_mhz(c)
                except Exception:
                    ch = ''
                row_summary += [f"{c:.1f}", ch, f"{bw:.0f}", f"{e:.2f}"]
            w.writerow(row_summary)

            # Per-incumbent details
            inr_by_id = {d.get('incumbent', 'unknown'): float(d.get('inr_db', 0.0)) for d in res.get('details', [])}
            row = [t]
            for lid in inc_ids:
                v = inr_by_id.get(lid, float('nan'))
                row.append(f"{v:.3f}" if isinstance(v, float) else '')
            for lid in inc_ids:
                v = inr_by_id.get(lid, float('nan'))
                passed = (isinstance(v, float) and v <= inr_limit_db)
                row.append(1 if passed else 0)
                if isinstance(v, float) and v > inr_limit_db:
                    viol_counts[lid] += 1
            wd.writerow(row)

    # Summary per incumbent
    with csv_summary_path.open('w', newline='', encoding='utf-8') as f_sum:
        ws = csv.writer(f_sum)
        ws.writerow(['incumbent', 'trials', 'violation_probability'])
        for lid in inc_ids:
            p = (viol_counts.get(lid, 0) / float(trials)) if trials > 0 else 0.0
            ws.writerow([lid, trials, f"{p:.4f}"])

    return csv_summary_path



def randomized_multibw_random_channels_unii5(
    *,
    spec: SpecParameters,
    incumbents: Iterable[Dict[str, Any]],
    ap_sites: Iterable[Dict[str, float]],
    ap_nominal_eirp_dbm: float = 30.0,
    duty_cycle: float = 0.04,
    duration_s: int = 500,
    sample_rate_hz: int = 1,
    inr_limit_db: float = -6.0,
    environment: str | None = None,
    path_model: str = "auto",
    out_dir: str | Path = "simulation_results_enhanced",
    seed: int = 20251029,
    write_timeseries: bool = True,
    run_tag: str | None = None,
    ap_indoor_fraction: float = 0.98,
    building_entry_loss_db: float = 15.0,
    bandwidth_probs: Optional[Dict[float, float]] = None,
	protection_margin_db: float = 0.0,
    channel_weighting: str = "uniform",  # "uniform" | "eirp_lin" | "eirp_dbm" | "per_mhz"
    clutter_correction_db: float = 0.0,
) -> Dict[str, Path]:
    """Randomized per-tick multi-bandwidth/channel AFC-capped aggregate INR study.

    For each 1-second tick:
      - Each AP becomes active with probability = duty_cycle
      - Independently chooses a bandwidth uniformly from {20, 40, 80, 160} MHz
      - Picks a random granted channel for that AP & BW (from its AFC grant table)
      - Transmits at min(nominal_eirp, allowed_eirp_for_that_channel) + small jitter
    We then compute aggregate INR per incumbent and accumulate:
      - IPC violation probability per incumbent (P[INR > inr_limit_db])
      - Noise rise statistics per incumbent: mean, p95, max of 10*log10(1+10^(INR/10))
      - Channel occupancy summary across the run (how often/how many APs use each channel)

    Returns paths to the written CSVs.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    # Basic input validation
    if not (0.0 <= duty_cycle <= 1.0):
        raise ValueError(f"duty_cycle must be in [0,1], got {duty_cycle}")
    if duration_s <= 0 or sample_rate_hz <= 0:
        raise ValueError("duration_s and sample_rate_hz must be positive")
    if channel_weighting not in ("uniform", "eirp_lin", "eirp_dbm", "per_mhz"):
        raise ValueError(f"Unsupported channel_weighting: {channel_weighting}")

    rng = random.Random(seed)
    bw_choices = [20.0, 40.0, 80.0, 160.0]
    if bandwidth_probs:
        # Normalize and build CDF for sampling
        pairs = [(float(k), float(v)) for k, v in bandwidth_probs.items() if float(k) in bw_choices and float(v) > 0]
        total = sum(v for _, v in pairs) or 1.0
        pairs = [(k, v / total) for k, v in pairs]
        cdf: List[Tuple[float, float]] = []
        acc = 0.0
        for k, v in sorted(pairs, key=lambda x: x[0]):
            acc += v
            cdf.append((k, acc))
        def pick_bw() -> float:
            x = rng.random()
            for k, a in cdf:
                if x <= a:
                    return k
            return cdf[-1][0]
    else:
        def pick_bw() -> float:
            return rng.choice(bw_choices)

    # Precompute per-AP grant tables for all BWs
    per_ap_grants_by_bw: List[Dict[float, List[Tuple[float, float]]]] = []  # [{bw: [(center, allowed_eirp), ...]}]
    for ap in ap_sites:
        grants_for_bw: Dict[float, List[Tuple[float, float]]] = {}
        for bw in bw_choices:
            rows = build_grant_table_with_incumbents(
                spec=spec,
                incumbents=incumbents,
                lower_mhz=5925.0,
                upper_mhz=6425.0,
                bandwidths_mhz=(bw,),
                inr_limit_db=inr_limit_db,
                environment=environment,
                path_model=path_model,
                ap_lat=float(ap['lat']),
                ap_lon=float(ap['lon']),
                protection_margin_db=protection_margin_db,
            )
            granted: List[Tuple[float, float]] = []
            for r in rows:
                decision = getattr(r, 'decision', '').lower()
                if decision == 'grant':
                    granted.append((float(r.center_mhz), float(r.allowed_eirp_dbm)))
            grants_for_bw[bw] = granted
        per_ap_grants_by_bw.append(grants_for_bw)

    # Incumbent ids (stable order)
    inc_ids: List[str] = []
    for inc in incumbents:
        lid = str(inc.get('link_id') or inc.get('fs_id') or inc.get('id') or 'unknown')
        inc_ids.append(lid)

    # Time-series accumulation per incumbent
    inr_series_by_inc: Dict[str, List[float]] = {lid: [] for lid in inc_ids}

    # Channel occupancy counters
    # occupancy[(center, bw)] = total number of active APs over the entire run
    # ticks_seen[(center, bw)] = number of ticks with >=1 active AP on that channel
    occupancy: Dict[Tuple[int, int], int] = {}
    ticks_seen: Dict[Tuple[int, int], int] = {}
    ts_rows: List[Tuple[int, str, float, float, int]] = []  # (t, incumbent, inr_db, noise_rise_db, pass)
    occ_rows: List[Tuple[int, int, int, int]] = []  # (t, center_mhz, bw_mhz, active_aps)

    num_samples = duration_s * sample_rate_hz
    for t in range(num_samples):
        assignments: List[Dict[str, float]] = []
        used_this_tick: Dict[Tuple[int, int], int] = {}

        for ap_idx, ap in enumerate(ap_sites):
            # Duty-cycle Bernoulli
            if rng.random() >= duty_cycle:
                continue
            # Pick bandwidth per provided probabilities or uniformly
            bw = pick_bw()
            granted = per_ap_grants_by_bw[ap_idx].get(bw, [])
            if not granted:
                continue
            # Weighted channel selection if requested
            if channel_weighting == "uniform" or len(granted) == 1:
                center, allowed = rng.choice(granted)
            else:
                weights: List[float] = []
                for c_i, a_dbm in granted:
                    if channel_weighting == "eirp_lin":
                        weights.append(max(0.0, 10.0 ** (float(a_dbm) / 10.0)))
                    elif channel_weighting == "eirp_dbm":
                        weights.append(max(0.0, float(a_dbm)))
                    elif channel_weighting == "per_mhz":
                        weights.append(float(bw))
                    else:
                        weights.append(1.0)
                total_w = sum(weights) or 1.0
                r = rng.random() * total_w
                acc = 0.0
                chosen = granted[-1]
                for (c_i, a_dbm), w in zip(granted, weights):
                    acc += w
                    if r <= acc:
                        chosen = (c_i, a_dbm)
                        break
                center, allowed = chosen
            eirp = min(ap_nominal_eirp_dbm, float(allowed))
            # Apply simple building entry loss for indoor APs
            if rng.random() < max(0.0, min(1.0, ap_indoor_fraction)):
                eirp -= max(0.0, building_entry_loss_db)
            jitter = (rng.random() - 0.5) * 2.0  # ±1 dB
            assignments.append({
                'lat': float(ap['lat']),
                'lon': float(ap['lon']),
                'eirp_dbm': eirp + jitter,
                'center_mhz': float(center),
                'bw_mhz': float(bw),
            })

            key = (int(round(center)), int(round(bw)))
            used_this_tick[key] = used_this_tick.get(key, 0) + 1

        # Update occupancy/ticks_seen
        for key, count in used_this_tick.items():
            occupancy[key] = occupancy.get(key, 0) + count
            ticks_seen[key] = ticks_seen.get(key, 0) + 1
            if write_timeseries:
                occ_rows.append((t, key[0], key[1], count))

        # Evaluate aggregate INR for this tick
        if assignments:
            res = evaluate_aggregate_inr_for_assignments(
                spec=spec,
                incumbents=incumbents,
                aps=assignments,
                inr_limit_db=inr_limit_db,
                environment=environment,
                path_model=path_model,
                clutter_correction_db=clutter_correction_db,
            )
            details = res.get('details', [])
            inr_map = {str(d.get('incumbent', 'unknown')): float(d.get('inr_db', float('nan'))) for d in details}
        else:
            inr_map = {}

        for lid in inc_ids:
            v = inr_map.get(lid, float('nan'))
            inr_series_by_inc[lid].append(v)
            if write_timeseries:
                if isinstance(v, float) and not math.isnan(v):
                    nr = 10.0 * math.log10(1.0 + (10.0 ** (v / 10.0)))
                    passed = 0 if v > inr_limit_db else 1
                else:
                    nr = float('nan')
                    passed = 1
                ts_rows.append((t, lid, v, nr, passed))

    # Compute per-incumbent IPC probability and noise rise stats
    def noise_rise_db(inr_db: float) -> float:
        # 10*log10(1 + I/N)
        return 10.0 * math.log10(1.0 + (10.0 ** (inr_db / 10.0)))

    def nan_filter(xs: List[float]) -> List[float]:
        return [x for x in xs if isinstance(x, float) and not math.isnan(x)]

    def percentile(xs: List[float], p: float) -> float:
        ys = sorted(nan_filter(xs))
        if not ys:
            return float('nan')
        k = max(0, min(len(ys) - 1, int(round((p / 100.0) * (len(ys) - 1)))))
        return ys[k]

    tag = (run_tag or datetime.now().strftime('%H%M'))
    per_inc_csv = out / f'scenario_unii5_randomized_per_incumbent_{tag}.csv'
    with per_inc_csv.open('w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['incumbent', 'samples', 'ipc_violation_probability_time', 'noise_rise_db_mean', 'noise_rise_db_p95', 'noise_rise_db_max'])
        for lid in inc_ids:
            series = inr_series_by_inc[lid]
            valid = nan_filter(series)
            if valid:
                viol = sum(1 for x in valid if x > inr_limit_db)
                p_viol = viol / float(len(valid))
                nr = [noise_rise_db(x) for x in valid]
                nr_mean = sum(nr) / len(nr)
                nr_p95 = percentile(nr, 95.0)
                nr_max = max(nr)
            else:
                p_viol = 0.0
                nr_mean = float('nan')
                nr_p95 = float('nan')
                nr_max = float('nan')
            w.writerow([lid, len(series), f"{p_viol:.4f}", f"{nr_mean:.3f}", f"{nr_p95:.3f}", f"{nr_max:.3f}"])

    occ_csv = out / f'scenario_unii5_randomized_channel_occupancy_{tag}.csv'
    with occ_csv.open('w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['center_mhz', 'bw_mhz', 'active_aps_total', 'ticks_used', 'mean_active_aps_per_used_tick'])
        for (center_i, bw_i), total in sorted(occupancy.items(), key=lambda kv: (kv[0][0], kv[0][1])):
            tu = ticks_seen.get((center_i, bw_i), 0)
            mean_per_tick = (total / tu) if tu > 0 else 0.0
            w.writerow([center_i, f"{bw_i:d}", total, tu, f"{mean_per_tick:.2f}"])

    # Optional per-tick CSVs for fine-grained analysis
    outputs: Dict[str, Path] = {'per_incumbent_csv': per_inc_csv, 'occupancy_csv': occ_csv}
    if write_timeseries:
        ts_csv = out / f'scenario_unii5_randomized_timeseries_per_incumbent_{tag}.csv'
        with ts_csv.open('w', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            w.writerow(['t_sec', 'incumbent', 'inr_db', 'noise_rise_db', 'pass_flag'])
            for row in ts_rows:
                t, lid, inr_db, nr_db, passed = row
                w.writerow([t, lid, f"{inr_db:.4f}" if isinstance(inr_db, float) and not math.isnan(inr_db) else '',
                            f"{nr_db:.4f}" if isinstance(nr_db, float) and not math.isnan(nr_db) else '', passed])
        outputs['timeseries_per_incumbent_csv'] = ts_csv

        occ_ts_csv = out / f'scenario_unii5_randomized_tick_occupancy_{tag}.csv'
        with occ_ts_csv.open('w', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            w.writerow(['t_sec', 'center_mhz', 'bw_mhz', 'active_aps'])
            for t, center_i, bw_i, count in occ_rows:
                w.writerow([t, center_i, bw_i, count])
        outputs['tick_occupancy_csv'] = occ_ts_csv

    # Audit manifest
    try:
        inc_digest = sha256_json(list(incumbents))
    except Exception:
        inc_digest = None

    manifest_args = {
        "ap_nominal_eirp_dbm": ap_nominal_eirp_dbm,
        "duty_cycle": duty_cycle,
        "duration_s": duration_s,
        "sample_rate_hz": sample_rate_hz,
        "inr_limit_db": inr_limit_db,
        "environment": environment,
        "path_model": path_model,
        "seed": seed,
        "ap_indoor_fraction": ap_indoor_fraction,
        "building_entry_loss_db": building_entry_loss_db,
        "bandwidth_probs": bandwidth_probs,
        "protection_margin_db": protection_margin_db,
        "channel_weighting": channel_weighting,
        "clutter_correction_db": clutter_correction_db,
    }
    manifest_outputs = {k: str(v) for k, v in outputs.items()}
    manifest = make_run_manifest(
        run_tag=tag,
        spec_path=None,
        incumbents_path=None,
        incumbents_data_digest=inc_digest,
        args=manifest_args,
        outputs=manifest_outputs,
        notes="randomized_multibw_random_channels_unii5",
    )
    manifest_path = write_manifest(out, manifest, filename=f'manifest_{tag}.json')

	# Quick integrity map (files exist & non-empty)
    integrity = verify_files_exist(list(manifest_outputs.values()))
    # Write integrity companion
    with (out / f'integrity_{tag}.json').open('w', encoding='utf-8') as f:
        json.dump(integrity, f, indent=2)

    outputs['manifest_json'] = manifest_path
    return outputs


