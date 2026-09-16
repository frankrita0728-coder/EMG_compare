from __future__ import annotations

import math
from typing import Any

import numpy as np

from detector import detect_contractions_dispatch


SPECTRAL_METRICS = ("duration", "iemg", "rms", "mdf", "mpf", "peak_rms")
TTRI_METRICS = ("duration", "aemg", "iemg", "rms", "mdf", "mpf", "peak_rms")


def compute_mdf_mpf(
    segment: np.ndarray,
    sample_rate_hz: float,
    *,
    f_low_hz: float = 20.0,
    f_high_hz: float = 450.0,
) -> tuple[float, float]:
    arr = np.asarray(segment, dtype=float)
    fs = float(sample_rate_hz)
    if arr.size < 4 or fs <= 0:
        return 0.0, 0.0

    x = arr - float(arr.mean())
    n = int(x.size)
    window = np.hanning(n)
    spectrum = np.fft.rfft(x * window)
    power = np.abs(spectrum) ** 2
    freqs = np.fft.rfftfreq(n, d=1.0 / fs)
    nyquist = 0.5 * fs
    lo = max(0.0, float(f_low_hz))
    hi = min(float(f_high_hz), nyquist)
    if hi <= lo:
        lo, hi = 0.0, nyquist
    band = (freqs >= lo) & (freqs <= hi)
    power = np.where(band, power, 0.0)
    total = float(power.sum())
    if total <= 0.0:
        return 0.0, 0.0

    mpf = float(np.sum(freqs * power) / total)
    half = 0.5 * total
    cum = np.cumsum(power)
    idx = int(np.searchsorted(cum, half, side="left"))
    idx = min(max(idx, 0), len(freqs) - 1)
    mdf = float(freqs[idx])
    return mdf, mpf


def _index_at_time(times: list[float], target: float) -> int:
    if not times:
        return 0
    best = 0
    best_diff = abs(times[0] - target)
    for i, t in enumerate(times):
        diff = abs(t - target)
        if diff < best_diff:
            best = i
            best_diff = diff
    return best


def features_for_interval(
    times: list[float],
    values: list[float],
    *,
    index: int,
    start: float,
    end: float,
    sample_rate: float,
    peak_rms: float = 0.0,
) -> dict[str, Any]:
    i0 = _index_at_time(times, start)
    i1 = _index_at_time(times, end)
    if i1 <= i0:
        i1 = min(len(values), i0 + 1)
    seg = np.asarray(values[i0:i1], dtype=float)
    duration = float(end - start)
    if seg.size == 0:
        return {
            "index": index,
            "start": round(start, 4),
            "end": round(end, 4),
            "duration": round(duration, 4),
            "iemg": 0.0,
            "rms": 0.0,
            "mdf": 0.0,
            "mpf": 0.0,
            "peak_rms": round(peak_rms, 6),
            "method": "spectral",
        }

    abs_seg = np.abs(seg)
    mdf, mpf = compute_mdf_mpf(seg, sample_rate)
    return {
        "index": index,
        "start": round(start, 4),
        "end": round(end, 4),
        "duration": round(duration, 4),
        "iemg": round(float(abs_seg.sum()), 4),
        "rms": round(float(math.sqrt(float(np.mean(seg * seg)))), 6),
        "mdf": round(mdf, 2),
        "mpf": round(mpf, 2),
        "peak_rms": round(peak_rms, 6),
        "method": "spectral",
    }


def analyze_signal_features(
    times: list[float],
    values: list[float],
    *,
    sample_rate: float,
    expected_count: int = 3,
    contraction_method: str = "rms_peak",
    feature_method: str = "spectral",
    source: str | None = None,
) -> dict[str, Any]:
    contractions = detect_contractions_dispatch(
        times,
        values,
        method=contraction_method,
        expected_count=expected_count,
        sample_rate=sample_rate,
        source=source,
    )

    feature_method = (feature_method or "spectral").strip().lower()
    rows: list[dict[str, Any]] = []

    if feature_method in {"ttri", "ze1", "muscle_capture"}:
        from ze1_algo import compute_ttri_feature_series, features_ze1_for_interval

        for item in contractions:
            rows.append(
                features_ze1_for_interval(
                    values,
                    index=item["index"],
                    start=item["start"],
                    end=item["end"],
                    sample_rate=sample_rate,
                    start_sample=item.get("start_sample"),
                    end_sample=item.get("end_sample"),
                )
            )
        metrics = TTRI_METRICS
        series = compute_ttri_feature_series(values, sample_rate=sample_rate)
    else:
        for item in contractions:
            rows.append(
                features_for_interval(
                    times,
                    values,
                    index=item["index"],
                    start=item["start"],
                    end=item["end"],
                    sample_rate=sample_rate,
                    peak_rms=item.get("peak_rms", 0.0),
                )
            )
        metrics = SPECTRAL_METRICS
        series = None

    return {
        "contractions": contractions,
        "features": rows,
        "count": len(rows),
        "contraction_method": contraction_method,
        "feature_method": feature_method,
        "metrics": list(metrics),
        "series": series,
    }


def compare_feature_rows(
    left_rows: list[dict[str, Any]],
    right_rows: list[dict[str, Any]],
    metrics: tuple[str, ...] | list[str] | None = None,
) -> list[dict[str, Any]]:
    count = max(len(left_rows), len(right_rows))
    pairs: list[dict[str, Any]] = []
    keys = tuple(metrics) if metrics else SPECTRAL_METRICS
    for i in range(count):
        left = left_rows[i] if i < len(left_rows) else None
        right = right_rows[i] if i < len(right_rows) else None
        delta: dict[str, Any] = {}
        for key in keys:
            lv = None if left is None else left.get(key)
            rv = None if right is None else right.get(key)
            if isinstance(lv, (int, float)) and isinstance(rv, (int, float)):
                delta[key] = round(float(lv) - float(rv), 6)
            else:
                delta[key] = None
        pairs.append({"index": i + 1, "delsys": left, "txt": right, "delta": delta})
    return pairs


def pearson_corr(xs: list[float], ys: list[float]) -> float | None:
    """Pearson r for paired samples; None if fewer than 2 pairs or zero variance."""
    if len(xs) != len(ys) or len(xs) < 2:
        return None
    x = np.asarray(xs, dtype=float)
    y = np.asarray(ys, dtype=float)
    if not np.isfinite(x).all() or not np.isfinite(y).all():
        return None
    x_std = float(np.std(x))
    y_std = float(np.std(y))
    if x_std <= 0.0 or y_std <= 0.0:
        return None
    r = float(np.corrcoef(x, y)[0, 1])
    if not np.isfinite(r):
        return None
    return round(r, 4)


SERIES_CORR_METRICS = ("rms", "iemg", "mpf", "mdf")


def feature_correlations(
    left_rows: list[dict[str, Any]],
    right_rows: list[dict[str, Any]],
    metrics: tuple[str, ...] | list[str] | None = None,
) -> dict[str, float | None]:
    """
    Pearson r per metric across paired contraction intervals (same index).
    Requires at least 2 valid numeric pairs for a metric.
    """
    keys = tuple(metrics) if metrics else SPECTRAL_METRICS
    count = min(len(left_rows), len(right_rows))
    out: dict[str, float | None] = {}
    for key in keys:
        xs: list[float] = []
        ys: list[float] = []
        for i in range(count):
            lv = left_rows[i].get(key)
            rv = right_rows[i].get(key)
            if isinstance(lv, (int, float)) and isinstance(rv, (int, float)):
                xs.append(float(lv))
                ys.append(float(rv))
        out[key] = pearson_corr(xs, ys)
    return out


def _interval_mask(times: np.ndarray, intervals: list[dict[str, Any]] | None) -> np.ndarray:
    """True where time falls inside any [start, end] contraction interval."""
    if times.size == 0:
        return np.zeros(0, dtype=bool)
    if not intervals:
        return np.ones(times.size, dtype=bool)
    mask = np.zeros(times.size, dtype=bool)
    for item in intervals:
        try:
            start = float(item.get("start"))
            end = float(item.get("end"))
        except (TypeError, ValueError):
            continue
        if end > start:
            mask |= (times >= start) & (times <= end)
    return mask


def series_correlations(
    left_series: dict[str, Any] | None,
    right_series: dict[str, Any] | None,
    metrics: tuple[str, ...] | list[str] | None = None,
    *,
    intervals: list[dict[str, Any]] | None = None,
) -> dict[str, float | None]:
    """
    Pearson r per TTRI sliding-window feature curve.

    Aligns by overlapping time range: interpolate the right series onto the
    left series time stamps, optionally keep only samples inside contraction
    intervals (rest excluded), then compute r.
    """
    keys = tuple(metrics) if metrics else SERIES_CORR_METRICS
    out: dict[str, float | None] = {key: None for key in keys}
    if not left_series or not right_series:
        return out

    for key in keys:
        left = left_series.get(key) or {}
        right = right_series.get(key) or {}
        lt = np.asarray(left.get("times") or [], dtype=float)
        lv = np.asarray(left.get("values") or [], dtype=float)
        rt = np.asarray(right.get("times") or [], dtype=float)
        rv = np.asarray(right.get("values") or [], dtype=float)
        if lt.size < 2 or rt.size < 2 or lv.size != lt.size or rv.size != rt.size:
            continue
        t0 = float(max(lt[0], rt[0]))
        t1 = float(min(lt[-1], rt[-1]))
        if t1 <= t0:
            continue
        mask = (lt >= t0) & (lt <= t1)
        if intervals is not None:
            mask &= _interval_mask(lt, intervals)
        t_common = lt[mask]
        if t_common.size < 2:
            continue
        x = lv[mask]
        y = np.interp(t_common, rt, rv)
        out[key] = pearson_corr(x.tolist(), y.tolist())
    return out
