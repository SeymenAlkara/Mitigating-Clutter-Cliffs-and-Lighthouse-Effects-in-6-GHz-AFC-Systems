"""Grant table generator for Wi‑Fi 6 GHz channels.

This module helps produce an "AFC-style" table for an Access Point (AP):
for each Wi‑Fi 6 GHz channel (center frequency and bandwidth), compute
the maximum allowed EIRP under the incumbent protection rule I/N <= -6 dB.

We keep it simple and very explicit so it is easy to follow:
- We create the list of Wi‑Fi 6 GHz channel centers for a given bandwidth.
- We assume a *hypothetical* Fixed Service (FS) receiver at a given center
  frequency (e.g., the middle of 5925–6425 MHz which is 6175 MHz).
- For each Wi‑Fi channel, we compute the *offset* from the FS center. That
  offset (e.g., 0, 20, 40 MHz) selects the adjacent-channel protection via ACIR.
- We compute path loss (AP -> FS) and the FS receiver noise, then derive the
  allowed EIRP for the AP on that channel.

Scope notes (what is included vs. pluggable):
- Exact FS bandwidth: supported. We honor incumbent field variants and the
  R2‑AIP‑19 precedence via fs_bandwidth.py when needed.
- Antenna radiation patterns and geometry: supported. We compute per‑incumbent
  distances/bearings and apply off‑axis discrimination; optional RPE tables are
  supported via antenna_rpe.py.
- Aggregate interference: handled in afc_new/aggregate.py (not within this
  per‑AP grant generator). Use that module for multi‑AP INR evaluation.
- Terrain/ITM: partial. ITM scaffolding exists (afc_new/itm.py) and can be
  selected via path_model='itm', but a certified Longley–Rice with terrain and
  reliability inputs should replace the scaffold for production.

WINNF-TS-1014 references:
- 9.1.1 Interference Protection Criteria and evaluation across co/adjacent channels
- R0-AIP-04 and R2-AIP-03 (first-adjacent and 1.5× checks)
"""

from dataclasses import dataclass
from typing import Iterable, List, Tuple
import csv
from pathlib import Path

from .spec_params import SpecParameters
import math
from .propagation import select_pathloss_db
from .link_budget import noise_power_dbm
from .fs_bandwidth import determine_fs_noise_bw_hz
from .allocator import allowed_eirp_dbm_with_spec, allowed_eirp_dbm_with_spec_multi, psd_dbm_per_mhz_from_eirp
from .link_budget import i_threshold_dbm
from .acir_masks import acir_db_from_masks
from .acir_defaults import ensure_defaults
from .geodesy import haversine_distance_m, initial_bearing_deg
from .antenna import AntennaPatternParams, off_axis_azimuth_deg, effective_gain_dbi
from .antenna_rpe import combined_rpe_gain_dbi
from .itm import longley_rice_pathloss_db
from .device_constraints import DeviceConstraints, apply_constraints_to_decision
try:  # Prefer exact ITU envelopes from the openafc_py clone for parity
	from openafc_py.antenna_itu import calc_itu699_gain as _calc_itu699_gain  # type: ignore
except Exception:  # pragma: no cover
	_calc_itu699_gain = None  # type: ignore
try:  # Prefer ACIR masks from openafc_py for parity
	from openafc_py.acir_chain import default_acir_maps as _ofa_acir_defaults, acir_db as _ofa_acir_db  # type: ignore
except Exception:  # pragma: no cover
	_ofa_acir_defaults = None  # type: ignore
	_ofa_acir_db = None  # type: ignore


# The Wi‑Fi 6 GHz 20 MHz channel grid uses a center at 5955 MHz for channel 1
# and increments of 5 MHz per channel number. For 20 MHz channels, valid centers
# are every 20 MHz (channel numbers 1, 5, 9, ...). We generate by center frequency
# directly to avoid channel-number confusion.


def enumerate_centers_mhz(lower_mhz: float, upper_mhz: float, bandwidth_mhz: float) -> List[float]:
	"""Generate canonical 6 GHz centers (MHz) within [lower, upper] for a given bandwidth.
	
	Anchors per 6 GHz CFI:
	- 20 MHz: 5955 MHz
	- 40 MHz: 5955 + 10 = 5965 MHz
	- 80 MHz: 5955 + 30 = 5985 MHz
	- 160 MHz: 5955 + 80 = 6035 MHz
	We then step by 20 MHz regardless of BW, which matches the standard 20 MHz raster.
	"""
	anchor_20 = 5955.0
	bw = float(bandwidth_mhz)
	# Parity shift relative to 20 MHz raster
	if abs(bw - 20.0) < 1e-6:
		anchor = anchor_20
	elif abs(bw - 40.0) < 1e-6:
		anchor = anchor_20 + 10.0
	elif abs(bw - 80.0) < 1e-6:
		anchor = anchor_20 + 30.0
	elif abs(bw - 160.0) < 1e-6:
		anchor = anchor_20 + 80.0
	else:
		# Fallback: align to 20 MHz raster
		anchor = anchor_20

	step = 20.0
	centers: List[float] = []
	# find the first center >= lower that fits parity
	# we advance from anchor by k*20
	k = math.ceil((lower_mhz - anchor) / step)
	if k < 0:
		k = 0
	c = anchor + k * step
	while c + bw / 2.0 <= upper_mhz + 1e-9:
		lo = c - bw / 2.0
		hi = c + bw / 2.0
		if lo >= lower_mhz - 1e-9 and hi <= upper_mhz + 1e-9:
			centers.append(round(c, 1))
		c += step
	return centers


def channel_number_from_center_mhz(center_mhz: float) -> int:
	"""Compute the Wi‑Fi 6 GHz channel number from center frequency.

	Channel number formula for 6 GHz: f_center_MHz = 5955 + 5*(ch - 1)
	=> ch = 1 + (f_center_MHz - 5955) / 5
	This returns an integer if the center is on the standard grid.
	"""
	return int(round(1 + (center_mhz - 5955.0) / 5.0))


@dataclass
class GrantRow:
	"""One line of the grant table for a (channel, bandwidth) entry."""
	channel_number: int
	center_mhz: float
	bandwidth_mhz: float
	offset_mhz: int
	path_loss_db: float
	noise_dbm: float
	allowed_eirp_dbm: float
	allowed_psd_dbm_per_mhz: float
	decision: str  # "grant" or "deny"
	# Optional trace fields (for debugging/analysis)
	limiting_incumbent: str | None = None
	limiting_mode: str | None = None  # "co" or "adj"
	acir_db_used: float | None = None


def build_grant_table_for_hypothetical_fs(    
	spec: SpecParameters,
	distance_m: float,
	lower_mhz: float = 5925.0,
	upper_mhz: float = 6425.0,
	fs_center_mhz: float = 6175.0,
	bandwidths_mhz: Iterable[float] = (20.0, 40.0, 80.0, 160.0),
	inr_limit_db: float = -6.0,
	environment: str | None = None,
	override_fs_bandwidth_hz: float | None = None,
	emission_designator: str | None = None,
	override_fs_gain_dbi: float | None = None,
	device_constraints: DeviceConstraints | None = None,
	indoor: bool = False,
	penetration_db: float | None = None,
	protection_margin_db: float = 0.0,
) -> List[GrantRow]:
	"""Create a grant table for the given distance using a hypothetical FS at fs_center_mhz.
    This function is the main calculator. It takes all the technical inputs and produces a table of which channels are allowed and at what power levels. 

	Args:
		spec: parsed spec parameters (NF, bandwidth, antenna gain, ACIR, limits)
		distance_m: AP to FS distance in meters
		lower_mhz / upper_mhz: channelable band limits to consider
		fs_center_mhz: hypothetical FS receiver center frequency (MHz)
		bandwidths_mhz: channel widths to consider (20/40/80/160)
		inr_limit_db: protection criterion (default -6 dB)
	"""
	rows: List[GrantRow] = []
	for bw in bandwidths_mhz:
		for center in enumerate_centers_mhz(lower_mhz, upper_mhz, bw):
			# Center delta (for reference); edge-to-edge offset is used for ACIR decisions
			center_delta = abs(center - fs_center_mhz)
			# Compute path loss at this channel's center frequency
			f_hz = center * 1e6
			pl_db = select_pathloss_db(distance_m=distance_m, frequency_hz=f_hz, environment=environment, indoor=indoor, penetration_db=penetration_db)
			# Compute FS noise (using FS bandwidth from spec; we could refine later)
			n_bw = determine_fs_noise_bw_hz(
				spec=spec,
				emission_designator=emission_designator,
				explicit_rx_bw_hz=override_fs_bandwidth_hz,
				ul_bandwidth_hz=None,
			)
			n_dbm = noise_power_dbm(n_bw, spec.incumbent.noise_figure_db)
			# Determine spectral overlap to decide co-channel vs adjacent handling
			ch_bw_mhz = bw
			fs_bw_mhz = n_bw / 1e6
			ch_lo = center - ch_bw_mhz / 2.0
			ch_hi = center + ch_bw_mhz / 2.0
			fs_lo = fs_center_mhz - fs_bw_mhz / 2.0
			fs_hi = fs_center_mhz + fs_bw_mhz / 2.0
			overlaps = min(ch_hi, fs_hi) - max(ch_lo, fs_lo)  # MHz

			if overlaps > 0:
				# Co-channel overlap region: no ACIR, enforce directly
				eirp_dbm = allowed_eirp_dbm_with_spec(
					n_dbm=n_dbm,
					inr_limit_db=inr_limit_db - protection_margin_db,
					path_loss_db=pl_db,
					spec=spec,
					channel_offset_mhz=None,
					eirp_regulatory_max_dbm=spec.wifi_limits.max_eirp_dbm,
					l_polarization_db=spec.incumbent.polarization_mismatch_db,
					override_g_rx_dbi=spec.incumbent.antenna_gain_dbi,
				)
			else:
				# Adjacent: compute ACIR at the actual offset via mask interpolation
				a_tx, a_rx = ensure_defaults(spec.acir.a_tx_db_by_offset_mhz, spec.acir.a_rx_db_by_offset_mhz)
				tx_points = sorted((float(k), float(v)) for k, v in a_tx.items())
				rx_points = sorted((float(k), float(v)) for k, v in a_rx.items())
				# Edge-to-edge offset (MHz): distance between nearest channel edges
				if ch_hi <= fs_lo:
					edge_offset = fs_lo - ch_hi
				else:
					edge_offset = ch_lo - fs_hi
				acir_val = acir_db_from_masks(edge_offset, tx_points, rx_points)
				eirp_dbm = allowed_eirp_dbm_with_spec(
					n_dbm=n_dbm,
					inr_limit_db=inr_limit_db - protection_margin_db,
					path_loss_db=pl_db,
					spec=spec,
					channel_offset_mhz=int(round(edge_offset)) if edge_offset > 0 else None,
					eirp_regulatory_max_dbm=spec.wifi_limits.max_eirp_dbm,
					l_polarization_db=spec.incumbent.polarization_mismatch_db,
					override_g_rx_dbi=spec.incumbent.antenna_gain_dbi,
				)
			psd_dbm_mhz = psd_dbm_per_mhz_from_eirp(eirp_dbm, bw)
			if device_constraints is not None:
				is_ok = apply_constraints_to_decision(eirp_dbm, psd_dbm_mhz, device_constraints)
				decision = "grant" if is_ok else "deny"
			else:
				decision = "grant" if eirp_dbm >= 0.0 else "deny"
			rows.append(
				GrantRow(
					channel_number=channel_number_from_center_mhz(center),
					center_mhz=center,
					bandwidth_mhz=bw,
					offset_mhz=(0 if overlaps > 0 else int(round(edge_offset))),
					path_loss_db=pl_db,
					noise_dbm=n_dbm,
					allowed_eirp_dbm=eirp_dbm,
					allowed_psd_dbm_per_mhz=psd_dbm_mhz,
					decision=decision,
					limiting_incumbent=None,
					limiting_mode=("co" if overlaps > 0 else "adj"),
					acir_db_used=(None if overlaps > 0 else acir_val),
				)
			)
	return rows


def build_grant_table_both_blocks(
	spec: SpecParameters,
	distance_m: float,
	fs_center_mhz: float = 6175.0,
	bandwidths_mhz: Iterable[float] = (20.0, 40.0, 80.0, 160.0),
	inr_limit_db: float = -6.0,
	environment: str | None = None,
	override_fs_bandwidth_hz: float | None = None,
	override_fs_gain_dbi: float | None = None,
) -> List[GrantRow]:
	"""Convenience: build grant table for 5925–6425 and 6525–6875, skipping the gap."""
	rows = []
	rows += build_grant_table_for_hypothetical_fs(
		spec=spec,
		distance_m=distance_m,
		lower_mhz=5925.0,
		upper_mhz=6425.0,
		fs_center_mhz=fs_center_mhz,
		bandwidths_mhz=bandwidths_mhz,
		inr_limit_db=inr_limit_db,
		environment=environment,
		override_fs_bandwidth_hz=override_fs_bandwidth_hz,
		override_fs_gain_dbi=override_fs_gain_dbi,
	)
	rows += build_grant_table_for_hypothetical_fs(
		spec=spec,
		distance_m=distance_m,
		lower_mhz=6525.0,
		upper_mhz=6875.0,
		fs_center_mhz=fs_center_mhz,
		bandwidths_mhz=bandwidths_mhz,
		inr_limit_db=inr_limit_db,
		environment=environment,
		override_fs_bandwidth_hz=override_fs_bandwidth_hz,
		override_fs_gain_dbi=override_fs_gain_dbi,
	)
	return rows


def build_grant_table_with_incumbents(
    spec: SpecParameters,
    incumbents: Iterable[dict],
    distance_m: float | None = None,
    ap_lat: float | None = None,
    ap_lon: float | None = None,
    lower_mhz: float = 5925.0,
    upper_mhz: float = 6425.0,
    bandwidths_mhz: Iterable[float] = (20.0, 40.0, 80.0, 160.0),
    inr_limit_db: float = -6.0,
    environment: str | None = None,
    path_model: str = "auto",  # "auto"|"fspl"|"winner"|"two_slope"|"itm"
    device_constraints: DeviceConstraints | None = None,
    indoor: bool = False,
    penetration_db: float | None = None,
	protection_margin_db: float = 0.0,
) -> List[GrantRow]:
    """Compute a single grant table considering all incumbents simultaneously.

    For each Wi‑Fi channel, we compute the allowed EIRP against each incumbent and
    take the minimum (most restrictive). Co-channel is triggered by spectral overlap
    (channel and FS bandwidths overlap); otherwise ACIR is applied at the actual
    center frequency offset using mask interpolation.
    """
    # Precompute incumbents derived params
    def _v(d: dict, keys: list[str], default=None):
        for k in keys:
            if k in d and d[k] is not None:
                return d[k]
        return default

    inc_params: List[tuple[float, float, float, float, float, float, str, list | None, list | None, float | None, str]] = []
    # (fs_center_mhz, fs_bw_mhz, fs_rx_gain, rx_lat, rx_lon, rx_az_deg, pol, rpe_az, rpe_el, rx_h_m, link_id)
    for inc in incumbents:
        fs_center_mhz = float(_v(inc, ["freq_center_mhz", "center_mhz", "fs_center_mhz"]))
        # Prefer explicit receiver noise BW (rx_noise_bw_mhz), then rx_bw_mhz, then declared FS bandwidth; default 20 MHz
        fs_bw_mhz = float(_v(inc, ["rx_noise_bw_mhz", "rx_bw_mhz", "bandwidth_mhz", "fs_bandwidth_mhz"], 20.0))
        link_id_root = str(_v(inc, ["link_id", "fs_id", "id"], "unknown"))

        # Helper to add one receiver site (primary or passive)
        def _add_site(rx_lat_val, rx_lon_val, rx_gain_val, rx_az_val, pol_val, rpe_az_val, rpe_el_val, rx_h_val, suffix=""):
            inc_params.append((
                fs_center_mhz,
                fs_bw_mhz,
                float(rx_gain_val) if rx_gain_val is not None else float(inc.get("rx_antenna_gain_dbi", spec.incumbent.antenna_gain_dbi)),
                float(rx_lat_val),
                float(rx_lon_val),
                float(rx_az_val) if rx_az_val is not None else float(inc.get("rx_antenna_azimuth_deg", 0.0)),
                str(pol_val).upper()[:1] if pol_val is not None else str(inc.get("polarization", "")).upper()[:1],
                rpe_az_val if rpe_az_val is not None else inc.get("rx_rpe_az"),
                rpe_el_val if rpe_el_val is not None else inc.get("rx_rpe_el"),
                rx_h_val if rx_h_val is not None else inc.get("rx_antenna_height_m"),
                f"{link_id_root}{suffix}",
            ))

        # Primary FS receiver
        _add_site(
            rx_lat_val=_v(inc, ["rx_lat", "lat"], 0.0),
            rx_lon_val=_v(inc, ["rx_lon", "lon"], 0.0),
            rx_gain_val=_v(inc, ["rx_antenna_gain_dbi", "rx_gain_dbi"], spec.incumbent.antenna_gain_dbi),
            rx_az_val=_v(inc, ["rx_antenna_azimuth_deg", "rx_azimuth_deg", "az_deg"], 0.0),
            pol_val=_v(inc, ["polarization"], ""),
            rpe_az_val=inc.get("rx_rpe_az"),
            rpe_el_val=inc.get("rx_rpe_el"),
            rx_h_val=_v(inc, ["rx_antenna_height_m", "rx_height_m", "height_m"]),
            suffix="",
        )

        # Passive sites (optional): list of dicts with lat/lon/gain_dbi/az_deg
        passive_sites = inc.get("passive_sites")
        if isinstance(passive_sites, list):
            for idx, ps in enumerate(passive_sites, start=1):
                _add_site(
                    rx_lat_val=ps.get("lat", _v(inc, ["rx_lat", "lat"], 0.0)),
                    rx_lon_val=ps.get("lon", _v(inc, ["rx_lon", "lon"], 0.0)),
                    rx_gain_val=ps.get("gain_dbi", _v(inc, ["rx_antenna_gain_dbi", "rx_gain_dbi"], spec.incumbent.antenna_gain_dbi)),
                    rx_az_val=ps.get("az_deg", _v(inc, ["rx_antenna_azimuth_deg", "rx_azimuth_deg", "az_deg"], 0.0)),
                    pol_val=ps.get("polarization", _v(inc, ["polarization"], "")),
                    rpe_az_val=ps.get("rpe_az", inc.get("rx_rpe_az")),
                    rpe_el_val=ps.get("rpe_el", inc.get("rx_rpe_el")),
                    rx_h_val=ps.get("height_m", _v(inc, ["rx_antenna_height_m", "rx_height_m", "height_m"])),
                    suffix=f":PS{idx}",
                )

    rows: List[GrantRow] = []
    for bw in bandwidths_mhz:
        # If the requested band is exactly one channel wide, force the center to the midpoint
        band_width = upper_mhz - lower_mhz
        if abs(band_width - bw) < 1e-6:
            centers_iter = [(lower_mhz + upper_mhz) / 2.0]
        else:
            centers_iter = enumerate_centers_mhz(lower_mhz, upper_mhz, bw)
        for center in centers_iter:
            f_hz = center * 1e6
            # If a per-incumbent geographic distance is intended, pass None here and compute per FS below
            pl_db = None

            # Evaluate per incumbent and keep the minimum allowed EIRP
            best_eirp = spec.wifi_limits.max_eirp_dbm
            best_pl_db = None
            limiting = None
            limiting_mode = None
            limiting_acir = None
            limiting_offset = 0
            for fs_center_mhz, fs_bw_mhz, fs_rx_gain, rx_lat, rx_lon, rx_az, pol, rpe_az, rpe_el, rx_h_m, link_id in inc_params:
                # center delta (reference only)
                center_delta = abs(center - fs_center_mhz)
                ch_lo = center - bw / 2.0
                ch_hi = center + bw / 2.0
                fs_lo = fs_center_mhz - fs_bw_mhz / 2.0
                fs_hi = fs_center_mhz + fs_bw_mhz / 2.0
                overlaps = min(ch_hi, fs_hi) - max(ch_lo, fs_lo)

                # Path loss for this incumbent: either use provided distance_m or compute from AP=FS Rx coords if available
                if distance_m is not None:
                    d_m = distance_m
                    brg = None
                else:
                    # Use provided AP coordinates
                    lat0 = ap_lat if ap_lat is not None else 41.0
                    lon0 = ap_lon if ap_lon is not None else 29.0
                    d_nom = haversine_distance_m(lat0, lon0, rx_lat, rx_lon)
                    # Include horizontal uncertainty (~10 m) conservatively
                    d_m = max(1.0, d_nom - 10.0)
                    brg = initial_bearing_deg(lat0, lon0, rx_lat, rx_lon)
                # Path loss model selection (evaluate at incumbent center frequency to mirror openafc_py)
                f_hz_inc = fs_center_mhz * 1e6
                if path_model == "fspl":
                    pl_db_inc = select_pathloss_db(distance_m=d_m, frequency_hz=f_hz_inc, environment=environment, selector="fspl", indoor=indoor, penetration_db=penetration_db)
                elif path_model == "winner":
                    pl_db_inc = select_pathloss_db(distance_m=d_m, frequency_hz=f_hz_inc, environment=environment, selector="winner2", indoor=indoor, penetration_db=penetration_db)
                elif path_model == "two_slope":
                    pl_db_inc = select_pathloss_db(distance_m=d_m, frequency_hz=f_hz_inc, environment=environment, indoor=indoor, penetration_db=penetration_db)
                elif path_model == "itm":
                    # Align default RX height with clone (20 m) when scenario omits it
                    rx_h_val = float(rx_h_m) if rx_h_m else 20.0
                    pl_db_inc = longley_rice_pathloss_db(distance_m=d_m, frequency_hz=f_hz_inc, tx_height_m=10.0, rx_height_m=rx_h_val, climate=environment)
                else:  # auto
                    pl_db_inc = select_pathloss_db(distance_m=d_m, frequency_hz=f_hz_inc, environment=environment, indoor=indoor, penetration_db=penetration_db)

                # Apply FS antenna pattern discrimination using azimuth only
                if brg is not None:
                    delta_az = off_axis_azimuth_deg(rx_az, (brg + 180.0) % 360.0)
                    # Prefer ITU‑R F.699 envelope when explicitly requested (parity with openafc_py)
                    if bool(inc.get("use_itu699", False)) and _calc_itu699_gain is not None:
                        g_eff = _calc_itu699_gain(delta_az, fs_rx_gain)  # type: ignore[misc]
                    elif rpe_az and rpe_el:
                        g_eff = combined_rpe_gain_dbi(fs_rx_gain, delta_az, 0.0, rpe_az, rpe_el)
                    else:
                        patt = AntennaPatternParams(g_max_dbi=fs_rx_gain)
                        g_eff = effective_gain_dbi(patt, delta_az, 0.0)
                else:
                    g_eff = fs_rx_gain

                # Receiver noise per incumbent (use fs_bw_mhz from above)
                n_dbm = noise_power_dbm(fs_bw_mhz * 1e6, spec.incumbent.noise_figure_db)

                if overlaps > 0:
                    eirp = allowed_eirp_dbm_with_spec(
                        n_dbm=n_dbm,
                        inr_limit_db=inr_limit_db - protection_margin_db,
                        path_loss_db=pl_db_inc,
                        spec=spec,
                        channel_offset_mhz=None,
                        eirp_regulatory_max_dbm=spec.wifi_limits.max_eirp_dbm,
                        l_polarization_db=spec.incumbent.polarization_mismatch_db,
                        override_g_rx_dbi=g_eff,
                    )
                    mode = "co"
                    acir_used = None
                else:
                    # Edge-to-edge offset (MHz): distance between nearest edges
                    if ch_hi <= fs_lo:
                        edge_offset = fs_lo - ch_hi
                    else:
                        edge_offset = ch_lo - fs_hi
                    # ACIR value: use openafc_py default masks if available; otherwise fall back to local spec masks
                    if _ofa_acir_db is not None and _ofa_acir_defaults is not None:
                        a_tx_def, a_rx_def = _ofa_acir_defaults(None, None)  # type: ignore[misc]
                        acir_val = float(_ofa_acir_db(edge_offset, a_tx_def, a_rx_def))  # type: ignore[misc]
                    else:
                        a_tx, a_rx = ensure_defaults(spec.acir.a_tx_db_by_offset_mhz, spec.acir.a_rx_db_by_offset_mhz)
                        tx_points = sorted((float(k), float(v)) for k, v in a_tx.items())
                        rx_points = sorted((float(k), float(v)) for k, v in a_rx.items())
                        acir_val = acir_db_from_masks(edge_offset, tx_points, rx_points)
                    # Direct EIRP computation to honor the exact ACIR value
                    i_thr = i_threshold_dbm(n_dbm=n_dbm, inr_limit_db=(inr_limit_db - protection_margin_db))
                    eirp = i_thr + float(acir_val) + pl_db_inc - float(g_eff) + float(spec.incumbent.rx_losses_db) + float(spec.incumbent.polarization_mismatch_db)
                    mode = "adj"
                    acir_used = acir_val
                if eirp < best_eirp:
                    best_eirp = eirp
                    best_pl_db = pl_db_inc
                    limiting = link_id
                    limiting_mode = mode
                    limiting_acir = acir_used
                    limiting_offset = (0 if overlaps > 0 else int(round(edge_offset)))

            # Fallback: if best_pl_db is still None (should not happen), approximate with
            # distance_m if provided or 3 km default
            if best_pl_db is None:
                d_fallback = distance_m if distance_m is not None else 3000.0
                best_pl_db = select_pathloss_db(distance_m=d_fallback, frequency_hz=f_hz, environment=environment)

            # Apply PSD cap binding before computing PSD value
            try:
                psd_cap = getattr(spec.wifi_limits, 'max_psd_dbm_per_mhz', None)
                if psd_cap is not None:
                    psd_total_cap = float(psd_cap) + 10.0 * math.log10(bw)
                    best_eirp = min(best_eirp, spec.wifi_limits.max_eirp_dbm, psd_total_cap)
                else:
                    best_eirp = min(best_eirp, spec.wifi_limits.max_eirp_dbm)
            except Exception:
                pass

            # If no incumbent limited the channel, keep limiting fields as None
            psd_dbm_mhz = psd_dbm_per_mhz_from_eirp(best_eirp, bw)
            if device_constraints is not None:
                is_ok = apply_constraints_to_decision(best_eirp, psd_dbm_mhz, device_constraints)
                decision = "grant" if is_ok else "deny"
            else:
                decision = "grant" if best_eirp >= 0.0 else "deny"
            rows.append(
                GrantRow(
                    channel_number=channel_number_from_center_mhz(center),
                    center_mhz=center,
                    bandwidth_mhz=bw,
                    offset_mhz=limiting_offset,
                    path_loss_db=best_pl_db,
                    noise_dbm=n_dbm,
                    allowed_eirp_dbm=best_eirp,
                    allowed_psd_dbm_per_mhz=psd_dbm_mhz,
                    decision=decision,
                    limiting_incumbent=limiting,
                    limiting_mode=limiting_mode,
                    acir_db_used=limiting_acir,
                )
            )
    return rows


def grant_rows_to_table(rows: Iterable[GrantRow]) -> List[List[str]]:
	"""Convert grant rows to a simple printable/CSV table."""
	table = [[
		"channel", "center_mhz", "bw_mhz", "offset_mhz",
		"path_loss_db", "noise_dbm", "allowed_eirp_dbm", "allowed_psd_dBm_per_MHz", "decision",
	]]
	for r in rows:
		table.append([
			str(r.channel_number),
			f"{r.center_mhz:.1f}",
			f"{r.bandwidth_mhz:.0f}",
			str(r.offset_mhz),
			f"{r.path_loss_db:.2f}",
			f"{r.noise_dbm:.2f}",
			f"{r.allowed_eirp_dbm:.2f}",
			f"{r.allowed_psd_dbm_per_mhz:.2f}",
			r.decision,
		])
	return table


def save_grant_table_csv(rows: Iterable[GrantRow], path: str | Path) -> None:
	"""Save grant rows to a CSV file.

	Columns: channel, center_mhz, bw_mhz, offset_mhz, path_loss_db, noise_dbm,
	allowed_eirp_dbm, allowed_psd_dBm_per_MHz, decision
	"""
	table = grant_rows_to_table(rows)
	p = Path(path)
	with p.open("w", newline="", encoding="utf-8") as f:
		writer = csv.writer(f)
		writer.writerows(table)

