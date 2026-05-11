"""Loaders and config utilities.

This module centralizes reading incumbent records (ULS-like JSON blocks) and
simple configs to reduce duplication across notebooks and CLI.
"""

import json
from pathlib import Path
from typing import List, Dict, Any


def load_incumbents_from_text(path: str | Path) -> List[dict]:
    text = Path(path).read_text(encoding="utf-8", errors="ignore")
    blocks: List[dict] = []
    buf: List[str] = []
    brace = 0
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("//") or "—" in s:
            continue
        if "{" in s:
            brace += s.count("{")
        if brace > 0:
            s = s.split("//")[0]
            buf.append(s)
        if "}" in s and brace > 0:
            brace -= s.count("}")
            if brace == 0 and buf:
                try:
                    blocks.append(json.loads("\n".join(buf)))
                except Exception:
                    pass
                buf = []
    return blocks


def normalize_incumbent_record(rec: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a raw incumbent record into fields our engine expects.

    Annex C mapping (simplified): ensures presence of keys:
      - freq_center_mhz, bandwidth_mhz
      - rx_lat, rx_lon, rx_antenna_gain_dbi, rx_antenna_azimuth_deg, rx_antenna_height_m
      - polarization, passive_sites
    """
    out = dict(rec)
    # Common aliases
    if "center_freq_mhz" in out and "freq_center_mhz" not in out:
        out["freq_center_mhz"] = out.pop("center_freq_mhz")
    if "bw_mhz" in out and "bandwidth_mhz" not in out:
        out["bandwidth_mhz"] = out.pop("bw_mhz")
    if "rx_latitude" in out and "rx_lat" not in out:
        out["rx_lat"] = out.pop("rx_latitude")
    if "rx_longitude" in out and "rx_lon" not in out:
        out["rx_lon"] = out.pop("rx_longitude")
    if "rx_gain_dbi" in out and "rx_antenna_gain_dbi" not in out:
        out["rx_antenna_gain_dbi"] = out.pop("rx_gain_dbi")
    if "rx_azimuth_deg" in out and "rx_antenna_azimuth_deg" not in out:
        out["rx_antenna_azimuth_deg"] = out.pop("rx_azimuth_deg")
    if "rx_height_m" in out and "rx_antenna_height_m" not in out:
        out["rx_antenna_height_m"] = out.pop("rx_height_m")
    # Ensure defaults
    out.setdefault("freq_center_mhz", 0.0)
    out.setdefault("bandwidth_mhz", 20.0)
    out.setdefault("rx_lat", 0.0)
    out.setdefault("rx_lon", 0.0)
    out.setdefault("rx_antenna_gain_dbi", 30.0)
    out.setdefault("rx_antenna_azimuth_deg", 0.0)
    out.setdefault("rx_antenna_height_m", 10.0)
    out.setdefault("polarization", "")
    out.setdefault("passive_sites", [])
    return out



