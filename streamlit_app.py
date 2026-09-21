from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

import numpy as np
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
from pairing import (
    CHANNEL_HINT_ROWS,
    channel_hint_label,
    extract_tags,
    prefer_recommended_files,
    scan_tag_groups,
    suggest_for_selection,
    suggest_pairs,
    suggest_triple_pairs,
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
    "#ffc857",
    "#e8a838",
    "#f5c542",
    "#d4a017",
    "#ffb347",
    "#e6b422",
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
      }
      div[data-testid="stTabs"] button[data-baseweb="tab"] {
        background: transparent;
        color: var(--muted);
        border-radius: 8px 8px 0 0;
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
      .block-container { max-width: 1400px; }
    </style>
    """,
    unsafe_allow_html=True,
)


def init_state() -> None:
    defaults = {
        "selected_delsys": None,
        "selected_txt": [],
        "selected_ze2": [],
        "ze2_fs": float(ZE2_DEFAULT_FS),
        "ze2_mv": float(ZE2_MV_PER_COUNT),
        "wave_delsys": None,
        "wave_txt": None,
        "wave_overlay": None,
        "contr_delsys": None,
        "contr_txt": None,
        "feat_delsys": None,
        "feat_txt_tables": None,
        "feat_delta": None,
        "corr_result": None,
        "corr_results": None,
        "corr_results_ze1": None,
        "corr_results_ze2": None,
        "file_nonce": 0,
        "contr_method": "ze1_schmitt",
        "feat_contr_method": "ze1_schmitt",
        "corr_contr_method": "ze1_schmitt",
        "feat_method": "ttri",
        "corr_feat_method": "ttri",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value
    # One-time migration so existing browser sessions pick up new UI defaults.
    if not st.session_state.get("_ui_defaults_v2"):
        st.session_state.feat_method = "ttri"
        st.session_state.corr_feat_method = "ttri"
        st.session_state.contr_method = "ze1_schmitt"
        st.session_state.feat_contr_method = "ze1_schmitt"
        st.session_state.corr_contr_method = "ze1_schmitt"
        st.session_state._ui_defaults_v2 = True


def refresh_file_lists() -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    ensure_data_dirs()
    return list_delsys_files(), list_txt_files(), list_ze2_files()


def save_uploads(uploaded_files, dest: Path) -> list[str]:
    ensure_data_dirs()
    dest.mkdir(parents=True, exist_ok=True)
    saved: list[str] = []
    for item in uploaded_files or []:
        target = dest / Path(item.name).name
        target.write_bytes(item.getbuffer())
        saved.append(target.name)
    return saved


def plot_layout(title: str = "", y_title: str = "Normalized", height: int = 320) -> dict[str, Any]:
    return {
        "title": {"text": title, "font": {"size": 14}},
        "height": height,
        "margin": {"t": 48, "r": 16, "b": 40, "l": 48},
        "legend": {"orientation": "h", "y": 1.12},
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
    """Tab label with full basename (max_len kept for compatibility; unused by default)."""
    name = Path(str(filename or "未命名")).name
    if max_len is not None and len(name) > max_len:
        name = name[: max_len - 1] + "…"
    return f"{prefix} · {name}"


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
                if st.button(
                    "清除此結果",
                    key=f"clear_result_{context}_{idx}_{label}",
                    type="secondary",
                ):
                    remove_fn()
                    st.rerun()
            render_fn()


def clear_wave_result(*, source: str, filename: str | None = None) -> None:
    if source == "delsys":
        st.session_state.wave_delsys = None
    elif source == "txt" and filename:
        st.session_state.wave_txt = [
            item for item in (st.session_state.wave_txt or []) if item.get("filename") != filename
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
    elif source == "delta":
        st.session_state.feat_delta = None


def clear_corr_result(*, kind: str, filename: str | None = None) -> None:
    if kind == "ze1" and filename:
        st.session_state.corr_results_ze1 = [
            item
            for item in (st.session_state.corr_results_ze1 or [])
            if ((item.get("ze1") or item.get("txt") or {}).get("filename") != filename)
        ]
    elif kind == "ze2" and filename:
        st.session_state.corr_results_ze2 = [
            item
            for item in (st.session_state.corr_results_ze2 or [])
            if ((item.get("ze2") or {}).get("filename") != filename)
        ]
    st.session_state.corr_results = list(st.session_state.corr_results_ze1 or []) + list(
        st.session_state.corr_results_ze2 or []
    )
    combined = st.session_state.corr_results
    st.session_state.corr_result = combined[0] if combined else None


def y_title_for_norm(method: str) -> str:
    if method == "none":
        return "mV"
    if method == "maxabs":
        return "Norm (maxabs)"
    return "Norm (zscore)"


def fig_from_trace(trace: dict[str, Any], *, color: str, title: str, y_title: str) -> go.Figure:
    fig = go.Figure(
        data=[
            go.Scattergl(
                x=trace["times"],
                y=trace["values"],
                mode="lines",
                name=trace.get("filename") or title,
                line={"color": color, "width": 1.2},
            )
        ]
    )
    fig.update_layout(**plot_layout(title=title or trace.get("filename", ""), y_title=y_title))
    return fig


def fig_overlay(traces: list[dict[str, Any]], *, title: str, y_title: str) -> go.Figure:
    fig = go.Figure()
    txt_i = 0
    for item in traces:
        if item.get("source") == "delsys":
            color = DELSYS_COLOR
            name = f"Delsys · {item['filename']}"
        else:
            color = TXT_COLORS[txt_i % len(TXT_COLORS)]
            name = f"TXT · {item['filename']}"
            txt_i += 1
        fig.add_trace(
            go.Scattergl(
                x=item["times"],
                y=item["values"],
                mode="lines",
                name=name,
                line={"color": color, "width": 1.3},
            )
        )
    fig.update_layout(**plot_layout(title=title, y_title=y_title, height=420))
    return fig


def fig_contractions(result: dict[str, Any], *, color: str, title: str) -> go.Figure:
    fig = go.Figure(
        data=[
            go.Scattergl(
                x=result["times"],
                y=result["values"],
                mode="lines",
                name=result.get("filename") or title,
                line={"color": color, "width": 1.2},
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
        **plot_layout(title=title, y_title="Norm (robust z)", height=320),
        shapes=shapes,
    )
    # Keep rare spikes from dominating the visible scale.
    ys = list(result.get("values") or [])
    if ys:
        lo = float(np.percentile(ys, 0.5))
        hi = float(np.percentile(ys, 99.5))
        pad = max(0.5, 0.08 * (hi - lo))
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
            fig.add_trace(
                go.Scatter(x=times, y=values, mode="lines", name=label, line={"color": color, "width": 1.3}),
                row=1,
                col=1,
            )
    for key, label, color in freq_specs:
        block = series.get(key) or {}
        times = block.get("times") or []
        values = block.get("values") or []
        if times and values:
            fig.add_trace(
                go.Scatter(x=times, y=values, mode="lines", name=label, line={"color": color, "width": 1.3}),
                row=2,
                col=1,
            )
    if not fig.data:
        return None

    short_name = Path(str(title)).name
    if len(short_name) > 42:
        short_name = short_name[:39] + "..."
    aemg = series.get("aemg")
    subtitle = f"{short_name}  ·  AEMG={aemg}" if aemg is not None else short_name

    fig.update_layout(
        title={"text": subtitle, "font": {"size": 13}, "x": 0.0, "xanchor": "left", "y": 0.995, "yanchor": "top"},
        height=660,
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
        right = item.get("ze2") or item.get("txt") or item.get("ze1") or {}
        prefix = "Z2" if item.get("ze2") else "Z1"
        for key, value in right.items():
            if key not in {"index"}:
                row[f"{prefix} {key}"] = value
        rows.append(row)
    return rows


def correlation_rows(correlation: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not correlation:
        return []
    return [{"metric": key, "r": value} for key, value in correlation.items()]


def interval_agreement_rows(rows: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if not rows:
        return []
    out = []
    for item in rows:
        out.append(
            {
                "metric": item.get("metric"),
                "n": item.get("n"),
                "Pearson r": item.get("pearson_r"),
                "ICC(A,1)": item.get("icc"),
            }
        )
    return out


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
        st.warning("請先選擇至少一個 ZE2 檔案")
        return None
    return names


def require_pair() -> tuple[str, list[str]] | None:
    delsys = require_delsys()
    txt = require_txt()
    if not delsys or not txt:
        return None
    return delsys, txt


def require_corr_selection() -> tuple[str, list[str], list[str]] | None:
    """Delsys required; at least one ZE1 or ZE2 selected."""
    delsys = require_delsys()
    if not delsys:
        return None
    ze1 = list(st.session_state.selected_txt or [])
    ze2 = list(st.session_state.selected_ze2 or [])
    if not ze1 and not ze2:
        st.warning("請至少選擇一個 ZE1 或 ZE2 檔案")
        return None
    return delsys, ze1, ze2


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


def render_sidebar() -> None:
    st.sidebar.markdown(
        """
        <p class="brand-kicker">Zentan</p>
        <p class="brand-title">emg-compare.app</p>
        <p class="brand-sub">Delsys × ZE1 × ZE2</p>
        """,
        unsafe_allow_html=True,
    )

    st.sidebar.markdown("##### 上傳檔案")
    up_delsys = st.sidebar.file_uploader("Delsys CSV", type=["csv"], accept_multiple_files=True, key="up_delsys")
    up_txt = st.sidebar.file_uploader("ZE1 TXT", type=["txt"], accept_multiple_files=True, key="up_txt")
    up_ze2 = st.sidebar.file_uploader("ZE2 TXT", type=["txt"], accept_multiple_files=True, key="up_ze2")
    if st.sidebar.button("儲存上傳檔案", use_container_width=True):
        saved_d = save_uploads(up_delsys, DATA_DELSYS)
        saved_t = save_uploads(up_txt, DATA_TXT)
        saved_z = save_uploads(up_ze2, DATA_ZE2)
        st.session_state.file_nonce += 1
        if saved_d or saved_t or saved_z:
            st.sidebar.success(f"已存入 {len(saved_d)} CSV、{len(saved_t)} ZE1、{len(saved_z)} ZE2")
        else:
            st.sidebar.info("沒有選到檔案")

    if st.sidebar.button("重新整理", use_container_width=True):
        st.session_state.file_nonce += 1

    delsys_files, txt_files, ze2_files = refresh_file_lists()
    delsys_names = [item["name"] for item in delsys_files]
    txt_names = [item["name"] for item in txt_files]
    ze2_names = [item["name"] for item in ze2_files]

    st.sidebar.markdown("##### Delsys CSV")
    if not delsys_names:
        st.sidebar.info("尚無 CSV")
        st.session_state.selected_delsys = None
    else:
        if st.session_state.selected_delsys not in delsys_names:
            st.session_state.selected_delsys = delsys_names[0]
        st.sidebar.radio(
            "選擇 Delsys",
            delsys_names,
            key="selected_delsys",
            label_visibility="collapsed",
        )

    st.sidebar.markdown("##### ZE1 TXT（可多選）")
    if not txt_names:
        st.sidebar.info("尚無 ZE1")
        st.session_state.selected_txt = []
    else:
        st.session_state.selected_txt = [
            name for name in (st.session_state.selected_txt or []) if name in txt_names
        ]
        st.sidebar.multiselect(
            "選擇 ZE1",
            options=txt_names,
            key="selected_txt",
            label_visibility="collapsed",
            help="可同時勾選多個，例如 ExgCh1 + ExgCh2",
        )
        if st.sidebar.button("自動勾選 ZE1 Ch1+Ch2 配對", use_container_width=True):
            st.session_state.selected_txt = sibling_txt_channels(
                list(st.session_state.selected_txt or []),
                txt_names,
            )
            st.rerun()

    st.sidebar.markdown("##### ZE2 TXT（可多選）")
    if not ze2_names:
        st.sidebar.info("尚無 ZE2")
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
        )
        st.sidebar.number_input("ZE2 取樣率 (Hz)", min_value=100.0, max_value=5000.0, value=float(st.session_state.ze2_fs), key="ze2_fs")
        st.sidebar.number_input(
            "ZE2 mV/count",
            min_value=1e-8,
            max_value=1.0,
            value=float(st.session_state.ze2_mv),
            format="%.8f",
            key="ze2_mv",
        )

    st.sidebar.markdown("##### 通道建議（依部位）")
    st.sidebar.caption("ZE2 與 ZE1 相反")
    st.sidebar.dataframe(list(CHANNEL_HINT_ROWS), hide_index=True, use_container_width=True)

    # If current ZE1/ZE2 picks carry site tags, remind which channel to keep.
    hint_sources: list[str] = []
    for name in list(st.session_state.selected_txt or [])[:1]:
        tags = extract_tags(name)
        label = channel_hint_label(tags.side, tags.muscle)
        if label:
            hint_sources.append(f"依目前 ZE1：{label}")
    for name in list(st.session_state.selected_ze2 or [])[:1]:
        tags = extract_tags(name)
        label = channel_hint_label(tags.side, tags.muscle)
        if label:
            hint_sources.append(f"依目前 ZE2：{label}")
    if st.session_state.selected_delsys:
        tags = extract_tags(st.session_state.selected_delsys)
        label = channel_hint_label(tags.side, tags.muscle)
        if label:
            hint_sources.append(f"依目前 Delsys：{label}")
    for line in hint_sources[:2]:
        st.sidebar.info(line)

    if (st.session_state.selected_txt or st.session_state.selected_ze2) and (
        st.sidebar.button("依通道建議篩選目前選取", use_container_width=True)
    ):
        if st.session_state.selected_txt:
            st.session_state.selected_txt = prefer_recommended_files(
                list(st.session_state.selected_txt), "ze1"
            )
        if st.session_state.selected_ze2:
            st.session_state.selected_ze2 = prefer_recommended_files(
                list(st.session_state.selected_ze2), "ze2"
            )
        st.rerun()

    st.sidebar.markdown("##### 自動建議（Delsys ↔ ZE1）")
    if st.session_state.selected_delsys:
        raw_suggestions = suggest_for_selection(st.session_state.selected_delsys, "delsys", txt_files)
        suggestions = [
            {
                "delsys": st.session_state.selected_delsys,
                "txt": item["name"],
                "score": item.get("score", 0),
            }
            for item in raw_suggestions
        ]
    elif st.session_state.selected_txt:
        raw_suggestions = suggest_for_selection(st.session_state.selected_txt[0], "txt", delsys_files)
        suggestions = [
            {
                "delsys": item["name"],
                "txt": st.session_state.selected_txt[0],
                "score": item.get("score", 0),
            }
            for item in raw_suggestions
        ]
    else:
        suggestions = suggest_pairs(delsys_files, txt_files)

    if not suggestions:
        st.sidebar.caption("尚無建議")
    else:
        for item in suggestions[:8]:
            delsys_name = item.get("delsys")
            txt_name = item.get("txt")
            label = f"{delsys_name} ↔ {txt_name}（{item.get('score', 0)}）"
            if st.sidebar.button(label, key=f"sug_{delsys_name}_{txt_name}", use_container_width=True):
                st.session_state.selected_delsys = delsys_name
                st.session_state.selected_txt = sibling_txt_channels(
                    [txt_name] if txt_name else [],
                    txt_names,
                )
                st.rerun()

    st.sidebar.divider()
    st.sidebar.caption(f"Delsys：{DATA_DELSYS}")
    st.sidebar.caption(f"ZE1：{DATA_TXT}")
    st.sidebar.caption(f"ZE2：{DATA_ZE2}")
    st.sidebar.caption(
        f"已選 Delsys：{st.session_state.selected_delsys or '（無）'} / "
        f"ZE1：{', '.join(st.session_state.selected_txt or []) or '（無）'} / "
        f"ZE2：{', '.join(st.session_state.selected_ze2 or []) or '（無）'}"
    )


def tab_waveform() -> None:
    c1, c2, c3 = st.columns([1.2, 1.2, 1.6])
    with c1:
        norm_method = st.selectbox(
            "正規化",
            options=["zscore", "maxabs", "none"],
            index=2,
            format_func=lambda x: {
                "zscore": "Z-score",
                "maxabs": "Max-abs",
                "none": "原始值（不正規化）",
            }[x],
        )
    with c2:
        align_by_start = st.checkbox("依起始時間對齊", value=True)
    with c3:
        b1, b2, b3 = st.columns(3)
        run_d = b1.button("執行 Delsys", use_container_width=True)
        run_t = b2.button("執行 TXT", use_container_width=True)
        run_both = b3.button("兩邊一起（疊圖）", type="primary", use_container_width=True)

    y_title = y_title_for_norm(norm_method)

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
                    data = build_waveform_single("txt", name, norm_method=norm_method)
                    traces.append(data["trace"])
                st.session_state.wave_txt = traces
                st.success(f"TXT 波形完成：{len(names)} 個")
            except (FileNotFoundError, ValueError) as exc:
                st.error(str(exc))

    if run_both:
        pair = require_pair()
        if pair:
            delsys_name, txt_names = pair
            try:
                data = build_waveform_overlay(
                    delsys_name,
                    txt_names,
                    norm_method=norm_method,
                    align_by_start=align_by_start,
                )
                st.session_state.wave_delsys = data["delsys"]
                st.session_state.wave_txt = data["txt_list"]
                st.session_state.wave_overlay = data
                st.success("疊圖完成")
            except (FileNotFoundError, ValueError) as exc:
                st.error(str(exc))

    pages: list[tuple[str, Any, Any]] = []

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

    if pages:
        st.caption("每個檔案／結果一個頁籤；可按「清除此結果」移除圖表。")
        c_clear, _ = st.columns([1, 3])
        with c_clear:
            if st.button("清除全部波形結果", key="clear_all_wave"):
                st.session_state.wave_delsys = None
                st.session_state.wave_txt = None
                st.session_state.wave_overlay = None
                st.rerun()
        render_result_pages(pages, context="wave")
    else:
        empty_slot()


def tab_contractions() -> None:
    c1, c2, c3 = st.columns([1.4, 0.8, 1.8])
    with c1:
        contraction_method = st.selectbox(
            "收縮判斷",
            options=["rms_peak", "ze1_schmitt"],
            index=1,
            format_func=lambda x: {
                "rms_peak": "RMS 峰值法（現有）",
                "ze1_schmitt": "ZE1 施密特觸發",
            }[x],
            key="contr_method",
        )
    with c2:
        expected = st.number_input("預期次數", min_value=1, max_value=10, value=3, key="contr_expected")
    with c3:
        b1, b2, b3 = st.columns(3)
        run_d = b1.button("執行 Delsys", key="contr_d", use_container_width=True)
        run_t = b2.button("執行 TXT", key="contr_t", use_container_width=True)
        run_both = b3.button("兩邊一起", key="contr_both", type="primary", use_container_width=True)

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

    if run_t or run_both:
        names = require_txt()
        if names:
            try:
                results = []
                for name in names:
                    data = build_contraction_single(
                        "txt",
                        name,
                        expected_count=int(expected),
                        contraction_method=contraction_method,
                    )
                    results.append(data["result"])
                st.session_state.contr_txt = results
            except (FileNotFoundError, ValueError) as exc:
                st.error(str(exc))

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

    if pages:
        st.caption("每個檔案一個頁籤；可按「清除此結果」移除圖表。")
        c_clear, _ = st.columns([1, 3])
        with c_clear:
            if st.button("清除全部收縮結果", key="clear_all_contr"):
                st.session_state.contr_delsys = None
                st.session_state.contr_txt = None
                st.rerun()
        render_result_pages(pages, context="contr")
    else:
        empty_slot()

    render_export_panel(context="contractions")


def tab_features() -> None:
    c1, c2, c3, c4 = st.columns([1.2, 1.4, 0.7, 1.6])
    with c1:
        contraction_method = st.selectbox(
            "收縮判斷",
            options=["rms_peak", "ze1_schmitt"],
            index=1,
            format_func=lambda x: {
                "rms_peak": "RMS 峰值法（現有）",
                "ze1_schmitt": "ZE1 施密特觸發",
            }[x],
            key="feat_contr_method",
        )
    with c2:
        feature_method = st.selectbox(
            "特徵計算",
            options=["ttri", "spectral"],
            format_func=lambda x: {
                "spectral": "Spectral（iEMG/RMS/MDF/MPF）",
                "ttri": "TTRI / ZE1（AEMG + 滑動窗）",
            }[x],
            key="feat_method",
        )
    with c3:
        expected = st.number_input("預期次數", min_value=1, max_value=10, value=3, key="feat_expected")
    with c4:
        b1, b2, b3 = st.columns(3)
        run_d = b1.button("執行 Delsys", key="feat_d", use_container_width=True)
        run_t = b2.button("執行 TXT", key="feat_t", use_container_width=True)
        run_both = b3.button("兩邊一起（含 Δ）", key="feat_both", type="primary", use_container_width=True)

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
                    )
                    tables.append(data)
                st.session_state.feat_txt_tables = tables
                st.success(f"TXT 特徵完成（{len(names)} 個）")
            except (FileNotFoundError, ValueError) as exc:
                st.error(str(exc))

    if run_both:
        pair = require_pair()
        if pair:
            delsys_name, txt_names = pair
            try:
                compare = build_feature_compare(
                    delsys_name,
                    txt_names[0],
                    expected_count=int(expected),
                    contraction_method=contraction_method,
                    feature_method=feature_method,
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
                    extra = build_feature_single(
                        "txt",
                        name,
                        expected_count=int(expected),
                        contraction_method=contraction_method,
                        feature_method=feature_method,
                    )
                    tables.append(extra)
                st.session_state.feat_txt_tables = tables
                st.session_state.feat_delta = compare
                st.success(f"特徵比對完成（Δ 以第一個 TXT：{txt_names[0]}）")
            except (FileNotFoundError, ValueError) as exc:
                st.error(str(exc))

    pages: list[tuple[str, Any, Any]] = []
    data = st.session_state.feat_delsys
    if data:
        method = data.get("feature_method") or feature_method

        def _render_delsys(d=data, m=method) -> None:
            st.dataframe(feature_rows(d["result"]["features"], m), use_container_width=True)
            series_fig = plot_ttri_series(d["result"].get("series"), title=d["result"].get("filename", "Delsys"))
            if series_fig:
                st.plotly_chart(series_fig, use_container_width=True, config={"displayModeBar": True})

        pages.append(
            (
                _short_tab_label("Delsys", data["result"].get("filename")),
                _render_delsys,
                lambda: clear_feat_result(source="delsys"),
            )
        )

    for i, data in enumerate(st.session_state.feat_txt_tables or []):
        method = data.get("feature_method") or feature_method
        fname = data["result"].get("filename")

        def _render_txt(d=data, m=method) -> None:
            st.dataframe(feature_rows(d["result"]["features"], m), use_container_width=True)
            series_fig = plot_ttri_series(d["result"].get("series"), title=d["result"].get("filename", "ZE1"))
            if series_fig:
                st.plotly_chart(series_fig, use_container_width=True, config={"displayModeBar": True})

        pages.append(
            (
                _short_tab_label("ZE1", fname),
                _render_txt,
                lambda name=fname: clear_feat_result(source="txt", filename=name),
            )
        )

    delta = st.session_state.feat_delta
    if delta:

        def _render_delta(d=delta) -> None:
            if d.get("note"):
                st.caption(d["note"])
            st.dataframe(delta_rows(d.get("pairs") or []), use_container_width=True)
            st.caption("相關係數／ICC 請到「相關係數」分頁執行與查看。")

        pages.append(("差異 Δ", _render_delta, lambda: clear_feat_result(source="delta")))

    if pages:
        st.caption("每個檔案／結果一個頁籤；可按「清除此結果」移除。")
        c_clear, _ = st.columns([1, 3])
        with c_clear:
            if st.button("清除全部特徵結果", key="clear_all_feat"):
                st.session_state.feat_delsys = None
                st.session_state.feat_txt_tables = None
                st.session_state.feat_delta = None
                st.rerun()
        render_result_pages(pages, context="feat")
    else:
        empty_slot()

    render_export_panel(context="features")


def _render_correlation_block(result: dict[str, Any], *, device_label: str) -> None:
    delsys_name = (result.get("delsys") or {}).get("filename") or ""
    device = result.get("ze2") or result.get("ze1") or result.get("txt") or {}
    device_name = device.get("filename") or ""
    n_intervals = min(
        int((result.get("delsys") or {}).get("count") or 0),
        int(device.get("count") or 0),
    )
    st.markdown(f"#### {device_label}：`{device_name}`  vs  Delsys `{delsys_name}`")
    if result.get("note"):
        st.caption(result["note"])

    agreement = result.get("interval_agreement") or []
    if agreement:
        st.markdown("**收縮區間一致性（Pearson r / ICC）**")
        st.caption(
            f"跨 {n_intervals} 段收縮特徵（同 index 配對）。"
            " Pearson \\(r\\)：同向變化；ICC(A,1)：絕對一致性。"
            " 公式見本頁上方「怎麼算」。"
        )
        st.dataframe(interval_agreement_rows(agreement), use_container_width=True)
    else:
        st.warning("沒有收縮區間一致性結果。")

    corr = result.get("correlation") or {}
    if corr:
        window = result.get("correlation_window") or {}
        w_l = window.get("window_l", 157)
        ov = window.get("overlap", 79)
        st.markdown("**TTRI 滑動窗相關係數（Pearson r）**")
        st.caption(
            f"window_l={w_l}, overlap={ov}；僅 Delsys {n_intervals} 段收縮區間內的點。"
        )
        st.dataframe(correlation_rows(corr), use_container_width=True)
    else:
        st.warning("沒有 TTRI 滑動窗相關係數結果。")

    with st.expander(f"對照用特徵表（Δ）— {device_label} {device_name}", expanded=False):
        st.dataframe(delta_rows(result.get("pairs") or []), use_container_width=True)


def tab_correlation() -> None:
    st.caption(
        "依側邊欄選取的檔案，分別做 **Delsys × ZE1** 與 **Delsys × ZE2** 相關／ICC 分析。"
    )
    with st.expander("收縮一致性／相關係數怎麼算（公式）", expanded=True):
        st.markdown(
            """
**資料怎麼配對**

- 每個收縮區間（第 1、2、3… 段）各算一組特徵（如 RMS、iEMG、MPF、MDF、AEMG）。
- Delsys 與 ZE1／ZE2 **同一段 index** 配成一對；有效對數為 \\(n\\)（至少 2 段才有相關）。

---

**1. Pearson \\(r\\)（同向變化）**

對某一特徵，令 Delsys 值為 \\(x_i\\)、裝置值為 \\(y_i\\)（\\(i=1\\ldots n\\)）：

\\[
r = \\frac{\\sum_{i=1}^{n}(x_i-\\bar{x})(y_i-\\bar{y})}
{\\sqrt{\\sum_{i=1}^{n}(x_i-\\bar{x})^2}\\;\\sqrt{\\sum_{i=1}^{n}(y_i-\\bar{y})^2}}
\\]

- 範圍約 \\([-1,1]\\)；接近 1＝兩裝置同向變化。
- 只看相對變化，**不要求數值一樣大**。
- 任一邊標準差為 0（各段數值幾乎相同）→ 回傳空白。

---

**2. ICC(A,1)／ICC(2,1)（絕對一致性）**

McGraw & Wong：**two-way random effects、single measurement、absolute agreement**。

把 \\((x_i,y_i)\\) 當成 \\(n\\) 個目標 × 2 個評分者（Delsys / 裝置）：

\\[
\\mathrm{ICC}(A,1)=\\frac{MS_B - MS_E}
{MS_B + (k-1)MS_E + \\dfrac{k}{n}(MS_R - MS_E)}
\\]

其中 \\(k=2\\)，\\(MS_B\\)=目標間均方，\\(MS_R\\)=評分者間均方，\\(MS_E\\)=誤差均方。

- 接近 1＝兩裝置數值也接近（不只同向）。
- 可比 Pearson 更嚴；一致性差時可能略為負值。

---

**3. TTRI 滑動窗 Pearson \\(r\\)**（下方另一張表）

- 在 **Delsys 收縮區間內** 的滑動窗序列（RMS／iEMG／MPF／MDF）對齊後算 Pearson \\(r\\)。
- 與「收縮區間一致性」不同：那是 **每段一個摘要值**；這是 **區間內時間序列**。
            """
        )

    delsys_files, ze1_files, ze2_files = refresh_file_lists()
    selected_delsys = st.session_state.selected_delsys
    selected_ze1 = list(st.session_state.selected_txt or [])
    selected_ze2 = list(st.session_state.selected_ze2 or [])
    st.info(
        f"**Delsys：** `{selected_delsys or '（未選）'}`　｜　"
        f"**ZE1：** {', '.join(f'`{n}`' for n in selected_ze1) if selected_ze1 else '（未選）'}　｜　"
        f"**ZE2：** {', '.join(f'`{n}`' for n in selected_ze2) if selected_ze2 else '（未選）'}"
    )

    with st.expander("自動掃描可配對組合（Delsys / ZE1 / ZE2）", expanded=True):
        triples = suggest_triple_pairs(delsys_files, ze1_files, ze2_files, limit=50)
        groups = scan_tag_groups(delsys_files, ze1_files, ze2_files)
        st.caption(
            f"資料庫目前：Delsys {len(delsys_files)}、ZE1 {len(ze1_files)}、ZE2 {len(ze2_files)}。"
            " 一對一：ZE1 需同場次碼；ZE2 只要同受試者／肌肉／側即可與 Delsys 比對。"
        )
        st.markdown("**通道建議（ZE2 與 ZE1 相反）**")
        st.dataframe(list(CHANNEL_HINT_ROWS), hide_index=True, use_container_width=True)
        if groups:
            st.markdown("**依標籤分組（受試者／肌肉／側／日期）**")
            group_rows = [
                {
                    "完整度": g["completeness"],
                    "受試者": g["subject"],
                    "肌肉": g["muscle"],
                    "側": g["side"],
                    "場次": g.get("session") or "—",
                    "日期": g.get("date") or "—",
                    "Delsys數": g["n_delsys"],
                    "ZE1數": g["n_ze1"],
                    "ZE2數": g["n_ze2"],
                    "ZE1建議Ch": g.get("ze1_channel_hint") or "—",
                    "ZE2建議Ch": g.get("ze2_channel_hint") or "—",
                }
                for g in groups[:30]
            ]
            st.dataframe(group_rows, use_container_width=True)
            st.markdown("**一鍵套用分組選取（優先建議通道）**")
            for idx, g in enumerate(groups[:12]):
                hint = g.get("channel_hint") or ""
                sess = g.get("session") or g.get("date") or "—"
                label = (
                    f"[{g['completeness']}] {g['subject']}/{g['muscle']}/{g['side']}/{sess} "
                    f"(D{g['n_delsys']} Z1:{g['n_ze1']} Z2:{g['n_ze2']})"
                    + (f"｜{hint}" if hint else "")
                )
                if st.button(label, key=f"corr_group_{idx}", use_container_width=True):
                    if g["delsys"]:
                        st.session_state.selected_delsys = g["delsys"][0]
                    if g["ze1"]:
                        st.session_state.selected_txt = list(
                            g.get("ze1_preferred") or prefer_recommended_files(g["ze1"], "ze1")
                        )
                    if g["ze2"]:
                        st.session_state.selected_ze2 = list(
                            g.get("ze2_preferred") or prefer_recommended_files(g["ze2"], "ze2")
                        )
                    st.rerun()
        if triples:
            st.markdown("**建議配對（可一鍵套用選取）**")
            for idx, item in enumerate(triples[:20]):
                hint = item.get("channel_hint") or ""
                label = (
                    f"[{item['completeness']}] score={item['score']}｜"
                    f"D:{item.get('delsys') or '—'} × "
                    f"ZE1:{item.get('ze1') or '—'} × "
                    f"ZE2:{item.get('ze2') or '—'}"
                    + (f"｜{hint}" if hint else f"｜{item.get('reason') or ''}")
                )
                if st.button(label, key=f"corr_triple_{idx}", use_container_width=True):
                    if item.get("delsys"):
                        st.session_state.selected_delsys = item["delsys"]
                    if item.get("ze1"):
                        st.session_state.selected_txt = prefer_recommended_files(
                            [item["ze1"]], "ze1"
                        )
                    if item.get("ze2"):
                        st.session_state.selected_ze2 = prefer_recommended_files(
                            [item["ze2"]], "ze2"
                        )
                    st.rerun()
        else:
            st.warning("目前掃不到可配對組合。請確認 data/delsys、data/txt、data/ZE2_txt 已放檔。")

    c1, c2, c3, c4 = st.columns([1.2, 1.4, 0.7, 1.4])
    with c1:
        contraction_method = st.selectbox(
            "收縮判斷",
            options=["rms_peak", "ze1_schmitt"],
            index=1,
            format_func=lambda x: {
                "rms_peak": "RMS 峰值法（現有）",
                "ze1_schmitt": "ZE1 施密特觸發",
            }[x],
            key="corr_contr_method",
        )
    with c2:
        feature_method = st.selectbox(
            "特徵計算",
            options=["ttri", "spectral"],
            format_func=lambda x: {
                "spectral": "Spectral（iEMG/RMS/MDF/MPF）",
                "ttri": "TTRI / ZE1（AEMG + 滑動窗）",
            }[x],
            key="corr_feat_method",
        )
    with c3:
        expected = st.number_input("預期次數", min_value=1, max_value=10, value=3, key="corr_expected")
    with c4:
        b_run, b_clear = st.columns(2)
        run_corr = b_run.button("執行相關分析", key="corr_run", type="primary", use_container_width=True)
        clear_corr = b_clear.button("清除結果", key="corr_clear", use_container_width=True)

    if clear_corr:
        st.session_state.corr_result = None
        st.session_state.corr_results = None
        st.session_state.corr_results_ze1 = None
        st.session_state.corr_results_ze2 = None
        st.rerun()

    if run_corr:
        selection = require_corr_selection()
        if selection:
            delsys_name, ze1_names, ze2_names = selection
            try:
                ze1_results = []
                for name in ze1_names:
                    ze1_results.append(
                        build_feature_compare(
                            delsys_name,
                            name,
                            expected_count=int(expected),
                            contraction_method=contraction_method,
                            feature_method=feature_method,
                        )
                    )
                ze2_results = []
                for name in ze2_names:
                    ze2_results.append(
                        build_feature_compare_ze2(
                            delsys_name,
                            name,
                            expected_count=int(expected),
                            contraction_method=contraction_method,
                            feature_method=feature_method,
                            ze2_sample_rate=float(st.session_state.get("ze2_fs") or ZE2_DEFAULT_FS),
                            ze2_mv_per_count=float(st.session_state.get("ze2_mv") or ZE2_MV_PER_COUNT),
                            apply_bandpass=True,
                        )
                    )
                st.session_state.corr_results_ze1 = ze1_results
                st.session_state.corr_results_ze2 = ze2_results
                st.session_state.corr_results = ze1_results + ze2_results
                st.session_state.corr_result = (ze1_results or ze2_results or [None])[0]
                st.success(
                    f"相關分析完成：Delsys「{delsys_name}」× "
                    f"ZE1 {len(ze1_results)} 個、ZE2 {len(ze2_results)} 個"
                )
            except (FileNotFoundError, ValueError, ImportError) as exc:
                st.error(str(exc))

    ze1_results = list(st.session_state.corr_results_ze1 or [])
    ze2_results = list(st.session_state.corr_results_ze2 or [])
    if not ze1_results and not ze2_results:
        st.info("請選取 Delsys，並至少選 ZE1 或 ZE2，再按「執行相關分析」。也可先用上方自動配對一鍵套用。")
        return

    st.caption(
        f"參考 Delsys：`{selected_delsys or (ze1_results or ze2_results)[0].get('delsys', {}).get('filename', '')}`"
        "　｜　每個配對結果一個頁籤。"
    )

    pages: list[tuple[str, Any, Any]] = []
    for result in ze1_results:
        device = result.get("ze1") or result.get("txt") or {}
        fname = device.get("filename")

        def _render_ze1(res=result) -> None:
            _render_correlation_block(res, device_label="ZE1")

        pages.append(
            (
                _short_tab_label("ZE1", fname),
                _render_ze1,
                lambda name=fname: clear_corr_result(kind="ze1", filename=name),
            )
        )
    for result in ze2_results:
        device = result.get("ze2") or {}
        fname = device.get("filename")

        def _render_ze2(res=result) -> None:
            _render_correlation_block(res, device_label="ZE2")

        pages.append(
            (
                _short_tab_label("ZE2", fname),
                _render_ze2,
                lambda name=fname: clear_corr_result(kind="ze2", filename=name),
            )
        )

    render_result_pages(pages, context="corr")
    render_export_panel(context="correlation")


def render_export_panel(*, context: str) -> None:
    """Download PDF / CSV exports from current session results."""
    corr = st.session_state.get("corr_result")
    has_feat = bool(
        st.session_state.feat_delsys
        or st.session_state.feat_txt_tables
        or st.session_state.feat_delta
        or corr
    )
    has_contr = bool(st.session_state.contr_delsys or st.session_state.contr_txt)
    if not has_feat and not has_contr:
        return

    st.markdown("---")
    st.subheader("匯出結果")
    st.caption("可下載 PDF 報告，或 CSV 壓縮檔（可用 Excel 開啟）。")

    page_label = {
        "features": "特徵",
        "contractions": "收縮區間",
        "correlation": "相關係數",
    }.get(context, context)
    meta = {
        "頁籤": page_label,
        "Delsys": st.session_state.selected_delsys or "（未選）",
        "ZE1": ", ".join(st.session_state.selected_txt or []) or "（未選）",
        "ZE2": ", ".join(st.session_state.selected_ze2 or []) or "（未選）",
    }
    if st.session_state.feat_delsys:
        meta["特徵方法"] = st.session_state.feat_delsys.get("feature_method") or ""
    if corr:
        meta["相關特徵方法"] = corr.get("feature_method") or ""
        meta["相關收縮判斷"] = corr.get("contraction_method") or ""
    elif st.session_state.feat_delta:
        meta["收縮判斷"] = st.session_state.feat_delta.get("contraction_method") or ""

    # Prefer dedicated correlation result for export when on that tab.
    feat_delta = corr if context == "correlation" and corr else st.session_state.feat_delta

    try:
        pdf_bytes = build_results_pdf(
            meta=meta,
            feat_delsys=st.session_state.feat_delsys,
            feat_txt_tables=st.session_state.feat_txt_tables,
            feat_delta=feat_delta,
            contr_delsys=st.session_state.contr_delsys,
            contr_txt=st.session_state.contr_txt,
        )
        csv_zip = build_results_csv_zip(
            feat_delsys=st.session_state.feat_delsys,
            feat_txt_tables=st.session_state.feat_txt_tables,
            feat_delta=feat_delta,
            contr_delsys=st.session_state.contr_delsys,
            contr_txt=st.session_state.contr_txt,
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
    tab1, tab2, tab3, tab4 = st.tabs(["波形", "收縮區間", "特徵", "相關係數"])
    with tab1:
        tab_waveform()
    with tab2:
        tab_contractions()
    with tab3:
        tab_features()
    with tab4:
        tab_correlation()


main()