from .link_budget import (
	compute_eirp_dbm,
	noise_power_dbm,
	interference_dbm,
	inr_db,
	i_threshold_dbm,
	interference_margin_db,
)
from .fspl import fspl_db, invert_fspl_distance_m
from .acir import acir_db, adjacent_channel_interference_dbm, acir_db_from_spec
from .phy import sinr_db
from .mac import bianchi_fixed_point
from .allocator import (
	allowed_eirp_dbm_for_path,
	psd_dbm_per_mhz_from_eirp,
	eirp_total_dbm_from_psd,
	verify_interference_meets_limit,
	allowed_eirp_dbm_with_spec,
)
from .propagation import (
	select_pathloss_db,
	winner2_pathloss_db,
	itm_pathloss_db,
    two_slope_pathloss_db,
)
from .kpi import inr_violation_probability, grant_stats
from .spec_params import (
	SpecParameters,
	IncumbentReceiverParams,
	WiFiRegulatoryLimits,
	ACIRSpec,
	parse_spec_text_to_params,
	load_params_from_text_file,
)
from .phy_mcs import (
	McsEntry,
	default_mcs_table,
	pick_mcs_from_snr_db,
	per_from_snr_db,
	phy_rate_bps_from_snr_db,
)
from .scenario import (
	Scenario,
	run_scenario,
	rows_to_table,
	print_table,
)
from .grant_table import (
    GrantRow,
    enumerate_centers_mhz,
    channel_number_from_center_mhz,
    build_grant_table_for_hypothetical_fs,
    build_grant_table_both_blocks,
    build_grant_table_with_incumbents,
    grant_rows_to_table,
    save_grant_table_csv,
)
from .antenna import AntennaPatternParams, effective_gain_dbi
from .acir_masks import (
    interpolate_mask_db,
    acir_db_from_masks,
    acir_profile_from_tables,
)
from .geodesy import haversine_distance_m
from .aggregate import (
    aggregate_interference_dbm,
    inr_db_from_components,
    meets_inr_limit,
)
from .itm import longley_rice_pathloss_db
from .antenna_rpe import (
    interpolate_rpe_db,
    combined_rpe_gain_dbi,
)
from .multi_ap import (
    APSite,
    evaluate_aggregate_inr_for_channel,
    evaluate_aggregate_inr_across,
)
# Override the multi_ap versions with the aggregate versions that accept `spec` and dict APS
from .aggregate import (
    evaluate_aggregate_inr_for_channel as evaluate_aggregate_inr_for_channel,
    evaluate_aggregate_inr_across as evaluate_aggregate_inr_across,
    evaluate_aggregate_inr_for_assignments,
)
from .api import build_available_channels_response
try:
	from .contours import render_exclusion_map  # heavy (matplotlib); optional for headless runs
	_export_contours = True
except Exception:
	render_exclusion_map = None  # type: ignore
	_export_contours = False
try:
	from .heatmaps import APSiteClient, generate_ap_heatmaps  # heavy (matplotlib); optional
	_export_heatmaps = True
except Exception:
	APSiteClient = None  # type: ignore
	generate_ap_heatmaps = None  # type: ignore
	_export_heatmaps = False
from .spectrum_inquiry import spectrum_inquiry
from .acir_loader import load_acir_from_json, load_acir_from_csv, apply_acir_to_spec
from .recipes import (
    cap_ap_eirp_and_run_aggregate,
    cap_ap_eirp_and_run_aggregate_across_unii5,
    monte_carlo_multi_ap_unii5,
    randomized_multibw_random_channels_unii5,
    generate_poisson_ap_field,
)
from .audit import (
    make_run_manifest,
    write_manifest,
    sha256_file,
    sha256_json,
    capture_env_info,
    verify_files_exist,
    get_git_commit,
)
from .paper_runner import run_paper_scenario
from .scenario_catalog import build_scenario_catalog

__all__ = [
	"compute_eirp_dbm",
	"noise_power_dbm",
	"interference_dbm",
	"inr_db",
	"i_threshold_dbm",
	"interference_margin_db",
	"fspl_db",
	"invert_fspl_distance_m",
	"acir_db",
	"adjacent_channel_interference_dbm",
    "acir_db_from_spec",
	"sinr_db",
	"bianchi_fixed_point",
	"allowed_eirp_dbm_for_path",
	"psd_dbm_per_mhz_from_eirp",
	"eirp_total_dbm_from_psd",
	"verify_interference_meets_limit",
	"allowed_eirp_dbm_with_spec",
	"select_pathloss_db",
	"winner2_pathloss_db",
	"itm_pathloss_db",
    "two_slope_pathloss_db",
	"inr_violation_probability",
    "grant_stats",
	"SpecParameters",
	"IncumbentReceiverParams",
	"WiFiRegulatoryLimits",
	"ACIRSpec",
	"parse_spec_text_to_params",
	"load_params_from_text_file",
	"McsEntry",
	"default_mcs_table",
	"pick_mcs_from_snr_db",
	"per_from_snr_db",
	"phy_rate_bps_from_snr_db",
	"Scenario",
	"run_scenario",
	"rows_to_table",
	"print_table",
    "GrantRow",
    "enumerate_centers_mhz",
    "channel_number_from_center_mhz",
    "build_grant_table_for_hypothetical_fs",
    "build_grant_table_both_blocks",
    "build_grant_table_with_incumbents",
    "grant_rows_to_table",
    "save_grant_table_csv",
    "AntennaPatternParams",
    "effective_gain_dbi",
    "interpolate_mask_db",
    "acir_db_from_masks",
    "acir_profile_from_tables",
    "haversine_distance_m",
    "aggregate_interference_dbm",
    "inr_db_from_components",
    "meets_inr_limit",
    "longley_rice_pathloss_db",
    "interpolate_rpe_db",
    "combined_rpe_gain_dbi",
    "APSite",
    "evaluate_aggregate_inr_for_channel",
    "evaluate_aggregate_inr_across",
    "evaluate_aggregate_inr_for_assignments",
    "build_available_channels_response",
    "spectrum_inquiry",
    "load_acir_from_json",
    "load_acir_from_csv",
    "apply_acir_to_spec",
    "cap_ap_eirp_and_run_aggregate",
    "cap_ap_eirp_and_run_aggregate_across_unii5",
		"monte_carlo_multi_ap_unii5",
		"randomized_multibw_random_channels_unii5",
        "generate_poisson_ap_field",
        "make_run_manifest",
        "write_manifest",
        "sha256_file",
        "sha256_json",
        "capture_env_info",
        "verify_files_exist",
        "get_git_commit",
        "run_paper_scenario",
        "build_scenario_catalog",
]

# Export optional plotting helpers only if imports succeeded
if _export_contours:
	__all__.append("render_exclusion_map")
if _export_heatmaps:
	__all__ += ["APSiteClient", "generate_ap_heatmaps"]

