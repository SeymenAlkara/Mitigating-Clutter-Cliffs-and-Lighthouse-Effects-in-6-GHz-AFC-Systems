"""End-to-end example: compute allowed EIRP for a path using parsed spec.

This example shows how to:
- Load spec parameters from the provided text file.
- Select a propagation model to compute path loss.
- Compute noise power at the incumbent receiver.
- Compute allowed EIRP (co-channel and adjacent-channel) under I/N <= -6 dB.

Run this as a script or copy snippets into a notebook.
"""

from pathlib import Path

# Use absolute imports so this file can be run from a notebook or as a module.
from afc_new.spec_params import load_params_from_text_file
from afc_new.propagation import select_pathloss_db
from afc_new.link_budget import noise_power_dbm
from afc_new.allocator import allowed_eirp_dbm_with_spec


def demo():
    project_root = Path(__file__).resolve().parents[1]
    text_spec_path = project_root / "docs" / "extracted_afc_text.txt"
    params = load_params_from_text_file(str(text_spec_path))

    # Example geometry/frequency
    f_hz = 6.0e9
    d_m = 5000.0
    pl_db = select_pathloss_db(distance_m=d_m, frequency_hz=f_hz)

    # Noise at incumbent
    n_dbm = noise_power_dbm(params.incumbent.bandwidth_hz, params.incumbent.noise_figure_db)

    # Co-channel allowed EIRP
    eirp_co = allowed_eirp_dbm_with_spec(
        n_dbm=n_dbm,
        inr_limit_db=-6.0,
        path_loss_db=pl_db,
        spec=params,
        channel_offset_mhz=None,
    )

    # Adjacent-channel (e.g., 20 MHz offset) allowed EIRP
    eirp_adj20 = allowed_eirp_dbm_with_spec(
        n_dbm=n_dbm,
        inr_limit_db=-6.0,
        path_loss_db=pl_db,
        spec=params,
        channel_offset_mhz=20,
    )

    print("Path loss (dB):", round(pl_db, 2))
    print("Noise (dBm):", round(n_dbm, 2))
    print("Allowed EIRP co-channel (dBm):", round(eirp_co, 2))
    print("Allowed EIRP +/−20 MHz (dBm):", round(eirp_adj20, 2))


if __name__ == "__main__":
    demo()

