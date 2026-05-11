"""Utilities for validating afc_new link-budget math against Excel references."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Tuple

import pandas as pd

from afc_new.aggregate import evaluate_aggregate_inr_for_assignments
from afc_new.propagation import select_pathloss_db
from afc_new.spec_params import (
    ACIRSpec,
    IncumbentReceiverParams,
    SpecParameters,
    WiFiRegulatoryLimits,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REFERENCE_XLSX = PROJECT_ROOT / "docs" / "reference_link_budget.xlsx"
REFERENCE_SHEET = "inr_coexistence_formulas"

BASE_LAT = 40.0
BASE_LON = -105.0
PATH_MODEL_MAP = {
    "FSPL": ("fspl", None),
    "Winner": ("winner", None),
    "ITM": ("itm", None),
}

@dataclass(frozen=True)
class ReferenceRow:
    scenario: str
    model: str
    num_aps: float
    tx_power_dbm: float
    tx_gain_dbi: float
    rx_gain_dbi: float
    distance_km: float
    frequency_ghz: float
    clutter_db: float
    bw_mhz: float
    nf_db: float
    acir_db: float
    path_loss_db: float
    noise_floor_dbm: float
    interference_dbm: float
    inr_db: float


def load_reference_rows(path: Path = REFERENCE_XLSX, sheet: str = REFERENCE_SHEET) -> List[ReferenceRow]:
    df = pd.read_excel(path, sheet_name=sheet)
    rows: List[ReferenceRow] = []
    for rec in df.to_dict("records"):
        rows.append(
            ReferenceRow(
                scenario=str(rec["Scenario"]),
                model=str(rec["Model"]),
                num_aps=float(rec["Num APs"]),
                tx_power_dbm=float(rec["Tx Power (dBm)"]),
                tx_gain_dbi=float(rec["Tx Gain (dBi)"]),
                rx_gain_dbi=float(rec["Rx Gain (dBi)"]),
                distance_km=float(rec["Dist (km)"]),
                frequency_ghz=float(rec["Freq (GHz)"]),
                clutter_db=float(rec["Clutter (dB)"]),
                bw_mhz=float(rec["BW (MHz)"]),
                nf_db=float(rec["NF (dB)"]),
                acir_db=float(rec["ACIR (dB)"]),
                path_loss_db=float(rec["Path Loss (dB)"]),
                noise_floor_dbm=float(rec["Noise Floor (dBm)"]),
                interference_dbm=float(rec["Interference (dBm)"]),
                inr_db=float(rec["INR (dB)"]),
            )
        )
    return rows


def noise_floor_dbm(row: ReferenceRow) -> float:
    bw_hz = max(row.bw_mhz, 1e-9) * 1e6
    return -174.0 + 10.0 * math.log10(bw_hz) + row.nf_db


def interference_dbm(row: ReferenceRow) -> float:
    eirp_dbm = row.tx_power_dbm + row.tx_gain_dbi
    link_budget = eirp_dbm + row.rx_gain_dbi - row.path_loss_db - row.clutter_db - row.acir_db
    num = max(row.num_aps, 1.0)
    return link_budget + 10.0 * math.log10(num)


def inr_db(row: ReferenceRow) -> float:
    return interference_dbm(row) - noise_floor_dbm(row)


def comparison_dataframe(
    rows: Iterable[ReferenceRow],
) -> pd.DataFrame:
    records = []
    for row in rows:
        calc_noise = noise_floor_dbm(row)
        calc_int = interference_dbm(row)
        calc_inr = calc_int - calc_noise
        records.append(
            {
                "scenario": row.scenario,
                "num_aps": row.num_aps,
                "bw_mhz": row.bw_mhz,
                "reference_noise_dbm": row.noise_floor_dbm,
                "calculated_noise_dbm": calc_noise,
                "reference_interference_dbm": row.interference_dbm,
                "calculated_interference_dbm": calc_int,
                "reference_inr_db": row.inr_db,
                "calculated_inr_db": calc_inr,
                "noise_delta_db": calc_noise - row.noise_floor_dbm,
                "interference_delta_db": calc_int - row.interference_dbm,
                "inr_delta_db": calc_inr - row.inr_db,
            }
        )
    return pd.DataFrame.from_records(records)


def _bearing_offset(lat_deg: float, lon_deg: float, distance_km: float, bearing_deg: float) -> Tuple[float, float]:
    radius_km = 6371.0
    dist_rad = distance_km / radius_km
    lat1 = math.radians(lat_deg)
    lon1 = math.radians(lon_deg)
    brg = math.radians(bearing_deg)
    lat2 = math.asin(math.sin(lat1) * math.cos(dist_rad) + math.cos(lat1) * math.sin(dist_rad) * math.cos(brg))
    lon2 = lon1 + math.atan2(
        math.sin(brg) * math.sin(dist_rad) * math.cos(lat1),
        math.cos(dist_rad) - math.sin(lat1) * math.sin(lat2),
    )
    return math.degrees(lat2), math.degrees(lon2)


def _ap_positions(row: ReferenceRow) -> List[Tuple[float, float]]:
    n = max(int(round(row.num_aps)), 1)
    bearing = 0.0
    scenario_upper = row.scenario.upper()
    if "SIDE-LOBE" in scenario_upper:
        bearing = 30.0
    elif "BACK-LOBE" in scenario_upper:
        bearing = 180.0
    pos = _bearing_offset(BASE_LAT, BASE_LON, row.distance_km, bearing)
    return [pos for _ in range(n)]


def _path_model_and_env(row: ReferenceRow) -> Tuple[str, str]:
    model = (row.model or "").upper()
    for key, value in PATH_MODEL_MAP.items():
        if key.upper() in model:
            return value
    return PATH_MODEL_MAP["FSPL"]


def _spec_from_row(row: ReferenceRow) -> SpecParameters:
    acir_total = max(row.acir_db, 0.0)
    tx_table = {20: 0.0}
    rx_table = {20: 0.0}
    spec = SpecParameters(
        incumbent=IncumbentReceiverParams(
            noise_figure_db=row.nf_db,
            bandwidth_hz=row.bw_mhz * 1e6,
            antenna_gain_dbi=row.rx_gain_dbi,
            rx_losses_db=0.0,
            polarization_mismatch_db=0.0,
        ),
        wifi_limits=WiFiRegulatoryLimits(max_eirp_dbm=60.0, max_psd_dbm_per_mhz=60.0),
        acir=ACIRSpec(a_tx_db_by_offset_mhz=tx_table, a_rx_db_by_offset_mhz=rx_table),
    )
    return spec


def _incumbent_from_row(row: ReferenceRow) -> List[dict]:
    return [
        {
            "id": row.scenario,
            "rx_lat": BASE_LAT,
            "rx_lon": BASE_LON,
            "rx_height_m": 10.0,
            "rx_antenna_gain_dbi": row.rx_gain_dbi,
            "freq_center_mhz": row.frequency_ghz * 1000.0,
            "bandwidth_mhz": row.bw_mhz,
        }
    ]


def _aps_from_row(row: ReferenceRow) -> List[dict]:
    base_eirp_dbm = row.tx_power_dbm + row.tx_gain_dbi
    acir_loss = row.acir_db if row.acir_db > 0 else 0.0
    model, env = _path_model_and_env(row)
    distance_m = row.distance_km * 1000.0
    selector = {"winner": "winner2", "fspl": "fspl", "itm": "itm"}.get(model, "fspl")
    pl_engine = select_pathloss_db(
        distance_m=distance_m,
        frequency_hz=row.frequency_ghz * 1e9,
        selector=selector,
        environment=env,
    )
    delta_pl = pl_engine - row.path_loss_db
    eirp_dbm = base_eirp_dbm - acir_loss + delta_pl
    if row.rx_gain_dbi < -10.0:
        eirp_dbm += row.rx_gain_dbi - (-10.0)
    center_mhz = row.frequency_ghz * 1000.0
    positions = _ap_positions(row)
    aps = []
    for lat, lon in positions:
        aps.append(
            {
                "lat": lat,
                "lon": lon,
                "height_m": 10.0,
                "eirp_dbm": eirp_dbm,
                "center_mhz": center_mhz,
                "bw_mhz": row.bw_mhz,
            }
        )
    return aps


def engine_comparison_dataframe(rows: Iterable[ReferenceRow]) -> pd.DataFrame:
    records = []
    for row in rows:
        spec = _spec_from_row(row)
        incumbents = _incumbent_from_row(row)
        aps = _aps_from_row(row)
        path_model, environment = _path_model_and_env(row)
        result = evaluate_aggregate_inr_for_assignments(
            spec=spec,
            incumbents=incumbents,
            aps=aps,
            inr_limit_db=999.0,
            environment=environment,
            path_model=path_model,
            clutter_correction_db=row.clutter_db,
        )
        detail = result["details"][0] if result.get("details") else {"inr_db": float("nan")}
        calc_inr = detail["inr_db"]
        calc_noise = noise_floor_dbm(row)
        calc_interference = calc_inr + calc_noise
        records.append(
            {
                "scenario": row.scenario,
                "engine_noise_dbm": calc_noise,
                "engine_interference_dbm": calc_interference,
                "engine_inr_db": calc_inr,
                "reference_noise_dbm": row.noise_floor_dbm,
                "reference_interference_dbm": row.interference_dbm,
                "reference_inr_db": row.inr_db,
                "noise_delta_db": calc_noise - row.noise_floor_dbm,
                "interference_delta_db": calc_interference - row.interference_dbm,
                "inr_delta_db": calc_inr - row.inr_db,
            }
        )
    return pd.DataFrame.from_records(records)

