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


def icc_absolute_agreement(xs: list[float], ys: list[float]) -> float | None:
    """
    ICC(A,1) / ICC(2,1) absolute agreement for two raters (Delsys vs device).

    McGraw & Wong two-way random effects, single measurement, absolute agreement.
    None if fewer than 2 pairs or degenerate mean squares.
    """
    if len(xs) != len(ys) or len(xs) < 2:
        return None
    x = np.asarray(xs, dtype=float)
    y = np.asarray(ys, dtype=float)
    if not np.isfinite(x).all() or not np.isfinite(y).all():
        return None

    n = int(x.size)
    k = 2
    data = np.column_stack([x, y])
    grand = float(np.mean(data))
    row_means = np.mean(data, axis=1)
    col_means = np.mean(data, axis=0)

    ss_rows = float(k * np.sum((row_means - grand) ** 2))
    ss_cols = float(n * np.sum((col_means - grand) ** 2))
    ss_total = float(np.sum((data - grand) ** 2))
    ss_err = ss_total - ss_rows - ss_cols
    if ss_err < 0 and abs(ss_err) < 1e-12:
        ss_err = 0.0

    df_rows = n - 1
    df_err = (n - 1) * (k - 1)
    if df_rows <= 0 or df_err <= 0:
        return None

    msb = ss_rows / df_rows
    msr = ss_cols / (k - 1)
    mse = ss_err / df_err
    denom = msb + (k - 1) * mse + k * (msr - mse) / n
    if abs(denom) <= 1e-15:
        return None
    icc = (msb - mse) / denom
    if not np.isfinite(icc):
        return None
    # ICC can be slightly negative when agreement is worse than chance.
    return round(float(icc), 4)


def interval_agreement(
    left_rows: list[dict[str, Any]],
    right_rows: list[dict[str, Any]],
    metrics: tuple[str, ...] | list[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Per-metric Pearson r and ICC(A,1) across paired contraction-interval features.
    Each row of left/right is one contraction interval (same index).
    """
    keys = tuple(metrics) if metrics else SPECTRAL_METRICS
    count = min(len(left_rows), len(right_rows))
    rows: list[dict[str, Any]] = []
    for key in keys:
        xs: list[float] = []
        ys: list[float] = []
        for i in range(count):
            lv = left_rows[i].get(key)
            rv = right_rows[i].get(key)
            if isinstance(lv, (int, float)) and isinstance(rv, (int, float)):
                xs.append(float(lv))
                ys.append(float(rv))
        rows.append(
            {
                "metric": key,
                "n": len(xs),
                "pearson_r": pearson_corr(xs, ys),
                "icc": icc_absolute_agreement(xs, ys),
            }
        )
    return rows


# Fatigue visibility: spectral shift across successive contractions.
# Classic EMG fatigue: MPF/MDF decline; amplitude (RMS/AEMG) may rise.
FATIGUE_MIN_SEGMENTS = 5
FATIGUE_SPECTRAL_R_MAX = -0.35  # Pearson r of metric vs contraction index
FATIGUE_SPECTRAL_PCT_MAX = -3.0  # first-third → last-third relative %
FATIGUE_AMP_R_MIN = 0.35
FATIGUE_AMP_PCT_MIN = 5.0


def _trend_vs_index(values: list[float]) -> dict[str, float | None]:
    """Linear trend of a metric across ordered contraction indices (1..n)."""
    n = len(values)
    if n < 2:
        return {
            "n": float(n),
            "r_vs_index": None,
            "slope_per_contraction": None,
            "first_third_mean": None,
            "last_third_mean": None,
            "pct_change": None,
        }
    idx = [float(i + 1) for i in range(n)]
    r = pearson_corr(idx, values)
    x = np.asarray(idx, dtype=float)
    y = np.asarray(values, dtype=float)
    slope = float(np.polyfit(x, y, 1)[0]) if np.isfinite(y).all() else None
    third = max(1, n // 3)
    first_m = float(np.mean(y[:third]))
    last_m = float(np.mean(y[-third:]))
    pct = None
    if abs(first_m) > 1e-12:
        pct = 100.0 * (last_m - first_m) / first_m
    return {
        "n": float(n),
        "r_vs_index": r,
        "slope_per_contraction": round(slope, 6) if slope is not None and np.isfinite(slope) else None,
        "first_third_mean": round(first_m, 6),
        "last_third_mean": round(last_m, 6),
        "pct_change": round(pct, 2) if pct is not None and np.isfinite(pct) else None,
    }


def _metric_series(rows: list[dict[str, Any]], key: str) -> list[float]:
    out: list[float] = []
    for row in rows:
        v = row.get(key)
        if isinstance(v, (int, float)) and np.isfinite(float(v)):
            out.append(float(v))
    return out


def assess_fatigue_visibility(
    feature_rows: list[dict[str, Any]] | None,
    *,
    label: str = "",
) -> dict[str, Any]:
    """
    Decide whether fatigue is visible within one recording's contraction sequence.

    Primary evidence: MPF and/or MDF decline across successive contractions
    (spectral compression). Supporting: RMS/AEMG rise.

    Returns Chinese ``visible`` label: 是 / 弱／不明顯 / 否 / 段數不足.
    """
    rows = list(feature_rows or [])
    n = len(rows)
    base: dict[str, Any] = {
        "label": label,
        "n_contractions": n,
        "visible": "段數不足",
        "visible_en": "insufficient",
        "evidence": [],
        "metrics": {},
        "rule": (
            f"需≥{FATIGUE_MIN_SEGMENTS}段；頻譜疲勞：MPF/MDF 對收縮序 r≤{FATIGUE_SPECTRAL_R_MAX} "
            f"且前→後三分之一變化≤{FATIGUE_SPECTRAL_PCT_MAX}%；"
            f"振幅輔助：RMS/AEMG r≥{FATIGUE_AMP_R_MIN} 且變化≥{FATIGUE_AMP_PCT_MIN}%。"
        ),
    }
    if n < FATIGUE_MIN_SEGMENTS:
        return base

    trends: dict[str, dict[str, float | None]] = {}
    for key in ("mpf", "mdf", "rms", "aemg"):
        series = _metric_series(rows, key)
        if len(series) >= FATIGUE_MIN_SEGMENTS:
            trends[key] = _trend_vs_index(series)
    base["metrics"] = trends

    evidence: list[str] = []
    spectral_hits = 0
    for key in ("mpf", "mdf"):
        t = trends.get(key) or {}
        r = t.get("r_vs_index")
        pct = t.get("pct_change")
        if (
            isinstance(r, (int, float))
            and isinstance(pct, (int, float))
            and float(r) <= FATIGUE_SPECTRAL_R_MAX
            and float(pct) <= FATIGUE_SPECTRAL_PCT_MAX
        ):
            spectral_hits += 1
            evidence.append(
                f"{key.upper()}↓ r={float(r):.2f}, Δ={float(pct):.1f}% "
                f"({t.get('first_third_mean')}→{t.get('last_third_mean')})"
            )

    amp_hits = 0
    for key in ("rms", "aemg"):
        t = trends.get(key) or {}
        r = t.get("r_vs_index")
        pct = t.get("pct_change")
        if (
            isinstance(r, (int, float))
            and isinstance(pct, (int, float))
            and float(r) >= FATIGUE_AMP_R_MIN
            and float(pct) >= FATIGUE_AMP_PCT_MIN
        ):
            amp_hits += 1
            evidence.append(
                f"{key.upper()}↑ r={float(r):.2f}, Δ={float(pct):.1f}% "
                f"({t.get('first_third_mean')}→{t.get('last_third_mean')})"
            )

    base["evidence"] = evidence
    base["spectral_hits"] = spectral_hits
    base["amplitude_hits"] = amp_hits

    if spectral_hits >= 2 or (spectral_hits >= 1 and amp_hits >= 1):
        base["visible"] = "是"
        base["visible_en"] = "yes"
    elif spectral_hits >= 1 or amp_hits >= 1:
        base["visible"] = "弱／不明顯"
        base["visible_en"] = "weak"
    else:
        base["visible"] = "否"
        base["visible_en"] = "no"
        if not evidence:
            # Summarize why not: report MPF/MDF direction briefly
            notes: list[str] = []
            for key in ("mpf", "mdf"):
                t = trends.get(key) or {}
                r = t.get("r_vs_index")
                pct = t.get("pct_change")
                if r is not None and pct is not None:
                    notes.append(f"{key.upper()} r={float(r):.2f}, Δ={float(pct):.1f}%")
            base["evidence"] = notes or ["頻譜／振幅趨勢未達門檻"]
    return base


def assess_pair_fatigue_visibility(
    left_rows: list[dict[str, Any]] | None,
    right_rows: list[dict[str, Any]] | None,
    *,
    left_label: str = "對照組",
    right_label: str = "實驗組",
) -> dict[str, Any]:
    """Fatigue visibility for both sides of a compare pair + combined verdict."""
    left = assess_fatigue_visibility(left_rows, label=left_label)
    right = assess_fatigue_visibility(right_rows, label=right_label)
    left_v = str(left.get("visible_en") or "")
    right_v = str(right.get("visible_en") or "")

    rank = {"yes": 3, "weak": 2, "no": 1, "insufficient": 0}
    # Combined: yes if either side clearly shows fatigue; weak if only weak; else no.
    if left_v == "yes" or right_v == "yes":
        combined, combined_en = "是", "yes"
    elif left_v == "weak" or right_v == "weak":
        combined, combined_en = "弱／不明顯", "weak"
    elif left_v == "insufficient" and right_v == "insufficient":
        combined, combined_en = "段數不足", "insufficient"
    else:
        combined, combined_en = "否", "no"

    return {
        "visible": combined,
        "visible_en": combined_en,
        "ref": left,
        "exp": right,
        "summary": (
            f"綜合：{combined}｜{left_label}：{left.get('visible')}｜"
            f"{right_label}：{right.get('visible')}"
        ),
        "score_ref": rank.get(left_v, 0),
        "score_exp": rank.get(right_v, 0),
    }


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
