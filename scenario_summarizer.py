from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple
import json
import csv


def _read_json(p: Path) -> Dict[str, Any]:
	with p.open("r", encoding="utf-8") as f:
		return json.load(f)


def _norm_float(x: Any) -> float | None:
	if x is None:
		return None
	try:
		return float(x)
	except Exception:
		return None


def summarize_scenarios_to_csv(
	*,
	scenarios_dir: str | Path,
	out_csv: str | Path,
	delimiter: str = ";",
) -> Path:
	"""
	Build a single table summarizing all paper-derived scenario JSONs.

	- One row per scenario JSON
	- Scalar scenario fields as columns (e.g., duty_cycle, environment, etc.)
	- Bandwidth probabilities serialized as a compact JSON string
	- Incumbents flattened into repeated column groups up to the maximum count
	  across scenarios: inc{k}_{id,center_mhz,bw_mhz,rx_lat,rx_lon,rx_gain_dbi}
	- Uses a semicolon (';') delimiter to avoid conflicts with commas inside JSON
	  payloads (like bandwidth_probs)
	"""
	sc_dir = Path(scenarios_dir)
	out_csv = Path(out_csv)
	rows: List[Dict[str, Any]] = []
	files = sorted(sc_dir.glob("*.json"))
	max_inc = 0
	raws: List[Tuple[str, Dict[str, Any]]] = []
	for p in files:
		try:
			d = _read_json(p)
			raws.append((p.name, d))
			max_inc = max(max_inc, len(d.get("incumbents", [])))
		except Exception:
			continue

	# Header fields
	base_cols = [
		"scenario_file",
		"name",
		"center_lat",
		"center_lon",
		"radius_km",
		"num_aps",
		"ap_nominal_eirp_dbm",
		"device_class",
		"ap_indoor_fraction",
		"building_entry_loss_db",
		"duty_cycle",
		"duration_s",
		"inr_limit_db",
		"environment",
		"path_model",
		"path_model_policy",
		"protection_margin_db",
		"channel_weighting",
		"bandwidth_probs_json",
	]
	inc_cols: List[str] = []
	for k in range(1, max_inc + 1):
		inc_cols += [
			f"inc{k}_id",
			f"inc{k}_center_mhz",
			f"inc{k}_bandwidth_mhz",
			f"inc{k}_rx_lat",
			f"inc{k}_rx_lon",
			f"inc{k}_rx_gain_dbi",
		]
	header = base_cols + inc_cols

	for fname, d in raws:
		bw_probs = d.get("bandwidth_probs") or {}
		inc_list = d.get("incumbents", []) or []
		row: Dict[str, Any] = dict(
			scenario_file=fname,
			name=d.get("name"),
			center_lat=_norm_float(d.get("center_lat")),
			center_lon=_norm_float(d.get("center_lon")),
			radius_km=_norm_float(d.get("radius_km")),
			num_aps=int(d.get("num_aps", 0)) if d.get("num_aps") is not None else None,
			ap_nominal_eirp_dbm=_norm_float(d.get("ap_nominal_eirp_dbm")),
			device_class=(str(d.get("device_class")) if d.get("device_class") is not None else None),
			ap_indoor_fraction=_norm_float(d.get("ap_indoor_fraction")),
			building_entry_loss_db=_norm_float(d.get("building_entry_loss_db")),
			duty_cycle=_norm_float(d.get("duty_cycle")),
			duration_s=int(d.get("duration_s", 0)) if d.get("duration_s") is not None else None,
			inr_limit_db=_norm_float(d.get("inr_limit_db")),
			environment=(str(d.get("environment")) if d.get("environment") is not None else None),
			path_model=(str(d.get("path_model")) if d.get("path_model") is not None else None),
			path_model_policy=(str(d.get("path_model_policy")) if d.get("path_model_policy") is not None else None),
			protection_margin_db=_norm_float(d.get("protection_margin_db")),
			channel_weighting=(str(d.get("channel_weighting")) if d.get("channel_weighting") is not None else None),
			bandwidth_probs_json=json.dumps(bw_probs, separators=(",", ":"), ensure_ascii=False),
		)
		for k in range(max_inc):
			inc = inc_list[k] if k < len(inc_list) else {}
			row[f"inc{k+1}_id"] = inc.get("id")
			row[f"inc{k+1}_center_mhz"] = _norm_float(inc.get("freq_center_mhz") or inc.get("center_mhz"))
			row[f"inc{k+1}_bandwidth_mhz"] = _norm_float(inc.get("bandwidth_mhz") or inc.get("rx_bw_mhz"))
			row[f"inc{k+1}_rx_lat"] = _norm_float(inc.get("rx_lat") or inc.get("lat"))
			row[f"inc{k+1}_rx_lon"] = _norm_float(inc.get("rx_lon") or inc.get("lon"))
			row[f"inc{k+1}_rx_gain_dbi"] = _norm_float(inc.get("rx_antenna_gain_dbi") or inc.get("rx_gain_dbi"))
		rows.append(row)

	out_csv.parent.mkdir(parents=True, exist_ok=True)
	with out_csv.open("w", newline="", encoding="utf-8") as f:
		w = csv.DictWriter(f, fieldnames=header, delimiter=delimiter)
		w.writeheader()
		for r in rows:
			w.writerow(r)
	return out_csv


