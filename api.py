"""AFC-style spectrum inquiry response builder (simplified).

This module converts our internal grant-table computation into an AFC-like
"available channels" JSON structure so that a caller (or UI) can consume it
in a single object.

WINNF-TS-1014 mapping: wraps the AIP evaluation to produce per-channel maximum
EIRP/PSD limits and a grant/deny flag.
"""

from typing import Any, Dict, Iterable, List, Tuple

from .spec_params import SpecParameters
from .grant_table import grant_rows_to_table
from .spectrum_inquiry import spectrum_inquiry
from .allocator import psd_dbm_per_mhz_from_eirp


def build_available_channels_response(
    spec: SpecParameters,
    incumbents: Iterable[Dict[str, Any]],
    ap_lat: float,
    ap_lon: float,
    band_ranges_mhz: Iterable[Tuple[float, float]] = ((5925.0, 6425.0), (6525.0, 6875.0)),
    bandwidths_mhz: Iterable[float] = (20.0, 40.0, 80.0, 160.0),
    inr_limit_db: float = -6.0,
    environment: str | None = None,
    path_model: str = "auto",
) -> Dict[str, Any]:
    """Return a dict with a list of available channels and power limits.

    Output format (simplified):
    {
      "availableChannelInfo": [
        {"centerMHz": 5955.0, "bandwidthMHz": 20.0, "maxEirpDbm": 36.0,
         "maxPsdDbmPerMHz": 3.0, "decision": "grant"}, ...
      ]
    }
    """
    rows = spectrum_inquiry(
        spec=spec,
        incumbents=incumbents,
        ap_lat=ap_lat,
        ap_lon=ap_lon,
        band_ranges_mhz=band_ranges_mhz,
        bandwidths_mhz=bandwidths_mhz,
        inr_limit_db=inr_limit_db,
        environment=environment,
        path_model=path_model,
    )
    table = grant_rows_to_table(rows)
    hdr, data = table[0], table[1:]
    idx_center = hdr.index("center_mhz")
    idx_bw = hdr.index("bw_mhz")
    idx_eirp = hdr.index("allowed_eirp_dbm")
    idx_dec = hdr.index("decision")
    # Optional trace fields (present in rows, not in table)

    resp: Dict[str, Any] = {"availableChannelInfo": []}
    for i, r in enumerate(data):
        center_mhz = float(r[idx_center])
        bw_mhz = float(r[idx_bw])
        eirp_dbm = float(r[idx_eirp])
        decision = r[idx_dec]
        psd = psd_dbm_per_mhz_from_eirp(eirp_dbm, bw_mhz)
        item: Dict[str, Any] = {
            "centerMHz": center_mhz,
            "bandwidthMHz": bw_mhz,
            "maxEirpDbm": eirp_dbm,
            "maxPsdDbmPerMHz": psd,
            "decision": decision,
        }
        row_obj = rows[i]
        lim = getattr(row_obj, "limiting_incumbent", None)
        mode = getattr(row_obj, "limiting_mode", None)
        acir = getattr(row_obj, "acir_db_used", None)
        if lim is not None:
            item["limitingIncumbent"] = lim
        if mode is not None:
            item["limitingMode"] = mode
        if acir is not None:
            item["acirDb"] = acir
        resp["availableChannelInfo"].append(item)
    return resp

def build_available_channels_response_json(*args, **kwargs) -> str:
    import json as _json
    return _json.dumps(build_available_channels_response(*args, **kwargs), ensure_ascii=False, indent=2)


