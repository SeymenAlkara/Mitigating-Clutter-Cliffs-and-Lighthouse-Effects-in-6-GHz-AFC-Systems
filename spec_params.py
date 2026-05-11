"""Specification parameter parsing and defaults.

This module provides:
- Data classes for key parameters (incumbent receiver, Wi‑Fi limits, ACIR tables).
- A tolerant regex-based parser that extracts defaults from free-form WINNF/FCC text.

Notes on defaults implemented from the spec text:
- When not explicitly given, the incumbent noise figure defaults to 4 dB for center
  frequencies ≤ 6425 MHz and 4.5 dB for > 6425 MHz, per ITU‑R F.758 reference
  mentioned in the WINNF document.
- Receiver bandwidth falls back to 20 MHz unless a line like "Receiver bandwidth: 40 MHz"
  or "B_Rx = 20 MHz" is found.
- ACIR lines like "ACIR ±20 MHz: 27 dB" split evenly into ACLR/ACS when only ACIR is
  provided; explicit ACLR/ACS lines override per offset.

WINNF-TS-1014 references:
- 9.1.2 Fixed Service Transmitter and Receiver Parameters (parsing NF/BW, G_rx, etc.)
- Annex C: Reference Table for FS Receiver Parameters (mapping from ULS to parameters)
"""
import re
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass(frozen=True)
class IncumbentReceiverParams:
    noise_figure_db: float = 5.0
    bandwidth_hz: float = 20e6
    antenna_gain_dbi: float = 30.0
    rx_losses_db: float = 1.0
    polarization_mismatch_db: float = 0.0


@dataclass(frozen=True)
class WiFiRegulatoryLimits:
    max_eirp_dbm: float = 36.0
    # Optional PSD cap (dBm/MHz). For SP this is typically 23 dBm/MHz; for LPI 5 dBm/MHz.
    max_psd_dbm_per_mhz: float = 23.0


@dataclass(frozen=True)
class ACIRSpec:
    # channel offset in MHz -> attenuation dB (Tx leakage and Rx selectivity)
    a_tx_db_by_offset_mhz: Dict[int, float]
    a_rx_db_by_offset_mhz: Dict[int, float]


@dataclass(frozen=True)
class SpecParameters:
    incumbent: IncumbentReceiverParams
    wifi_limits: WiFiRegulatoryLimits
    acir: ACIRSpec


def _parse_number_with_unit(value: str) -> Optional[float]:
    m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*(Hz|kHz|MHz|GHz)", value, re.IGNORECASE)
    if not m:
        return None
    num = float(m.group(1))
    unit = m.group(2).lower()
    scale = {"hz": 1.0, "khz": 1e3, "mhz": 1e6, "ghz": 1e9}[unit]
    return num * scale


def parse_spec_text_to_params(text: str, defaults: Optional[SpecParameters] = None) -> SpecParameters:
    """Parse a free-form spec text to extract a few key parameters; fall back to defaults.

    This is a best-effort regex-based extractor. It is tolerant to missing fields.
    """
    if defaults is None:
        defaults = SpecParameters(
            incumbent=IncumbentReceiverParams(),
            wifi_limits=WiFiRegulatoryLimits(),
            acir=ACIRSpec(a_tx_db_by_offset_mhz={20: 30.0, 40: 35.0}, a_rx_db_by_offset_mhz={20: 30.0, 40: 35.0}),
        )

    # Try to infer center frequency if present to apply NF default when not explicit.
    inferred_center_hz: Optional[float] = None
    for m_cf in re.finditer(r"(center\s*frequency|Fc|FS\s*-?Rx).*?([0-9]+(?:\.[0-9]+)?)\s*(GHz|MHz)", text, re.IGNORECASE | re.DOTALL):
        try:
            num = float(m_cf.group(2))
            unit = m_cf.group(3).lower()
            scale = 1e9 if unit == "ghz" else 1e6
            inferred_center_hz = num * scale
            break
        except Exception:
            continue

    nf_db = defaults.incumbent.noise_figure_db
    bw_hz = defaults.incumbent.bandwidth_hz
    g_rx = defaults.incumbent.antenna_gain_dbi
    rx_losses = defaults.incumbent.rx_losses_db
    pol = defaults.incumbent.polarization_mismatch_db
    max_eirp = defaults.wifi_limits.max_eirp_dbm
    a_tx = dict(defaults.acir.a_tx_db_by_offset_mhz)
    a_rx = dict(defaults.acir.a_rx_db_by_offset_mhz)

    # Noise figure
    m = re.search(r"noise\s*figure\s*[:=]\s*([0-9]+(?:\.[0-9]+)?)\s*dB", text, re.IGNORECASE)
    if m:
        nf_db = float(m.group(1))
    else:
        # Apply band-dependent default if center frequency inferred
        if inferred_center_hz is not None:
            if inferred_center_hz <= 6.425e9:
                nf_db = 4.0
            else:
                nf_db = 4.5

    # Receiver bandwidth
    m = re.search(r"(B[_ ]?Rx|receiver\s+bandwidth|noise\s+bandwidth)\s*[:=]\s*([^\n]+)", text, re.IGNORECASE)
    if m:
        parsed = _parse_number_with_unit(m.group(2))
        if parsed:
            bw_hz = parsed

    # Incumbent antenna gain
    m = re.search(r"incumbent\s*(antenna)?\s*gain\s*[:=]\s*([0-9]+(?:\.[0-9]+)?)\s*dBi", text, re.IGNORECASE)
    if m:
        g_rx = float(m.group(2))

    # Rx losses
    m = re.search(r"rx\s*loss(es)?\s*[:=]\s*([0-9]+(?:\.[0-9]+)?)\s*dB", text, re.IGNORECASE)
    if m:
        rx_losses = float(m.group(2))

    # Polarization
    m = re.search(r"polarizat(ion|ion mismatch)\s*[:=]\s*([0-9]+(?:\.[0-9]+)?)\s*dB", text, re.IGNORECASE)
    if m:
        pol = float(m.group(2))

    # Max EIRP
    m = re.search(r"max\s*EIRP\s*[:=]\s*([0-9]+(?:\.[0-9]+)?)\s*dBm", text, re.IGNORECASE)
    if m:
        max_eirp = float(m.group(1))

    # ACIR lines like: "ACIR ±20 MHz: 27 dB" or "ACLR/ACS at 20 MHz: 30/35 dB"
    for m in re.finditer(r"ACIR\s*[±+\-]?\s*([0-9]+)\s*MHz\s*[:=]\s*([0-9]+(?:\.[0-9]+)?)\s*dB", text, re.IGNORECASE):
        offset = int(m.group(1))
        val = float(m.group(2))
        # Split evenly between Tx/Rx if only ACIR provided
        a_tx[offset] = val / 2.0
        a_rx[offset] = val / 2.0

    for m in re.finditer(r"ACLR\s*at\s*([0-9]+)\s*MHz\s*[:=]\s*([0-9]+(?:\.[0-9]+)?)\s*dB", text, re.IGNORECASE):
        offset = int(m.group(1))
        a_tx[offset] = float(m.group(2))
    for m in re.finditer(r"ACS\s*at\s*([0-9]+)\s*MHz\s*[:=]\s*([0-9]+(?:\.[0-9]+)?)\s*dB", text, re.IGNORECASE):
        offset = int(m.group(1))
        a_rx[offset] = float(m.group(2))

    return SpecParameters(
        incumbent=IncumbentReceiverParams(
            noise_figure_db=nf_db,
            bandwidth_hz=bw_hz,
            antenna_gain_dbi=g_rx,
            rx_losses_db=rx_losses,
            polarization_mismatch_db=pol,
        ),
        wifi_limits=WiFiRegulatoryLimits(max_eirp_dbm=max_eirp),
        acir=ACIRSpec(a_tx_db_by_offset_mhz=a_tx, a_rx_db_by_offset_mhz=a_rx),
    )


def load_params_from_text_file(path: str, defaults: Optional[SpecParameters] = None) -> SpecParameters:
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        txt = f.read()
    return parse_spec_text_to_params(txt, defaults)

