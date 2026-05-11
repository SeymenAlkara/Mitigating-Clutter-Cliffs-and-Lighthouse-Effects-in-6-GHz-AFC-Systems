from __future__ import annotations

from typing import Optional, Tuple, List


def p452_basic_pathloss_db(
    *,
    distance_m: float,
    frequency_hz: float,
    tx_height_m_agl: float = 10.0,
    rx_height_m_agl: float = 10.0,
    tx_lon_deg: float = 0.0,
    tx_lat_deg: float = 0.0,
    rx_lon_deg: float = 0.0,
    rx_lat_deg: float = 0.0,
    polarization: int = 1,  # 1=H, 2=V
    pressure_hpa: float = 1013.0,
    temperature_c: float = 15.0,
    time_percentage: float = 50.0,
) -> float:
    """
    Minimal wrapper around Py452 to compute basic transmission loss (dB).

    Notes:
    - Builds a trivial two-point profile (flat terrain/clutter). For high
      fidelity, provide real profiles via Py452 directly.
    - Requires Py452 to be installed and its maps initialized.
    """
    try:
        from Py452 import P452  # type: ignore
    except Exception as e:  # pragma: no cover
        raise RuntimeError("Py452 not available. Install per README and run initiate_digital_maps.py") from e

    f_ghz = float(frequency_hz) / 1e9
    d_km: List[float] = [0.0, max(0.001, float(distance_m) / 1000.0)]
    # Flat terrain and no clutter profile (heights above sea level same)
    h_m_asl: List[float] = [0.0, 0.0]
    g_m_asl: List[float] = [0.0, 0.0]
    # Inland zone (2) as neutral default
    zone = [2 for _ in d_km]

    Lb = P452.bt_loss(
        f=f_ghz,
        p=float(time_percentage),
        d=d_km,
        h=h_m_asl,
        g=g_m_asl,
        zone=zone,
        htg=float(tx_height_m_agl),
        hrg=float(rx_height_m_agl),
        phit_e=float(tx_lon_deg),
        phit_n=float(tx_lat_deg),
        phir_e=float(rx_lon_deg),
        phir_n=float(rx_lat_deg),
        Gt=0.0,  # gains in the direction of horizon along path (handled elsewhere)
        Gr=0.0,
        pol=int(polarization),
        dct=0.0,
        dcr=0.0,
        press=float(pressure_hpa),
        temp=float(temperature_c),
    )
    return float(Lb)


