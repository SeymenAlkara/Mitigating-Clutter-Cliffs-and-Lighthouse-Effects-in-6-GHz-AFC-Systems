"""WINNF-TS-3007 AFC–SPD messaging (handler).

Implements section 6.2–6.3 request/response shape with validation and returns
standard response codes. Supported query modes:
- Channel-Based (NR‑U): accepts globalOperatingClass/channelCfi or bandwidthMHz
  fallback; maps CFIs to center MHz via Annex A. Builds availableChannelInfo
  with maxEirp arrays. Location may be provided as request.location or
  request.device.location.
- Frequency-Based: accepts inquiredFrequencyRange as list or single dict, with
  keys {lowMHz, highMHz} or {startMHz, endMHz}. Computes 1 MHz bins and, by
  default, merges adjacent bins that have identical PSD (configurable via
  mergeBins/mergeToleranceDb). Builds availableFrequencyInfo with per-range
  maxPsd.

Also supports optional overrides via keywords (environment, path_model,
protection_margin_db) that are threaded into the request for convenience.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Tuple

from .spec_params import SpecParameters
from .spectrum_inquiry import spectrum_inquiry
from .grant_table import build_grant_table_with_incumbents
from .link_budget import noise_power_dbm
from .propagation import select_pathloss_db
from .geodesy import haversine_distance_m, initial_bearing_deg
from .antenna import AntennaPatternParams, off_axis_azimuth_deg, effective_gain_dbi
from .antenna_rpe import combined_rpe_gain_dbi
from .acir_defaults import ensure_defaults
from .acir_masks import acir_db_from_masks
from .allocator import allowed_eirp_dbm_with_spec


# Response codes per TS-3007 §6.2/6.3
RC_SUCCESS = 0
RC_DEVICE_DISALLOWED = 101
RC_MISSING_PARAM = 102
RC_INVALID_VALUE = 103
RC_UNEXPECTED_PARAM = 106
RC_UNSUPPORTED_BASIS = 301


def _expiry_iso8601(seconds: int = 900) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()


def _is_number(x: Any) -> bool:
    try:
        float(x)
        return True
    except Exception:
        return False


def nru_goc_to_bw_mhz(goc: int) -> float | None:
    # Minimal placeholder mapping; may not include Wi‑Fi Operating Classes like 134
    mapping = {300: 20.0, 301: 40.0, 302: 60.0, 303: 80.0, 304: 100.0}
    return mapping.get(goc)


def nru_cfi_to_center_mhz(cfi: int) -> float:
    # Annex A: Fc (MHz) = 3000 + 15 * (CFI - 600000) / 1000
    return 3000.0 + 15.0 * (float(cfi) - 600000.0) / 1000.0


def handle_available_spectrum_inquiry(
    request: Dict[str, Any],
    spec: SpecParameters,
    incumbents: Iterable[Dict[str, Any]],
    *,
    # Optional policy controls; if provided, they override/mutate the request fields for convenience
    environment: str | None = None,
    path_model: str | None = None,
    protection_margin_db: float | None = None,
    # Certification filters
    certified_ids: Iterable[str] | None = None,
    disallowed_ids: Iterable[str] | None = None,
    disallowed_pairs: Iterable[Tuple[str, str]] | None = None,
    # Back-compat: allow a params_text_path kw (ignored here; parser happens outside)
    params_text_path: str | None = None,
) -> Dict[str, Any]:
    # Thread optional overrides into the request for consistent downstream use
    if environment is not None:
        request["environment"] = environment
    if path_model is not None:
        request["pathModel"] = path_model
    if protection_margin_db is not None:
        request["protectionMarginDb"] = float(protection_margin_db)
    # Basic validation: location
    missing: List[str] = []
    # Accept either top-level {"location":{...}} or {"device":{"location":{...}}}
    loc = request.get("location")
    if not isinstance(loc, dict) and isinstance(request.get("device"), dict):
        dev = request.get("device") or {}
        loc = dev.get("location") if isinstance(dev, dict) else None
    if not isinstance(loc, dict):
        missing.append("location")
    else:
        if not _is_number(loc.get("lat")):
            missing.append("location.lat")
        if not _is_number(loc.get("lon")):
            missing.append("location.lon")
        # §6.2 unexpected if multiple horizontal uncertainty fields present; reject if more than one given
        horiz_fields = [f for f in ("ellipse", "linearPolygon", "radialPolygon") if f in loc]
        if len(horiz_fields) > 1:
            return {"responseCode": RC_UNEXPECTED_PARAM, "supplementalInfo": {"unexpectedParams": horiz_fields}}
    if missing:
        return {
            "responseCode": RC_MISSING_PARAM,
            "supplementalInfo": {"missingParams": missing},
        }
    ap_lat = float(loc["lat"])  # type: ignore[index]
    ap_lon = float(loc["lon"])  # type: ignore[index]

    # §6.2 certification/disallowed lists (optional enforcement)
    cert = request.get("certification", {}) if isinstance(request.get("certification"), dict) else {}
    cert_id = cert.get("id")
    serial = cert.get("serialNumber")
    if certified_ids is not None and cert_id is not None:
        if cert_id not in set(certified_ids):
            return {"responseCode": RC_INVALID_VALUE, "supplementalInfo": {"invalidParams": ["certification.id"]}}
    if disallowed_ids is not None and cert_id is not None:
        if cert_id in set(disallowed_ids):
            return {"responseCode": RC_DEVICE_DISALLOWED}
    if disallowed_pairs is not None and cert_id is not None and serial is not None:
        if (cert_id, str(serial)) in set(disallowed_pairs):
            return {"responseCode": RC_DEVICE_DISALLOWED}

    # Decide which method is requested
    freq_req = request.get("inquiredFrequencyRange")
    chan_req = request.get("inquiredChannels")

    # If both are present -> unexpected per §6.2
    if isinstance(freq_req, list) and isinstance(chan_req, list):
        return {
            "responseCode": RC_UNEXPECTED_PARAM,
            "supplementalInfo": {"unexpectedParams": ["inquiredFrequencyRange", "inquiredChannels"]},
        }

    # Frequency-based query
    # Normalize frequency request: allow dict {startMHz/endMHz} or {lowMHz/highMHz}
    if isinstance(freq_req, dict):
        freq_req = [freq_req]
    if isinstance(freq_req, list):
        # If minDesiredPower is included in a pure frequency-based query: UNEXPECTED_PARAM (per §6.3.3)
        if "minDesiredPower" in request:
            return {"responseCode": RC_UNEXPECTED_PARAM, "supplementalInfo": {"unexpectedParams": ["minDesiredPower"]}}
        # Build 1 MHz bins per range and compute PSD per bin, then merge identical bins
        env = request.get("environment", "urban")
        model = request.get("pathModel", "auto")
        margin = float(request.get("protectionMarginDb", 0.0))
        results = []  # list of AvailableFrequencyInfo {frequencyRange:{low,high}, maxPsd}
        for fr in freq_req:
            try:
                if "lowMHz" in fr and "highMHz" in fr:
                    lo = float(fr["lowMHz"])  # type: ignore[index]
                    hi = float(fr["highMHz"])  # type: ignore[index]
                elif "startMHz" in fr and "endMHz" in fr:
                    lo = float(fr["startMHz"])  # type: ignore[index]
                    hi = float(fr["endMHz"])  # type: ignore[index]
                else:
                    raise KeyError
            except Exception:
                return {"responseCode": RC_INVALID_VALUE, "supplementalInfo": {"invalidParams": ["inquiredFrequencyRange"]}}
            if hi <= lo:
                return {"responseCode": RC_INVALID_VALUE, "supplementalInfo": {"invalidParams": ["inquiredFrequencyRange"]}}
            # 1 MHz bins, compute directly at center f+0.5 to avoid Wi‑Fi grid alignment
            start_mhz = int(lo)
            end_mhz = int(hi)
            bins = []  # (low, high, psd)
            a_tx_def, a_rx_def = ensure_defaults(spec.acir.a_tx_db_by_offset_mhz, spec.acir.a_rx_db_by_offset_mhz)
            tx_points = sorted((float(k), float(v)) for k, v in a_tx_def.items())
            rx_points = sorted((float(k), float(v)) for k, v in a_rx_def.items())

            def _v(d: dict, keys: list[str], default=None):
                for k in keys:
                    if k in d and d[k] is not None:
                        return d[k]
                return default

            for f in range(start_mhz, end_mhz):
                center = f + 0.5
                ch_lo = float(f)
                ch_hi = float(f + 1)
                f_hz = center * 1e6
                # FS noise from spec defaults
                n_dbm = noise_power_dbm(spec.incumbent.bandwidth_hz, spec.incumbent.noise_figure_db)

                best_eirp = spec.wifi_limits.max_eirp_dbm
                # Apply PSD cap for 1 MHz bin (min of EIRP and PSD-derived total)
                try:
                    from math import log10
                    psd_cap = getattr(spec.wifi_limits, 'max_psd_dbm_per_mhz', None)
                    if psd_cap is not None:
                        total_from_psd = float(psd_cap) + 10.0 * log10(1.0)
                        best_eirp = min(best_eirp, total_from_psd)
                except Exception:
                    pass
                for inc in incumbents:
                    fs_center_mhz = float(_v(inc, ["freq_center_mhz", "center_mhz", "fs_center_mhz"]))
                    fs_bw_mhz = float(_v(inc, ["bandwidth_mhz", "fs_bandwidth_mhz", "rx_bw_mhz"]))
                    rx_lat = float(_v(inc, ["rx_lat", "lat"], 0.0))
                    rx_lon = float(_v(inc, ["rx_lon", "lon"], 0.0))
                    fs_rx_gain = float(_v(inc, ["rx_antenna_gain_dbi", "rx_gain_dbi"],  spec.incumbent.antenna_gain_dbi))
                    rx_az = float(_v(inc, ["rx_antenna_azimuth_deg", "rx_azimuth_deg", "az_deg"], 0.0))
                    pol = str(_v(inc, ["polarization"], ""))[:1].upper()
                    rpe_az = inc.get("rx_rpe_az")
                    rpe_el = inc.get("rx_rpe_el")
                    rx_h_m = _v(inc, ["rx_antenna_height_m", "rx_height_m", "height_m"])  # may be None

                    # Geometry and path loss
                    # Include horizontal uncertainty (conservative worst-case closer by ~10 m)
                    d_nom = haversine_distance_m(ap_lat, ap_lon, rx_lat, rx_lon)
                    d_m = max(1.0, d_nom - 10.0)
                    brg = initial_bearing_deg(ap_lat, ap_lon, rx_lat, rx_lon)
                    pl_db = select_pathloss_db(distance_m=d_m, frequency_hz=f_hz, environment=env)

                    # Antenna discrimination (azimuth only)
                    delta_az = off_axis_azimuth_deg(rx_az, (brg + 180.0) % 360.0)
                    if rpe_az and rpe_el:
                        g_eff = combined_rpe_gain_dbi(fs_rx_gain, delta_az, 0.0, rpe_az, rpe_el)
                    else:
                        g_eff = effective_gain_dbi(AntennaPatternParams(g_max_dbi=fs_rx_gain), delta_az, 0.0)

                    # Overlap vs adjacent
                    fs_lo = fs_center_mhz - fs_bw_mhz / 2.0
                    fs_hi = fs_center_mhz + fs_bw_mhz / 2.0
                    overlaps = min(ch_hi, fs_hi) - max(ch_lo, fs_lo)
                    if overlaps > 0:
                        eirp = allowed_eirp_dbm_with_spec(
                            n_dbm=n_dbm,
                            inr_limit_db=-6.0 - margin,
                            path_loss_db=pl_db,
                            spec=spec,
                            channel_offset_mhz=None,
                            eirp_regulatory_max_dbm=best_eirp,
                            l_polarization_db=spec.incumbent.polarization_mismatch_db,
                            override_g_rx_dbi=g_eff,
                        )
                    else:
                        offset = int(round(abs(center - fs_center_mhz)))
                        eirp = allowed_eirp_dbm_with_spec(
                            n_dbm=n_dbm,
                            inr_limit_db=-6.0 - margin,
                            path_loss_db=pl_db,
                            spec=spec,
                            channel_offset_mhz=(offset if offset > 0 else None),
                            eirp_regulatory_max_dbm=best_eirp,
                            l_polarization_db=spec.incumbent.polarization_mismatch_db,
                            override_g_rx_dbi=g_eff,
                        )
                    if eirp < best_eirp:
                        best_eirp = eirp

                # For 1 MHz bins, PSD == EIRP numerically
                bins.append((float(f), float(f + 1), float(best_eirp)))
            # Merge adjacent bins with same PSD (within tol), unless disabled
            merge_bins = bool(request.get("mergeBins", True))
            tol = float(request.get("mergeToleranceDb", 1e-6))
            if merge_bins:
                merged: List[Tuple[float, float, float]] = []
                for b in bins:
                    if not merged:
                        merged.append(list(b))  # type: ignore[list-item]
                    else:
                        last = merged[-1]
                        if abs(last[2] - b[2]) < tol and abs(last[1] - b[0]) < 1e-9:
                            merged[-1] = (last[0], b[1], last[2])
                        else:
                            merged.append(b)
                for lo_b, hi_b, psd in merged:
                    results.append({
                        "frequencyRange": {"lowMHz": lo_b, "highMHz": hi_b},
                        "maxPsd": psd,
                    })
            else:
                for lo_b, hi_b, psd in bins:
                    results.append({
                        "frequencyRange": {"lowMHz": lo_b, "highMHz": hi_b},
                        "maxPsd": psd,
                    })
        return {"responseCode": RC_SUCCESS, "availabilityExpireTime": _expiry_iso8601(), "availableFrequencyInfo": results}

    # Channel-based query
    if not isinstance(chan_req, list) or not chan_req:
        return {"responseCode": RC_MISSING_PARAM, "supplementalInfo": {"missingParams": ["inquiredChannels"]}}

    # Each entry should normally have a globalOperatingClass; if not mappable, we accept bandwidthMHz as fallback
    centers: List[Tuple[float, float]] = []  # (center_mhz, bw_mhz)
    invalid: List[str] = []
    for item in chan_req:
        if not isinstance(item, dict):
            invalid.append("inquiredChannels[]")
            continue
        goc = item.get("globalOperatingClass")
        if goc is None and "goc" in item:
            goc = item.get("goc")
        cfis = item.get("channelCfi")
        if cfis is None and "cfi" in item:
            cfis = item.get("cfi")
        if cfis is None:
            # No CFIs provided: we require explicit CFIs for NR-U in this minimal handler
            return {"responseCode": RC_UNSUPPORTED_BASIS}
        if not isinstance(cfis, list) or not all(isinstance(c, int) for c in cfis):
            invalid.append("channelCfi")
            continue
        bw = None
        if isinstance(goc, int):
            bw = nru_goc_to_bw_mhz(goc)
        # Fallbacks: item-level, then request-level, then default to 20 MHz
        if bw is None and isinstance(item.get("bandwidthMHz"), (int, float)):
            bw = float(item["bandwidthMHz"])
        if bw is None and isinstance(request.get("bandwidthMHz"), (int, float)):
            bw = float(request["bandwidthMHz"])
        if bw is None:
            bw = 20.0
        for cfi in cfis:
            centers.append((nru_cfi_to_center_mhz(cfi), bw))

    if invalid:
        return {"responseCode": RC_INVALID_VALUE, "supplementalInfo": {"invalidParams": list(set(invalid))}}

    # Evaluate via spectrum inquiry across tiny per-channel bands
    band_ranges = [(fc - bw / 2.0, fc + bw / 2.0) for fc, bw in centers]
    rows = spectrum_inquiry(
        spec=spec,
        incumbents=list(incumbents),
        ap_lat=ap_lat,
        ap_lon=ap_lon,
        band_ranges_mhz=band_ranges,
        bandwidths_mhz=tuple(sorted({bw for _, bw in centers})),
        inr_limit_db=-6.0,
        environment=request.get("environment", "urban"),
        path_model=request.get("pathModel", "auto"),
        protection_margin_db=float(request.get("protectionMarginDb", 0.0)),
    )

    # Build AvailableChannelInfo with parallel arrays channelCfi/maxEirp as per §6.3.4
    # We preserve the order of CFIs per item. Bandwidth is resolved per-item using
    # globalOperatingClass, item.bandwidthMHz, request.bandwidthMHz, then default 20 MHz.

    available = []
    for item in chan_req:
        goc = item.get("globalOperatingClass", item.get("goc"))
        cfis = item.get("channelCfi", item.get("cfi", []))
        # Resolve bandwidth per item
        bw = None
        if isinstance(goc, int):
            bw = nru_goc_to_bw_mhz(goc)
        if bw is None and isinstance(item.get("bandwidthMHz"), (int, float)):
            bw = float(item["bandwidthMHz"])
        if bw is None and isinstance(request.get("bandwidthMHz"), (int, float)):
            bw = float(request["bandwidthMHz"])
        if bw is None:
            bw = 20.0
        max_eirp_list: List[float] = []
        for cfi in cfis:
            fc = nru_cfi_to_center_mhz(cfi)
            # Re-evaluate for this (fc,bw) to avoid dictionary key mismatch issues
            sub_rows = spectrum_inquiry(
                spec=spec,
                incumbents=list(incumbents),
                ap_lat=ap_lat,
                ap_lon=ap_lon,
                band_ranges_mhz=[(fc - bw / 2.0, fc + bw / 2.0)],
                bandwidths_mhz=(bw,),
                inr_limit_db=-6.0,
                environment=request.get("environment", "urban"),
                path_model=request.get("pathModel", "auto"),
                protection_margin_db=float(request.get("protectionMarginDb", 0.0)),
            )
            if sub_rows:
                eirp = sub_rows[0].allowed_eirp_dbm
            else:
                eirp = 0.0
            max_eirp_list.append(eirp)
        entry = {
            "channelCfi": cfis,
            "maxEirp": max_eirp_list,
        }
        if isinstance(goc, int):
            entry["globalOperatingClass"] = goc
        else:
            entry["bandwidthMHz"] = bw
        available.append(entry)

    return {"responseCode": RC_SUCCESS, "availabilityExpireTime": _expiry_iso8601(), "availableChannelInfo": available}


