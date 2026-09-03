from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

import numpy as np

# Fully initialize pandas before Plotly validators touch it (avoids circular-import races).
import pandas as pd  # noqa: F401
import plotly.graph_objects as go
import streamlit as st

from compare import (
    build_feature_compare,
    build_feature_compare_ze2,
    build_feature_single,
    build_contraction_single,
    build_waveform_overlay,
    build_waveform_single,
)
from parsers.delsys import list_delsys_files
from parsers.txt_device import list_txt_files
from parsers.ze2_txt import DEFAULT_SAMPLE_RATE as ZE2_DEFAULT_FS
from parsers.ze2_txt import ZE2_MV_PER_COUNT, list_ze2_files
from paths import DATA_DELSYS, DATA_TXT, DATA_ZE2, ensure_data_dirs
from export_report import build_results_csv_zip, build_results_pdf

DELSYS_COLOR = "#5ec8ff"
TXT_COLORS = [
    "#3dd68c",
    "#a0e85c",
    "#5ef0c8",
    "#80d4ff",
    "#c8f070",
    "#48e0a0",
    "#90f0b0",
    "#68d8e0",
]
ZE2_COLORS = [
    "#f0b429",
    "#ff9f43",
    "#e8c547",
    "#f4a261",
    "#e9c46a",
    "#f7b267",
    "#ffd166",
    "#f4d35e",
]

SPECTRAL_COLS = ["index", "start", "end", "duration", "iemg", "rms", "mdf", "mpf", "peak_rms"]
TTRI_COLS = ["index", "start", "end", "duration", "aemg", "rms", "iemg", "mpf", "mdf", "peak_rms"]

st.set_page_config(
    page_title="emg-compare.app",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
      :root {
        --bg: #0f1412;
        --bg-elevated: #18201c;
        --bg-panel: #141b18;
        --line: #2c3a33;
        --text: #e7efe9;
        --muted: #93a59a;
        --accent: #3dd68c;
        --accent-2: #5ec8ff;
      }
      html, body, .stApp {
        color: var(--text);
        background:
          radial-gradient(1200px 600px at 10% -10%, rgba(62, 214, 140, 0.12), transparent 55%),
          radial-gradient(900px 500px at 100% 0%, rgba(94, 200, 255, 0.10), transparent 50%),
          linear-gradient(180deg, #101612 0%, #0c100e 100%);
      }
      [data-testid="stHeader"] { background: transparent; }
      [data-testid="stToolbar"] { visibility: hidden; height: 0; }
      #MainMenu { visibility: hidden; }
      footer { visibility: hidden; }
      [data-testid="stSidebar"] {
        background: rgba(14, 20, 17, 0.95);
        border-right: 1px solid var(--line);
      }
      [data-testid="stSidebar"] > div:first-child {
        padding-top: 1rem;
      }
      section.main > div {
        padding-top: 0.6rem;
        padding-left: 1.2rem;
        padding-right: 1.2rem;
      }
      .brand-kicker {
        margin: 0;
        letter-spacing: 0.16em;
        text-transform: uppercase;
        font-size: 0.72rem;
        color: var(--accent);
      }
      .brand-title {
        margin: 0.25rem 0 0.15rem;
        font-size: 1.55rem;
        font-weight: 700;
        color: var(--text);
      }
      .brand-sub {
        margin: 0 0 0.8rem;
        color: var(--muted);
        font-size: 0.9rem;
      }
      .result-card {
        border: 1px solid var(--line);
        border-radius: 12px;
        background: rgba(20, 27, 24, 0.85);
        padding: 0.85rem 1rem 1rem;
        margin-bottom: 0.85rem;
      }
      .result-card h3 {
        margin: 0 0 0.55rem;
        font-size: 0.98rem;
        font-weight: 650;
        color: var(--text);
      }
      .empty-slot {
        margin: 0;
        padding: 0.75rem 0.9rem;
        border-radius: 8px;
        background: rgba(94, 200, 255, 0.12);
        color: var(--accent-2);
        font-size: 0.92rem;
      }
      div[data-testid="stTabs"] [data-baseweb="tab-list"] {
        gap: 0.35rem;
        border-bottom: 1px solid var(--line);
        margin-bottom: 0.8rem;
        flex-wrap: wrap;
        overflow-x: auto;
        row-gap: 0.25rem;
      }
      div[data-testid="stTabs"] button[data-baseweb="tab"] {
        background: transparent;
        color: var(--muted);
        border-radius: 8px 8px 0 0;
        white-space: normal !important;
        height: auto !important;
        min-height: 2.4rem;
        max-width: none !important;
        overflow: visible !important;
        text-overflow: unset !important;
        line-height: 1.25;
        padding-top: 0.45rem;
        padding-bottom: 0.45rem;
        align-items: flex-start;
      }
      div[data-testid="stTabs"] button[data-baseweb="tab"] > div,
      div[data-testid="stTabs"] button[data-baseweb="tab"] p,
      div[data-testid="stTabs"] button[data-baseweb="tab"] span {
        white-space: normal !important;
        overflow: visible !important;
        text-overflow: unset !important;
        word-break: break-all;
      }
      div[data-testid="stTabs"] button[aria-selected="true"] {
        color: var(--text);
        border-bottom: 2px solid var(--accent);
      }
      .stButton > button {
        border: 1px solid var(--line);
        background: var(--bg-elevated);
        color: var(--text);
        border-radius: 8px;
        white-space: nowrap;
        min-height: 2.6rem;
        height: auto !important;
      }
      .stButton > button[kind="primary"],
      .stButton > button[data-testid="baseButton-primary"] {
        background: linear-gradient(180deg, #3dd68c, #2bb673);
        color: #062316;
        border-color: transparent;
        font-weight: 650;
      }
      div[data-testid="stFileUploader"] section {
        background: var(--bg-panel);
        border: 1px solid var(--line);
        border-radius: 10px;
      }
      .block-container { max-width: 1680px; }
    </style>
    """,
    unsafe_allow_html=True,
)


def init_state() -> None:
    # Migrate legacy shared filter toggle before seeding defaults.
    if "apply_bandpass" in st.session_state:
        legacy = bool(st.session_state.pop("apply_bandpass"))
        if "apply_bandpass_ze1" not in st.session_state:
            st.session_state.apply_bandpass_ze1 = legacy
        if "apply_bandpass_ze2" not in st.session_state:
            st.session_state.apply_bandpass_ze2 = legacy

    defaults = {
        "selected_delsys": None,
        "selected_txt": [],
        "selected_ze2": [],
        "ze2_fs": float(ZE2_DEFAULT_FS),
        "ze2_mv": float(ZE2_MV_PER_COUNT),
        "apply_bandpass_ze1": True,
        "apply_bandpass_ze2": True,
        "wave_delsys": None,
        "wave_txt": None,
        "wave_ze2": None,
        "wave_overlay": None,
        "contr_delsys": None,
        "contr_txt": None,
        "contr_ze2": None,
        "feat_delsys": None,
        "feat_txt_tables": None,
        "feat_ze2_tables": None,
        "feat_delta": None,
        "file_nonce": 0,
        "hidden_files": [],
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value
    # Refresh ZE2 mV default once (0.00026 → 0.000048).
    if st.session_state.get("_ze2_mv_ver") != 2:
        st.session_state.ze2_mv = float(ZE2_MV_PER_COUNT)
        st.session_state._ze2_mv_ver = 2


def refresh_file_lists() -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    ensure_data_dirs()
    return list_delsys_files(), list_txt_files(), list_ze2_files()


def device_load_kwargs() -> dict[str, Any]:
    return {
        "ze2_sample_rate": float(st.session_state.get("ze2_fs") or ZE2_DEFAULT_FS),
        "ze2_mv_per_count": float(st.session_state.get("ze2_mv") or ZE2_MV_PER_COUNT),
        "apply_bandpass_ze1": bool(st.session_state.get("apply_bandpass_ze1", True)),
        "apply_bandpass_ze2": bool(st.session_state.get("apply_bandpass_ze2", True)),
    }


def ze2_run_kwargs() -> dict[str, Any]:
    """Kwargs for ZE2 loaders that take a single apply_bandpass flag."""
    opts = device_load_kwargs()
    return {
        "ze2_sample_rate": opts["ze2_sample_rate"],
        "ze2_mv_per_count": opts["ze2_mv_per_count"],
        "apply_bandpass": opts["apply_bandpass_ze2"],
    }


def save_uploads(uploaded_files, dest: Path) -> list[str]:
    ensure_data_dirs()
    dest.mkdir(parents=True, exist_ok=True)
    saved: list[str] = []
    for item in uploaded_files or []:
        target = dest / Path(item.name).name
        target.write_bytes(item.getbuffer())
        saved.append(target.name)
    return saved


def plot_layout(title: str = "", y_title: str = "Normalized", height: int = 520) -> dict[str, Any]:
    return {
        "title": {"text": title, "font": {"size": 15}},
        "height": height,
        "margin": {"t": 56, "r": 24, "b": 48, "l": 56},
        "legend": {"orientation": "h", "y": 1.08},
        "xaxis_title": "Time (s)",
        "yaxis_title": y_title,
        "template": "plotly_dark",
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": "rgba(0,0,0,0)",
        "font": {"color": "#e7efe9"},
    }


def card_open(title: str) -> None:
    st.markdown(f'<div class="result-card"><h3>{title}</h3>', unsafe_allow_html=True)


def card_close() -> None:
    st.markdown("</div>", unsafe_allow_html=True)


def empty_slot(text: str = "尚未執行") -> None:
    st.markdown(f'<p class="empty-slot">{text}</p>', unsafe_allow_html=True)


def _short_tab_label(prefix: str, filename: str | None, *, max_len: int | None = None) -> str:
    """Tab label with full basename (max_len kept for compatibility; unused)."""
    name = Path(str(filename or "未命名")).name
    if max_len is not None and len(name) > max_len:
        name = name[: max_len - 1] + "…"
    return f"{prefix} · {name}"


def clear_wave_result(*, source: str, filename: str | None = None) -> None:
    if source == "delsys":
        st.session_state.wave_delsys = None
    elif source == "txt" and filename:
        st.session_state.wave_txt = [
            item for item in (st.session_state.wave_txt or []) if item.get("filename") != filename
        ]
    elif source == "ze2" and filename:
        st.session_state.wave_ze2 = [
            item for item in (st.session_state.wave_ze2 or []) if item.get("filename") != filename
        ]
    elif source == "overlay":
        st.session_state.wave_overlay = None


def clear_contr_result(*, source: str, filename: str | None = None) -> None:
    if source == "delsys":
        st.session_state.contr_delsys = None
    elif source == "txt" and filename:
        st.session_state.contr_txt = [
            item for item in (st.session_state.contr_txt or []) if item.get("filename") != filename
        ]
    elif source == "ze2" and filename:
        st.session_state.contr_ze2 = [
            item for item in (st.session_state.contr_ze2 or []) if item.get("filename") != filename
        ]


def clear_feat_result(*, source: str, filename: str | None = None) -> None:
    if source == "delsys":
        st.session_state.feat_delsys = None
        st.session_state.feat_delta = None
    elif source == "txt" and filename:
        st.session_state.feat_txt_tables = [
            item
            for item in (st.session_state.feat_txt_tables or [])
            if (item.get("result") or {}).get("filename") != filename
        ]
        st.session_state.feat_delta = None
    elif source == "ze2" and filename:
        st.session_state.feat_ze2_tables = [
            item
            for item in (st.session_state.feat_ze2_tables or [])
            if (item.get("result") or {}).get("filename") != filename
        ]
        st.session_state.feat_delta = None


def clear_all_results_for_files(filenames: set[str]) -> None:
    """Drop cached charts/tables that reference deleted filenames."""
    if st.session_state.wave_delsys and st.session_state.wave_delsys.get("filename") in filenames:
        st.session_state.wave_delsys = None
    st.session_state.wave_txt = [
        item for item in (st.session_state.wave_txt or []) if item.get("filename") not in filenames
    ]
    st.session_state.wave_ze2 = [
        item for item in (st.session_state.wave_ze2 or []) if item.get("filename") not in filenames
    ]
    if st.session_state.wave_overlay:
        overlay = st.session_state.wave_overlay.get("overlay") or []
        if any(item.get("filename") in filenames for item in overlay):
            st.session_state.wave_overlay = None

    if st.session_state.contr_delsys and st.session_state.contr_delsys.get("filename") in filenames:
        st.session_state.contr_delsys = None
    st.session_state.contr_txt = [
        item for item in (st.session_state.contr_txt or []) if item.get("filename") not in filenames
    ]
    st.session_state.contr_ze2 = [
        item for item in (st.session_state.contr_ze2 or []) if item.get("filename") not in filenames
    ]

    feat_d = st.session_state.feat_delsys
    if feat_d and (feat_d.get("result") or {}).get("filename") in filenames:
        st.session_state.feat_delsys = None
    st.session_state.feat_txt_tables = [
        item
        for item in (st.session_state.feat_txt_tables or [])
        if (item.get("result") or {}).get("filename") not in filenames
    ]
    st.session_state.feat_ze2_tables = [
        item
        for item in (st.session_state.feat_ze2_tables or [])
        if (item.get("result") or {}).get("filename") not in filenames
    ]
    st.session_state.feat_delta = None


def hidden_file_set() -> set[str]:
    return set(st.session_state.get("hidden_files") or [])


def hide_files_from_picker(names: Sequence[str]) -> int:
    """Remove filenames from selectable lists only (disk files stay)."""
    nameset = {str(name) for name in names if name}
    if not nameset:
        return 0
    hidden = hidden_file_set() | nameset
    st.session_state.hidden_files = sorted(hidden)
    if st.session_state.selected_delsys in nameset:
        st.session_state.selected_delsys = None
    st.session_state.selected_txt = [
        name for name in (st.session_state.selected_txt or []) if name not in nameset
    ]
    st.session_state.selected_ze2 = [
        name for name in (st.session_state.selected_ze2 or []) if name not in nameset
    ]
    clear_all_results_for_files(nameset)
    return len(nameset)


def restore_files_to_picker(names: Sequence[str] | None = None) -> int:
    """Put previously hidden names back into selectable lists."""
    hidden = hidden_file_set()
    if not hidden:
        return 0
    if names is None:
        restored = len(hidden)
        st.session_state.hidden_files = []
        return restored
    nameset = {str(name) for name in names if name}
    keep = sorted(hidden - nameset)
    restored = len(hidden) - len(keep)
    st.session_state.hidden_files = keep
    return restored


def render_result_pages(
    pages: list[tuple[str, Any]] | list[tuple[str, Any, Any]],
    *,
    context: str,
) -> None:
    """One full-width chart page (Streamlit tab) per file / view, with optional clear button."""
    if not pages:
        empty_slot()
        return
    labels = [item[0] for item in pages]
    tabs = st.tabs(labels)
    for idx, (tab, page) in enumerate(zip(tabs, pages)):
        label = page[0]
        render_fn = page[1]
        remove_fn = page[2] if len(page) > 2 else None
        with tab:
            if remove_fn is not None:
                if st.button("清除此結果", key=f"clear_result_{context}_{idx}_{label}", type="secondary"):
                    remove_fn()
                    st.rerun()
            render_fn()


def y_title_for_norm(method: str) -> str:
    if method == "none":
        return "mV"
    if method == "maxabs":
        return "Norm (maxabs)"
    return "Norm (zscore)"


def _plot_series(xs: Sequence[Any] | None, ys: Sequence[Any] | None) -> tuple[list[float], list[float]]:
    """Convert trace arrays to plain Python lists for Plotly (avoids pandas validator races)."""
    x = np.asarray(xs if xs is not None else [], dtype=float).reshape(-1)
    y = np.asarray(ys if ys is not None else [], dtype=float).reshape(-1)
    n = int(min(x.size, y.size))
    if n <= 0:
        return [], []
    return x[:n].tolist(), y[:n].tolist()


def fig_from_trace(
    trace: dict[str, Any],
    *,
    color: str,
    title: str,
    y_title: str,
    height: int = 520,
) -> go.Figure:
    x, y = _plot_series(trace.get("times"), trace.get("values"))
    fig = go.Figure(
        data=[
            go.Scatter(
                x=x,
                y=y,
                mode="lines",
                name=trace.get("filename") or title,
                line={"color": color, "width": 1.4},
            )
        ]
    )
    fig.update_layout(**plot_layout(title=title or trace.get("filename", ""), y_title=y_title, height=height))
    return fig


def fig_overlay(traces: list[dict[str, Any]], *, title: str, y_title: str, height: int = 560) -> go.Figure:
    fig = go.Figure()
    txt_i = 0
    ze2_i = 0
    for item in traces:
        source = item.get("source")
        if source == "delsys":
            color = DELSYS_COLOR
            name = f"Delsys · {item['filename']}"
        elif source == "ze2":
            color = ZE2_COLORS[ze2_i % len(ZE2_COLORS)]
            name = f"ZE2 · {item['filename']}"
            ze2_i += 1
        else:
            color = TXT_COLORS[txt_i % len(TXT_COLORS)]
            name = f"TXT · {item['filename']}"
            txt_i += 1
        x, y = _plot_series(item.get("times"), item.get("values"))
        fig.add_trace(
            go.Scatter(
                x=x,
                y=y,
                mode="lines",
                name=name,
                line={"color": color, "width": 1.5},
            )
        )
    fig.update_layout(**plot_layout(title=title, y_title=y_title, height=height))
    return fig


def fig_contractions(result: dict[str, Any], *, color: str, title: str, height: int = 520) -> go.Figure:
    x, y = _plot_series(result.get("times"), result.get("values"))
    fig = go.Figure(
        data=[
            go.Scatter(
                x=x,
                y=y,
                mode="lines",
                name=result.get("filename") or title,
                line={"color": color, "width": 1.4},
            )
        ]
    )
    shapes = []
    for item in result.get("contractions") or []:
        shapes.append(
            {
                "type": "rect",
                "xref": "x",
                "yref": "paper",
                "x0": item["start"],
                "x1": item["end"],
                "y0": 0,
                "y1": 1,
                "fillcolor": color,
                "opacity": 0.18,
                "line": {"width": 0},
                "layer": "below",
            }
        )
    fig.update_layout(
        **plot_layout(title=title, y_title=str(result.get("unit") or "mV"), height=height),
        shapes=shapes,
    )
    # Keep rare spikes from dominating the visible scale.
    ys = list(result.get("values") or [])
    if ys:
        lo = float(np.percentile(ys, 0.5))
        hi = float(np.percentile(ys, 99.5))
        pad = max(0.02, 0.08 * (hi - lo))
        fig.update_yaxes(range=[lo - pad, hi + pad])
    return fig


def contractions_to_rows(contractions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for item in contractions:
        rows.append(
            {
                "index": item.get("index"),
                "start": item.get("start"),
                "end": item.get("end"),
                "duration": item.get("duration"),
                "peak_rms": item.get("peak_rms"),
            }
        )
    return rows


def feature_rows(features: list[dict[str, Any]], method: str) -> list[dict[str, Any]]:
    cols = TTRI_COLS if method in {"ttri", "ze1", "muscle_capture"} else SPECTRAL_COLS
    rows = []
    for item in features:
        rows.append({col: item.get(col) for col in cols if col in item or col in {"index", "start", "end"}})
    return rows


def plot_ttri_series(series: dict[str, Any] | None, *, title: str) -> go.Figure | None:
    if not series:
        return None

    # Split amplitude vs frequency so small mV-scale RMS/iEMG stay visible.
    from pathlib import Path

    from plotly.subplots import make_subplots

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.14,
        subplot_titles=("Amplitude (RMS / iEMG)", "Frequency (MPF / MDF)"),
        row_heights=[0.5, 0.5],
    )
    amp_specs = [("rms", "RMS", "#5ec8ff"), ("iemg", "iEMG", "#3dd68c")]
    freq_specs = [("mpf", "MPF", "#f0b429"), ("mdf", "MDF", "#c78bff")]
    for key, label, color in amp_specs:
        block = series.get(key) or {}
        times = block.get("times") or []
        values = block.get("values") or []
        if times and values:
            x, y = _plot_series(times, values)
            fig.add_trace(
                go.Scatter(x=x, y=y, mode="lines", name=label, line={"color": color, "width": 1.3}),
                row=1,
                col=1,
            )
    for key, label, color in freq_specs:
        block = series.get(key) or {}
        times = block.get("times") or []
        values = block.get("values") or []
        if times and values:
            x, y = _plot_series(times, values)
            fig.add_trace(
                go.Scatter(x=x, y=y, mode="lines", name=label, line={"color": color, "width": 1.3}),
                row=2,
                col=1,
            )
    if not fig.data:
        return None

    short_name = Path(str(title)).name
    aemg = series.get("aemg")
    subtitle = f"{short_name}  ·  AEMG={aemg}" if aemg is not None else short_name

    fig.update_layout(
        title={"text": subtitle, "font": {"size": 13}, "x": 0.0, "xanchor": "left", "y": 0.995, "yanchor": "top"},
        height=720,
        margin={"t": 56, "r": 24, "b": 72, "l": 60},
        legend={
            "orientation": "h",
            "yanchor": "top",
            "y": -0.08,
            "xanchor": "center",
            "x": 0.5,
            "bgcolor": "rgba(0,0,0,0)",
            "font": {"size": 11},
        },
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"color": "#e7efe9"},
        hovermode="x unified",
    )
    fig.update_annotations(font={"size": 12}, yshift=8)
    fig.update_yaxes(title_text="Amplitude", title_font={"size": 11}, row=1, col=1, automargin=True)
    fig.update_yaxes(title_text="Hz", title_font={"size": 11}, row=2, col=1, automargin=True)
    fig.update_xaxes(title_text="Time (s)", title_font={"size": 11}, row=2, col=1, automargin=True)
    return fig


def delta_rows(pairs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for item in pairs:
        row = {"index": item.get("index")}
        for key, value in (item.get("delta") or {}).items():
            row[f"Δ {key}"] = value
        for key, value in (item.get("delsys") or {}).items():
            if key not in {"index"}:
                row[f"D {key}"] = value
        right = item.get("ze2") or item.get("txt") or {}
        prefix = "Z" if item.get("ze2") else "T"
        for key, value in right.items():
            if key not in {"index"}:
                row[f"{prefix} {key}"] = value
        rows.append(row)
    return rows


def require_delsys() -> str | None:
    name = st.session_state.selected_delsys
    if not name:
        st.warning("請先選擇一個 Delsys CSV")
        return None
    return name


def require_txt() -> list[str] | None:
    names = list(st.session_state.selected_txt or [])
    if not names:
        st.warning("請先選擇至少一個 ZE1 TXT")
        return None
    return names


def require_ze2() -> list[str] | None:
    names = list(st.session_state.selected_ze2 or [])
    if not names:
        st.warning("請先選擇至少一個 ZE2 TXT")
        return None
    return names


def require_pair() -> tuple[str, list[str], list[str]] | None:
    """Require Delsys plus at least one of ZE1 TXT or ZE2."""
    delsys = require_delsys()
    if not delsys:
        return None
    txt = list(st.session_state.selected_txt or [])
    ze2 = list(st.session_state.selected_ze2 or [])
    if not txt and not ze2:
        st.warning("請至少選擇一個 ZE1 TXT 或 ZE2")
        return None
    return delsys, txt, ze2


def sibling_txt_channels(selected: list[str], available: list[str]) -> list[str]:
    """If user picks ExgCh1/Ch2, also include the matching pair name when present."""
    out: list[str] = []
    seen: set[str] = set()
    for name in selected:
        if name in seen:
            continue
        out.append(name)
        seen.add(name)
        if "ExgCh1" in name:
            alt = name.replace("ExgCh1", "ExgCh2")
        elif "ExgCh2" in name:
            alt = name.replace("ExgCh2", "ExgCh1")
        else:
            continue
        if alt in available and alt not in seen:
            out.append(alt)
            seen.add(alt)
    return out


def sibling_ze2_channels(selected: list[str], available: list[str]) -> list[str]:
    """If user picks _Ch1/_Ch2, also include the matching pair name when present."""
    out: list[str] = []
    seen: set[str] = set()
    for name in selected:
        if name in seen:
            continue
        out.append(name)
        seen.add(name)
        if "_Ch1." in name or name.endswith("_Ch1.txt"):
            alt = name.replace("_Ch1.", "_Ch2.").replace("_Ch1.txt", "_Ch2.txt")
        elif "_Ch2." in name or name.endswith("_Ch2.txt"):
            alt = name.replace("_Ch2.", "_Ch1.").replace("_Ch2.txt", "_Ch1.txt")
        else:
            continue
        if alt in available and alt not in seen:
            out.append(alt)
            seen.add(alt)
    return out


def render_sidebar() -> None:
    st.sidebar.markdown(
        """
        <p class="brand-kicker">Zentan</p>
        <p class="brand-title">emg-compare.app</p>
        <p class="brand-sub">Delsys × ZE1 TXT × ZE2</p>
        """,
        unsafe_allow_html=True,
    )

    with st.sidebar.expander("上傳檔案", expanded=False):
        up_delsys = st.file_uploader("Delsys CSV", type=["csv"], accept_multiple_files=True, key="up_delsys")
        up_txt = st.file_uploader("自研 ZE1 TXT", type=["txt"], accept_multiple_files=True, key="up_txt")
        up_ze2 = st.file_uploader("ZE2 TXT", type=["txt"], accept_multiple_files=True, key="up_ze2")
        if st.button("儲存上傳檔案", use_container_width=True):
            saved_d = save_uploads(up_delsys, DATA_DELSYS)
            saved_t = save_uploads(up_txt, DATA_TXT)
            saved_z = save_uploads(up_ze2, DATA_ZE2)
            st.session_state.file_nonce += 1
            if saved_d or saved_t or saved_z:
                st.success(f"已存入 {len(saved_d)} CSV、{len(saved_t)} ZE1、{len(saved_z)} ZE2")
            else:
                st.info("沒有選到檔案")

    if st.sidebar.button("重新整理檔案列表", use_container_width=True):
        st.session_state.file_nonce += 1

    delsys_files, txt_files, ze2_files = refresh_file_lists()
    hidden = hidden_file_set()
    delsys_names_all = [item["name"] for item in delsys_files]
    txt_names_all = [item["name"] for item in txt_files]
    ze2_names_all = [item["name"] for item in ze2_files]
    delsys_names = [name for name in delsys_names_all if name not in hidden]
    txt_names = [name for name in txt_names_all if name not in hidden]
    ze2_names = [name for name in ze2_names_all if name not in hidden]
    hidden_delsys = [name for name in delsys_names_all if name in hidden]
    hidden_txt = [name for name in txt_names_all if name in hidden]
    hidden_ze2 = [name for name in ze2_names_all if name in hidden]
    hidden_total = len(hidden_delsys) + len(hidden_txt) + len(hidden_ze2)

    st.sidebar.markdown(f"##### Delsys CSV（{len(delsys_names)}）")
    if not delsys_names:
        st.sidebar.info("尚無可選 CSV" if delsys_names_all else "尚無 CSV")
        st.session_state.selected_delsys = None
    else:
        if st.session_state.selected_delsys not in delsys_names:
            st.session_state.selected_delsys = delsys_names[0]
        st.sidebar.selectbox(
            "選擇 Delsys",
            delsys_names,
            key="selected_delsys",
            label_visibility="collapsed",
        )

    st.sidebar.markdown(f"##### 自研 ZE1 TXT（{len(txt_names)}，可多選）")
    if not txt_names:
        st.sidebar.info("尚無可選 ZE1 TXT" if txt_names_all else "尚無 ZE1 TXT")
        st.session_state.selected_txt = []
    else:
        st.session_state.selected_txt = [
            name for name in (st.session_state.selected_txt or []) if name in txt_names
        ]
        st.sidebar.multiselect(
            "選擇 ZE1 TXT",
            options=txt_names,
            key="selected_txt",
            label_visibility="collapsed",
            placeholder="點擊搜尋／選擇檔案…",
            help="可同時勾選多個，例如 ExgCh1 + ExgCh2",
        )
        if st.sidebar.button("自動勾選 ZE1 Ch1+Ch2", use_container_width=True):
            st.session_state.selected_txt = sibling_txt_channels(
                list(st.session_state.selected_txt or []),
                txt_names,
            )
            st.rerun()

    st.sidebar.markdown(f"##### ZE2 TXT（{len(ze2_names)}，可多選）")
    if not ze2_names:
        st.sidebar.info("尚無可選 ZE2 TXT" if ze2_names_all else "尚無 ZE2 TXT")
        st.session_state.selected_ze2 = []
    else:
        st.session_state.selected_ze2 = [
            name for name in (st.session_state.selected_ze2 or []) if name in ze2_names
        ]
        st.sidebar.multiselect(
            "選擇 ZE2",
            options=ze2_names,
            key="selected_ze2",
            label_visibility="collapsed",
            placeholder="點擊搜尋／選擇檔案…",
            help="24-bit hex；可同時勾選 Ch1 + Ch2",
        )
        if st.sidebar.button("自動勾選 ZE2 Ch1+Ch2", use_container_width=True):
            st.session_state.selected_ze2 = sibling_ze2_channels(
                list(st.session_state.selected_ze2 or []),
                ze2_names,
            )
            st.rerun()

    with st.sidebar.expander(
        f"整理可選檔案（已隱藏 {hidden_total}）",
        expanded=False,
    ):
        st.caption("只從選單移出，不刪除 data 資料夾內的實體檔。")
        hide_delsys = st.multiselect(
            "移出 Delsys",
            options=delsys_names,
            key="hide_delsys_files",
        )
        hide_txt = st.multiselect(
            "移出 ZE1 TXT",
            options=txt_names,
            key="hide_txt_files",
        )
        hide_ze2 = st.multiselect(
            "移出 ZE2 TXT",
            options=ze2_names,
            key="hide_ze2_files",
        )
        if st.button("從選單移出", use_container_width=True):
            n = hide_files_from_picker([*hide_delsys, *hide_txt, *hide_ze2])
            st.session_state.hide_delsys_files = []
            st.session_state.hide_txt_files = []
            st.session_state.hide_ze2_files = []
            if n:
                st.success(f"已移出 {n} 個檔案")
                st.rerun()
            else:
                st.info("請先勾選要移出的檔案")

        restore_options = [*hidden_delsys, *hidden_txt, *hidden_ze2]
        if restore_options:
            restore_pick = st.multiselect(
                "恢復到選單",
                options=restore_options,
                key="restore_hidden_files",
            )
            c_restore, c_all = st.columns(2)
            with c_restore:
                if st.button("恢復勾選", use_container_width=True):
                    n = restore_files_to_picker(restore_pick)
                    st.session_state.restore_hidden_files = []
                    if n:
                        st.success(f"已恢復 {n} 個")
                        st.rerun()
                    else:
                        st.info("請先勾選要恢復的檔案")
            with c_all:
                if st.button("全部恢復", use_container_width=True):
                    n = restore_files_to_picker(None)
                    st.session_state.restore_hidden_files = []
                    st.success(f"已恢復 {n} 個")
                    st.rerun()

    with st.sidebar.expander("濾波 / ZE2 參數", expanded=False):
        st.selectbox(
            "ZE1 數位濾波",
            options=[True, False],
            format_func=lambda on: "開啟（20–400 Hz）" if on else "關閉（原始）",
            key="apply_bandpass_ze1",
            help="僅套用在 ZE1 TXT。",
        )
        st.selectbox(
            "ZE2 數位濾波",
            options=[True, False],
            format_func=lambda on: "開啟（20–400 Hz）" if on else "關閉（原始）",
            key="apply_bandpass_ze2",
            help="僅套用在 ZE2 TXT。",
        )
        st.number_input(
            "ZE2 採樣率 Hz",
            min_value=1.0,
            max_value=10000.0,
            step=1.0,
            key="ze2_fs",
            help=f"預設 {ZE2_DEFAULT_FS}",
        )
        st.number_input(
            "ZE2 mV / count",
            min_value=1e-9,
            max_value=1.0,
            step=0.000001,
            format="%.6f",
            key="ze2_mv",
            help=f"預設 {ZE2_MV_PER_COUNT}",
        )


def tab_waveform() -> None:
    c1, c2 = st.columns([1.2, 1.2])
    with c1:
        norm_method = st.selectbox(
            "正規化",
            options=["zscore", "maxabs", "none"],
            format_func=lambda x: {
                "zscore": "Z-score",
                "maxabs": "Max-abs",
                "none": "原始值（不正規化）",
            }[x],
        )
    with c2:
        align_by_start = st.checkbox("依起始時間對齊", value=True)

    b1, b2, b3, b4 = st.columns([1, 1, 1, 1.3])
    run_d = b1.button("Delsys", use_container_width=True)
    run_t = b2.button("ZE1", use_container_width=True)
    run_z = b3.button("ZE2", use_container_width=True)
    run_both = b4.button("一起疊圖", type="primary", use_container_width=True)

    y_title = y_title_for_norm(norm_method)
    opts = device_load_kwargs()
    apply_bandpass_ze1 = bool(opts["apply_bandpass_ze1"])
    ze2_kwargs = ze2_run_kwargs()

    if run_d:
        name = require_delsys()
        if name:
            try:
                data = build_waveform_single("delsys", name, norm_method=norm_method)
                st.session_state.wave_delsys = data["trace"]
                st.success(f"Delsys 波形完成：{name}")
            except (FileNotFoundError, ValueError) as exc:
                st.error(str(exc))

    if run_t:
        names = require_txt()
        if names:
            try:
                traces = []
                for name in names:
                    data = build_waveform_single(
                        "txt",
                        name,
                        norm_method=norm_method,
                        apply_bandpass=apply_bandpass_ze1,
                    )
                    traces.append(data["trace"])
                st.session_state.wave_txt = traces
                st.success(f"ZE1 波形完成：{len(names)} 個")
            except (FileNotFoundError, ValueError) as exc:
                st.error(str(exc))

    if run_z:
        names = require_ze2()
        if names:
            try:
                traces = []
                for name in names:
                    data = build_waveform_single(
                        "ze2",
                        name,
                        norm_method=norm_method,
                        **ze2_kwargs,
                    )
                    traces.append(data["trace"])
                st.session_state.wave_ze2 = traces
                st.success(f"ZE2 波形完成：{len(names)} 個")
            except (FileNotFoundError, ValueError) as exc:
                st.error(str(exc))

    if run_both:
        pair = require_pair()
        if pair:
            delsys_name, txt_names, ze2_names = pair
            try:
                data = build_waveform_overlay(
                    delsys_name,
                    txt_names,
                    ze2_names,
                    norm_method=norm_method,
                    align_by_start=align_by_start,
                    ze2_sample_rate=opts["ze2_sample_rate"],
                    ze2_mv_per_count=opts["ze2_mv_per_count"],
                    apply_bandpass_ze1=opts["apply_bandpass_ze1"],
                    apply_bandpass_ze2=opts["apply_bandpass_ze2"],
                )
                st.session_state.wave_delsys = data["delsys"]
                st.session_state.wave_txt = data.get("txt_list") or []
                st.session_state.wave_ze2 = data.get("ze2_list") or []
                st.session_state.wave_overlay = data
                st.success("疊圖完成")
            except (FileNotFoundError, ValueError) as exc:
                st.error(str(exc))

    pages: list[tuple[str, Any, Any]] = []

    if st.session_state.wave_delsys:
        trace = st.session_state.wave_delsys

        def _render_delsys(tr=trace) -> None:
            st.plotly_chart(
                fig_from_trace(
                    tr,
                    color=DELSYS_COLOR,
                    title=tr.get("filename", "Delsys"),
                    y_title=y_title,
                ),
                use_container_width=True,
                config={"displayModeBar": True},
            )

        pages.append(
            (
                _short_tab_label("Delsys", trace.get("filename")),
                _render_delsys,
                lambda: clear_wave_result(source="delsys"),
            )
        )

    for i, trace in enumerate(st.session_state.wave_txt or []):
        color = TXT_COLORS[i % len(TXT_COLORS)]
        fname = trace.get("filename")

        def _render_txt(tr=trace, c=color) -> None:
            st.plotly_chart(
                fig_from_trace(
                    tr,
                    color=c,
                    title=tr.get("filename", "ZE1"),
                    y_title=y_title,
                ),
                use_container_width=True,
                config={"displayModeBar": True},
            )

        pages.append(
            (
                _short_tab_label("ZE1", fname),
                _render_txt,
                lambda name=fname: clear_wave_result(source="txt", filename=name),
            )
        )

    for i, trace in enumerate(st.session_state.wave_ze2 or []):
        color = ZE2_COLORS[i % len(ZE2_COLORS)]
        fname = trace.get("filename")

        def _render_ze2(tr=trace, c=color) -> None:
            st.plotly_chart(
                fig_from_trace(
                    tr,
                    color=c,
                    title=tr.get("filename", "ZE2"),
                    y_title=y_title,
                ),
                use_container_width=True,
                config={"displayModeBar": True},
            )

        pages.append(
            (
                _short_tab_label("ZE2", fname),
                _render_ze2,
                lambda name=fname: clear_wave_result(source="ze2", filename=name),
            )
        )

    overlay = st.session_state.wave_overlay
    if overlay and overlay.get("overlay"):

        def _render_overlay(ov=overlay) -> None:
            st.plotly_chart(
                fig_overlay(
                    ov["overlay"],
                    title=f"波形疊圖（{ov.get('norm_method')}）",
                    y_title=y_title,
                ),
                use_container_width=True,
                config={"displayModeBar": True},
            )
            if ov.get("note"):
                st.caption(ov["note"])

        pages.append(("疊圖", _render_overlay, lambda: clear_wave_result(source="overlay")))

    if pages:
        st.caption("每個檔案一個頁籤；可按「清除此結果」移除圖表。")
        c_clear, _ = st.columns([1, 3])
        with c_clear:
            if st.button("清除全部波形結果", key="clear_all_wave"):
                st.session_state.wave_delsys = None
                st.session_state.wave_txt = None
                st.session_state.wave_ze2 = None
                st.session_state.wave_overlay = None
                st.rerun()
        render_result_pages(pages, context="wave")
    else:
        empty_slot()


def tab_contractions() -> None:
    c1, c2 = st.columns([1.6, 0.8])
    with c1:
        contraction_method = st.selectbox(
            "收縮判斷",
            options=["rms_peak", "ze1_schmitt"],
            format_func=lambda x: {
                "rms_peak": "RMS 峰值法（現有）",
                "ze1_schmitt": "ZE1 施密特觸發",
            }[x],
            key="contr_method",
        )
    with c2:
        expected = st.number_input("預期次數", min_value=1, max_value=10, value=3, key="contr_expected")

    b1, b2, b3, b4 = st.columns([1, 1, 1, 1.3])
    run_d = b1.button("Delsys", key="contr_d", use_container_width=True)
    run_t = b2.button("ZE1", key="contr_t", use_container_width=True)
    run_z = b3.button("ZE2", key="contr_z", use_container_width=True)
    run_both = b4.button("一起", key="contr_both", type="primary", use_container_width=True)

    opts = device_load_kwargs()
    apply_bandpass_ze1 = bool(opts["apply_bandpass_ze1"])
    ze2_kwargs = ze2_run_kwargs()

    if run_d or run_both:
        name = require_delsys()
        if name:
            try:
                data = build_contraction_single(
                    "delsys",
                    name,
                    expected_count=int(expected),
                    contraction_method=contraction_method,
                )
                st.session_state.contr_delsys = data["result"]
            except (FileNotFoundError, ValueError) as exc:
                st.error(str(exc))

    if run_t or (run_both and st.session_state.selected_txt):
        names = list(st.session_state.selected_txt or [])
        if run_t and not names:
            require_txt()
        elif names:
            try:
                results = []
                for name in names:
                    data = build_contraction_single(
                        "txt",
                        name,
                        expected_count=int(expected),
                        contraction_method=contraction_method,
                        apply_bandpass=apply_bandpass_ze1,
                    )
                    results.append(data["result"])
                st.session_state.contr_txt = results
            except (FileNotFoundError, ValueError) as exc:
                st.error(str(exc))

    if run_z or (run_both and st.session_state.selected_ze2):
        names = list(st.session_state.selected_ze2 or [])
        if run_z and not names:
            require_ze2()
        elif names:
            try:
                results = []
                for name in names:
                    data = build_contraction_single(
                        "ze2",
                        name,
                        expected_count=int(expected),
                        contraction_method=contraction_method,
                        **ze2_kwargs,
                    )
                    results.append(data["result"])
                st.session_state.contr_ze2 = results
            except (FileNotFoundError, ValueError) as exc:
                st.error(str(exc))

    if run_both:
        require_pair()

    pages: list[tuple[str, Any, Any]] = []

    if st.session_state.contr_delsys:
        result = st.session_state.contr_delsys

        def _render_delsys(res=result) -> None:
            st.plotly_chart(
                fig_contractions(res, color=DELSYS_COLOR, title=res.get("filename", "Delsys")),
                use_container_width=True,
                config={"displayModeBar": True},
            )
            st.dataframe(contractions_to_rows(res.get("contractions") or []), use_container_width=True)

        pages.append(
            (
                _short_tab_label("Delsys", result.get("filename")),
                _render_delsys,
                lambda: clear_contr_result(source="delsys"),
            )
        )

    for i, result in enumerate(st.session_state.contr_txt or []):
        color = TXT_COLORS[i % len(TXT_COLORS)]
        fname = result.get("filename")

        def _render_txt(res=result, c=color) -> None:
            st.plotly_chart(
                fig_contractions(res, color=c, title=res.get("filename", "ZE1")),
                use_container_width=True,
                config={"displayModeBar": True},
            )
            st.dataframe(contractions_to_rows(res.get("contractions") or []), use_container_width=True)

        pages.append(
            (
                _short_tab_label("ZE1", fname),
                _render_txt,
                lambda name=fname: clear_contr_result(source="txt", filename=name),
            )
        )

    for i, result in enumerate(st.session_state.contr_ze2 or []):
        color = ZE2_COLORS[i % len(ZE2_COLORS)]
        fname = result.get("filename")

        def _render_ze2(res=result, c=color) -> None:
            st.plotly_chart(
                fig_contractions(res, color=c, title=res.get("filename", "ZE2")),
                use_container_width=True,
                config={"displayModeBar": True},
            )
            st.dataframe(contractions_to_rows(res.get("contractions") or []), use_container_width=True)

        pages.append(
            (
                _short_tab_label("ZE2", fname),
                _render_ze2,
                lambda name=fname: clear_contr_result(source="ze2", filename=name),
            )
        )

    if pages:
        st.caption("每個檔案一個頁籤；可按「清除此結果」移除圖表。")
        c_clear, _ = st.columns([1, 3])
        with c_clear:
            if st.button("清除全部收縮結果", key="clear_all_contr"):
                st.session_state.contr_delsys = None
                st.session_state.contr_txt = None
                st.session_state.contr_ze2 = None
                st.rerun()
        render_result_pages(pages, context="contr")
    else:
        empty_slot()

    render_export_panel(context="contractions")


def tab_features() -> None:
    c1, c2, c3 = st.columns([1.3, 1.5, 0.7])
    with c1:
        contraction_method = st.selectbox(
            "收縮判斷",
            options=["rms_peak", "ze1_schmitt"],
            format_func=lambda x: {
                "rms_peak": "RMS 峰值法（現有）",
                "ze1_schmitt": "ZE1 施密特觸發",
            }[x],
            key="feat_contr_method",
        )
    with c2:
        feature_method = st.selectbox(
            "特徵計算",
            options=["spectral", "ttri"],
            format_func=lambda x: {
                "spectral": "Spectral（iEMG/RMS/MDF/MPF）",
                "ttri": "TTRI / ZE1（AEMG + 滑動窗）",
            }[x],
            key="feat_method",
        )
    with c3:
        expected = st.number_input("預期次數", min_value=1, max_value=10, value=3, key="feat_expected")

    b1, b2, b3, b4 = st.columns([1, 1, 1, 1.4])
    run_d = b1.button("Delsys", key="feat_d", use_container_width=True)
    run_t = b2.button("ZE1", key="feat_t", use_container_width=True)
    run_z = b3.button("ZE2", key="feat_z", use_container_width=True)
    run_both = b4.button("一起（含 Δ）", key="feat_both", type="primary", use_container_width=True)

    opts = device_load_kwargs()
    apply_bandpass_ze1 = bool(opts["apply_bandpass_ze1"])
    ze2_kwargs = ze2_run_kwargs()

    if run_d:
        name = require_delsys()
        if name:
            try:
                data = build_feature_single(
                    "delsys",
                    name,
                    expected_count=int(expected),
                    contraction_method=contraction_method,
                    feature_method=feature_method,
                )
                st.session_state.feat_delsys = data
                st.success(f"Delsys 特徵完成（{data['result']['count']} 段）")
            except (FileNotFoundError, ValueError) as exc:
                st.error(str(exc))

    if run_t:
        names = require_txt()
        if names:
            try:
                tables = []
                for name in names:
                    data = build_feature_single(
                        "txt",
                        name,
                        expected_count=int(expected),
                        contraction_method=contraction_method,
                        feature_method=feature_method,
                        apply_bandpass=apply_bandpass_ze1,
                    )
                    tables.append(data)
                st.session_state.feat_txt_tables = tables
                st.success(f"ZE1 特徵完成（{len(names)} 個）")
            except (FileNotFoundError, ValueError) as exc:
                st.error(str(exc))

    if run_z:
        names = require_ze2()
        if names:
            try:
                tables = []
                for name in names:
                    data = build_feature_single(
                        "ze2",
                        name,
                        expected_count=int(expected),
                        contraction_method=contraction_method,
                        feature_method=feature_method,
                        **ze2_kwargs,
                    )
                    tables.append(data)
                st.session_state.feat_ze2_tables = tables
                st.success(f"ZE2 特徵完成（{len(names)} 個）")
            except (FileNotFoundError, ValueError) as exc:
                st.error(str(exc))

    if run_both:
        pair = require_pair()
        if pair:
            delsys_name, txt_names, ze2_names = pair
            try:
                if txt_names:
                    compare = build_feature_compare(
                        delsys_name,
                        txt_names[0],
                        expected_count=int(expected),
                        contraction_method=contraction_method,
                        feature_method=feature_method,
                        apply_bandpass=apply_bandpass_ze1,
                    )
                    st.session_state.feat_delsys = {
                        "feature_method": feature_method,
                        "result": {
                            "filename": compare["delsys"]["filename"],
                            "features": compare["delsys"]["features"],
                            "count": compare["delsys"]["count"],
                            "series": compare["delsys"].get("series"),
                        },
                    }
                    tables = [
                        {
                            "feature_method": feature_method,
                            "result": {
                                "filename": compare["txt"]["filename"],
                                "features": compare["txt"]["features"],
                                "count": compare["txt"]["count"],
                                "series": compare["txt"].get("series"),
                            },
                        }
                    ]
                    for name in txt_names[1:]:
                        tables.append(
                            build_feature_single(
                                "txt",
                                name,
                                expected_count=int(expected),
                                contraction_method=contraction_method,
                                feature_method=feature_method,
                                apply_bandpass=apply_bandpass_ze1,
                            )
                        )
                    st.session_state.feat_txt_tables = tables
                    st.session_state.feat_delta = compare
                    delta_label = f"ZE1：{txt_names[0]}"
                else:
                    compare = build_feature_compare_ze2(
                        delsys_name,
                        ze2_names[0],
                        expected_count=int(expected),
                        contraction_method=contraction_method,
                        feature_method=feature_method,
                        **ze2_kwargs,
                    )
                    st.session_state.feat_delsys = {
                        "feature_method": feature_method,
                        "result": {
                            "filename": compare["delsys"]["filename"],
                            "features": compare["delsys"]["features"],
                            "count": compare["delsys"]["count"],
                            "series": compare["delsys"].get("series"),
                        },
                    }
                    st.session_state.feat_delta = compare
                    delta_label = f"ZE2：{ze2_names[0]}"

                if ze2_names:
                    z_tables = []
                    for name in ze2_names:
                        z_tables.append(
                            build_feature_single(
                                "ze2",
                                name,
                                expected_count=int(expected),
                                contraction_method=contraction_method,
                                feature_method=feature_method,
                                **ze2_kwargs,
                            )
                        )
                    st.session_state.feat_ze2_tables = z_tables
                st.success(f"特徵比對完成（Δ 以 {delta_label}）")
            except (FileNotFoundError, ValueError) as exc:
                st.error(str(exc))

    pages: list[tuple[str, Any, Any]] = []

    if st.session_state.feat_delsys:
        data = st.session_state.feat_delsys

        def _render_delsys(payload=data) -> None:
            method = payload.get("feature_method") or feature_method
            st.dataframe(feature_rows(payload["result"]["features"], method), use_container_width=True)
            series_fig = plot_ttri_series(
                payload["result"].get("series"),
                title=payload["result"].get("filename", "Delsys"),
            )
            if series_fig:
                st.plotly_chart(series_fig, use_container_width=True, config={"displayModeBar": True})

        pages.append(
            (
                _short_tab_label("Delsys", data["result"].get("filename")),
                _render_delsys,
                lambda: clear_feat_result(source="delsys"),
            )
        )

    for data in st.session_state.feat_txt_tables or []:
        fname = data["result"].get("filename")

        def _render_txt(payload=data) -> None:
            method = payload.get("feature_method") or feature_method
            st.dataframe(feature_rows(payload["result"]["features"], method), use_container_width=True)
            series_fig = plot_ttri_series(
                payload["result"].get("series"),
                title=payload["result"].get("filename", "ZE1"),
            )
            if series_fig:
                st.plotly_chart(series_fig, use_container_width=True, config={"displayModeBar": True})

        pages.append(
            (
                _short_tab_label("ZE1", fname),
                _render_txt,
                lambda name=fname: clear_feat_result(source="txt", filename=name),
            )
        )

    for data in st.session_state.feat_ze2_tables or []:
        fname = data["result"].get("filename")

        def _render_ze2(payload=data) -> None:
            method = payload.get("feature_method") or feature_method
            st.dataframe(feature_rows(payload["result"]["features"], method), use_container_width=True)
            series_fig = plot_ttri_series(
                payload["result"].get("series"),
                title=payload["result"].get("filename", "ZE2"),
            )
            if series_fig:
                st.plotly_chart(series_fig, use_container_width=True, config={"displayModeBar": True})

        pages.append(
            (
                _short_tab_label("ZE2", fname),
                _render_ze2,
                lambda name=fname: clear_feat_result(source="ze2", filename=name),
            )
        )

    if pages:
        st.caption("每個檔案一個頁籤；可按「清除此結果」移除圖表。")
        c_clear, _ = st.columns([1, 3])
        with c_clear:
            if st.button("清除全部特徵結果", key="clear_all_feat"):
                st.session_state.feat_delsys = None
                st.session_state.feat_txt_tables = None
                st.session_state.feat_ze2_tables = None
                st.session_state.feat_delta = None
                st.rerun()
        render_result_pages(pages, context="feat")
    else:
        st.info("尚未執行")

    st.subheader("差異對照 Δ")
    delta = st.session_state.feat_delta
    if delta:
        if delta.get("note"):
            st.caption(delta["note"])
        st.dataframe(delta_rows(delta.get("pairs") or []), use_container_width=True)
        if st.button("清除 Δ 對照", key="clear_feat_delta"):
            st.session_state.feat_delta = None
            st.rerun()
    else:
        st.info("執行「一起（含 Δ）」後顯示")

    render_export_panel(context="features")


def render_export_panel(*, context: str) -> None:
    """Download PDF / CSV exports from current session results."""
    has_feat = bool(
        st.session_state.feat_delsys
        or st.session_state.feat_txt_tables
        or st.session_state.feat_ze2_tables
        or st.session_state.feat_delta
    )
    has_contr = bool(st.session_state.contr_delsys or st.session_state.contr_txt or st.session_state.contr_ze2)
    if not has_feat and not has_contr:
        return

    st.markdown("---")
    st.subheader("匯出結果")
    st.caption("可下載 PDF 報告，或 CSV 壓縮檔（可用 Excel 開啟）。")

    meta = {
        "頁籤": "特徵" if context == "features" else "收縮區間",
        "Delsys": st.session_state.selected_delsys or "（未選）",
        "ZE1": ", ".join(st.session_state.selected_txt or []) or "（未選）",
        "ZE2": ", ".join(st.session_state.selected_ze2 or []) or "（未選）",
        "ZE2 fs": st.session_state.get("ze2_fs"),
        "ZE2 mV/count": st.session_state.get("ze2_mv"),
        "ZE1 濾波": "開" if st.session_state.get("apply_bandpass_ze1", True) else "關",
        "ZE2 濾波": "開" if st.session_state.get("apply_bandpass_ze2", True) else "關",
    }
    if st.session_state.feat_delsys:
        meta["特徵方法"] = st.session_state.feat_delsys.get("feature_method") or ""
    if st.session_state.feat_delta:
        meta["收縮判斷"] = st.session_state.feat_delta.get("contraction_method") or ""

    try:
        pdf_bytes = build_results_pdf(
            meta=meta,
            feat_delsys=st.session_state.feat_delsys,
            feat_txt_tables=st.session_state.feat_txt_tables,
            feat_ze2_tables=st.session_state.feat_ze2_tables,
            feat_delta=st.session_state.feat_delta,
            contr_delsys=st.session_state.contr_delsys,
            contr_txt=st.session_state.contr_txt,
            contr_ze2=st.session_state.contr_ze2,
        )
        csv_zip = build_results_csv_zip(
            feat_delsys=st.session_state.feat_delsys,
            feat_txt_tables=st.session_state.feat_txt_tables,
            feat_ze2_tables=st.session_state.feat_ze2_tables,
            feat_delta=st.session_state.feat_delta,
            contr_delsys=st.session_state.contr_delsys,
            contr_txt=st.session_state.contr_txt,
            contr_ze2=st.session_state.contr_ze2,
        )
    except Exception as exc:  # noqa: BLE001 — show export errors in UI
        st.error(f"產生匯出檔失敗：{exc}")
        return

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    c1, c2 = st.columns(2)
    with c1:
        st.download_button(
            "下載 PDF 報告",
            data=pdf_bytes,
            file_name=f"emg_compare_report_{stamp}.pdf",
            mime="application/pdf",
            use_container_width=True,
            key=f"dl_pdf_{context}",
        )
    with c2:
        st.download_button(
            "下載 CSV（ZIP）",
            data=csv_zip,
            file_name=f"emg_compare_tables_{stamp}.zip",
            mime="application/zip",
            use_container_width=True,
            key=f"dl_csv_{context}",
        )


def main() -> None:
    init_state()
    render_sidebar()
    tab1, tab2, tab3 = st.tabs(["波形", "收縮區間", "特徵"])
    with tab1:
        tab_waveform()
    with tab2:
        tab_contractions()
    with tab3:
        tab_features()


main()
