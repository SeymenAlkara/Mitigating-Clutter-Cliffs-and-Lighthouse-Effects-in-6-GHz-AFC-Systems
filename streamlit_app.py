"""Streamlit UI: UNII-5/UNII-7 grant tables and quick visuals.

Run:
    streamlit run -q afc_new/streamlit_app.py

This page computes channel-based grants for both UNII-5 and UNII-7 at a chosen
AP location, using the current afc_new engine settings. It shows sortable tables
and quick charts, with caching to minimize flicker.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Tuple, List, Dict, Any

import json
import math

# Ensure project root (parent of this file's package) is on sys.path for imports
import sys as _sys
from pathlib import Path as _Path
_pkg_root = _Path(__file__).resolve().parents[1]
if str(_pkg_root) not in _sys.path:
	_sys.path.insert(0, str(_pkg_root))

import pandas as pd
import streamlit as st

# Optional mapping support
try:
    import folium  # type: ignore
    from streamlit_folium import st_folium  # type: ignore
    try:
        from folium.plugins import MarkerCluster  # type: ignore
    except Exception:  # pragma: no cover
        MarkerCluster = None
except Exception:  # pragma: no cover
    folium = None
    st_folium = None
    MarkerCluster = None

# Import narrowly from submodules to avoid optional heavy imports on package __init__
from afc_new.spec_params import load_params_from_text_file
from afc_new.grant_table import build_grant_table_with_incumbents, save_grant_table_csv
from afc_new.recipes import randomized_multibw_random_channels_unii5, generate_poisson_ap_field
from afc_new.paper_runner import run_paper_scenario


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SPEC_DIR = PROJECT_ROOT / "spec"
DEFAULT_PARAMS = SPEC_DIR / "extracted_afc_text.txt"
DEFAULT_INCS = SPEC_DIR / "example_incumbents.json"


@st.cache_data(show_spinner=False)
def load_params_and_incumbents(params_path: Path, inc_path: Path):
    params = load_params_from_text_file(params_path)
    with inc_path.open("r", encoding="utf-8") as f:
        incumbents = json.load(f)
    return params, incumbents


@st.cache_data(show_spinner=False)
def compute_grants(
    *,
    params_path: Path,
    inc_path: Path,
    ap_lat: float,
    ap_lon: float,
    inr_limit_db: float,
    environment: str,
    path_model: str,
    bandwidths: Tuple[float, ...],
    protection_margin_db: float,
):
    params, incumbents = load_params_and_incumbents(params_path, inc_path)

    rows_5 = build_grant_table_with_incumbents(
        spec=params,
        incumbents=incumbents,
        lower_mhz=5925.0,
        upper_mhz=6425.0,
        bandwidths_mhz=bandwidths,
        inr_limit_db=inr_limit_db,
        environment=environment,
        path_model=path_model,
        ap_lat=ap_lat,
        ap_lon=ap_lon,
        protection_margin_db=protection_margin_db,
    )
    rows_7 = build_grant_table_with_incumbents(
        spec=params,
        incumbents=incumbents,
        lower_mhz=6525.0,
        upper_mhz=6875.0,
        bandwidths_mhz=bandwidths,
        inr_limit_db=inr_limit_db,
        environment=environment,
        path_model=path_model,
        ap_lat=ap_lat,
        ap_lon=ap_lon,
        protection_margin_db=protection_margin_db,
    )
    return rows_5, rows_7


def rows_to_df(rows) -> pd.DataFrame:
    data = []
    for r in rows:
        data.append(
            dict(
                channel=int(r.channel_number),
                center_mhz=float(r.center_mhz),
                bw_mhz=float(r.bandwidth_mhz),
                path_loss_db=float(r.path_loss_db),
                noise_dbm=float(r.noise_dbm),
                allowed_eirp_dbm=float(r.allowed_eirp_dbm),
                allowed_psd_dbm_per_mhz=float(r.allowed_psd_dbm_per_mhz),
                decision=str(r.decision),
                limiting_incumbent=("" if r.limiting_incumbent is None else str(r.limiting_incumbent)),
                limiting_mode=("" if r.limiting_mode is None else str(r.limiting_mode)),
				# Keep numeric dtype for Arrow: use NaN when missing
				acir_db_used=(math.nan if r.acir_db_used is None else float(r.acir_db_used)),
            )
        )
    df = pd.DataFrame(data)
    if not df.empty:
        df = df.sort_values(["bw_mhz", "center_mhz"]).reset_index(drop=True)
    return df


def main():
    st.set_page_config(page_title="AFC Grants (UNII-5/7)", layout="wide")
    st.title("AFC Grants — UNII‑5 and UNII‑7")
    st.caption("Interactive grant tables at a selected AP site. Uses current engine settings (PSD/EIRP caps, ACIR, ITM knobs).")

    with st.sidebar:
        st.header("Inputs")
        params_path = st.text_input("Spec parameters file", str(DEFAULT_PARAMS))
        inc_path = st.text_input("Incumbents JSON", str(DEFAULT_INCS))
        col = st.columns(2)
        ap_lat = col[0].number_input("AP lat", value=41.015, format="%.6f")
        ap_lon = col[1].number_input("AP lon", value=28.979, format="%.6f")
        inr_limit_db = st.number_input("I/N limit (dB)", value=-6.0, step=0.5, format="%.2f")
        environment = st.selectbox("Environment", ["urban", "suburban", "rural", "indoor"], index=0)
        path_model = st.selectbox("Path model", ["auto", "fspl", "winner", "two_slope", "itm"], index=0)
        bw_opts = st.multiselect("Bandwidths (MHz)", [20.0, 40.0, 80.0, 160.0], default=[20.0, 40.0, 80.0, 160.0])
        protection_margin_db = st.number_input("Protection margin (dB)", value=0.0, step=0.5, format="%.2f")
        show_psd = st.toggle("Show PSD instead of EIRP", value=False)
        run_btn = st.button("Compute grants")

    # Compute and persist results to prevent flicker on reruns
    if run_btn:
        try:
            rows5, rows7 = compute_grants(
                params_path=Path(params_path),
                inc_path=Path(inc_path),
                ap_lat=float(ap_lat),
                ap_lon=float(ap_lon),
                inr_limit_db=float(inr_limit_db),
                environment=str(environment),
                path_model=str(path_model),
                bandwidths=tuple(float(x) for x in bw_opts) or (20.0,),
                protection_margin_db=float(protection_margin_db),
            )
            st.session_state["rows5"] = rows5
            st.session_state["rows7"] = rows7
        except Exception as e:
            st.error(f"Failed to compute grants: {e}")

    # Auto-compute once on first load so tables are not empty
    if "rows5" not in st.session_state or "rows7" not in st.session_state:
        try:
            rows5, rows7 = compute_grants(
                params_path=Path(params_path),
                inc_path=Path(inc_path),
                ap_lat=float(ap_lat),
                ap_lon=float(ap_lon),
                inr_limit_db=float(inr_limit_db),
                environment=str(environment),
                path_model=str(path_model),
                bandwidths=tuple(float(x) for x in bw_opts) or (20.0,),
                protection_margin_db=float(protection_margin_db),
            )
            st.session_state["rows5"] = rows5
            st.session_state["rows7"] = rows7
        except Exception:
            pass

    # Read from session (if available) and render
    rows5 = st.session_state.get("rows5", [])
    rows7 = st.session_state.get("rows7", [])
    df5 = rows_to_df(rows5) if rows5 else pd.DataFrame()
    df7 = rows_to_df(rows7) if rows7 else pd.DataFrame()

    st.subheader("UNII‑5 (5925–6425 MHz)")
    if df5.empty:
        st.info("No rows.")
    else:
        def _style(df: pd.DataFrame):
            def color_denied(s: pd.Series):
                return ["background-color: #ffe6e6" if (str(v).lower() == "deny") else "" for v in s]
            styled = df.style.apply(color_denied, subset=["decision"])
            # Add a gradient on the allowed power column in view
            try:
                col = "allowed_psd_dbm_per_mhz" if show_psd else "allowed_eirp_dbm"
                styled = styled.background_gradient(subset=[col], cmap="YlGn")
            except Exception:
                pass
            return styled
        view_cols = ["channel", "center_mhz", "bw_mhz", "decision"] + (["allowed_psd_dbm_per_mhz"] if show_psd else ["allowed_eirp_dbm"])
        st.dataframe(_style(df5[view_cols]), use_container_width=True, height=360)

    st.subheader("UNII‑7 (6525–6875 MHz)")
    if df7.empty:
        st.info("No rows.")
    else:
        view_cols = ["channel", "center_mhz", "bw_mhz", "decision"] + (["allowed_psd_dbm_per_mhz"] if show_psd else ["allowed_eirp_dbm"])
        st.dataframe(df7[view_cols], use_container_width=True, height=360)

    # Quick charts: EIRP by center for each BW
    def plot_block(df: pd.DataFrame, title: str):
        if df.empty:
            return
        import altair as alt
        y_field = "allowed_psd_dbm_per_mhz:Q" if show_psd else "allowed_eirp_dbm:Q"
        y_title = "Allowed PSD (dBm/MHz)" if show_psd else "Allowed EIRP (dBm)"
        ch = (
            alt.Chart(df)
            .mark_line(point=True)
            .encode(
                x=alt.X("center_mhz:Q", title="Center (MHz)"),
                y=alt.Y(y_field, title=y_title),
                color=alt.Color("bw_mhz:N", title="BW (MHz)"),
                tooltip=["center_mhz", "bw_mhz", ("allowed_psd_dbm_per_mhz" if show_psd else "allowed_eirp_dbm"), "decision", "limiting_incumbent", "limiting_mode"],
            )
            .properties(title=title, height=280)
        )
        st.altair_chart(ch, use_container_width=True)

    plot_block(df5, "UNII‑5 allowed EIRP vs center")
    plot_block(df7, "UNII‑7 allowed EIRP vs center")

    # Map with AP and incumbents
    with st.expander("Map: AP and incumbents", expanded=False):
        if folium is None or st_folium is None:
            st.info("Install streamlit-folium and folium to enable the map: pip install streamlit-folium folium")
        else:
            try:
                _params, _incs = load_params_and_incumbents(Path(params_path), Path(inc_path))
                m = folium.Map(location=[ap_lat, ap_lon], tiles="cartodbpositron", zoom_start=11)
                folium.Marker([ap_lat, ap_lon], tooltip="AP", icon=folium.Icon(color="blue")).add_to(m)
                for inc in _incs:
                    lat = float(inc.get("rx_lat") or inc.get("lat") or ap_lat)
                    lon = float(inc.get("rx_lon") or inc.get("lon") or ap_lon)
                    lid = str(inc.get("link_id") or inc.get("fs_id") or inc.get("id") or "FS")
                    folium.Marker([lat, lon], tooltip=f"FS {lid}", icon=folium.Icon(color="red")).add_to(m)
                # If we have last Monte Carlo APs, show them
                ap_sites = st.session_state.get("last_ap_sites")
                if isinstance(ap_sites, list) and len(ap_sites) > 0:
                    if MarkerCluster is not None:
                        cluster = MarkerCluster(name="APs").add_to(m)
                        for ap in ap_sites:
                            folium.CircleMarker([float(ap["lat"]), float(ap["lon"])], radius=2, color="#3388ff", fill=True, fill_opacity=0.7).add_to(cluster)
                    else:
                        # Fallback: sample at most 1000 to avoid heavy maps
                        for ap in ap_sites[:1000]:
                            folium.CircleMarker([float(ap["lat"]), float(ap["lon"])], radius=2, color="#3388ff", fill=True, fill_opacity=0.7).add_to(m)
                st_folium(m, width=None, height=420)
            except Exception as e:
                st.warning(f"Map error: {e}")

    # Monte Carlo form
    st.subheader("Monte Carlo: randomized multi‑BW/channel aggregate INR")
    with st.form("mc_form"):
        c1, c2, c3, c4 = st.columns(4)
        n_aps = int(c1.number_input("# APs", value=300, min_value=1, step=50))
        radius_km = float(c2.number_input("Radius (km)", value=1.0, min_value=0.1, step=0.1, format="%.1f"))
        dc = float(c3.number_input("Duty cycle", value=0.04, min_value=0.0, max_value=1.0, step=0.01, format="%.2f"))
        dur = int(c4.number_input("Duration (s)", value=300, min_value=10, step=10))
        wsel = st.selectbox("Channel weighting", ["uniform", "eirp_lin", "eirp_dbm", "per_mhz"], index=0)
        run_mc = st.form_submit_button("Run Monte Carlo")
    if run_mc:
        try:
            params, incs = load_params_and_incumbents(Path(params_path), Path(inc_path))
            ap_sites = generate_poisson_ap_field(center_lat=float(ap_lat), center_lon=float(ap_lon), radius_km=radius_km, fixed_num_aps=n_aps, seed=20251112)
            # Persist for map
            st.session_state["last_ap_sites"] = ap_sites
            out = randomized_multibw_random_channels_unii5(
                spec=params,
                incumbents=incs,
                ap_sites=ap_sites,
                ap_nominal_eirp_dbm=30.0,
                duty_cycle=dc,
                duration_s=dur,
                inr_limit_db=float(inr_limit_db),
                environment=str(environment),
                path_model=str(path_model),
                out_dir="simulation_results_enhanced",
                seed=20251112,
                write_timeseries=True,
                protection_margin_db=float(protection_margin_db),
                channel_weighting=wsel,
            )
            st.success("Monte Carlo run complete.")
            per_csv = out.get("per_incumbent_csv")
            if per_csv:
                df = pd.read_csv(per_csv)
                st.dataframe(df, use_container_width=True)
        except Exception as e:
            st.error(f"Monte Carlo failed: {e}")

    # Paper validations panel
    st.subheader("Paper validations")
    with st.expander("Run a paper scenario (JSON)", expanded=False):
        sc_path = st.text_input("Scenario JSON path", str(PROJECT_ROOT / "docs" / "papers_scenarios" / "example.json"))
        run_paper = st.button("Run paper scenario")
        if run_paper:
            try:
                params2, incs2 = load_params_and_incumbents(Path(params_path), Path(inc_path))
            except Exception:
                # Some paper scenarios include incumbents within JSON, so we only need params here
                params2 = load_params_from_text_file(Path(params_path))
                incs2 = []
            try:
                out_map = run_paper_scenario(
                    spec=params2,
                    scenario_path=Path(sc_path),
                    out_dir=PROJECT_ROOT / "simulation_results_enhanced",
                )
                st.success("Scenario complete.")
                st.json({k: str(v) for k, v in out_map.items()})
            except Exception as e:
                st.error(f"Paper scenario failed: {e}")


if __name__ == "__main__":
    main()


