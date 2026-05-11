"""Load simple RPE tables from CSV or list for Annex E-style interpolation.

CSV format (semicolon or comma):
angle_deg,attenuation_db
0,0
1,1.2
... etc.
"""

from pathlib import Path
from typing import Iterable, List, Tuple


def load_rpe_csv(path: str | Path) -> List[Tuple[float, float]]:
    text = Path(path).read_text(encoding="utf-8", errors="ignore")
    pts: List[Tuple[float, float]] = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        s = s.replace(";", ",")
        parts = [p.strip() for p in s.split(",")]
        if len(parts) < 2:
            continue
        try:
            ang = float(parts[0])
            att = float(parts[1])
            pts.append((ang, att))
        except Exception:
            continue
    pts.sort(key=lambda x: x[0])
    return pts


def rpe_from_list(values: Iterable[Tuple[float, float]]) -> List[Tuple[float, float]]:
    pts = [(float(a), float(d)) for a, d in values]
    pts.sort(key=lambda x: x[0])
    return pts


