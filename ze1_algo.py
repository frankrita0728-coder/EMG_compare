"""ZE1 / TTRI style EMG algorithms (from muscleCaptureForZE1).

Contraction: drift remove → abs → baseline@2s → downsample to ~128Hz →
threshold@3s → Schmitt UP/DOWN with merge gap.

Features: sliding-window RMS / iEMG / AEMG / MPF / MDF (window scaled vs 1259 Hz).
"""

from __future__ import annotations

from typing import Any

import numpy as np

try:
    from scipy.ndimage import uniform_filter1d
except ImportError:  # pragma: no cover
    uniform_filter1d = None


# ---------------------------------------------------------------------------
# Helpers / feature kernels (TTRI)
# ---------------------------------------------------------------------------

def moving_average(arr: np.ndarray, window: int, shift: int) -> np.ndarray:
    if arr.ndim != 1:
        raise ValueError("目前僅支援一維 ndarray")
    if window <= 0 or shift <= 0:
        raise ValueError("window 和 shift 必須為正整數")
    if window > len(arr):
        raise ValueError("window 大小不能大於資料長度")

    averages = []
    for start in range(0, len(arr) - window + 1, shift):
        averages.append(float(np.mean(arr[start : start + window])))
    return np.asarray(averages, dtype=float)


def downsample_mean(data: np.ndarray, ratio: int) -> np.ndarray:
    length = len(data)
    truncate_len = length - (length % ratio)
    data = data[:truncate_len]
    if truncate_len == 0:
        return np.asarray([], dtype=float)
    return data.reshape(-1, ratio).mean(axis=1)


def remove_drift_by_moving_average(signal: np.ndarray, window: int) -> np.ndarray:
    if uniform_filter1d is not None:
        baseline = uniform_filter1d(signal, size=max(1, int(window)))
        return signal - baseline
    # Fallback without scipy
    out = np.empty_like(signal, dtype=float)
    for i in range(len(signal)):
        start = max(0, i - window + 1)
        out[i] = signal[i] - float(np.mean(signal[start : i + 1]))
    return out


def emg_rms_modify(D, W_L, overlap, Fs):
    W_L = int((W_L * Fs) / 1259)
    overlap = int((overlap * Fs) / 1259)
    step = max(1, W_L - overlap)
    if W_L <= 0:
        return np.asarray([], dtype=float)

    emg_raw: list[float] = []
    rms_data: list[float] = []
    for value in D:
        emg_raw.append(float(value))
        if len(emg_raw) >= W_L:
            segment = np.asarray(emg_raw, dtype=float)
            rms_data.append(float(np.sqrt(np.mean(segment**2))))
            emg_raw = emg_raw[step:]
    return np.asarray(rms_data, dtype=float)


def emg_iemg_ttri(D, W_L, overlap, Fs):
    W_L = int((W_L * Fs) / 1259)
    overlap = int((overlap * Fs) / 1259)
    if W_L <= 0:
        return np.asarray([], dtype=float)
    if overlap >= W_L:
        raise ValueError("overlap 不能 >= W_L")

    emg_abs: list[float] = []
    iemg: list[float] = []
    sum_d = 0.0
    for value in np.abs(np.asarray(D, dtype=float)):
        emg_abs.append(float(value))
        if len(emg_abs) >= W_L:
            sum_d += float(np.sum(emg_abs)) / float(Fs)
            iemg.append(sum_d)
            del emg_abs[: (W_L - overlap)]
    return np.asarray(iemg, dtype=float)


def emg_aemg_ttri(D) -> float:
    arr = np.abs(np.asarray(D, dtype=float))
    if arr.size == 0:
        return 0.0
    return float(np.sum(arr) / len(arr))


def emg_mpf_ttri(D, W_L, overlap, Fs):
    W_L = int((W_L * Fs) / 1259)
    overlap = int((overlap * Fs) / 1259)
    if W_L <= 0:
        return []
    if overlap >= W_L:
        raise ValueError("overlap 必須小於 W_L")

    emg_raw: list[float] = []
    mpf_data: list[float] = []
    for value in D:
        emg_raw.append(float(value))
        if len(emg_raw) >= W_L:
            window = np.asarray(emg_raw, dtype=float)
            length = len(window)
            spectrum = np.fft.fft(window)
            p2 = np.abs(spectrum / length)
            p1 = p2[: length // 2 + 1].copy()
            if len(p1) > 2:
                p1[1:-1] = 2 * p1[1:-1]
            freqs = Fs * np.arange(0, length // 2 + 1) / length
            power = p1**2
            denom = float(np.sum(power))
            mpf_data.append(0.0 if denom <= 0 else float(np.sum(power * freqs) / denom))
            del emg_raw[: (W_L - overlap)]
    return mpf_data


def emg_mdf_ttri(D, W_L, overlap, Fs):
    W_L = int((W_L * Fs) / 1259)
    overlap = int((overlap * Fs) / 1259)
    if W_L <= 0:
        return []
    if overlap >= W_L:
        raise ValueError("overlap 必須小於 W_L")

    emg_raw: list[float] = []
    mdf_data: list[float] = []
    for value in D:
        emg_raw.append(float(value))
        if len(emg_raw) >= W_L:
            window = np.asarray(emg_raw, dtype=float)
            length = len(window)
            spectrum = np.fft.fft(window)
            p2 = np.abs(spectrum / length)
            p1 = p2[: length // 2 + 1].copy()
            if len(p1) > 2:
                p1[1:-1] = 2 * p1[1:-1]
            freqs = Fs * np.arange(0, length // 2 + 1) / length
            power = p1**2
            half = float(np.sum(power)) * 0.5
            cum = np.cumsum(power)
            idx = int(np.argmin(np.abs(half - cum)))
            mdf_data.append(float(freqs[idx]))
            del emg_raw[: (W_L - overlap)]
    return mdf_data


# ---------------------------------------------------------------------------
# Contraction detection (ZE1 Schmitt + merge gap)
# Delsys CSV 與自研 TXT 使用不同預設（對應各自原始腳本）。
# ---------------------------------------------------------------------------

ZE1_PRESETS: dict[str, dict[str, Any]] = {
    # muscleCaptureForZE1_v2_Rita(Delsys).py
    "delsys": {
        "up_n": 20,
        "down_n": 20,
        "merge_gap_n": 20,
        "window_size": 529,
        "threshold_mode": "delsys",
        "data_max": 0.1,  # mV 尺度（原腳本 Volt 用 0.0001）
    },
    # muscleCaptureForZE1_v2_Rita.py（ZE1 / TXT）
    "txt": {
        "up_n": 30,
        "down_n": 40,
        "merge_gap_n": 50,
        "window_size": 512,
        "threshold_mode": "legacy_mv",
        "data_max": 0.1,
    },
}


def resolve_ze1_preset(source: str | None = None) -> dict[str, Any]:
    key = (source or "delsys").strip().lower()
    if key in {"txt", "device", "ze1_device"}:
        return dict(ZE1_PRESETS["txt"])
    return dict(ZE1_PRESETS["delsys"])


def detect_contractions_ze1(
    values: list[float] | np.ndarray,
    *,
    sample_rate_hz: float = 1259.0,
    expected_count: int | None = None,
    source: str | None = None,
    up_n: int | None = None,
    down_n: int | None = None,
    merge_gap_n: int | None = None,
    window_size: int | None = None,
    smooth_bins: int = 32,
    target_hz: float = 128.0,
    data_max: float | None = None,
    threshold_mode: str | None = None,
    trim_to_expected: bool = False,
) -> dict[str, Any]:
    """
    Online-style ZE1 contraction capture rewritten as batch processing.

    Pass source=\"delsys\" or \"txt\" to apply the matching preset.
    Explicit keyword args override the preset.
    """
    preset = resolve_ze1_preset(source)
    if up_n is None:
        up_n = int(preset["up_n"])
    if down_n is None:
        down_n = int(preset["down_n"])
    if merge_gap_n is None:
        merge_gap_n = int(preset["merge_gap_n"])
    if window_size is None:
        window_size = int(preset["window_size"])
    if data_max is None:
        data_max = float(preset["data_max"])
    if threshold_mode is None:
        threshold_mode = str(preset["threshold_mode"])
    emg = np.asarray(values, dtype=float)
    fs = float(sample_rate_hz) if sample_rate_hz > 0 else 1259.0
    if emg.size < int(fs * 3) + 10:
        return {
            "contractions": [],
            "threshold": 0.0,
            "baseline": 0.0,
            "analysis_hz": target_hz,
            "method": "ze1_schmitt",
        }

    block = max(1, int(round(fs / target_hz)))
    analysis_hz = fs / block

    emg_raw_data: list[float] = []
    emg128_raw_data: list[float] = []
    baseline_acc: list[float] = []
    base_check = False
    emg_base_check = False
    active_muscle: list[float] = []
    up_trigger = False
    down_count = 0
    emg_raw_active: list[float] = []
    baseline = 0.0
    threshold = 0.0
    tentative_end = False
    gap_count = 0
    up_streak = 0
    current_start_bin: int | None = None
    moving_avg_list: list[float] = []
    bin_end_samples: list[int] = []
    segments: list[dict[str, Any]] = []

    mode = (threshold_mode or "delsys").strip().lower()
    # TXT×mV: wait a bit after 3 s so the post-baseline envelope settles before arming.
    threshold_ready_s = 4.0 if mode in {"legacy_mv", "mv_old", "txt"} else 3.0

    for i in range(len(emg)):
        start = max(0, i - window_size + 1)
        drift = float(np.mean(emg[start : i + 1]))
        corrected = float(emg[i] - drift)
        corrected_abs = abs(corrected)
        emg_raw_data.append(corrected)

        # Collect full 0–2 s for baseline (original comment intent)
        if not base_check:
            baseline_acc.append(corrected_abs)
            if i >= int(fs * 2):
                baseline = float(np.mean(baseline_acc)) if baseline_acc else 0.0
                base_check = True

        if len(emg_raw_data) < block:
            continue

        emg_raw_abs = np.abs(np.asarray(emg_raw_data, dtype=float))
        if base_check:
            emg_128mean = float(np.mean(emg_raw_abs - baseline))
        else:
            emg_128mean = float(np.mean(emg_raw_abs))

        emg128_raw_data.append(emg_128mean)
        emg_raw_data = []

        if len(emg128_raw_data) < smooth_bins:
            continue

        # Threshold after warm-up (TXT uses 4 s to avoid baseline-settling transient)
        if base_check and (not emg_base_check) and (i >= int(fs * threshold_ready_s)):
            recent = np.asarray(emg128_raw_data[-smooth_bins:], dtype=float)
            emg_base = float(np.mean(recent))
            std_online = float(np.std(recent))
            if mode in {"raw", "raw_std", "std"}:
                threshold = emg_base + std_online * 4.0
            elif mode in {"legacy_mv", "mv_old", "txt"}:
                legacy = emg_base + (0.1 - emg_base) * 4 / 100
                if emg_base < 0.5 and std_online < 0.2:
                    threshold = legacy
                else:
                    # Settled rest: mean + 2*std of last 32 bins (~0.25 s)
                    threshold = emg_base + 2.0 * max(std_online, 1e-6)
            else:
                # Delsys capture script (active formula), mV-scaled dataMax
                threshold = emg_base + (float(data_max) - emg_base) * 3 / 100
            emg_base_check = True

        if emg_base_check:
            emg_data = float(np.mean(emg128_raw_data[-smooth_bins:]))
            moving_avg_list.append(emg_data)
            bin_end_samples.append(i)

            if emg_data > threshold:
                active_muscle.append(emg_data)
                emg_raw_active.extend([emg_data] * block)
                down_count = 0

                if not up_trigger:
                    if len(active_muscle) >= up_n:
                        up_trigger = True
                        tentative_end = False
                        gap_count = 0
                        up_streak = 0
                        current_start_bin = len(moving_avg_list) - 1 - (up_n - 1)
                else:
                    if tentative_end:
                        up_streak += 1
                        gap_count += 1
                        if up_streak >= up_n and gap_count <= merge_gap_n:
                            tentative_end = False
                            gap_count = 0
                            up_streak = 0
            else:
                if not up_trigger:
                    active_muscle = []
                    emg_raw_active = []
                    down_count = 0
                    tentative_end = False
                    gap_count = 0
                    up_streak = 0
                else:
                    active_muscle.append(emg_data)
                    emg_raw_active.extend([emg_data] * block)

                    if not tentative_end:
                        down_count += 1
                        if down_count >= down_n:
                            tentative_end = True
                            gap_count = 0
                            up_streak = 0
                            down_count = 0
                    else:
                        gap_count += 1
                        up_streak = 0
                        if gap_count > merge_gap_n:
                            end_bin = len(moving_avg_list) - 1 - merge_gap_n
                            start_bin = (
                                current_start_bin
                                if current_start_bin is not None
                                else max(0, end_bin - len(active_muscle) + 1)
                            )
                            end_bin = max(int(start_bin), int(end_bin))
                            segments.append({"start_bin": int(start_bin), "end_bin": int(end_bin)})
                            emg_raw_active = []
                            active_muscle = []
                            down_count = 0
                            up_trigger = False
                            tentative_end = False
                            gap_count = 0
                            up_streak = 0
                            current_start_bin = None

        # Sliding 32-bin overlap window (same as original: del first sample)
        del emg128_raw_data[0]

    # Flush open segment at EOF
    if up_trigger and moving_avg_list:
        end_bin = len(moving_avg_list) - 1
        start_bin = (
            current_start_bin
            if current_start_bin is not None
            else max(0, end_bin)
        )
        segments.append({"start_bin": int(start_bin), "end_bin": int(end_bin)})

    contractions: list[dict[str, Any]] = []
    for index, seg in enumerate(segments, start=1):
        start_bin = max(0, min(int(seg["start_bin"]), len(bin_end_samples) - 1))
        end_bin = max(0, min(int(seg["end_bin"]), len(bin_end_samples) - 1))
        # bin_end_samples[k] = source sample when moving-avg bin k was produced.
        # Start of that analysis block ≈ end - block + 1.
        end_sample = int(bin_end_samples[end_bin]) + 1
        start_sample = int(bin_end_samples[start_bin]) - block + 1
        # Pull start back by Schmitt arming lag is already in start_bin (UP_N).
        # End includes DOWN_N + MERGE_GAP; trim trailing quiet bins for display.
        start_sample = max(0, min(start_sample, len(emg) - 1))
        end_sample = max(start_sample + 1, min(end_sample, len(emg)))
        start_s = start_sample / fs
        end_s = end_sample / fs
        contractions.append(
            {
                "index": index,
                "start": round(start_s, 4),
                "end": round(end_s, 4),
                "duration": round(end_s - start_s, 4),
                "peak_rms": 0.0,
                "start_sample": start_sample,
                "end_sample": end_sample,
            }
        )

    if (
        trim_to_expected
        and expected_count
        and expected_count > 0
        and len(contractions) > expected_count
    ):
        ranked = sorted(contractions, key=lambda c: c["duration"], reverse=True)
        selected = ranked[:expected_count]
        selected.sort(key=lambda c: c["start"])
        for i, item in enumerate(selected, start=1):
            item["index"] = i
        contractions = selected

    for item in contractions:
        s = item["start_sample"]
        e = item["end_sample"]
        seg = emg[s:e]
        if seg.size:
            item["peak_rms"] = round(float(np.sqrt(np.mean(seg * seg))), 6)

    return {
        "contractions": contractions,
        "threshold": float(threshold),
        "baseline": float(baseline),
        "analysis_hz": float(analysis_hz),
        "method": "ze1_schmitt",
        "envelope": moving_avg_list,
        "threshold_mode": mode,
        "source_preset": (source or "delsys").strip().lower(),
        "up_n": up_n,
        "down_n": down_n,
        "merge_gap_n": merge_gap_n,
        "window_size": window_size,
        "data_max": float(data_max),
    }


def features_ze1_for_interval(
    values: list[float] | np.ndarray,
    *,
    index: int,
    start: float,
    end: float,
    sample_rate: float,
    start_sample: int | None = None,
    end_sample: int | None = None,
    window_l: float = 157,
    overlap: float = 79,
) -> dict[str, Any]:
    arr = np.asarray(values, dtype=float)
    fs = float(sample_rate) if sample_rate > 0 else 1024.0
    if start_sample is None:
        start_sample = max(0, int(round(start * fs)))
    if end_sample is None:
        end_sample = max(start_sample + 1, int(round(end * fs)))
    start_sample = max(0, min(int(start_sample), len(arr)))
    end_sample = max(start_sample + 1, min(int(end_sample), len(arr)))
    seg = arr[start_sample:end_sample]

    rms_series = emg_rms_modify(seg, window_l, overlap, fs)
    iemg_series = emg_iemg_ttri(seg, window_l, 1, fs)
    mpf_series = emg_mpf_ttri(seg, window_l, overlap, fs)
    mdf_series = emg_mdf_ttri(seg, window_l, overlap, fs)
    aemg = emg_aemg_ttri(seg)

    return {
        "index": index,
        "start": round(float(start), 4),
        "end": round(float(end), 4),
        "duration": round(float(end - start), 4),
        "aemg": round(float(aemg), 6),
        "rms": round(float(np.mean(rms_series)) if len(rms_series) else 0.0, 6),
        "iemg": round(float(iemg_series[-1]) if len(iemg_series) else 0.0, 6),
        "mpf": round(float(np.mean(mpf_series)) if len(mpf_series) else 0.0, 2),
        "mdf": round(float(np.mean(mdf_series)) if len(mdf_series) else 0.0, 2),
        "peak_rms": round(float(np.max(rms_series)) if len(rms_series) else 0.0, 6),
        "method": "ttri",
    }


def _series_time_axis(n: int, sample_rate: float, window_l: float, overlap: float) -> list[float]:
    """Approximate center time (seconds) for each sliding window result."""
    fs = float(sample_rate) if sample_rate > 0 else 1024.0
    w = max(1, int((window_l * fs) / 1259))
    o = max(0, int((overlap * fs) / 1259))
    step = max(1, w - o)
    # First window ends at sample w; center ≈ w/2
    return [round((w / 2.0 + i * step) / fs, 4) for i in range(n)]


def _downsample_xy(xs: list[float], ys: list[float], max_points: int = 2500) -> tuple[list[float], list[float]]:
    if len(xs) <= max_points:
        return xs, ys
    step = max(1, len(xs) // max_points)
    out_x = xs[::step]
    out_y = ys[::step]
    if xs and out_x and xs[-1] != out_x[-1]:
        out_x.append(xs[-1])
        out_y.append(ys[-1])
    return out_x, out_y


def compute_ttri_feature_series(
    values: list[float] | np.ndarray,
    *,
    sample_rate: float,
    window_l: float = 157,
    overlap: float = 79,
    max_points: int = 2500,
) -> dict[str, Any]:
    """
    Full-signal TTRI feature curves (same kernels as muscleCaptureForZE1 plots).
    Returns downsampled x/y series for web plotting.
    """
    arr = np.asarray(values, dtype=float)
    fs = float(sample_rate) if sample_rate > 0 else 1024.0

    rms = np.asarray(emg_rms_modify(arr, window_l, overlap, fs), dtype=float)
    iemg = np.asarray(emg_iemg_ttri(arr, window_l, 1, fs), dtype=float)
    mpf = np.asarray(emg_mpf_ttri(arr, window_l, overlap, fs), dtype=float)
    mdf = np.asarray(emg_mdf_ttri(arr, window_l, overlap, fs), dtype=float)
    aemg = emg_aemg_ttri(arr)

    def pack(series: np.ndarray, ov: float) -> dict[str, list[float]]:
        ys = [float(v) for v in series.tolist()]
        xs = _series_time_axis(len(ys), fs, window_l, ov)
        xs, ys = _downsample_xy(xs, ys, max_points=max_points)
        return {"times": xs, "values": ys}

    return {
        "aemg": round(float(aemg), 6),
        "rms": pack(rms, overlap),
        "iemg": pack(iemg, 1),
        "mpf": pack(mpf, overlap),
        "mdf": pack(mdf, overlap),
        "window_l": window_l,
        "overlap": overlap,
        "sample_rate": fs,
    }
