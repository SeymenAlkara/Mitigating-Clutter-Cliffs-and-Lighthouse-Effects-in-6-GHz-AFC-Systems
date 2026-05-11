"""Wi‑Fi 6/6E PHY: MCS thresholds and simple PER model.

This module provides a conservative MCS↔SNR mapping table (AWGN assumptions) and a
simple PER model to estimate effective PHY rate from SINR.

Notes:
- Thresholds here are indicative only; you can replace with lab‑measured values.
- Throughput calculation is simplified to payload efficiency times nominal MCS rate; a
  full MAC/PHY pipeline (coding, aggregation, preamble/overheads) is beyond scope here.
"""

from dataclasses import dataclass
from typing import List, Tuple
import math


@dataclass(frozen=True)
class McsEntry:
    mcs_index: int
    modulation: str
    code_rate: str
    snr_db_threshold: float  # minimum SNR to use this MCS (dB)
    spectral_eff_bps_hz: float  # nominal bits/s/Hz at this MCS per spatial stream


def default_mcs_table() -> List[McsEntry]:
    # Approximate thresholds (dB) for 20 MHz AWGN, per spatial stream; conservative.
    # spectral_eff ~ modulation order * code rate * OFDM efficiency.
    return [
        McsEntry(0, "BPSK", "1/2", 4.0, 0.5),
        McsEntry(1, "QPSK", "1/2", 7.0, 1.0),
        McsEntry(2, "QPSK", "3/4", 9.0, 1.5),
        McsEntry(3, "16-QAM", "1/2", 12.0, 2.0),
        McsEntry(4, "16-QAM", "3/4", 15.0, 3.0),
        McsEntry(5, "64-QAM", "2/3", 18.0, 4.0),
        McsEntry(6, "64-QAM", "3/4", 20.0, 4.5),
        McsEntry(7, "64-QAM", "5/6", 22.0, 5.0),
        McsEntry(8, "256-QAM", "3/4", 25.0, 6.0),
        McsEntry(9, "256-QAM", "5/6", 28.0, 6.7),
        # 1024-QAM entries may be used for HE (11ax) under favorable conditions
        McsEntry(10, "1024-QAM", "3/4", 31.0, 7.5),
        McsEntry(11, "1024-QAM", "5/6", 34.0, 8.0),
    ]


def pick_mcs_from_snr_db(snr_db: float, table: List[McsEntry] | None = None) -> McsEntry:
    if table is None:
        table = default_mcs_table()
    candidates = [m for m in table if snr_db >= m.snr_db_threshold]
    if not candidates:
        return table[0]
    return candidates[-1]


def per_from_snr_db(snr_db: float, mcs: McsEntry, k_packets_bits: int = 12000) -> float:
    """Toy PER model: logistic curve around threshold.

    We define PER(snr) = 1 / (1 + exp(alpha * (snr - (thr + delta)))) with alpha>0.
    delta determines margin beyond threshold for low PER. Chosen to drop below ~1% at thr+6 dB.
    """
    alpha = 0.8
    delta = 6.0
    x = alpha * (snr_db - (mcs.snr_db_threshold + delta))
    return 1.0 / (1.0 + math.exp(x))


def phy_rate_bps_from_snr_db(
    snr_db: float,
    bandwidth_hz: float,
    spatial_streams: int = 1,
    mcs_table: List[McsEntry] | None = None,
    mac_efficiency: float = 0.85,
) -> Tuple[McsEntry, float, float]:
    """Compute MCS, PER, and effective PHY throughput.

    Returns:
        (chosen_mcs, per, rate_bps)
    """
    mcs = pick_mcs_from_snr_db(snr_db, mcs_table)
    per = per_from_snr_db(snr_db, mcs)
    spectral = mcs.spectral_eff_bps_hz * spatial_streams
    raw_rate = spectral * bandwidth_hz
    eff_rate = raw_rate * mac_efficiency * (1.0 - per)
    return mcs, per, eff_rate

