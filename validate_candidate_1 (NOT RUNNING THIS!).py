"""
Validation Script for Candidate 1: Kim et al. (Urban Microwave)
Run this script to execute the batch simulation using afc_new.
"""

import os
import json
import inspect
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path
from typing import List, Dict, Any

# Import from your codebase
# Assuming this script is placed in the root directory alongside the 'afc_new' folder
from afc_new.recipes import randomized_multibw_random_channels_unii5
from afc_new.spec_params import SpecParameters, IncumbentReceiverParams
from afc_new.antenna import AntennaPatternParams

# Configuration
SCENARIO_FILE = "scenario_kim_urban.json"
OUTPUT_DIR = "validation_results/kim_urban"
NUM_RUNS = 10  # Number of Monte Carlo iterations (seeds)
BASE_SEED = 20250101

def load_scenario(filepath: str) -> Dict:
    with open(filepath, 'r') as f:
        return json.load(f)

def resolve_tag_argument(func, tag_value: str) -> Dict[str, Any]:
    """
    Inspects the function signature to determine the correct argument name for the run ID.
    Common variations: 'tag', 'run_tag', 'run_id', 'experiment_tag'.
    """
    sig = inspect.signature(func)
    params = list(sig.parameters.keys())
    
    # Priority list of likely argument names based on your error
    # We check if 'tag' is present; if not, we look for alternatives.
    candidates = ['tag', 'run_tag', 'id', 'name', 'run_id']
    
    for candidate in candidates:
        if candidate in params:
            print(f"DEBUG: Resolved run identifier argument to: '{candidate}'")
            return {candidate: tag_value}
            
    # If no keyword matches, it might rely on position 0 being the tag.
    # However, recipes usually have many args, so we try the first parameter name.
    if params:
        first_param = params[0]
        print(f"WARNING: Could not find standard tag name. Using first parameter: '{first_param}'")
        return {first_param: tag_value}
        
    return {"tag": tag_value}

def run_validation():
    print(f"--- Starting Validation for {SCENARIO_FILE} ---")
    scenario = load_scenario(SCENARIO_FILE)
    
    # Create output directory
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    aggregated_kpis = []
    
    # Monte Carlo Loop
    for i in range(NUM_RUNS):
        seed = BASE_SEED + i
        run_id = f"run_{seed}"
        print(f"Executing Run {i+1}/{NUM_RUNS} (Seed: {seed})...")
        
        # 1. Parse Incumbents from JSON to Internal Objects
        incumbents_list = []
        for inc_data in scenario.get("incumbents", []):
            ant_data = inc_data.get("antenna", {})
            
            # Construct Antenna Pattern
            pattern = AntennaPatternParams(
                g_max_dbi=ant_data.get("gain_dbi", 38.0),
                hpbw_az_deg=ant_data.get("hpbw_az_deg", 1.73),
                hpbw_el_deg=ant_data.get("hpbw_el_deg", 1.73),
                sidelobe_floor_db=25.0 
            )
            
            # Construct Incumbent Object
            inc = {
                "id": inc_data["id"],
                "lat": inc_data["lat"],
                "lon": inc_data["lon"],
                "height_agl_m": inc_data["height_agl_m"],
                "freq_mhz": inc_data["freq_mhz"],
                "bw_mhz": inc_data["bw_mhz"],
                "antenna_pattern": pattern,
                "pointing_az_deg": ant_data.get("azimuth_deg", 0.0),
                "pointing_el_deg": ant_data.get("elevation_deg", 0.0)
            }
            incumbents_list.append(inc)

        # 2. Prepare Arguments
        # Dynamically resolve the 'tag' argument name to prevent TypeError
        tag_arg = resolve_tag_argument(randomized_multibw_random_channels_unii5, run_id)
        
        common_args = {
            "out_dir": Path(OUTPUT_DIR),
            "incumbents": incumbents_list,
            "ap_nominal_eirp_dbm": scenario["ap_nominal_eirp_dbm"],
            "duty_cycle": scenario["duty_cycle"],
            "duration_s": scenario["duration_s"],
            "sample_rate_hz": scenario["sample_rate_hz"],
            "inr_limit_db": scenario["inr_limit_db"],
            "environment": scenario["environment"],
            "path_model": scenario["path_model"],
            "seed": seed,
            "ap_indoor_fraction": scenario["ap_indoor_fraction"],
            "building_entry_loss_db": scenario["building_entry_loss_db"],
            "clutter_correction_db": scenario["clutter_correction_db"],
            "bandwidth_probs": {20.0: 0.2, 40.0: 0.4, 80.0: 0.4, 160.0: 0.0},
            "channel_weighting": "uniform"
        }
        
        # Merge arguments
        call_args = {**tag_arg, **common_args}

        # 3. Run the Recipe
        # This will return a dictionary of output paths
        try:
            result_paths = randomized_multibw_random_channels_unii5(**call_args)
        except TypeError as e:
            print(f"CRITICAL ERROR: Function signature mismatch. Error: {e}")
            print("Inspecting signature for debugging...")
            print(inspect.signature(randomized_multibw_random_channels_unii5))
            raise e
        
        # 4. Harvest Results
        csv_path = result_paths.get("per_incumbent_csv")
        if csv_path and os.path.exists(csv_path):
            df = pd.read_csv(csv_path)
            if not df.empty:
                row = df.iloc[0]
                kpi = {
                    "seed": seed,
                    "noise_rise_mean": row.get("noise_rise_db_mean", 0),
                    "noise_rise_p95": row.get("noise_rise_db_p95", 0),
                    "ipc_violation_prob": row.get("ipc_violation_probability_time", 0)
                }
                aggregated_kpis.append(kpi)
        
    # 5. Save Raw Aggregation
    if aggregated_kpis:
        results_df = pd.DataFrame(aggregated_kpis)
        summary_path = os.path.join(OUTPUT_DIR, "validation_summary_kim.csv")
        results_df.to_csv(summary_path, index=False)
        print(f"\n--- Batch Complete ---")
        print(f"Results aggregated to: {summary_path}")
        print("Ready for analytics phase.")
    else:
        print("No results were harvested. Check if simulation runs generated CSVs.")

if __name__ == "__main__":
    run_validation()