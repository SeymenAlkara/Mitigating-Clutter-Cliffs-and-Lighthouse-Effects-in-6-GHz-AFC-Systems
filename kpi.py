from typing import Iterable


def inr_violation_probability(inr_db_values: Iterable[float], limit_db: float = -6.0) -> float:
    """Compute the fraction of samples where I/N > limit (violation).

    Args:
        inr_db_values: iterable of INR values in dB
        limit_db: threshold (default -6 dB)
    Returns:
        probability in [0, 1]
    """
    values = list(inr_db_values)
    if not values:
        return 0.0
    num_viol = sum(1 for x in values if x > limit_db)
    return num_viol / len(values)


def grant_stats(rows: Iterable[object]) -> dict:
    """Compute simple stats from grant rows (objects with .decision and .allowed_eirp_dbm).

    Returns a dict with counts and basic EIRP stats.
    """
    total = 0
    grants = 0
    denies = 0
    eirps: list[float] = []
    for r in rows:
        total += 1
        if getattr(r, "decision", "").lower() == "grant":
            grants += 1
        else:
            denies += 1
        e = getattr(r, "allowed_eirp_dbm", None)
        if isinstance(e, (int, float)):
            eirps.append(float(e))
    avg_eirp = sum(eirps) / len(eirps) if eirps else 0.0
    min_eirp = min(eirps) if eirps else 0.0
    max_eirp = max(eirps) if eirps else 0.0
    return {
        "total": total,
        "grants": grants,
        "denies": denies,
        "avg_eirp_dbm": avg_eirp,
        "min_eirp_dbm": min_eirp,
        "max_eirp_dbm": max_eirp,
    }


def ipc_violation_probability_from_grants(rows: Iterable[object]) -> float:
    """Approximate IPC violation probability from grant rows (deny => violation).

    This treats each row as one outcome; for finer granularity use aggregate INR helpers.
    """
    rows_list = list(rows)
    if not rows_list:
        return 0.0
    viol = sum(1 for r in rows_list if getattr(r, "decision", "").lower() == "deny")
    return viol / len(rows_list)


def ipc_violation_probability_from_aggregate(per_inc_results: Iterable[dict], limit_db: float = -6.0) -> float:
    """IPC violation probability from aggregate evaluator per-incumbent results.

    Expects items like {"inr_db": x, ...}. Returns fraction exceeding limit.
    """
    vals = [float(r.get("inr_db", -999.0)) for r in per_inc_results]
    return inr_violation_probability(vals, limit_db)

