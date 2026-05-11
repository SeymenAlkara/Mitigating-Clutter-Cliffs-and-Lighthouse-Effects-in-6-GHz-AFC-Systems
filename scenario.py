"""Scenario runner for AFC allowed EIRP calculations.

This module provides a very simple way to evaluate allowed EIRP for a set of
channels and device-to-incumbent distances. It uses:
- Parsed spec parameters (e.g., incumbent NF, bandwidth, antenna gain, ACIR tables)
- A propagation selector to compute path loss
- The EIRP allocator with I/N <= -6 dB

The goal is educational clarity over completeness. We can expand the scenario
format to include GIS, antenna patterns, and terrain later.
"""

from dataclasses import dataclass
from typing import Iterable, List, Optional

from .spec_params import SpecParameters
from .propagation import select_pathloss_db
from .link_budget import noise_power_dbm
from .allocator import allowed_eirp_dbm_with_spec


@dataclass
class Scenario:
	"""Minimal scenario definition.

	Fields:
	- frequency_hz: carrier frequency (e.g., 6.0e9 for 6 GHz)
	- distances_m: list of distances from Wi‑Fi AP to the fixed service receiver (meters)
	- channel_offsets_mhz: list of channel offsets to test; use 0 for co-channel,
	  20 for ±20 MHz adjacent, etc.
	- inr_limit_db: protection criterion (use -6.0 as per FCC/WINNF guidance)
	"""
	frequency_hz: float
	distances_m: List[float]
	channel_offsets_mhz: List[int]
	inr_limit_db: float = -6.0


@dataclass
class ResultRow:
	"""One row of results for a distance/offset pair."""
	distance_m: float
	channel_offset_mhz: int
	path_loss_db: float
	noise_dbm: float
	allowed_eirp_dbm: float


def run_scenario(spec: SpecParameters, scenario: Scenario) -> List[ResultRow]:
	"""Compute allowed EIRP for each distance and channel offset.

	Steps per pair:
	1) Compute path loss using the selector (WINNER-II placeholder at short range,
	   ITM-like placeholder for longer range).
	2) Compute noise power at the incumbent receiver using its bandwidth and NF
	   from the spec.
	3) Compute allowed EIRP using I/N <= -6 dB (or scenario.inr_limit_db) and
	   ACIR if offset > 0.
	"""
	rows: List[ResultRow] = []
	for d_m in scenario.distances_m:
		pl_db = select_pathloss_db(distance_m=d_m, frequency_hz=scenario.frequency_hz)
		n_dbm = noise_power_dbm(spec.incumbent.bandwidth_hz, spec.incumbent.noise_figure_db)
		for off in scenario.channel_offsets_mhz:
			eirp = allowed_eirp_dbm_with_spec(
				n_dbm=n_dbm,
				inr_limit_db=scenario.inr_limit_db,
				path_loss_db=pl_db,
				spec=spec,
				channel_offset_mhz=(None if off == 0 else off),
			)
			rows.append(ResultRow(
				distance_m=d_m,
				channel_offset_mhz=off,
				path_loss_db=pl_db,
				noise_dbm=n_dbm,
				allowed_eirp_dbm=eirp,
			))
	return rows


def rows_to_table(rows: Iterable[ResultRow]) -> List[List[str]]:
	"""Convert results to a simple table (strings) for printing or CSV export."""
	table = [["distance_m", "offset_mhz", "path_loss_db", "noise_dbm", "allowed_eirp_dbm"]]
	for r in rows:
		table.append([
			f"{r.distance_m:.1f}",
			str(r.channel_offset_mhz),
			f"{r.path_loss_db:.2f}",
			f"{r.noise_dbm:.2f}",
			f"{r.allowed_eirp_dbm:.2f}",
		])
	return table


def print_table(table: List[List[str]]) -> None:
	"""Pretty-print a simple table to the console."""
	# Compute column widths
	widths = [max(len(row[i]) for row in table) for i in range(len(table[0]))]
	for i, row in enumerate(table):
		line = "  ".join(cell.ljust(widths[j]) for j, cell in enumerate(row))
		print(line)
