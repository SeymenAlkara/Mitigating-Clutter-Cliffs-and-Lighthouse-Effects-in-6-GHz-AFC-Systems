"""CLI to run spectrum inquiry and save CSVs.

Usage:
    python -m afc_new.cli --ap-lat 41.0 --ap-lon 29.0 --bands unii5 --env urban --out grants.csv
"""

import argparse
from pathlib import Path

from . import (
    load_params_from_text_file,
    spectrum_inquiry,
    grant_rows_to_table,
    save_grant_table_csv,
)
from .loaders import load_incumbents_from_text
from .device_constraints import DeviceConstraints


def main():
    parser = argparse.ArgumentParser(description="Run AFC spectrum inquiry and save CSV")
    parser.add_argument("--ap-lat", type=float, required=True)
    parser.add_argument("--ap-lon", type=float, required=True)
    parser.add_argument("--env", type=str, default="urban", choices=["urban","suburban","rural","indoor"])
    parser.add_argument("--path-model", type=str, default="auto", choices=["auto","fspl","winner","two_slope","itm"])
    parser.add_argument("--bands", type=str, default="unii5", choices=["unii5","unii7","both"])  # simple selector
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--indoor", action="store_true", help="apply indoor penetration loss")
    parser.add_argument("--penetration-db", type=float, default=None, help="override penetration loss (dB)")
    parser.add_argument("--min-eirp", type=float, default=None, help="device min EIRP dBm")
    parser.add_argument("--min-psd", type=float, default=None, help="device min PSD dBm/MHz")
    parser.add_argument("--power-basis", type=str, default="EIRP", choices=["EIRP","ERP"], help="basis for min power constraints")
    parser.add_argument("--spec-text", type=Path, default=Path("docs/extracted_afc_text.txt"))
    parser.add_argument("--incs", type=Path, default=Path("spec/Example incumbents.txt"))
    args = parser.parse_args()

    if args.bands == "unii5":
        band_ranges = [(5925.0, 6425.0)]
    elif args.bands == "unii7":
        band_ranges = [(6525.0, 6875.0)]
    else:
        band_ranges = [(5925.0, 6425.0), (6525.0, 6875.0)]

    params = load_params_from_text_file(str(args.spec_text))
    incs = load_incumbents_from_text(args.incs)
    cons = None
    if args.min_eirp is not None or args.min_psd is not None:
        cons = DeviceConstraints(
            min_eirp_dbm=(args.min_eirp if args.min_eirp is not None else 0.0),
            min_psd_dbm_per_mhz=(args.min_psd if args.min_psd is not None else -10.0),
            power_basis=args.power_basis,
        )

    rows = spectrum_inquiry(
        spec=params,
        incumbents=incs,
        ap_lat=args.ap_lat,
        ap_lon=args.ap_lon,
        band_ranges_mhz=band_ranges,
        bandwidths_mhz=(20.0, 40.0, 80.0, 160.0),
        inr_limit_db=-6.0,
        environment=args.env,
        path_model=args.path_model,
        device_constraints=cons,
        indoor=args.indoor,
        penetration_db=args.penetration_db,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    save_grant_table_csv(rows, args.out)
    print(f"Saved {len(rows)} rows to {args.out}")


if __name__ == "__main__":
    main()


