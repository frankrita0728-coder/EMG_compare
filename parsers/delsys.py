from __future__ import annotations

from pathlib import Path
from typing import Any

from align import parse_delsys_start, start_payload
from paths import MAX_PLOT_POINTS, resolve_delsys_dirs


def list_delsys_files() -> list[dict[str, str]]:
    seen: set[str] = set()
    files: list[dict[str, str]] = []
    for folder in resolve_delsys_dirs():
        for path in sorted(folder.glob("*.csv"), key=lambda p: p.name.lower()):
            if path.name in seen:
                continue
            seen.add(path.name)
            files.append(
                {
                    "name": path.name,
                    "path": str(path),
                    "source": "delsys",
                    "label": path.stem,
                }
            )
    return files


def find_delsys_path(filename: str) -> Path | None:
    name = Path(filename).name
    for folder in resolve_delsys_dirs():
        path = folder / name
        if path.exists():
            return path
    return None


def _split_csv_line(line: str) -> list[str]:
    return [part.strip() for part in line.rstrip("\n").split(",")]


def _parse_metadata(lines: list[str]) -> dict[str, str]:
    metadata: dict[str, str] = {}
    for line in lines[:3]:
        if ":" not in line:
            continue
        key, value = line.split(",", 1)
        metadata[key.strip().rstrip(":")] = value.strip()
    return metadata


def _build_signals(headers: list[str], sample_rates: list[str]) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    index = 0
    while index < len(headers):
        header = headers[index]
        if "Time Series" in header and index + 1 < len(headers):
            value_header = headers[index + 1]
            rate = ""
            if index + 1 < len(sample_rates) and sample_rates[index + 1]:
                rate = sample_rates[index + 1]
            elif index < len(sample_rates):
                rate = sample_rates[index]
            signals.append(
                {
                    "id": str(index),
                    "name": value_header,
                    "sample_rate": rate,
                    "time_col": index,
                    "value_col": index + 1,
                }
            )
            index += 2
        else:
            index += 1
    return signals


def parse_delsys_csv(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8-sig")
    lines = text.splitlines()
    if len(lines) < 8:
        raise ValueError(f"CSV 格式不完整：{path.name}")

    metadata = _parse_metadata(lines)
    headers = _split_csv_line(lines[5])
    sample_rates = _split_csv_line(lines[6])
    signals = _build_signals(headers, sample_rates)
    rows = [_split_csv_line(line) for line in lines[7:] if line.strip()]
    return {
        "filename": path.name,
        "metadata": metadata,
        "sensor_name": lines[3].strip() if len(lines) > 3 else "",
        "sensor_mode": lines[4].strip() if len(lines) > 4 else "",
        "signals": signals,
        "rows": rows,
    }


def extract_signal(rows: list[list[str]], time_col: int, value_col: int) -> tuple[list[float], list[float]]:
    times: list[float] = []
    values: list[float] = []
    for row in rows:
        if time_col >= len(row) or value_col >= len(row):
            continue
        time_text = row[time_col].strip()
        value_text = row[value_col].strip()
        if not time_text or not value_text:
            continue
        try:
            times.append(float(time_text))
            values.append(float(value_text))
        except ValueError:
            continue
    return times, values


def downsample(times: list[float], values: list[float], max_points: int = MAX_PLOT_POINTS) -> tuple[list[float], list[float]]:
    if len(times) <= max_points:
        return times, values
    step = max(1, len(times) // max_points)
    sampled_times = times[::step]
    sampled_values = values[::step]
    if times and times[-1] != sampled_times[-1]:
        sampled_times.append(times[-1])
        sampled_values.append(values[-1])
    return sampled_times, sampled_values


def _parse_rate(rate_text: str) -> float:
    digits = "".join(ch if (ch.isdigit() or ch == ".") else " " for ch in rate_text)
    parts = [p for p in digits.split() if p]
    if not parts:
        return 1259.0
    try:
        return float(parts[0])
    except ValueError:
        return 1259.0


def find_preferred_emg_signal(signals: list[dict[str, Any]]) -> dict[str, Any] | None:
    for signal in signals:
        if "EMG" in signal["name"].upper():
            return signal
    return signals[0] if signals else None


def load_delsys_emg(filename: str, *, for_plot: bool = False) -> dict[str, Any]:
    path = find_delsys_path(filename)
    if path is None:
        raise FileNotFoundError(f"找不到 Delsys 檔案：{filename}")

    parsed = parse_delsys_csv(path)
    signal = find_preferred_emg_signal(parsed["signals"])
    if signal is None:
        raise ValueError(f"找不到 EMG 欄位：{filename}")

    times, values = extract_signal(parsed["rows"], signal["time_col"], signal["value_col"])
    sample_rate = _parse_rate(str(signal.get("sample_rate") or ""))
    point_count = len(times)
    if for_plot:
        times, values = downsample(times, values)

    start_info = start_payload(parse_delsys_start(parsed["metadata"]))
    return {
        "source": "delsys",
        "filename": parsed["filename"],
        "label": path.stem,
        "signal_name": signal["name"],
        "unit": "mV",
        "sample_rate": sample_rate,
        "point_count": point_count,
        "times": times,
        "values": values,
        "metadata": parsed["metadata"],
        "sensor_name": parsed["sensor_name"],
        **start_info,
    }
