"""Streamlit dashboard for AFC grant visualization (simple MVP).

Renders:
- Band axis for UNII-5/6/7/8 with tick labels
- Green bar (PSD) per center frequency
- EIRP grids for 20/40/80/160 MHz (cell values, color-coded)
- Minimal map (Folium) with location marker

Usage:
    streamlit run -m afc_new.dashboard_app

Design choices per user request:
- Colors: green=grant, yellow=medium, red=deny (thresholds configurable below)
- Simplicity first: no hover tooltips in v1, no server dropdown; only core display

WINNF-TS-1014 mapping: visualization of per-channel allowed EIRP/PSD following 9.1.1 and
adjacent handling.
"""

import json
import sys
from pathlib import Path
from typing import List, Tuple

import streamlit as st
import numpy as np
import pandas as pd
import folium
from streamlit_folium import st_folium

# Ensure project root is on sys.path when run via `streamlit run .../dashboard_app.py`
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from afc_new import (
    load_params_from_text_file,
    grant_rows_to_table,
    spectrum_inquiry,
)


def _color_for_eirp(eirp_dbm: float, green_thresh: float = 10.0, red_thresh: float = 0.0) -> str:
    if eirp_dbm < red_thresh:
        return "#e74c3c"  # red
    if eirp_dbm >= green_thresh:
        return "#2ecc71"  # green
    return "#f1c40f"  # yellow


def _bands():
    # (name, lower, upper)
    return [
        ("UNII-5", 5925.0, 6425.0),
        ("UNII-6", 6425.0, 6525.0),
        ("UNII-7", 6525.0, 6875.0),
        ("UNII-8", 6875.0, 7125.0),
    ]


def _load_incumbents(path: Path) -> List[dict]:
    text = path.read_text(encoding="utf-8", errors="ignore")
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


def render_grid(rows: List[List[str]], band_lo: float, band_hi: float):
    # Filter table rows for band range and make a small DataFrame to pivot per BW
    header, data = rows[0], rows[1:]
    df = pd.DataFrame(data, columns=header)
    df["center_mhz"] = df["center_mhz"].astype(float)
    df = df[(df["center_mhz"] >= band_lo) & (df["center_mhz"] <= band_hi)]
    for bw in [20, 40, 80, 160]:
        sub = df[df["bw_mhz"] == f"{bw}"]
        if sub.empty:
            continue
        st.write(f"{bw} MHz")
        # Build a simple row of colored boxes with EIRP labels
        eirps = sub["allowed_eirp_dbm"].astype(float).tolist()
        centers = sub["center_mhz"].astype(float).tolist()
        cols = st.columns(len(eirps))
        for i, (eirp, fc) in enumerate(zip(eirps, centers)):
            color = _color_for_eirp(eirp)
            cols[i].markdown(
                f"<div style='text-align:center; background:{color}; padding:8px; border-radius:4px;'>"
                f"<div style='font-size:12px;'>{int(fc)}</div><div style='font-weight:bold;'>{eirp:.0f}</div></div>",
                unsafe_allow_html=True,
            )


def main():
    st.set_page_config(page_title="AFC Grant Viewer", layout="wide")
    st.title("AFC Grant Viewer (UNII-5/6/7/8)")

    project_root = Path(__file__).resolve().parents[1]
    spec_text_path = project_root / "docs" / "extracted_afc_text.txt"
    incumbents_path = project_root / "spec" / "Example incumbents.txt"

    with st.sidebar:
        st.header("Inputs")
        environment = st.selectbox("Environment", ["urban", "suburban", "rural", "indoor"], index=0)
        path_model = st.selectbox("Path model", ["auto", "fspl", "winner", "two_slope", "itm"], index=0)
        st.markdown("AP coordinates (WGS‑84)")
        ap_lat = st.number_input("AP latitude", value=41.000000, format="%.6f")
        ap_lon = st.number_input("AP longitude", value=29.000000, format="%.6f")
        hint = st.checkbox("Place AP ~0.6 km north of first FS for demo")
        run_btn = st.button("Compute grants", type="primary")

    # Map (minimal)
    st.subheader("Location")
    incs = _load_incumbents(incumbents_path)
    if hint and incs:
        ap_lat = float(incs[0].get("rx_lat", ap_lat)) + 0.006
        ap_lon = float(incs[0].get("rx_lon", ap_lon))

    m = folium.Map(location=[ap_lat, ap_lon], zoom_start=12, tiles="OpenStreetMap")
    folium.Marker([ap_lat, ap_lon], tooltip="AP site", icon=folium.Icon(color="blue")).add_to(m)
    for inc in incs:
        rx_lat = float(inc.get("rx_lat", 0.0))
        rx_lon = float(inc.get("rx_lon", 0.0))
        link_id = inc.get("link_id", "FS")
        fc = inc.get("freq_center_mhz", "?")
        folium.Marker([rx_lat, rx_lon], tooltip=f"{link_id} @ {fc} MHz", icon=folium.Icon(color="red")).add_to(m)
        folium.PolyLine([[ap_lat, ap_lon], [rx_lat, rx_lon]], color="gray", weight=1, opacity=0.6).add_to(m)
    st_folium(m, height=300, width=None)

    if run_btn:
        params = load_params_from_text_file(str(spec_text_path))
        rows = spectrum_inquiry(
            spec=params,
            incumbents=incs,
            ap_lat=float(ap_lat),
            ap_lon=float(ap_lon),
            band_ranges_mhz=[(5925.0, 6425.0)],
            bandwidths_mhz=(20.0, 40.0, 80.0, 160.0),
            inr_limit_db=-6.0,
            environment=environment,
            path_model=path_model,
        )
        table = grant_rows_to_table(rows)
        st.subheader("UNII-5 (5925–6425)")
        render_grid(table, 5925.0, 6425.0)
        denies = [r for r in rows if r.decision == "deny"]
        st.write(f"Denied channels: {len(denies)} out of {len(rows)} entries")
        if denies:
            df_deny = pd.DataFrame(grant_rows_to_table(denies)[1:], columns=grant_rows_to_table(denies)[0])
            st.dataframe(df_deny, use_container_width=True)
        # Future: add UNII-6/7/8 by calling the builder with their ranges

        st.download_button(
            label="Download CSV",
            data="\n".join([",".join(r) for r in table]),
            file_name="grant_UNII5.csv",
            mime="text/csv",
        )


if __name__ == "__main__":
    main()


