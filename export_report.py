"""Export analysis results to PDF / CSV for download."""

from __future__ import annotations

import csv
import io
import zipfile
from datetime import datetime
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def _register_fonts() -> str:
    """Return a CID font name that can render Traditional Chinese."""
    name = "MHei-Medium"
    try:
        pdfmetrics.registerFont(UnicodeCIDFont(name))
    except Exception:
        name = "Helvetica"
    return name


def _fmt(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def _rows_from_features(features: list[dict[str, Any]], method: str) -> list[list[str]]:
    if method in {"ttri", "ze1", "muscle_capture"}:
        cols = ["index", "start", "end", "duration", "aemg", "rms", "iemg", "mpf", "mdf", "peak_rms"]
    else:
        cols = ["index", "start", "end", "duration", "iemg", "rms", "mdf", "mpf", "peak_rms"]
    header = cols
    body = [[_fmt(row.get(col)) for col in cols] for row in features]
    return [header, *body]


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
    header = ["index", *[f"Δ {k}" for k in keys]]
    body = []
    for item in pairs:
        delta = item.get("delta") or {}
        body.append([_fmt(item.get("index")), *[_fmt(delta.get(k)) for k in keys]])
    return [header, *body]


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


def build_results_pdf(
    *,
    title: str = "emg-compare.app 分析報告",
    meta: dict[str, Any] | None = None,
    feat_delsys: dict[str, Any] | None = None,
    feat_txt_tables: list[dict[str, Any]] | None = None,
    feat_delta: dict[str, Any] | None = None,
    contr_delsys: dict[str, Any] | None = None,
    contr_txt: list[dict[str, Any]] | None = None,
) -> bytes:
    """Build a PDF report bytes for feature / contraction results."""
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
    story.append(Paragraph(title, title_style))
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    story.append(Paragraph(f"匯出時間：{stamp}", body_style))

    meta = meta or {}
    if meta:
        lines = [f"{key}：{_fmt(value)}" for key, value in meta.items()]
        story.append(Paragraph(" / ".join(lines), body_style))
    story.append(Spacer(1, 0.3 * cm))

    if feat_delsys and feat_delsys.get("result"):
        method = feat_delsys.get("feature_method") or "spectral"
        filename = feat_delsys["result"].get("filename") or "Delsys"
        story.append(Paragraph(f"Delsys 特徵 — {filename}（{method}）", h_style))
        story.append(_make_table(_rows_from_features(feat_delsys["result"].get("features") or [], method), font_name))

    for item in feat_txt_tables or []:
        result = item.get("result") or {}
        method = item.get("feature_method") or "spectral"
        filename = result.get("filename") or "TXT"
        story.append(Paragraph(f"TXT 特徵 — {filename}（{method}）", h_style))
        story.append(_make_table(_rows_from_features(result.get("features") or [], method), font_name))

    if feat_delta and feat_delta.get("pairs"):
        story.append(Paragraph("差異對照 Δ（Delsys − 第一個 TXT）", h_style))
        if feat_delta.get("note"):
            story.append(Paragraph(str(feat_delta["note"]), body_style))
        story.append(_make_table(_rows_from_delta(feat_delta.get("pairs") or []), font_name))

    if contr_delsys:
        filename = contr_delsys.get("filename") or "Delsys"
        story.append(Paragraph(f"Delsys 收縮區間 — {filename}", h_style))
        story.append(_make_table(_rows_from_contractions(contr_delsys.get("contractions") or []), font_name))

    for item in contr_txt or []:
        filename = item.get("filename") or "TXT"
        story.append(Paragraph(f"TXT 收縮區間 — {filename}", h_style))
        story.append(_make_table(_rows_from_contractions(item.get("contractions") or []), font_name))

    if len(story) <= 3:
        story.append(Paragraph("尚無可匯出的結果，請先執行分析。", body_style))

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
