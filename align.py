from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any


DELSYS_DT_RE = re.compile(
    r"(?P<year>\d{4})[/-](?P<month>\d{1,2})[/-](?P<day>\d{1,2})"
    r".*?(?P<ampm>上午|下午|AM|PM)?"
    r"\s*(?P<hour>\d{1,2}):(?P<minute>\d{2})(?::(?P<second>\d{2}))?",
    re.IGNORECASE,
)

TXT_START_RE = re.compile(
    r"Start\s*time\s*,\s*(?P<stamp>\d{1,2}-\d{1,2}_\d{1,2}-\d{2}-\d{2}(?:_\d+)?)",
    re.IGNORECASE,
)

TXT_STAMP_RE = re.compile(
    r"^(?P<month>\d{1,2})-(?P<day>\d{1,2})_"
    r"(?P<hour>\d{1,2})-(?P<minute>\d{2})-(?P<second>\d{2})"
    r"(?:_(?P<ms>\d+))?$"
)

FILENAME_STAMP_RE = re.compile(
    r"(?P<month>\d{1,2})-(?P<day>\d{1,2})_"
    r"(?P<hour>\d{1,2})-(?P<minute>\d{2})-(?P<second>\d{2})"
    r"(?:_(?P<ms>\d+))?"
)


def parse_delsys_start(metadata: dict[str, Any] | None) -> datetime | None:
    if not metadata:
        return None
    raw = str(metadata.get("Date/Time") or metadata.get("Date/Time:") or "").strip()
    if not raw:
        return None
    match = DELSYS_DT_RE.search(raw)
    if not match:
        return None

    year = int(match.group("year"))
    month = int(match.group("month"))
    day = int(match.group("day"))
    hour = int(match.group("hour"))
    minute = int(match.group("minute"))
    second = int(match.group("second") or 0)
    ampm = (match.group("ampm") or "").strip().lower()

    if ampm in {"下午", "pm"} and hour < 12:
        hour += 12
    elif ampm in {"上午", "am"} and hour == 12:
        hour = 0

    try:
        return datetime(year, month, day, hour, minute, second)
    except ValueError:
        return None


def _datetime_from_stamp_parts(
    *,
    year: int,
    month: int,
    day: int,
    hour: int,
    minute: int,
    second: int,
    ms_text: str | None,
) -> datetime | None:
    micro = 0
    if ms_text:
        # Header uses 3-digit ms like 209 → 209000 us; keep as milliseconds.
        digits = ms_text.strip()
        if len(digits) <= 3:
            micro = int(digits.ljust(3, "0")[:3]) * 1000
        else:
            micro = int(digits[:6].ljust(6, "0")[:6])
    try:
        return datetime(year, month, day, hour, minute, second, micro)
    except ValueError:
        return None


def parse_txt_start(
    *,
    header_text: str = "",
    filename: str = "",
    year: int | None = None,
) -> datetime | None:
    year = int(year) if year else datetime.now().year

    stamp = None
    match = TXT_START_RE.search(header_text or "")
    if match:
        stamp = match.group("stamp")
    else:
        file_match = FILENAME_STAMP_RE.search(filename or "")
        if file_match:
            stamp = file_match.group(0)

    if not stamp:
        return None

    parts = TXT_STAMP_RE.match(stamp)
    if not parts:
        return None

    return _datetime_from_stamp_parts(
        year=year,
        month=int(parts.group("month")),
        day=int(parts.group("day")),
        hour=int(parts.group("hour")),
        minute=int(parts.group("minute")),
        second=int(parts.group("second")),
        ms_text=parts.group("ms"),
    )


def format_start(dt: datetime | None) -> str:
    if dt is None:
        return ""
    if dt.microsecond:
        return dt.strftime("%Y-%m-%d %H:%M:%S.") + f"{dt.microsecond // 1000:03d}"
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def start_payload(dt: datetime | None) -> dict[str, Any]:
    if dt is None:
        return {"start_time": None, "start_epoch": None, "start_label": ""}
    return {
        "start_time": dt.isoformat(timespec="milliseconds"),
        "start_epoch": dt.timestamp(),
        "start_label": format_start(dt),
    }


def align_traces_by_start(
    traces: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    Shift each trace's relative times onto a common timeline.

    Absolute time for a sample = start_epoch + relative_time.
    Common axis zero = earliest start among traces that have start_epoch.
    Traces without start_epoch keep original relative times (no shift).
    """
    epochs = [
        float(trace["start_epoch"])
        for trace in traces
        if trace.get("start_epoch") is not None
    ]
    if not epochs:
        return traces, {
            "aligned": False,
            "reason": "缺少起始時間，無法對齊",
            "offset_seconds": {},
        }

    ref = min(epochs)
    aligned: list[dict[str, Any]] = []
    offsets: dict[str, float] = {}

    for trace in traces:
        item = dict(trace)
        epoch = trace.get("start_epoch")
        if epoch is None:
            offsets[str(trace.get("filename") or trace.get("name") or "unknown")] = 0.0
            aligned.append(item)
            continue
        offset = float(epoch) - ref
        key = str(trace.get("filename") or trace.get("name") or "unknown")
        offsets[key] = round(offset, 6)
        times = list(trace.get("times") or [])
        item["times"] = [float(t) + offset for t in times]
        item["time_offset"] = round(offset, 6)
        aligned.append(item)

    return aligned, {
        "aligned": True,
        "reference_epoch": ref,
        "reference_label": datetime.fromtimestamp(ref).isoformat(timespec="milliseconds"),
        "offset_seconds": offsets,
    }
