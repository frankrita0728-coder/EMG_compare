from __future__ import annotations

from typing import Any

from align import align_traces_by_start, parse_delsys_start
from detector import detect_contractions_dispatch
from features import analyze_signal_features, compare_feature_rows
from normalize import normalize_trace
from parsers.delsys import load_delsys_emg
from parsers.txt_device import load_txt_emg


def load_signal(
    source: str,
    filename: str,
    *,
    for_plot: bool = False,
    year: int | None = None,
) -> dict[str, Any]:
    if source == "delsys":
        return load_delsys_emg(filename, for_plot=for_plot)
    if source == "txt":
        return load_txt_emg(filename, for_plot=for_plot, year=year)
    raise ValueError(f"未知來源：{source}")


def _year_from_delsys(delsys_name: str | None) -> int | None:
    if not delsys_name:
        return None
    try:
        left = load_delsys_emg(delsys_name, for_plot=True)
    except (FileNotFoundError, ValueError):
        return None
    start = parse_delsys_start(left.get("metadata"))
    return start.year if start else None


def build_waveform_single(
    source: str,
    filename: str,
    *,
    norm_method: str = "zscore",
    year: int | None = None,
) -> dict[str, Any]:
    raw = load_signal(source, filename, for_plot=True, year=year)
    normalized = normalize_trace(raw, method=norm_method)
    return {
        "mode": "waveform_single",
        "source": source,
        "norm_method": norm_method,
        "trace": {
            "filename": raw["filename"],
            "signal_name": raw["signal_name"],
            "sample_rate": raw["sample_rate"],
            "unit": raw["unit"],
            "point_count": raw["point_count"],
            "times": normalized["times"],
            "values": normalized["values"],
            "raw_unit": raw["unit"],
            "start_time": raw.get("start_time"),
            "start_epoch": raw.get("start_epoch"),
            "start_label": raw.get("start_label") or "",
        },
    }


def build_waveform_compare(
    delsys_name: str,
    txt_name: str,
    *,
    norm_method: str = "zscore",
    align_by_start: bool = True,
) -> dict[str, Any]:
    left = load_delsys_emg(delsys_name, for_plot=True)
    year = None
    start = parse_delsys_start(left.get("metadata"))
    if start:
        year = start.year
    right = load_txt_emg(txt_name, for_plot=True, year=year)
    left_n = normalize_trace(left, method=norm_method)
    right_n = normalize_trace(right, method=norm_method)

    delsys_trace = {
        "filename": left["filename"],
        "signal_name": left["signal_name"],
        "sample_rate": left["sample_rate"],
        "unit": left_n["unit"],
        "point_count": left["point_count"],
        "times": left_n["times"],
        "values": left_n["values"],
        "raw_unit": left["unit"],
        "start_time": left.get("start_time"),
        "start_epoch": left.get("start_epoch"),
        "start_label": left.get("start_label") or "",
        "source": "delsys",
    }
    txt_trace = {
        "filename": right["filename"],
        "signal_name": right["signal_name"],
        "sample_rate": right["sample_rate"],
        "unit": right_n["unit"],
        "point_count": right["point_count"],
        "times": right_n["times"],
        "values": right_n["values"],
        "raw_unit": right["unit"],
        "start_time": right.get("start_time"),
        "start_epoch": right.get("start_epoch"),
        "start_label": right.get("start_label") or "",
        "source": "txt",
    }

    align_info: dict[str, Any] = {"aligned": False}
    if align_by_start:
        aligned, align_info = align_traces_by_start([delsys_trace, txt_trace])
        delsys_trace, txt_trace = aligned[0], aligned[1]

    note_parts = []
    if norm_method == "none":
        note_parts.append("顯示原始單位波形（Delsys / TXT 皆為 mV；TXT 已套用 ×0.03 mV/count）。")
    else:
        note_parts.append("兩來源單位已換算後再正規化疊圖。")
    if align_by_start and align_info.get("aligned"):
        note_parts.append(
            f"已依起始時間對齊（參考點 {align_info.get('reference_label')}）。"
        )
    elif align_by_start:
        note_parts.append(str(align_info.get("reason") or "起始時間對齊失敗。"))

    return {
        "mode": "waveform",
        "norm_method": norm_method,
        "align_by_start": align_by_start,
        "align": align_info,
        "delsys": delsys_trace,
        "txt": txt_trace,
        "note": " ".join(note_parts),
    }


def build_waveform_overlay(
    delsys_name: str,
    txt_names: list[str],
    *,
    norm_method: str = "zscore",
    align_by_start: bool = True,
) -> dict[str, Any]:
    """Overlay one Delsys file with one or more TXT files, optionally aligned by start time."""
    if not txt_names:
        raise ValueError("請至少選擇一個 TXT 檔案")

    left = load_delsys_emg(delsys_name, for_plot=True)
    year = None
    start = parse_delsys_start(left.get("metadata"))
    if start:
        year = start.year

    left_n = normalize_trace(left, method=norm_method)
    traces: list[dict[str, Any]] = [
        {
            "filename": left["filename"],
            "signal_name": left["signal_name"],
            "sample_rate": left["sample_rate"],
            "unit": left_n["unit"],
            "point_count": left["point_count"],
            "times": list(left_n["times"]),
            "values": list(left_n["values"]),
            "raw_unit": left["unit"],
            "start_time": left.get("start_time"),
            "start_epoch": left.get("start_epoch"),
            "start_label": left.get("start_label") or "",
            "source": "delsys",
        }
    ]

    for name in txt_names:
        right = load_txt_emg(name, for_plot=True, year=year)
        right_n = normalize_trace(right, method=norm_method)
        traces.append(
            {
                "filename": right["filename"],
                "signal_name": right["signal_name"],
                "sample_rate": right["sample_rate"],
                "unit": right_n["unit"],
                "point_count": right["point_count"],
                "times": list(right_n["times"]),
                "values": list(right_n["values"]),
                "raw_unit": right["unit"],
                "start_time": right.get("start_time"),
                "start_epoch": right.get("start_epoch"),
                "start_label": right.get("start_label") or "",
                "source": "txt",
            }
        )

    # Keep unaligned copies for side panels (relative t=0).
    side_delsys = dict(traces[0])
    side_txt = [dict(item) for item in traces[1:]]

    align_info: dict[str, Any] = {"aligned": False}
    overlay_traces = [dict(item) for item in traces]
    if align_by_start:
        overlay_traces, align_info = align_traces_by_start(overlay_traces)

    note_parts = []
    if norm_method == "none":
        note_parts.append("顯示原始單位波形（Delsys / TXT 皆為 mV；TXT 已套用 ×0.03 mV/count）。")
    else:
        note_parts.append("兩來源單位已換算後再正規化疊圖。")
    if align_by_start and align_info.get("aligned"):
        note_parts.append(
            f"已依起始時間對齊（參考點 {align_info.get('reference_label')}）。"
        )
        offsets = align_info.get("offset_seconds") or {}
        if offsets:
            parts = [f"{name}: {offset:+.3f}s" for name, offset in offsets.items()]
            note_parts.append("偏移 " + "；".join(parts) + "。")
    elif align_by_start:
        note_parts.append(str(align_info.get("reason") or "起始時間對齊失敗。"))

    return {
        "mode": "waveform_overlay",
        "norm_method": norm_method,
        "align_by_start": align_by_start,
        "align": align_info,
        "delsys": side_delsys,
        "txt_list": side_txt,
        "overlay": overlay_traces,
        "note": " ".join(note_parts),
    }


def build_contraction_single(
    source: str,
    filename: str,
    *,
    expected_count: int = 3,
    contraction_method: str = "rms_peak",
) -> dict[str, Any]:
    full = load_signal(source, filename, for_plot=False)
    contractions = detect_contractions_dispatch(
        full["times"],
        full["values"],
        method=contraction_method,
        expected_count=expected_count,
        sample_rate=full["sample_rate"],
        source=source,
    )
    plot = normalize_trace(load_signal(source, filename, for_plot=True), method="zscore")
    return {
        "mode": "contractions_single",
        "source": source,
        "expected_count": expected_count,
        "contraction_method": contraction_method,
        "result": {
            "filename": full["filename"],
            "signal_name": full["signal_name"],
            "sample_rate": full["sample_rate"],
            "contractions": contractions,
            "times": plot["times"],
            "values": plot["values"],
        },
    }


def build_feature_single(
    source: str,
    filename: str,
    *,
    expected_count: int = 3,
    contraction_method: str = "rms_peak",
    feature_method: str = "spectral",
) -> dict[str, Any]:
    full = load_signal(source, filename, for_plot=False)
    feat = analyze_signal_features(
        full["times"],
        full["values"],
        sample_rate=full["sample_rate"],
        expected_count=expected_count,
        contraction_method=contraction_method,
        feature_method=feature_method,
        source=source,
    )
    return {
        "mode": "features_single",
        "source": source,
        "expected_count": expected_count,
        "contraction_method": contraction_method,
        "feature_method": feature_method,
        "result": {
            "filename": full["filename"],
            "signal_name": full["signal_name"],
            "sample_rate": full["sample_rate"],
            "unit": full["unit"],
            "features": feat["features"],
            "count": feat["count"],
            "metrics": feat["metrics"],
            "series": feat.get("series"),
        },
    }


def build_contraction_compare(
    delsys_name: str,
    txt_name: str,
    *,
    expected_count: int = 3,
    contraction_method: str = "rms_peak",
) -> dict[str, Any]:
    left = load_delsys_emg(delsys_name, for_plot=False)
    right = load_txt_emg(txt_name, for_plot=False)
    left_c = detect_contractions_dispatch(
        left["times"],
        left["values"],
        method=contraction_method,
        expected_count=expected_count,
        sample_rate=left["sample_rate"],
        source="delsys",
    )
    right_c = detect_contractions_dispatch(
        right["times"],
        right["values"],
        method=contraction_method,
        expected_count=expected_count,
        sample_rate=right["sample_rate"],
        source="txt",
    )
    left_plot = normalize_trace(load_delsys_emg(delsys_name, for_plot=True), method="zscore")
    right_plot = normalize_trace(load_txt_emg(txt_name, for_plot=True), method="zscore")
    return {
        "mode": "contractions",
        "expected_count": expected_count,
        "contraction_method": contraction_method,
        "delsys": {
            "filename": left["filename"],
            "signal_name": left["signal_name"],
            "sample_rate": left["sample_rate"],
            "contractions": left_c,
            "times": left_plot["times"],
            "values": left_plot["values"],
        },
        "txt": {
            "filename": right["filename"],
            "signal_name": right["signal_name"],
            "sample_rate": right["sample_rate"],
            "contractions": right_c,
            "times": right_plot["times"],
            "values": right_plot["values"],
        },
    }


def build_feature_compare(
    delsys_name: str,
    txt_name: str,
    *,
    expected_count: int = 3,
    contraction_method: str = "rms_peak",
    feature_method: str = "spectral",
) -> dict[str, Any]:
    left = load_delsys_emg(delsys_name, for_plot=False)
    right = load_txt_emg(txt_name, for_plot=False)
    left_feat = analyze_signal_features(
        left["times"],
        left["values"],
        sample_rate=left["sample_rate"],
        expected_count=expected_count,
        contraction_method=contraction_method,
        feature_method=feature_method,
        source="delsys",
    )
    right_feat = analyze_signal_features(
        right["times"],
        right["values"],
        sample_rate=right["sample_rate"],
        expected_count=expected_count,
        contraction_method=contraction_method,
        feature_method=feature_method,
        source="txt",
    )
    pairs = compare_feature_rows(
        left_feat["features"],
        right_feat["features"],
        metrics=left_feat["metrics"],
    )
    return {
        "mode": "features",
        "expected_count": expected_count,
        "contraction_method": contraction_method,
        "feature_method": feature_method,
        "metrics": left_feat["metrics"],
        "delsys": {
            "filename": left["filename"],
            "signal_name": left["signal_name"],
            "sample_rate": left["sample_rate"],
            "unit": left["unit"],
            "features": left_feat["features"],
            "count": left_feat["count"],
            "series": left_feat.get("series"),
        },
        "txt": {
            "filename": right["filename"],
            "signal_name": right["signal_name"],
            "sample_rate": right["sample_rate"],
            "unit": right["unit"],
            "features": right_feat["features"],
            "count": right_feat["count"],
            "series": right_feat.get("series"),
        },
        "pairs": pairs,
        "note": "TXT 已換算為 mV（×0.03）；iEMG / RMS / 時長 / MDF / MPF 可直接對照。",
    }
