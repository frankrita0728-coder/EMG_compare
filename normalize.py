from __future__ import annotations

import math
from typing import Any


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    avg = _mean(values)
    variance = sum((v - avg) ** 2 for v in values) / len(values)
    return math.sqrt(variance)


def zscore(values: list[float]) -> list[float]:
    avg = _mean(values)
    sigma = _std(values)
    if sigma <= 1e-12:
        return [0.0 for _ in values]
    return [(v - avg) / sigma for v in values]


def robust_zscore(values: list[float]) -> list[float]:
    """Median/MAD z-score so brief electrode spikes do not flatten the plot."""
    if not values:
        return []
    sorted_vals = sorted(values)
    mid = len(sorted_vals) // 2
    if len(sorted_vals) % 2:
        med = sorted_vals[mid]
    else:
        med = 0.5 * (sorted_vals[mid - 1] + sorted_vals[mid])
    deviations = sorted(abs(v - med) for v in values)
    mid_d = len(deviations) // 2
    if len(deviations) % 2:
        mad = deviations[mid_d]
    else:
        mad = 0.5 * (deviations[mid_d - 1] + deviations[mid_d])
    sigma = 1.4826 * mad
    if sigma <= 1e-12:
        return zscore(values)
    return [(v - med) / sigma for v in values]


def maxabs(values: list[float]) -> list[float]:
    peak = max((abs(v) for v in values), default=0.0)
    if peak <= 1e-12:
        return [0.0 for _ in values]
    return [v / peak for v in values]


def normalize_trace(trace: dict[str, Any], method: str = "zscore") -> dict[str, Any]:
    values = list(trace["values"])
    raw_unit = str(trace.get("unit") or "raw")

    if method in {"none", "raw", "original"}:
        method = "none"
        normalized = values
        unit = raw_unit
    elif method == "maxabs":
        normalized = maxabs(values)
        unit = "norm (maxabs)"
    elif method in {"robust", "robust_zscore", "mad"}:
        method = "robust_zscore"
        normalized = robust_zscore(values)
        unit = "norm (robust z)"
    else:
        method = "zscore"
        normalized = zscore(values)
        unit = "norm (zscore)"

    return {
        **trace,
        "values": normalized,
        "norm_method": method,
        "unit": unit,
    }
