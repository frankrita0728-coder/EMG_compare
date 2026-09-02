from __future__ import annotations

from typing import Any

import numpy as np

# Shared EMG preprocessing for ZE1 / ZE2 (and any device using the same band).
BANDPASS_HZ = (20.0, 400.0)
BANDPASS_ORDER = 4


def bandpass_filter(
    values: list[float] | np.ndarray,
    sample_rate: float,
    *,
    low_hz: float = BANDPASS_HZ[0],
    high_hz: float = BANDPASS_HZ[1],
    order: int = BANDPASS_ORDER,
) -> tuple[list[float], dict[str, Any]]:
    """Zero-phase Butterworth bandpass before analysis/plot."""
    arr = np.asarray(values, dtype=float)
    info: dict[str, Any] = {
        "applied": False,
        "low_hz": float(low_hz),
        "high_hz": float(high_hz),
        "order": int(order),
        "method": "butterworth_sosfiltfilt",
    }
    if arr.size < max(16, order * 6) or sample_rate <= 0:
        info["reason"] = "樣本過少或採樣率無效，略過濾波"
        return arr.tolist(), info

    nyquist = 0.5 * float(sample_rate)
    lo = max(0.1, float(low_hz))
    hi = min(float(high_hz), nyquist * 0.95)
    if hi <= lo:
        info["reason"] = f"截止頻率無效（fs={sample_rate}），略過濾波"
        return arr.tolist(), info

    try:
        from scipy.signal import butter, sosfiltfilt
    except ImportError as exc:
        raise ImportError("帶通濾波需要 scipy，請安裝：pip install scipy") from exc

    sos = butter(order, [lo, hi], btype="bandpass", fs=float(sample_rate), output="sos")
    filtered = sosfiltfilt(sos, arr)
    info.update(
        {
            "applied": True,
            "low_hz": lo,
            "high_hz": hi,
            "nyquist_hz": nyquist,
        }
    )
    return filtered.astype(float).tolist(), info


def filter_metadata_label(filter_info: dict[str, Any] | None) -> str:
    if not filter_info:
        return ""
    if filter_info.get("applied"):
        return (
            f"Butterworth bandpass {filter_info['low_hz']:.0f}-{filter_info['high_hz']:.0f} Hz "
            f"(order {filter_info['order']}, zero-phase)"
        )
    return str(filter_info.get("reason") or "")
