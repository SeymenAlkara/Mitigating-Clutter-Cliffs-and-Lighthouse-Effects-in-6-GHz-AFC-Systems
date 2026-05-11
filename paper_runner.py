from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import json
from datetime import datetime
import pandas as pd

from .spec_params import SpecParameters
from .recipes import (
	randomized_multibw_random_channels_unii5,
	generate_poisson_ap_field,
)


def _load_json(p: Path) -> Dict[str, Any]:
	with p.open("r", encoding="utf-8") as f:
		return json.load(f)


def run_paper_scenario(
	*,
	spec: SpecParameters,
	scenario_path: str | Path,
	out_dir: str | Path,
	seed: int = 20251112,
) -> Dict[str, Path]:
	"""
	Run a paper-derived validation scenario.

	The scenario JSON is expected to contain:
	{
	  "name": "...",
	  "center_lat": 41.015, "center_lon": 28.979,
	  "radius_km": 10.0,
	  "num_aps": 900,
	  "duty_cycle": 0.04,
	  "ap_nominal_eirp_dbm": 30.0,
	  "environment": "urban",
	  "inr_limit_db": -6.0,
	  "path_model_policy": "selector",  // FSPL<=30m, WINNER2<1km, ITM>=1km (enforced by engine)
	  "bandwidth_probs": {"20":0.1,"40":0.1,"80":0.3,"160":0.3,"320":0.2},
	  "protection_margin_db": 0.0,
	  "channel_weighting": "uniform",
	  "incumbents": [
	    {"id":"FS_A","freq_center_mhz":6025.0,"bandwidth_mhz":30.0,"rx_lat":41.02,"rx_lon":28.98,"rx_antenna_gain_dbi":38.0},
	    ...
	  ]
	}
	"""
	p = Path(scenario_path)
	data = _load_json(p)

	center_lat = float(data.get("center_lat"))
	center_lon = float(data.get("center_lon"))
	radius_km = float(data.get("radius_km", 10.0))
	num_aps = int(data.get("num_aps", 300))
	ap_sites = generate_poisson_ap_field(
		center_lat=center_lat, center_lon=center_lon, radius_km=radius_km, fixed_num_aps=num_aps, seed=seed
	)

	incumbents = data.get("incumbents", [])

	# Map scenario to recipe args
	ap_nominal_eirp_dbm = float(data.get("ap_nominal_eirp_dbm", 30.0))
	duty_cycle = float(data.get("duty_cycle", 0.04))
	duration_s = int(data.get("duration_s", 300))
	inr_limit_db = float(data.get("inr_limit_db", -6.0))
	environment = str(data.get("environment", "urban"))
	path_model = str(data.get("path_model", "auto"))  # the selector is enforced in the engine/aggregate
	# Per-scenario, per-run subdirectory to avoid filename collisions
	ts = datetime.now().strftime("%Y%m%d_%H%M%S")
	scenario_slug = p.stem
	scenario_out = Path(out_dir) / "batch_runs" / f"{scenario_slug}_{ts}"
	scenario_out.mkdir(parents=True, exist_ok=True)
	out_dir = str(scenario_out)
	write_timeseries = bool(data.get("write_timeseries", True))
	# Default margin: 0 dB for LPI, 3 dB for SP/unknown (conservative to avoid unrealistically hot grants)
	_default_margin = 0.0 if str(data.get("device_class", "") or "").upper() == "LPI" else 3.0
	protection_margin_db = float(data.get("protection_margin_db", _default_margin))
	channel_weighting = str(data.get("channel_weighting", "uniform"))
	clutter_correction_db = float(data.get("clutter_correction_db", 0.0))
	# Strict paper fidelity: use only what the JSON specifies; do NOT invent defaults here
	device_class = str(data.get("device_class", "") or "").upper()
	ap_indoor_fraction = data.get("ap_indoor_fraction")
	building_entry_loss_db = data.get("building_entry_loss_db")

	# Bandwidth probabilities
	bw_probs = data.get("bandwidth_probs") or {"20":0.25,"40":0.25,"80":0.25,"160":0.25}
	bw_probs_f = {float(k): float(v) for k, v in bw_probs.items()}

	# Build args strictly from scenario
	recipe_kwargs: Dict[str, Any] = dict(
		spec=spec,
		incumbents=incumbents,
		ap_sites=ap_sites,
		ap_nominal_eirp_dbm=ap_nominal_eirp_dbm,
		duty_cycle=duty_cycle,
		duration_s=duration_s,
		inr_limit_db=inr_limit_db,
		environment=environment,
		path_model=path_model,
		out_dir=out_dir,
		seed=seed,
		write_timeseries=write_timeseries,
		protection_margin_db=protection_margin_db,
		channel_weighting=channel_weighting,
		bandwidth_probs=bw_probs_f,
		clutter_correction_db=clutter_correction_db,
	)
	if ap_indoor_fraction is not None:
		recipe_kwargs["ap_indoor_fraction"] = float(ap_indoor_fraction)
	if building_entry_loss_db is not None:
		recipe_kwargs["building_entry_loss_db"] = float(building_entry_loss_db)

	out_map = randomized_multibw_random_channels_unii5(**recipe_kwargs)
	# Attach scenario metadata
	out_map["scenario"] = scenario_slug  # type: ignore
	out_map["out_dir"] = scenario_out  # type: ignore
	return out_map


def run_paper_batch(
	*,
	spec: SpecParameters,
	scenarios_dir: str | Path,
	out_dir: str | Path,
	seed: int = 20251112,
) -> Tuple[Dict[str, Dict[str, Path]], Path]:
	"""
	Run all scenario JSONs in a directory, write per-scenario outputs into distinct
	subdirectories, and produce a batch summary CSV with key metrics aggregated
	per scenario and incumbent.
	"""
	sc_dir = Path(scenarios_dir)
	out_base = Path(out_dir)
	out_base.mkdir(parents=True, exist_ok=True)

	results: Dict[str, Dict[str, Path]] = {}
	rows: List[Dict[str, Any]] = []
	for sc_path in sorted(sc_dir.glob("*.json")):
		res = run_paper_scenario(spec=spec, scenario_path=sc_path, out_dir=out_base, seed=seed)
		results[sc_path.name] = {k: v for k, v in res.items() if isinstance(v, Path)}
		# Summarize: P_exceed from per_incumbent CSV; mean/tightest INR from timeseries CSV
		per_csv = res.get("per_incumbent_csv")
		ts_csv = res.get("timeseries_per_incumbent_csv")
		df_p = None; df_ts = None
		try:
			if per_csv:
				df_p = pd.read_csv(per_csv)
		except Exception:
			df_p = None
		try:
			if ts_csv:
				df_ts = pd.read_csv(ts_csv)
		except Exception:
			df_ts = None

		def _group_mean_max(df: pd.DataFrame) -> Dict[str, Tuple[float, float]]:
			out: Dict[str, Tuple[float, float]] = {}
			if df is None or df.empty:
				return out
			# enforce numeric
			df2 = df.copy()
			for c in ("inr_db",):
				if c in df2.columns:
					df2[c] = pd.to_numeric(df2[c], errors="coerce")
			for inc, g in df2.groupby("incumbent"):
				vs = g["inr_db"].dropna()
				if not vs.empty:
					out[str(inc)] = (float(vs.mean()), float(vs.max()))
			return out

		mean_max_by_inc: Dict[str, Tuple[float, float]] = _group_mean_max(df_ts) if df_ts is not None else {}

		if df_p is not None and not df_p.empty:
			for _, r in df_p.iterrows():
				inc = str(r.get("incumbent") or r.get("id") or "")
				p_exc = r.get("ipc_violation_probability_time") or r.get("P_exceed") or r.get("p_exceed")
				try:
					p_exc = float(p_exc)
				except Exception:
					p_exc = float("nan")
				mm = mean_max_by_inc.get(inc, (float("nan"), float("nan")))
				rows.append(
					{
						"scenario": res.get("scenario"),
						"incumbent": inc,
						"P_exceed": p_exc,
						"mean_inr_db": mm[0],
						"tightest_inr_db": mm[1],  # worst/most stringent = max INR
					}
				)

	# Write batch summary
	ts = datetime.now().strftime("%Y%m%d_%H%M%S")
	batch_summary = out_base / f"batch_summary_{ts}.csv"
	if rows:
		pd.DataFrame(rows).to_csv(batch_summary, index=False)
	return results, batch_summary
