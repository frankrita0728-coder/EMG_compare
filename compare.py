from __future__ import annotations

from typing import Any

from align import align_traces_by_start, parse_delsys_start
from detector import detect_contractions_dispatch
from features import analyze_signal_features, compare_feature_rows
from normalize import normalize_trace
from parsers.delsys import load_delsys_emg
from parsers.txt_device import TXT_MV_PER_COUNT, load_txt_emg
from parsers.ze2_txt import ZE2_MV_PER_COUNT, load_ze2_emg


def load_signal(
    source: str,
    filename: str,
    *,
    for_plot: bool = False,
    year: int | None = None,
    ze2_sample_rate: float | None = None,
    ze2_mv_per_count: float | None = None,
    apply_bandpass: bool = True,
) -> dict[str, Any]:
    if source == "delsys":
        return load_delsys_emg(filename, for_plot=for_plot)
    if source == "txt":
        return load_txt_emg(filename, for_plot=for_plot, year=year, apply_bandpass=apply_bandpass)
    if source == "ze2":
        return load_ze2_emg(
            filename,
            for_plot=for_plot,
            year=year,
            sample_rate=ze2_sample_rate,
            mv_per_count=ze2_mv_per_count,
            apply_bandpass=apply_bandpass,
        )
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


def _trace_from_raw(raw: dict[str, Any], normalized: dict[str, Any], *, source: str) -> dict[str, Any]:
    return {
        "filename": raw["filename"],
        "signal_name": raw["signal_name"],
        "sample_rate": raw["sample_rate"],
        "unit": normalized["unit"],
        "point_count": raw["point_count"],
        "times": list(normalized["times"]),
        "values": list(normalized["values"]),
        "raw_unit": raw["unit"],
        "start_time": raw.get("start_time"),
        "start_epoch": raw.get("start_epoch"),
        "start_label": raw.get("start_label") or "",
        "source": source,
    }


def build_waveform_single(
    source: str,
    filename: str,
    *,
    norm_method: str = "zscore",
    year: int | None = None,
    ze2_sample_rate: float | None = None,
    ze2_mv_per_count: float | None = None,
    apply_bandpass: bool = True,
) -> dict[str, Any]:
    raw = load_signal(
        source,
        filename,
        for_plot=True,
        year=year,
        ze2_sample_rate=ze2_sample_rate,
        ze2_mv_per_count=ze2_mv_per_count,
        apply_bandpass=apply_bandpass,
    )
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
            "source": source,
        },
    }


def build_waveform_compare(
    delsys_name: str,
    txt_name: str,
    *,
    norm_method: str = "zscore",
    align_by_start: bool = True,
    apply_bandpass: bool = True,
) -> dict[str, Any]:
    left = load_delsys_emg(delsys_name, for_plot=True)
    year = None
    start = parse_delsys_start(left.get("metadata"))
    if start:
        year = start.year
    right = load_txt_emg(txt_name, for_plot=True, year=year, apply_bandpass=apply_bandpass)
    left_n = normalize_trace(left, method=norm_method)
    right_n = normalize_trace(right, method=norm_method)

    delsys_trace = _trace_from_raw(left, left_n, source="delsys")
    txt_trace = _trace_from_raw(right, right_n, source="txt")

    align_info: dict[str, Any] = {"aligned": False}
    if align_by_start:
        aligned, align_info = align_traces_by_start([delsys_trace, txt_trace])
        delsys_trace, txt_trace = aligned[0], aligned[1]

    note_parts = []
    if norm_method == "none":
        note_parts.append("顯示原始單位波形（Delsys / TXT 皆為 mV；TXT 已套用 ×0.00026 mV/count）。")
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
    txt_names: list[str] | None = None,
    ze2_names: list[str] | None = None,
    *,
    norm_method: str = "zscore",
    align_by_start: bool = True,
    ze2_sample_rate: float | None = None,
    ze2_mv_per_count: float | None = None,
    apply_bandpass: bool = True,
) -> dict[str, Any]:
    """Overlay one Delsys file with ZE1 TXT and/or ZE2 files, optionally aligned by start time."""
    txt_names = list(txt_names or [])
    ze2_names = list(ze2_names or [])
    if not txt_names and not ze2_names:
        raise ValueError("請至少選擇一個 ZE1 TXT 或 ZE2 檔案")

    left = load_delsys_emg(delsys_name, for_plot=True)
    year = None
    start = parse_delsys_start(left.get("metadata"))
    if start:
        year = start.year

    left_n = normalize_trace(left, method=norm_method)
    traces: list[dict[str, Any]] = [_trace_from_raw(left, left_n, source="delsys")]

    for name in txt_names:
        right = load_txt_emg(name, for_plot=True, year=year, apply_bandpass=apply_bandpass)
        right_n = normalize_trace(right, method=norm_method)
        traces.append(_trace_from_raw(right, right_n, source="txt"))

    for name in ze2_names:
        right = load_ze2_emg(
            name,
            for_plot=True,
            year=year,
            sample_rate=ze2_sample_rate,
            mv_per_count=ze2_mv_per_count,
            apply_bandpass=apply_bandpass,
        )
        right_n = normalize_trace(right, method=norm_method)
        traces.append(_trace_from_raw(right, right_n, source="ze2"))

    # Keep unaligned copies for side panels (relative t=0).
    side_delsys = dict(traces[0])
    side_txt = [dict(item) for item in traces if item.get("source") == "txt"]
    side_ze2 = [dict(item) for item in traces if item.get("source") == "ze2"]

    align_info: dict[str, Any] = {"aligned": False}
    overlay_traces = [dict(item) for item in traces]
    if align_by_start:
        overlay_traces, align_info = align_traces_by_start(overlay_traces)

    note_parts = []
    if norm_method == "none":
        note_parts.append(
            f"顯示原始單位波形（皆為 mV；ZE1 ×{TXT_MV_PER_COUNT}、ZE2 ×{ze2_mv_per_count or ZE2_MV_PER_COUNT}）。"
        )
    else:
        note_parts.append("多來源單位已換算後再正規化疊圖。")
    if apply_bandpass:
        note_parts.append("ZE1 / ZE2 已套用 20–400 Hz 帶通濾波。")
    else:
        note_parts.append("ZE1 / ZE2 未套用帶通濾波。")
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
        "ze2_list": side_ze2,
        "overlay": overlay_traces,
        "note": " ".join(note_parts),
    }


def build_contraction_single(
    source: str,
    filename: str,
    *,
    expected_count: int = 3,
    contraction_method: str = "rms_peak",
    ze2_sample_rate: float | None = None,
    ze2_mv_per_count: float | None = None,
    apply_bandpass: bool = True,
) -> dict[str, Any]:
    full = load_signal(
        source,
        filename,
        for_plot=False,
        ze2_sample_rate=ze2_sample_rate,
        ze2_mv_per_count=ze2_mv_per_count,
        apply_bandpass=apply_bandpass,
    )
    contractions = detect_contractions_dispatch(
        full["times"],
        full["values"],
        method=contraction_method,
        expected_count=expected_count,
        sample_rate=full["sample_rate"],
        source=source,
    )
    plot = normalize_trace(
        load_signal(
            source,
            filename,
            for_plot=True,
            ze2_sample_rate=ze2_sample_rate,
            ze2_mv_per_count=ze2_mv_per_count,
            apply_bandpass=apply_bandpass,
        ),
        method="robust_zscore",
    )
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
            "source": source,
        },
    }


def build_feature_single(
    source: str,
    filename: str,
    *,
    expected_count: int = 3,
    contraction_method: str = "rms_peak",
    feature_method: str = "spectral",
    ze2_sample_rate: float | None = None,
    ze2_mv_per_count: float | None = None,
    apply_bandpass: bool = True,
) -> dict[str, Any]:
    full = load_signal(
        source,
        filename,
        for_plot=False,
        ze2_sample_rate=ze2_sample_rate,
        ze2_mv_per_count=ze2_mv_per_count,
        apply_bandpass=apply_bandpass,
    )
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
            "source": source,
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
    left_plot = normalize_trace(load_delsys_emg(delsys_name, for_plot=True), method="robust_zscore")
    right_plot = normalize_trace(load_txt_emg(txt_name, for_plot=True), method="robust_zscore")
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
    apply_bandpass: bool = True,
) -> dict[str, Any]:
    left = load_delsys_emg(delsys_name, for_plot=False)
    right = load_txt_emg(txt_name, for_plot=False, apply_bandpass=apply_bandpass)
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
        "note": (
            f"TXT 已換算為 mV（×{TXT_MV_PER_COUNT}）"
            + ("；已套用 20–400 Hz 帶通。" if apply_bandpass else "；未套用帶通濾波。")
            + " iEMG / RMS / 時長 / MDF / MPF 可直接對照。"
        ),
    }


def build_feature_compare_ze2(
    delsys_name: str,
    ze2_name: str,
    *,
    expected_count: int = 3,
    contraction_method: str = "rms_peak",
    feature_method: str = "spectral",
    ze2_sample_rate: float | None = None,
    ze2_mv_per_count: float | None = None,
    apply_bandpass: bool = True,
) -> dict[str, Any]:
    left = load_delsys_emg(delsys_name, for_plot=False)
    year = _year_from_delsys(delsys_name)
    right = load_ze2_emg(
        ze2_name,
        for_plot=False,
        year=year,
        sample_rate=ze2_sample_rate,
        mv_per_count=ze2_mv_per_count,
        apply_bandpass=apply_bandpass,
    )
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
        source="ze2",
    )
    pairs = compare_feature_rows(
        left_feat["features"],
        right_feat["features"],
        metrics=left_feat["metrics"],
    )
    for item in pairs:
        item["ze2"] = item.pop("txt", None)
    scale = ze2_mv_per_count or ZE2_MV_PER_COUNT
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
        "ze2": {
            "filename": right["filename"],
            "signal_name": right["signal_name"],
            "sample_rate": right["sample_rate"],
            "unit": right["unit"],
            "features": right_feat["features"],
            "count": right_feat["count"],
            "series": right_feat.get("series"),
        },
        "pairs": pairs,
        "note": (
            f"ZE2 已換算為 mV（×{scale}）"
            + ("；已套用 20–400 Hz 帶通。" if apply_bandpass else "；未套用帶通濾波。")
            + " iEMG / RMS / 時長 / MDF / MPF 可直接對照。"
        ),
    }
