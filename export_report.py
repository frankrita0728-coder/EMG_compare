"""Export analysis results to PDF / CSV for download."""

from __future__ import annotations

import csv
import io
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def _find_cjk_font() -> str | None:
    """Prefer a single-file CJK TTF/OTF; TTC collections are less reliable in ReportLab/Matplotlib."""
    root = Path(__file__).resolve().parent
    candidates = [
        *sorted((root / "assets" / "fonts").glob("*.ttf")),
        *sorted((root / "assets" / "fonts").glob("*.otf")),
        # Standalone TTF first (cmap works with ReportLab TTFont).
        Path(r"C:\Windows\Fonts\kaiu.ttf"),  # DFKai-SB Traditional Chinese
        Path(r"C:\Windows\Fonts\simhei.ttf"),
        Path(r"C:\Windows\Fonts\simsun.ttc"),
        Path(r"C:\Windows\Fonts\msjh.ttc"),
        Path(r"C:\Windows\Fonts\msjhbd.ttc"),
        Path(r"C:\Windows\Fonts\msyh.ttc"),
        Path(r"C:\Windows\Fonts\mingliu.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"),
        *sorted((root / "assets" / "fonts").glob("*.ttc")),
    ]
    for path in candidates:
        if path.exists():
            return str(path)
    return None


def _register_fonts() -> str:
    font_path = _find_cjk_font()
    if font_path:
        suffix = Path(font_path).suffix.lower()
        # TTC: try a few subfont indices; some collections put CJK face at index 0/1.
        indices = (0, 1, 2) if suffix == ".ttc" else (0,)
        for idx in indices:
            try:
                pdfmetrics.registerFont(TTFont("EMG_CJK", font_path, subfontIndex=idx))
                return "EMG_CJK"
            except Exception:
                continue
    # Streamlit Cloud / Linux without CJK TTF: ReportLab built-in CID fonts.
    for cid_name in ("MHei-Medium", "MSung-Light", "STSong-Light"):
        try:
            from reportlab.pdfbase.cidfonts import UnicodeCIDFont

            pdfmetrics.registerFont(UnicodeCIDFont(cid_name))
            return cid_name
        except Exception:
            continue
    return "Helvetica"


def _matplotlib_font_properties():
    """Return FontProperties for CJK titles, or None."""
    font_path = _find_cjk_font()
    if not font_path:
        return None
    try:
        from matplotlib import font_manager

        return font_manager.FontProperties(fname=font_path)
    except Exception:
        return None


def _fmt(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def _escape(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _rows_from_features(features: list[dict[str, Any]], method: str) -> list[list[str]]:
    if method in {"ttri", "ze1", "muscle_capture"}:
        cols = ["index", "start", "end", "duration", "aemg", "rms", "iemg", "mpf", "mdf", "peak_rms"]
    else:
        cols = ["index", "start", "end", "duration", "iemg", "rms", "mdf", "mpf", "peak_rms"]
    body = [[_fmt(row.get(col)) for col in cols] for row in features]
    return [cols, *body]


def _rows_from_contractions(contractions: list[dict[str, Any]]) -> list[list[str]]:
    cols = ["index", "start", "end", "duration", "peak_rms"]
    body = [[_fmt(row.get(col)) for col in cols] for row in contractions]
    return [cols, *body]


def _rows_from_delta(pairs: list[dict[str, Any]]) -> list[list[str]]:
    if not pairs:
        return [["index", "note"], ["", "no pairs"]]
    keys: list[str] = []
    for item in pairs:
        for key in (item.get("delta") or {}):
            if key not in keys:
                keys.append(key)
    header = ["index", *[f"d_{k}" for k in keys]]
    body = []
    for item in pairs:
        delta = item.get("delta") or {}
        body.append([_fmt(item.get("index")), *[_fmt(delta.get(k)) for k in keys]])
    return [header, *body]


def _rows_from_correlation(correlation: dict[str, Any] | None) -> list[list[str]]:
    if not correlation:
        return [["metric", "r"], ["", "no correlation"]]
    body = [[str(key), _fmt(value)] for key, value in correlation.items()]
    return [["metric", "r"], *body]


def _rows_from_interval_agreement(rows: list[dict[str, Any]] | None) -> list[list[str]]:
    if not rows:
        return [["metric", "n", "pearson_r", "icc"], ["", "", "", "no agreement"]]
    body = [
        [
            str(item.get("metric") or ""),
            _fmt(item.get("n")),
            _fmt(item.get("pearson_r")),
            _fmt(item.get("icc")),
        ]
        for item in rows
    ]
    return [["metric", "n", "pearson_r", "icc"], *body]


def _make_table(data: list[list[str]], font_name: str) -> Table:
    table = Table(data, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), font_name),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#18201c")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#e7efe9")),
                ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#f7faf8")),
                ("TEXTCOLOR", (0, 1), (-1, -1), colors.HexColor("#102018")),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#9aa89f")),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def _series_chart_png(series: dict[str, Any] | None, *, title: str) -> bytes | None:
    """
    Render TTRI feature curves for PDF.
    Amplitude (RMS/iEMG) and frequency (MPF/MDF) use separate panels so scales stay readable.
    """
    if not series:
        return None

    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return None

    font_prop = _matplotlib_font_properties()
    if font_prop is not None:
        try:
            plt.rcParams["font.family"] = font_prop.get_name()
            plt.rcParams["axes.unicode_minus"] = False
        except Exception:
            pass

    fig, (ax_amp, ax_freq) = plt.subplots(2, 1, figsize=(10.5, 5.2), sharex=True)
    fig.patch.set_facecolor("#0f1412")
    for ax in (ax_amp, ax_freq):
        ax.set_facecolor("#141b18")
        ax.tick_params(colors="#e7efe9")
        ax.xaxis.label.set_color("#e7efe9")
        ax.yaxis.label.set_color("#e7efe9")
        for spine in ax.spines.values():
            spine.set_color("#2c3a33")
        ax.grid(True, color="#24322b", alpha=0.7)

    amp_specs = [("rms", "RMS", "#5ec8ff"), ("iemg", "iEMG", "#3dd68c")]
    freq_specs = [("mpf", "MPF", "#f0b429"), ("mdf", "MDF", "#c78bff")]

    for key, label, color in amp_specs:
        block = series.get(key) or {}
        times = block.get("times") or []
        values = block.get("values") or []
        if times and values:
            ax_amp.plot(times, values, label=label, color=color, linewidth=1.2)

    for key, label, color in freq_specs:
        block = series.get(key) or {}
        times = block.get("times") or []
        values = block.get("values") or []
        if times and values:
            ax_freq.plot(times, values, label=label, color=color, linewidth=1.2)

    aemg = series.get("aemg")
    # Keep chart title ASCII-safe: full Chinese filenames are shown in the PDF heading above.
    short = Path(str(title)).name
    try:
        short.encode("ascii")
        label = short if len(short) <= 54 else short[:51] + "..."
    except UnicodeEncodeError:
        label = "Feature series"
    subtitle = f"{label}  |  AEMG={aemg}" if aemg is not None else label
    title_kwargs: dict[str, Any] = {"color": "#e7efe9", "fontsize": 11}
    if font_prop is not None:
        title_kwargs["fontproperties"] = font_prop
        # With a CJK-capable font, show the real filename (truncated if long).
        shown = Path(str(title)).name
        if len(shown) > 54:
            shown = shown[:51] + "..."
        subtitle = f"{shown}  |  AEMG={aemg}" if aemg is not None else shown
    ax_amp.set_title(subtitle, **title_kwargs)
    ax_amp.set_ylabel("Amplitude")
    ax_freq.set_ylabel("Frequency (Hz)")
    ax_freq.set_xlabel("Time (s)")
    ax_amp.legend(loc="upper right", facecolor="#18201c", edgecolor="#2c3a33", labelcolor="#e7efe9")
    ax_freq.legend(loc="upper right", facecolor="#18201c", edgecolor="#2c3a33", labelcolor="#e7efe9")
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=140, facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()


def _add_series_image(story: list[Any], series: dict[str, Any] | None, title: str) -> None:
    png = _series_chart_png(series, title=title)
    if not png:
        return
    img = Image(io.BytesIO(png), width=24 * cm, height=11.8 * cm)
    story.append(Spacer(1, 0.25 * cm))
    story.append(img)


def _stride(times: list[float], values: list[float], max_points: int = 4000) -> tuple[list[float], list[float]]:
    n = min(len(times), len(values))
    times, values = times[:n], values[:n]
    if n <= max_points:
        return times, values
    step = max(1, n // max_points)
    return times[::step], values[::step]


def _percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    pos = (len(ordered) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(ordered) - 1)
    frac = pos - lo
    return float(ordered[lo]) * (1.0 - frac) + float(ordered[hi]) * frac


def _readable_ylim(values: list[float]) -> tuple[float, float]:
    """Frame the main waveform with headroom so peaks do not sit on the border."""
    if not values:
        return -1.0, 1.0
    lo = _percentile(values, 0.005)
    hi = _percentile(values, 0.995)
    span = hi - lo
    if span <= 0:
        span = max(abs(hi), abs(lo), 1e-3)
    # Extra room so the trace is not flush with the frame (that reads as clipping).
    pad = 0.4 * span
    return lo - pad, hi + pad


def _style_dark_ax(ax, font_prop) -> None:
    ax.set_facecolor("#141b18")
    ax.tick_params(colors="#e7efe9", labelsize=8)
    ax.xaxis.label.set_color("#e7efe9")
    ax.yaxis.label.set_color("#e7efe9")
    for spine in ax.spines.values():
        spine.set_color("#2c3a33")
    ax.grid(True, color="#24322b", alpha=0.7)
    if font_prop is not None:
        for label in ax.get_xticklabels() + ax.get_yticklabels():
            label.set_fontproperties(font_prop)


def _spans_from_pairs(
    pairs: list[dict[str, Any]], keys: tuple[str, ...], offset: float
) -> list[tuple[float, float]]:
    spans: list[tuple[float, float]] = []
    for item in pairs:
        block = None
        for key in keys:
            if isinstance(item.get(key), dict):
                block = item[key]
                break
        if not block:
            continue
        try:
            start = float(block["start"]) + offset
            end = float(block["end"]) + offset
        except (KeyError, TypeError, ValueError):
            continue
        if end > start:
            spans.append((start, end))
    return spans


def _waveform_compare_png(
    *,
    delsys: dict[str, Any],
    exp: dict[str, Any],
    exp_label: str,
    title: str,
) -> bytes | None:
    """Two-panel raw waveform. Y-axis includes the full peak-to-peak range."""
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.ticker import ScalarFormatter
    except Exception:
        return None

    font_prop = _matplotlib_font_properties()
    if font_prop is not None:
        try:
            plt.rcParams["font.family"] = font_prop.get_name()
            plt.rcParams["axes.unicode_minus"] = False
        except Exception:
            pass

    fig, (ax_ref, ax_exp) = plt.subplots(2, 1, figsize=(11.2, 5.3), sharex=False)
    fig.patch.set_facecolor("#0f1412")
    for ax in (ax_ref, ax_exp):
        _style_dark_ax(ax, font_prop)

    def _draw(ax, trace: dict[str, Any], *, color: str, label: str) -> None:
        times = [float(t) for t in (trace.get("times") or [])]
        values = [float(v) for v in (trace.get("values") or [])]
        n = min(len(times), len(values))
        times, values = times[:n], values[:n]
        for start, end in trace.get("spans") or []:
            ax.axvspan(start, end, color=color, alpha=0.16, linewidth=0)
        if times and values:
            y0, y1 = _readable_ylim(values)
            draw_t, draw_v = _stride(times, values)
            ax.plot(draw_t, draw_v, color=color, linewidth=0.7, label=label)
            ax.set_ylim(y0, y1)
            ax.set_xlim(times[0], times[-1])
        formatter = ScalarFormatter(useOffset=False)
        formatter.set_scientific(False)
        ax.yaxis.set_major_formatter(formatter)
        ax.margins(x=0.01)
        y_kwargs: dict[str, Any] = {"color": "#e7efe9", "fontsize": 9}
        if font_prop is not None:
            y_kwargs["fontproperties"] = font_prop
        unit = str(trace.get("unit") or "mV")
        ax.set_ylabel(f"{label} ({unit})", **y_kwargs)
        legend_kwargs: dict[str, Any] = {
            "loc": "upper right",
            "facecolor": "#18201c",
            "edgecolor": "#2c3a33",
            "labelcolor": "#e7efe9",
            "fontsize": 8,
        }
        if font_prop is not None:
            legend_kwargs["prop"] = font_prop
        ax.legend(**legend_kwargs)

    _draw(ax_ref, delsys, color="#5ec8ff", label="Delsys")
    _draw(ax_exp, exp, color="#3dd68c", label=exp_label)

    title_kwargs: dict[str, Any] = {"color": "#e7efe9", "fontsize": 11, "pad": 8}
    if font_prop is not None:
        title_kwargs["fontproperties"] = font_prop
    ax_ref.set_title(title, **title_kwargs)
    x_kwargs: dict[str, Any] = {"color": "#e7efe9", "fontsize": 9}
    if font_prop is not None:
        x_kwargs["fontproperties"] = font_prop
    ax_exp.set_xlabel("Time (s)", **x_kwargs)
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130, facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()


def _device_waveform_block(
    row: dict[str, Any],
    payload: dict[str, Any],
    *,
    h_style: ParagraphStyle,
    body_style: ParagraphStyle,
) -> list[Any]:
    """One device-comparison waveform: heading, caption, plot."""
    row_i = row.get("row")
    site = row.get("site") or row.get("部位") or ""
    device = str(row.get("device_note") or row.get("裝置") or payload.get("device_note") or "")
    ref_name = (
        payload.get("ref_resolved")
        or payload.get("ref")
        or row.get("ref")
        or row.get("ref_resolved")
        or ((payload.get("delsys") or {}).get("filename") if isinstance(payload.get("delsys"), dict) else "")
        or ""
    )
    exp_name = payload.get("exp_resolved") or payload.get("exp") or row.get("exp") or row.get("exp_resolved") or ""
    if not exp_name:
        for key in ("ze2", "ze1", "txt"):
            block = payload.get(key)
            if isinstance(block, dict) and block.get("filename"):
                exp_name = block["filename"]
                break

    heading = f"第 {row_i} 列　{site}　{device}"
    bits = [Paragraph(_escape(heading), h_style)]
    status = str(row.get("status") or "")
    if status and status != "done":
        bits.append(Paragraph(_escape(f"未繪製波形：{status}"), body_style))
        return bits
    if not ref_name or not exp_name:
        bits.append(Paragraph(_escape("未繪製波形：缺少對照或實驗檔名。"), body_style))
        return bits

    try:
        from compare import build_device_compare_waveform

        wave = build_device_compare_waveform(
            str(ref_name),
            str(exp_name),
            device_note=device,
            align_by_start=False,
        )
    except Exception as exc:  # noqa: BLE001
        bits.append(Paragraph(_escape(f"波形讀取失敗：{exc}"), body_style))
        return bits

    pairs = payload.get("pairs") if isinstance(payload.get("pairs"), list) else []
    delsys = dict(wave["delsys"])
    exp = dict(wave["exp"])
    delsys["spans"] = _spans_from_pairs(pairs, ("delsys",), 0.0)
    exp["spans"] = _spans_from_pairs(pairs, ("txt", "ze2", "ze1", "exp"), 0.0)
    exp_label = str(wave.get("exp_label") or "ZE1")
    rms_r = row.get("rms_pearson_r") if "rms_pearson_r" in row else row.get("RMS r")
    iemg_r = row.get("iemg_pearson_r") if "iemg_pearson_r" in row else row.get("iEMG r")
    filter_note = ""
    if device.lower() in {"a10", "ze2"}:
        filter_note = "　｜　實驗組已套用 20–400 Hz 帶通"
    caption = (
        f"Delsys：{ref_name}　｜　{exp_label}：{exp_name}　｜　"
        f"RMS r={_fmt(rms_r)}　iEMG r={_fmt(iemg_r)}　｜　"
        f"時間軸以各檔錄音起點為 0 秒；縱軸依主要振幅留白"
        f"{filter_note}"
    )
    bits.append(Paragraph(_escape(caption), body_style))
    png = _waveform_compare_png(
        delsys=delsys,
        exp=exp,
        exp_label=exp_label,
        title=f"#{row_i}  {site}  {device}  Delsys vs {exp_label}",
    )
    if not png:
        bits.append(Paragraph(_escape("波形圖產生失敗。"), body_style))
        return bits
    bits.append(Spacer(1, 0.15 * cm))
    bits.append(Image(io.BytesIO(png), width=26.2 * cm, height=12.2 * cm))
    return bits


def build_results_pdf(
    *,
    title: str = "emg-compare.app Report",
    meta: dict[str, Any] | None = None,
    feat_delsys: dict[str, Any] | None = None,
    feat_txt_tables: list[dict[str, Any]] | None = None,
    feat_delta: dict[str, Any] | None = None,
    contr_delsys: dict[str, Any] | None = None,
    contr_txt: list[dict[str, Any]] | None = None,
) -> bytes:
    """Build a PDF report bytes for feature / contraction results (tables + charts)."""
    font_name = _register_fonts()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=1.2 * cm,
        rightMargin=1.2 * cm,
        topMargin=1.2 * cm,
        bottomMargin=1.2 * cm,
        title=title,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "TitleCJK",
        parent=styles["Title"],
        fontName=font_name,
        fontSize=16,
        leading=20,
        textColor=colors.HexColor("#102018"),
    )
    h_style = ParagraphStyle(
        "HeadingCJK",
        parent=styles["Heading2"],
        fontName=font_name,
        fontSize=12,
        leading=16,
        textColor=colors.HexColor("#1f3b2e"),
        spaceBefore=10,
        spaceAfter=6,
    )
    body_style = ParagraphStyle(
        "BodyCJK",
        parent=styles["Normal"],
        fontName=font_name,
        fontSize=9,
        leading=13,
    )

    story: list[Any] = []
    story.append(Paragraph(_escape(title), title_style))
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    story.append(Paragraph(_escape(f"匯出時間：{stamp}"), body_style))

    meta = meta or {}
    if meta:
        lines = [f"{key}：{_fmt(value)}" for key, value in meta.items()]
        story.append(Paragraph(_escape(" / ".join(lines)), body_style))
    story.append(Spacer(1, 0.3 * cm))

    if feat_delsys and feat_delsys.get("result"):
        method = feat_delsys.get("feature_method") or "spectral"
        filename = feat_delsys["result"].get("filename") or "Delsys"
        story.append(Paragraph(_escape(f"Delsys 特徵 — {filename}（{method}）"), h_style))
        story.append(_make_table(_rows_from_features(feat_delsys["result"].get("features") or [], method), font_name))
        _add_series_image(story, feat_delsys["result"].get("series"), str(filename))

    for item in feat_txt_tables or []:
        result = item.get("result") or {}
        method = item.get("feature_method") or "spectral"
        filename = result.get("filename") or "TXT"
        story.append(Paragraph(_escape(f"TXT 特徵 — {filename}（{method}）"), h_style))
        story.append(_make_table(_rows_from_features(result.get("features") or [], method), font_name))
        _add_series_image(story, result.get("series"), str(filename))

    if feat_delta and feat_delta.get("pairs"):
        story.append(Paragraph(_escape("差異對照（Delsys − 第一個 TXT）"), h_style))
        if feat_delta.get("note"):
            story.append(Paragraph(_escape(str(feat_delta["note"])), body_style))
        story.append(_make_table(_rows_from_delta(feat_delta.get("pairs") or []), font_name))
        if feat_delta.get("interval_agreement"):
            story.append(Paragraph(_escape("收縮區間一致性（Pearson r / ICC(A,1)）"), h_style))
            story.append(
                _make_table(
                    _rows_from_interval_agreement(feat_delta.get("interval_agreement") or []),
                    font_name,
                )
            )
        if feat_delta.get("correlation"):
            story.append(Paragraph(_escape("TTRI 滑動窗相關係數（Pearson r）"), h_style))
            story.append(
                _make_table(_rows_from_correlation(feat_delta.get("correlation") or {}), font_name)
            )

    if contr_delsys:
        filename = contr_delsys.get("filename") or "Delsys"
        story.append(Paragraph(_escape(f"Delsys 收縮區間 — {filename}"), h_style))
        story.append(_make_table(_rows_from_contractions(contr_delsys.get("contractions") or []), font_name))

    for item in contr_txt or []:
        filename = item.get("filename") or "TXT"
        story.append(Paragraph(_escape(f"TXT 收縮區間 — {filename}"), h_style))
        story.append(_make_table(_rows_from_contractions(item.get("contractions") or []), font_name))

    if len(story) <= 3:
        story.append(Paragraph(_escape("尚無可匯出的結果，請先執行分析。"), body_style))

    doc.build(story)
    return buffer.getvalue()


def _short(text: Any, max_len: int = 42) -> str:
    s = "" if text is None else str(text)
    if len(s) <= max_len:
        return s
    return s[: max_len - 1] + "…"


def build_pair_list_pdf(
    summary_rows: list[dict[str, Any]],
    *,
    result_payloads: list[dict[str, Any]] | None = None,
    title: str = "ZE1 清單分析結果報告",
) -> bytes:
    """
    Standalone PDF for Excel pair-list batch results.

    Includes overview metrics and a fatigue-visibility section with evidence.
    """
    font_name = _register_fonts()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=1.0 * cm,
        rightMargin=1.0 * cm,
        topMargin=1.0 * cm,
        bottomMargin=1.0 * cm,
        title=title,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "TitleCJK",
        parent=styles["Title"],
        fontName=font_name,
        fontSize=16,
        leading=20,
        textColor=colors.HexColor("#102018"),
    )
    h_style = ParagraphStyle(
        "HeadingCJK",
        parent=styles["Heading2"],
        fontName=font_name,
        fontSize=12,
        leading=16,
        textColor=colors.HexColor("#1f3b2e"),
        spaceBefore=10,
        spaceAfter=6,
    )
    body_style = ParagraphStyle(
        "BodyCJK",
        parent=styles["Normal"],
        fontName=font_name,
        fontSize=9,
        leading=13,
    )
    small_style = ParagraphStyle(
        "SmallCJK",
        parent=styles["Normal"],
        fontName=font_name,
        fontSize=7.5,
        leading=10,
    )

    story: list[Any] = []
    story.append(Paragraph(_escape(title), title_style))
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    n_done = sum(1 for r in summary_rows if r.get("status") == "done")
    n_miss = sum(1 for r in summary_rows if r.get("status") == "missing_files")
    n_err = sum(1 for r in summary_rows if str(r.get("status") or "").startswith("error"))
    story.append(Paragraph(_escape(f"匯出時間：{stamp}"), body_style))
    story.append(
        Paragraph(
            _escape(
                f"完成 {n_done}／缺檔 {n_miss}／錯誤 {n_err}　｜　"
                "收縮：ze1_schmitt　特徵：TTRI　裝置比對／刮腿毛預期 3 段、疲勞 10 段"
            ),
            body_style,
        )
    )
    story.append(
        Paragraph(
            _escape(
                "疲勞可視性：跨收縮 MPF／MDF 下降為主（RMS／AEMG 上升為輔）→ 是／弱／否"
            ),
            body_style,
        )
    )
    story.append(Spacer(1, 0.25 * cm))

    # --- Overview ---
    story.append(Paragraph(_escape("一、總覽"), h_style))
    overview_header = [
        "列",
        "部位",
        "目的",
        "裝置",
        "段數",
        "RMS r",
        "RMS ICC",
        "iEMG r",
        "TTRI RMS",
        "疲勞",
    ]
    overview_body: list[list[str]] = []
    for row in summary_rows:
        overview_body.append(
            [
                _fmt(row.get("row")),
                _short(row.get("site"), 8),
                _short(row.get("purpose"), 6),
                _short(row.get("device_note") or row.get("裝置"), 5),
                _fmt(
                    row.get("段數")
                    or f"{row.get('ref_count') or '—'}/{row.get('exp_count') or '—'}"
                ),
                _fmt(row.get("rms_pearson_r") if "rms_pearson_r" in row else row.get("RMS r")),
                _fmt(row.get("rms_icc") if "rms_icc" in row else row.get("RMS ICC")),
                _fmt(row.get("iemg_pearson_r") if "iemg_pearson_r" in row else row.get("iEMG r")),
                _fmt(row.get("ttri_rms_r") if "ttri_rms_r" in row else row.get("TTRI RMS r")),
                _short(
                    row.get("fatigue_visible")
                    or row.get("疲勞可視")
                    or ("—" if str(row.get("purpose") or row.get("目的") or "") != "疲勞" else ""),
                    8,
                ),
            ]
        )
    story.append(_make_table([overview_header, *overview_body], font_name))

    device_rows = [
        r
        for r in summary_rows
        if str(r.get("purpose") or r.get("目的") or "") == "裝置比對"
    ]
    payload_by_row: dict[Any, dict[str, Any]] = {}
    for payload in result_payloads or []:
        if isinstance(payload, dict) and payload.get("row") is not None:
            try:
                key = int(payload["row"])
            except (TypeError, ValueError):
                key = payload["row"]
            payload_by_row[key] = payload

    if device_rows:
        story.append(PageBreak())
        story.append(Paragraph(_escape("二、裝置比對波形"), h_style))
        story.append(
            Paragraph(
                _escape(
                    "每組一頁。上圖 Delsys、下圖 ZE1 或 ZE2，皆為原始 mV，時間軸以各檔錄音起點為 0 秒。"
                    "縱軸依主要振幅留白，波峰不貼齊框線；極少數單點突波不拿來撐滿刻度。"
                    "色帶是 Schmitt 抓到的收縮段。a10 與 ZE2 的實驗組另套用 20–400 Hz 帶通。"
                ),
                small_style,
            )
        )
        for index, row in enumerate(device_rows):
            try:
                row_i = int(row.get("row"))
            except (TypeError, ValueError):
                row_i = row.get("row")
            if index:
                story.append(PageBreak())
            story.extend(
                _device_waveform_block(
                    row,
                    payload_by_row.get(row_i) or {},
                    h_style=h_style,
                    body_style=body_style,
                )
            )

    # --- Fatigue ---
    fatigue_rows = [
        r for r in summary_rows if str(r.get("purpose") or r.get("目的") or "") == "疲勞"
    ]
    if fatigue_rows:
        story.append(PageBreak())
        story.append(Paragraph(_escape("三、疲勞：這一次能否看出疲勞"), h_style))
        story.append(
            Paragraph(
                _escape(
                    "規則：≥5 段；MPF/MDF 對收縮序 r≤−0.35 且前→後三分之一 ≤−3%；"
                    "振幅輔助 RMS/AEMG r≥0.35 且 ≥+5%。是＝兩項頻譜或一頻譜+一振幅。"
                ),
                small_style,
            )
        )
        fat_header = ["列", "部位", "綜合", "Delsys", "TXT", "依據摘要"]
        fat_body: list[list[Any]] = []
        for row in fatigue_rows:
            try:
                row_i = int(row.get("row"))
            except (TypeError, ValueError):
                row_i = row.get("row")
            payload = payload_by_row.get(row_i) or {}
            fv = payload.get("fatigue_visibility") or {}
            bits: list[str] = []
            for side_key, tag in (("ref", "D"), ("exp", "T")):
                side = fv.get(side_key) or {}
                ev = side.get("evidence") or []
                if ev:
                    bits.append(f"{tag}: " + "; ".join(str(x) for x in ev[:2]))
            evidence = " / ".join(bits) if bits else str(fv.get("summary") or "")
            fat_body.append(
                [
                    _fmt(row_i),
                    _short(row.get("site") or row.get("部位"), 8),
                    _fmt(row.get("fatigue_visible") or row.get("綜合可視") or ""),
                    _fmt(row.get("fatigue_ref") or row.get("對照組可視") or ""),
                    _fmt(row.get("fatigue_exp") or row.get("實驗組可視") or ""),
                    Paragraph(_escape(_short(evidence, 120)), small_style),
                ]
            )
        story.append(_make_table([fat_header, *fat_body], font_name))

    # --- Notes ---
    story.append(Paragraph(_escape("四、備註"), h_style))
    notes = [
        "詳細數值另見 analysis_results.xlsx（總覽／疲勞可視／區間特徵／區間一致性）。",
        "裝置比對波形為原始 mV。縱軸依主要振幅留白，避免波峰貼齊框線。a10 與 ZE2 實驗組套用 20–400 Hz 帶通；a09 維持原訊號。",
        "第 15 列右腓腸肌 a09 缺 Delsys 對照檔，未執行。",
        "RMS＝各收縮段單一 RMS 再跨段比；TTRI RMS＝滑動窗 RMS 曲線僅收縮區間內相關。",
    ]
    for line in notes:
        story.append(Paragraph(_escape(f"• {line}"), body_style))

    doc.build(story)
    return buffer.getvalue()


def _write_csv(path_or_buf, rows: list[list[str]]) -> None:
    writer = csv.writer(path_or_buf)
    for row in rows:
        writer.writerow(row)


def build_results_csv_zip(
    *,
    feat_delsys: dict[str, Any] | None = None,
    feat_txt_tables: list[dict[str, Any]] | None = None,
    feat_delta: dict[str, Any] | None = None,
    contr_delsys: dict[str, Any] | None = None,
    contr_txt: list[dict[str, Any]] | None = None,
) -> bytes:
    """Build a ZIP of CSV tables (UTF-8 BOM for Excel)."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        if feat_delsys and feat_delsys.get("result"):
            method = feat_delsys.get("feature_method") or "spectral"
            rows = _rows_from_features(feat_delsys["result"].get("features") or [], method)
            text = io.StringIO()
            text.write("\ufeff")
            _write_csv(text, rows)
            zf.writestr("features_delsys.csv", text.getvalue().encode("utf-8"))

        for idx, item in enumerate(feat_txt_tables or [], start=1):
            result = item.get("result") or {}
            method = item.get("feature_method") or "spectral"
            rows = _rows_from_features(result.get("features") or [], method)
            text = io.StringIO()
            text.write("\ufeff")
            _write_csv(text, rows)
            stem = str(result.get("filename") or f"txt_{idx}").replace("/", "_")
            zf.writestr(f"features_txt_{idx}_{stem}.csv", text.getvalue().encode("utf-8"))

        if feat_delta and feat_delta.get("pairs"):
            rows = _rows_from_delta(feat_delta.get("pairs") or [])
            text = io.StringIO()
            text.write("\ufeff")
            _write_csv(text, rows)
            zf.writestr("features_delta.csv", text.getvalue().encode("utf-8"))
            if feat_delta.get("interval_agreement"):
                agr_rows = _rows_from_interval_agreement(feat_delta.get("interval_agreement") or [])
                agr_text = io.StringIO()
                agr_text.write("\ufeff")
                _write_csv(agr_text, agr_rows)
                zf.writestr("features_interval_agreement.csv", agr_text.getvalue().encode("utf-8"))
            if feat_delta.get("correlation"):
                corr_rows = _rows_from_correlation(feat_delta.get("correlation") or {})
                corr_text = io.StringIO()
                corr_text.write("\ufeff")
                _write_csv(corr_text, corr_rows)
                zf.writestr("features_correlation.csv", corr_text.getvalue().encode("utf-8"))

        if contr_delsys:
            rows = _rows_from_contractions(contr_delsys.get("contractions") or [])
            text = io.StringIO()
            text.write("\ufeff")
            _write_csv(text, rows)
            zf.writestr("contractions_delsys.csv", text.getvalue().encode("utf-8"))

        for idx, item in enumerate(contr_txt or [], start=1):
            rows = _rows_from_contractions(item.get("contractions") or [])
            text = io.StringIO()
            text.write("\ufeff")
            _write_csv(text, rows)
            stem = str(item.get("filename") or f"txt_{idx}").replace("/", "_")
            zf.writestr(f"contractions_txt_{idx}_{stem}.csv", text.getvalue().encode("utf-8"))

    return buffer.getvalue()
