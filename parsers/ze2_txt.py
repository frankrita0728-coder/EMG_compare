from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from align import parse_txt_start, start_payload
from emg_filter import BANDPASS_HZ, BANDPASS_ORDER, bandpass_filter, filter_metadata_label
from paths import MAX_PLOT_POINTS, resolve_ze2_dirs

HEX_VALUE = re.compile(r"^[0-9A-Fa-f]+$")
MV_RE = re.compile(r"(?P<mv>\d+(?:\.\d+)?)\s*mV", re.IGNORECASE)
BPM_RE = re.compile(r"(?P<bpm>\d+(?:\.\d+)?)\s*bpm", re.IGNORECASE)
CHANNEL_RE = re.compile(r"(?:^|_)Ch(?P<ch>[12])(?:_|\.|$)", re.IGNORECASE)

DEFAULT_SAMPLE_RATE = 1000.0
# ADC count → mV (provisional; calibrate against Delsys as needed).
ZE2_MV_PER_COUNT = 0.000048
ZE2_BANDPASS_HZ = BANDPASS_HZ
ZE2_BANDPASS_ORDER = BANDPASS_ORDER


def list_ze2_files() -> list[dict[str, str]]:
    seen: set[str] = set()
    files: list[dict[str, str]] = []
    for folder in resolve_ze2_dirs():
        for path in sorted(folder.glob("*.txt"), key=lambda p: p.name.lower()):
            if path.name in seen:
                continue
            seen.add(path.name)
            files.append(
                {
                    "name": path.name,
                    "path": str(path),
                    "source": "ze2",
                    "label": path.stem,
                }
            )
    return files


def find_ze2_path(filename: str) -> Path | None:
    name = Path(filename).name
    for folder in resolve_ze2_dirs():
        path = folder / name
        if path.exists():
            return path
    return None


def hex24_to_decimal(token: str) -> int | None:
    token = token.strip()
    if not token or len(token) != 6 or not HEX_VALUE.fullmatch(token):
        return None
    value = int(token, 16)
    if value >= 0x800000:
        value -= 0x1000000
    return value


def parse_filename_meta(filename: str) -> dict[str, Any]:
    stem = Path(filename).stem
    mv_match = MV_RE.search(stem)
    bpm_match = BPM_RE.search(stem)
    ch_match = CHANNEL_RE.search(stem)
    channel = f"Ch{ch_match.group('ch')}" if ch_match else "Ch1"
    return {
        "range_mv": float(mv_match.group("mv")) if mv_match else None,
        "bpm": float(bpm_match.group("bpm")) if bpm_match else None,
        "channel": channel,
    }


def load_column(path: Path) -> list[int]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        raise ValueError(f"無法讀取 ZE2 檔案：{path.name}") from exc

    column: list[int] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        for field in line.split(","):
            value = hex24_to_decimal(field)
            if value is not None:
                column.append(value)
    if not column:
        # Single-line files may omit trailing newline; also try whole text once.
        for field in text.replace("\n", ",").split(","):
            value = hex24_to_decimal(field)
            if value is not None:
                column.append(value)
    if not column:
        raise ValueError(f"找不到數值資料：{path.name}")
    return column


def downsample_series(
    times: list[float],
    values: list[float],
    max_points: int = MAX_PLOT_POINTS,
) -> tuple[list[float], list[float]]:
    if len(times) <= max_points:
        return times, values
    step = max(1, len(times) // max_points)
    sampled_times = times[::step]
    sampled_values = values[::step]
    if times and times[-1] != sampled_times[-1]:
        sampled_times.append(times[-1])
        sampled_values.append(values[-1])
    return sampled_times, sampled_values


def load_ze2_emg(
    filename: str,
    *,
    for_plot: bool = False,
    year: int | None = None,
    sample_rate: float | None = None,
    mv_per_count: float | None = None,
    apply_bandpass: bool = True,
) -> dict[str, Any]:
    path = find_ze2_path(filename)
    if path is None:
        raise FileNotFoundError(f"找不到 ZE2 檔案：{filename}")

    meta = parse_filename_meta(path.name)
    fs = float(sample_rate) if sample_rate and sample_rate > 0 else DEFAULT_SAMPLE_RATE
    scale = float(mv_per_count) if mv_per_count and mv_per_count > 0 else ZE2_MV_PER_COUNT

    samples = load_column(path)
    values = [float(v) * scale for v in samples]
    filter_info: dict[str, Any] = {"applied": False}
    if apply_bandpass:
        values, filter_info = bandpass_filter(values, fs)

    times = [i / fs for i in range(len(values))]
    point_count = len(values)
    if for_plot:
        times, values = downsample_series(times, values)

    channel = str(meta["channel"])
    start_info = start_payload(parse_txt_start(header_text="", filename=path.name, year=year))
    metadata: dict[str, Any] = {
        "ExgSampleRate": f"{fs} Hz",
        "Start time": start_info.get("start_label") or "",
        "Scale": f"{scale} mV/count",
        "Channel": channel,
    }
    filter_label = filter_metadata_label(filter_info)
    if filter_label:
        metadata["Filter"] = filter_label
    if meta.get("range_mv") is not None:
        metadata["Range"] = f"{meta['range_mv']} mV"
    if meta.get("bpm") is not None:
        metadata["BPM"] = str(meta["bpm"])

    return {
        "source": "ze2",
        "filename": path.name,
        "label": path.stem,
        "signal_name": f"ZE2 {channel}",
        "unit": "mV",
        "sample_rate": fs,
        "point_count": point_count,
        "times": times,
        "values": values,
        "metadata": metadata,
        "filter": filter_info,
        "sensor_name": channel,
        **start_info,
    }
