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
