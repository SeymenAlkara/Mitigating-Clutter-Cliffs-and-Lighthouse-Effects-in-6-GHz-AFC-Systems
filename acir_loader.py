"""ACIR mask loaders (JSON/CSV) and helper to apply to SpecParameters.

Accepted inputs:
- JSON file with keys "tx" and "rx" mapping offset MHz (string or number)
  to attenuation dB, e.g. {"tx": {"20": 32.0, "40": 35.0}, "rx": {"20": 28.0}}.
- CSV with header: offset_mhz,a_tx_db,a_rx_db (any missing cells ignored).

If a given side is missing at an offset, we leave it untouched; call ensure_defaults
upstream when combining with defaults.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Dict, Tuple
import json
import csv

from .spec_params import SpecParameters, ACIRSpec


def load_acir_from_json(path: str) -> Tuple[Dict[int, float], Dict[int, float]]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    a_tx: Dict[int, float] = {}
    a_rx: Dict[int, float] = {}
    for k, v in (data.get("tx", {}) or {}).items():
        try:
            a_tx[int(k)] = float(v)
        except Exception:
            continue
    for k, v in (data.get("rx", {}) or {}).items():
        try:
            a_rx[int(k)] = float(v)
        except Exception:
            continue
    return a_tx, a_rx


def load_acir_from_csv(path: str) -> Tuple[Dict[int, float], Dict[int, float]]:
    a_tx: Dict[int, float] = {}
    a_rx: Dict[int, float] = {}
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                off = int(float(row.get("offset_mhz", "")))
            except Exception:
                continue
            try:
                txv = row.get("a_tx_db")
                if txv is not None and txv != "":
                    a_tx[off] = float(txv)
            except Exception:
                pass
            try:
                rxv = row.get("a_rx_db")
                if rxv is not None and rxv != "":
                    a_rx[off] = float(rxv)
            except Exception:
                pass
    return a_tx, a_rx


def apply_acir_to_spec(spec: SpecParameters, a_tx: Dict[int, float], a_rx: Dict[int, float]) -> SpecParameters:
    merged_tx = dict(spec.acir.a_tx_db_by_offset_mhz)
    merged_rx = dict(spec.acir.a_rx_db_by_offset_mhz)
    merged_tx.update({int(k): float(v) for k, v in a_tx.items()})
    merged_rx.update({int(k): float(v) for k, v in a_rx.items()})
    return replace(spec, acir=ACIRSpec(a_tx_db_by_offset_mhz=merged_tx, a_rx_db_by_offset_mhz=merged_rx))


