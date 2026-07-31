from __future__ import annotations

import math
from typing import Any


def _percentile(sorted_values: list[float], percent: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = (len(sorted_values) - 1) * (percent / 100.0)
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return sorted_values[low]
    weight = rank - low
    return sorted_values[low] * (1.0 - weight) + sorted_values[high] * weight


def _estimate_sample_rate(times: list[float]) -> float:
    if len(times) < 2:
        return 1000.0
    dt = times[1] - times[0]
    if dt <= 0:
        return 1000.0
    return 1.0 / dt


def _build_rms_envelope(
    times: list[float],
    values: list[float],
    window_seconds: float = 0.06,
) -> tuple[list[float], list[float]]:
    sample_rate = _estimate_sample_rate(times)
    window = max(1, int(sample_rate * window_seconds))
    hop = max(1, window // 2)
    env_times: list[float] = []
    env_values: list[float] = []
    for start in range(0, max(1, len(values) - window + 1), hop):
        chunk = values[start : start + window]
        if not chunk:
            continue
        rms = math.sqrt(sum(sample * sample for sample in chunk) / len(chunk))
        center = start + len(chunk) // 2
        env_times.append(times[min(center, len(times) - 1)])
        env_values.append(rms)
    return env_times, env_values


def _trim_to_max_duration(
    env_times: list[float],
    env_values: list[float],
    left: int,
    right: int,
    peak_index: int,
    max_duration_seconds: float,
) -> tuple[int, int]:
    if env_times[right] - env_times[left] <= max_duration_seconds:
        return left, right

    target_start = env_times[peak_index] - max_duration_seconds / 2.0
    target_end = env_times[peak_index] + max_duration_seconds / 2.0
    new_left = left
    new_right = right
    while new_left < peak_index and env_times[new_left] < target_start:
        new_left += 1
    while new_right > peak_index and env_times[new_right] > target_end:
        new_right -= 1

    while env_times[new_right] - env_times[new_left] > max_duration_seconds and new_right > new_left:
        if env_values[new_left] <= env_values[new_right] and new_left < peak_index:
            new_left += 1
        elif new_right > peak_index:
            new_right -= 1
        else:
            break
    return new_left, new_right


def detect_contractions(
    times: list[float],
    values: list[float],
    expected_count: int = 3,
    min_duration_seconds: float = 0.5,
    merge_gap_seconds: float = 0.7,
    expand_relative: float = 0.18,
    pad_seconds: float = 0.6,
    max_duration_seconds: float = 7.0,
) -> list[dict[str, Any]]:
    if len(times) < 10 or len(values) < 10 or expected_count <= 0:
        return []

    env_times, env_values = _build_rms_envelope(times, values)
    if len(env_values) < 5:
        return []

    ranked = sorted(env_values)
    median = _percentile(ranked, 50)
    p75 = _percentile(ranked, 75)
    p80 = _percentile(ranked, 80)
    threshold = max(median + 1.5 * (p75 - median), p75)
    threshold = min(threshold, p80)

    above = [value >= threshold for value in env_values]
    raw_regions: list[list[int | float]] = []
    index = 0
    while index < len(above):
        if not above[index]:
            index += 1
            continue
        end = index
        while end < len(above) and above[end]:
            end += 1
        segment = env_values[index:end]
        peak = max(segment)
        peak_index = index + segment.index(peak)
        raw_regions.append([index, end - 1, peak, peak_index])
        index = end

    if not raw_regions:
        ranked_idx = sorted(range(len(env_values)), key=lambda i: env_values[i], reverse=True)
        used = [False] * len(env_values)
        for peak_i in ranked_idx:
            if used[peak_i]:
                continue
            left = peak_i
            right = peak_i
            floor = median + expand_relative * (env_values[peak_i] - median)
            while left > 0 and env_values[left - 1] >= floor:
                left -= 1
            while right < len(env_values) - 1 and env_values[right + 1] >= floor:
                right += 1
            for i in range(left, right + 1):
                used[i] = True
            raw_regions.append([left, right, env_values[peak_i], peak_i])
            if len(raw_regions) >= expected_count * 3:
                break

    merged: list[list[int | float]] = []
    for left, right, peak, peak_index in raw_regions:
        if merged and env_times[int(left)] - env_times[int(merged[-1][1])] <= merge_gap_seconds:
            current = merged[-1]
            current[1] = right
            if peak > current[2]:
                current[2] = peak
                current[3] = peak_index
        else:
            merged.append([left, right, peak, peak_index])

    expanded: list[list[float]] = []
    for left, right, peak, peak_index in merged:
        left_i = int(left)
        right_i = int(right)
        peak_i = int(peak_index)
        floor = median + expand_relative * (float(peak) - median)
        while left_i > 0 and env_values[left_i - 1] >= floor:
            left_i -= 1
        while right_i < len(env_values) - 1 and env_values[right_i + 1] >= floor:
            right_i += 1
        left_i, right_i = _trim_to_max_duration(
            env_times, env_values, left_i, right_i, peak_i, max_duration_seconds
        )
        start = max(env_times[0], env_times[left_i] - pad_seconds)
        end = min(env_times[-1], env_times[right_i] + pad_seconds)
        if end - start < min_duration_seconds:
            continue
        expanded.append([start, end, float(peak)])

    expanded.sort(key=lambda region: region[0])
    fused: list[list[float]] = []
    for start, end, peak in expanded:
        if fused and start <= fused[-1][1] + 0.2:
            span = max(fused[-1][1], end) - fused[-1][0]
            if span <= max_duration_seconds + 1.0:
                fused[-1][1] = max(fused[-1][1], end)
                fused[-1][2] = max(fused[-1][2], peak)
                continue
        fused.append([start, end, peak])

    fused.sort(key=lambda region: region[2], reverse=True)
    selected = fused[:expected_count]
    selected.sort(key=lambda region: region[0])

    results: list[dict[str, Any]] = []
    for index, (start, end, peak) in enumerate(selected, start=1):
        results.append(
            {
                "index": index,
                "start": round(float(start), 4),
                "end": round(float(end), 4),
                "duration": round(float(end - start), 4),
                "peak_rms": round(float(peak), 6),
            }
        )
    return results


def detect_contractions_dispatch(
    times: list[float],
    values: list[float],
    *,
    method: str = "rms_peak",
    expected_count: int = 3,
    sample_rate: float | None = None,
    source: str | None = None,
) -> list[dict[str, Any]]:
    """Select contraction detector by method name."""
    method = (method or "rms_peak").strip().lower()
    if method in {"ze1", "ze1_schmitt", "schmitt"}:
        from ze1_algo import detect_contractions_ze1

        fs = sample_rate
        if not fs or fs <= 0:
            fs = _estimate_sample_rate(times)
        result = detect_contractions_ze1(
            values,
            sample_rate_hz=float(fs),
            expected_count=expected_count,
            source=source,
        )
        return list(result.get("contractions") or [])

    return detect_contractions(times, values, expected_count=expected_count)
