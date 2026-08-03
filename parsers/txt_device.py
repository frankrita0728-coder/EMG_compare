from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from align import parse_txt_start, start_payload
from paths import MAX_PLOT_POINTS, resolve_txt_dirs

TIME_PREFIX = re.compile(r"^\d{1,2}:\d{2}:\d{2}(?:\.\d+)?$")
HEX_VALUE = re.compile(r"^[0-9A-Fa-f]+$")
SAMPLE_RATE_RE = re.compile(r"ExgSampleRate\s*,\s*([0-9.]+)", re.IGNORECASE)
DEFAULT_SAMPLE_RATE = 1024.0
# ADC count → mV. Calibrated against paired Delsys CSV (same session);
# previous 0.03 made TXT amplitude features ~100× larger than Delsys mV.
TXT_MV_PER_COUNT = 0.00026


def list_txt_files() -> list[dict[str, str]]:
    seen: set[str] = set()
    files: list[dict[str, str]] = []
    for folder in resolve_txt_dirs():
        for path in sorted(folder.glob("*.txt"), key=lambda p: p.name.lower()):
            if path.name in seen:
                continue
            seen.add(path.name)
            files.append(
                {
                    "name": path.name,
                    "path": str(path),
                    "source": "txt",
                    "label": path.stem,
                }
            )
    return files


def find_txt_path(filename: str) -> Path | None:
    name = Path(filename).name
    for folder in resolve_txt_dirs():
        path = folder / name
        if path.exists():
            return path
    return None


def hex_to_decimal(token: str) -> int | None:
    token = token.strip()
    if not token or len(token) != 4 or not HEX_VALUE.fullmatch(token):
        return None
    value = int(token, 16)
    if value >= 0x8000:
        value -= 0x10000
    return value


def row_to_column(fields: list[str]) -> list[int]:
    column: list[int] = []
    for field in fields:
        value = hex_to_decimal(field)
        if value is not None:
            column.append(value)
    return column


def parse_sample_rate(path: Path) -> float:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return DEFAULT_SAMPLE_RATE
    match = SAMPLE_RATE_RE.search(text)
    if not match:
        return DEFAULT_SAMPLE_RATE
    try:
        return float(match.group(1))
    except ValueError:
        return DEFAULT_SAMPLE_RATE


def load_column(path: Path) -> list[int]:
    column: list[int] = []
    with path.open(encoding="utf-8", newline="") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            fields = [part.strip() for part in line.split(",")]
            if not fields or not TIME_PREFIX.match(fields[0]):
                continue
            sample_fields = fields[2:] if len(fields) >= 3 else fields[1:]
            column.extend(row_to_column(sample_fields))
    if not column:
        raise ValueError(f"找不到數值資料：{path.name}")
    return column


def downsample_series(times: list[float], values: list[float], max_points: int = MAX_PLOT_POINTS) -> tuple[list[float], list[float]]:
    if len(times) <= max_points:
        return times, values
    step = max(1, len(times) // max_points)
    sampled_times = times[::step]
    sampled_values = values[::step]
    if times and times[-1] != sampled_times[-1]:
        sampled_times.append(times[-1])
        sampled_values.append(values[-1])
    return sampled_times, sampled_values


def load_txt_emg(
    filename: str,
    *,
    for_plot: bool = False,
    year: int | None = None,
) -> dict[str, Any]:
    path = find_txt_path(filename)
    if path is None:
        raise FileNotFoundError(f"找不到 TXT 檔案：{filename}")

    try:
        header_text = path.read_text(encoding="utf-8", errors="ignore")[:2000]
    except OSError:
        header_text = ""

    samples = load_column(path)
    sample_rate = parse_sample_rate(path)
    values = [float(v) * TXT_MV_PER_COUNT for v in samples]
    times = [i / sample_rate for i in range(len(values))]
    point_count = len(values)
    if for_plot:
        times, values = downsample_series(times, values)

    channel = "Ch2" if "EXGCH2" in path.name.upper().replace(" ", "") else "Ch1"
    start_info = start_payload(
        parse_txt_start(header_text=header_text, filename=path.name, year=year)
    )
    return {
        "source": "txt",
        "filename": path.name,
        "label": path.stem,
        "signal_name": f"EXG {channel}",
        "unit": "mV",
        "sample_rate": sample_rate,
        "point_count": point_count,
        "times": times,
        "values": values,
        "metadata": {
            "ExgSampleRate": f"{sample_rate} Hz",
            "Start time": start_info.get("start_label") or "",
            "Scale": f"{TXT_MV_PER_COUNT} mV/count",
        },
        "sensor_name": channel,
        **start_info,
    }
