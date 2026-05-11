from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pandas as pd


def _get(d: Dict[str, Any], key: str, default: Any = None) -> Any:
	v = d.get(key, default)
	return v if v is not None else default


def _fmt_bandwidth_probs(d: Dict[str, Any] | None) -> str:
	if not d:
		return ""
	try:
		items: List[Tuple[float, float]] = [(float(k), float(v)) for k, v in d.items()]
		items.sort(key=lambda x: x[0])
		return "|".join(f"{int(k) if k.is_integer() else k}:{v:g}" for k, v in items)  # type: ignore[attr-defined]
	except Exception:
		# Fallback to JSON string in one cell
		return json.dumps(d, separators=(",", ":"))


def _fmt_incumbents(lst: List[Dict[str, Any]] | None) -> Tuple[int, str]:
	if not lst:
		return 0, ""
	parts: List[str] = []
	for inc in lst:
		part = []
		for k in ("id", "link_id", "fs_id"):
			if k in inc and inc[k] is not None:
				part.append(f"id={inc[k]}")
				break
		if "freq_center_mhz" in inc:
			part.append(f"fc={inc['freq_center_mhz']}")
		if "bandwidth_mhz" in inc:
			part.append(f"bw={inc['bandwidth_mhz']}")
		if "rx_antenna_gain_dbi" in inc:
			part.append(f"g={inc['rx_antenna_gain_dbi']}")
		if "rx_lat" in inc and "rx_lon" in inc:
			part.append(f"lat={inc['rx_lat']}")
			part.append(f"lon={inc['rx_lon']}")
		# RPE flags
		if "rx_rpe_az" in inc or "rx_rpe_el" in inc:
			part.append("rpe=Y")
		parts.append(",".join(part))
	return len(lst), " || ".join(parts)


def build_scenario_catalog(
	*,
	scenarios_dir: str | Path,
	out_dir: str | Path,
) -> Path:
	"""Create a CSV catalog summarizing all scenario JSONs.

	- Columns include top-level parameters and compact incumbent info.
	- Dict/array fields are collapsed into single-cell strings using '|' between pairs/items.
	"""
	sc_dir = Path(scenarios_dir)
	out_base = Path(out_dir)
	out_base.mkdir(parents=True, exist_ok=True)

	rows: List[Dict[str, Any]] = []
	for p in sorted(sc_dir.glob("*.json")):
		try:
			data = json.loads(p.read_text(encoding="utf-8"))
		except Exception:
			continue
		name = _get(data, "name", p.stem)
		incs = _get(data, "incumbents", [])
		inc_count, inc_compact = _fmt_incumbents(incs)

		rows.append(
			{
				"scenario": name,
				"file": str(p),
				"center_lat": _get(data, "center_lat", ""),
				"center_lon": _get(data, "center_lon", ""),
				"radius_km": _get(data, "radius_km", ""),
				"num_aps": _get(data, "num_aps", ""),
				"device_class": _get(data, "device_class", ""),
				"ap_nominal_eirp_dbm": _get(data, "ap_nominal_eirp_dbm", ""),
				"ap_indoor_fraction": _get(data, "ap_indoor_fraction", ""),
				"building_entry_loss_db": _get(data, "building_entry_loss_db", ""),
				"duty_cycle": _get(data, "duty_cycle", ""),
				"duration_s": _get(data, "duration_s", ""),
				"inr_limit_db": _get(data, "inr_limit_db", ""),
				"environment": _get(data, "environment", ""),
				"path_model": _get(data, "path_model", ""),
				"path_model_policy": _get(data, "path_model_policy", ""),
				"protection_margin_db": _get(data, "protection_margin_db", ""),
				"channel_weighting": _get(data, "channel_weighting", ""),
				"bandwidth_probs": _fmt_bandwidth_probs(_get(data, "bandwidth_probs", {})),
				"incumbents_count": inc_count,
				"incumbents_compact": inc_compact,
			}
		)

	df = pd.DataFrame(rows)
	csv_path = out_base / "scenario_catalog.csv"
	# Use UTF-8 and standard comma; internal dicts/lists are pipe-delimited in a single cell
	df.to_csv(csv_path, index=False, encoding="utf-8")
	return csv_path


