from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import plotly.graph_objects as go
import streamlit as st

from compare import (
    build_feature_compare,
    build_feature_single,
    build_contraction_single,
    build_waveform_overlay,
    build_waveform_single,
)
from pairing import suggest_for_selection, suggest_pairs
from parsers.delsys import list_delsys_files
from parsers.txt_device import list_txt_files
from paths import DATA_DELSYS, DATA_TXT, ensure_data_dirs
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
        "wave_delsys": None,
        "wave_txt": None,
        "wave_overlay": None,
        "contr_delsys": None,
        "contr_txt": None,
        "feat_delsys": None,
        "feat_txt_tables": None,
        "feat_delta": None,
        "file_nonce": 0,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def refresh_file_lists() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    ensure_data_dirs()
    return list_delsys_files(), list_txt_files()


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
        for key, value in (item.get("txt") or {}).items():
            if key not in {"index"}:
                row[f"T {key}"] = value
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
        st.warning("請先選擇至少一個 TXT")
        return None
    return names


def require_pair() -> tuple[str, list[str]] | None:
    delsys = require_delsys()
    txt = require_txt()
    if not delsys or not txt:
        return None
    return delsys, txt


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
        <p class="brand-sub">Delsys CSV × 自研 TXT</p>
        """,
        unsafe_allow_html=True,
    )

    st.sidebar.markdown("##### 上傳檔案")
    up_delsys = st.sidebar.file_uploader("Delsys CSV", type=["csv"], accept_multiple_files=True, key="up_delsys")
    up_txt = st.sidebar.file_uploader("自研 TXT", type=["txt"], accept_multiple_files=True, key="up_txt")
    if st.sidebar.button("儲存上傳檔案", use_container_width=True):
        saved_d = save_uploads(up_delsys, DATA_DELSYS)
        saved_t = save_uploads(up_txt, DATA_TXT)
        st.session_state.file_nonce += 1
        if saved_d or saved_t:
            st.sidebar.success(f"已存入 {len(saved_d)} CSV、{len(saved_t)} TXT")
        else:
            st.sidebar.info("沒有選到檔案")

    if st.sidebar.button("重新整理", use_container_width=True):
        st.session_state.file_nonce += 1

    delsys_files, txt_files = refresh_file_lists()
    delsys_names = [item["name"] for item in delsys_files]
    txt_names = [item["name"] for item in txt_files]

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

    st.sidebar.markdown("##### 自研 TXT（可多選）")
    if not txt_names:
        st.sidebar.info("尚無 TXT")
        st.session_state.selected_txt = []
    else:
        # Bind via key only — assigning return value + default= breaks multi-select.
        st.session_state.selected_txt = [
            name for name in (st.session_state.selected_txt or []) if name in txt_names
        ]
        st.sidebar.multiselect(
            "選擇 TXT",
            options=txt_names,
            key="selected_txt",
            label_visibility="collapsed",
            help="可同時勾選多個，例如 ExgCh1 + ExgCh2",
        )
        if st.sidebar.button("自動勾選 Ch1+Ch2 配對", use_container_width=True):
            st.session_state.selected_txt = sibling_txt_channels(
                list(st.session_state.selected_txt or []),
                txt_names,
            )
            st.rerun()

    st.sidebar.markdown("##### 自動建議")
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
    st.sidebar.caption(f"Delsys 資料夾：{DATA_DELSYS}")
    st.sidebar.caption(f"TXT 資料夾：{DATA_TXT}")
    st.sidebar.caption(
        f"已選：{st.session_state.selected_delsys or '（無）'} / "
        f"{', '.join(st.session_state.selected_txt or []) or '（無）'}"
    )


def tab_waveform() -> None:
    c1, c2, c3 = st.columns([1.2, 1.2, 1.6])
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

    left, right = st.columns(2)
    with left:
        card_open("Delsys 結果")
        if st.session_state.wave_delsys:
            st.plotly_chart(
                fig_from_trace(
                    st.session_state.wave_delsys,
                    color=DELSYS_COLOR,
                    title=st.session_state.wave_delsys.get("filename", "Delsys"),
                    y_title=y_title,
                ),
                use_container_width=True,
                config={"displayModeBar": False},
            )
        else:
            empty_slot()
        card_close()
    with right:
        card_open("TXT 結果")
        if st.session_state.wave_txt:
            fig = go.Figure()
            for i, trace in enumerate(st.session_state.wave_txt):
                fig.add_trace(
                    go.Scattergl(
                        x=trace["times"],
                        y=trace["values"],
                        mode="lines",
                        name=trace.get("filename"),
                        line={"color": TXT_COLORS[i % len(TXT_COLORS)], "width": 1.2},
                    )
                )
            fig.update_layout(**plot_layout(title="TXT", y_title=y_title))
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        else:
            empty_slot()
        card_close()

    card_open("疊圖結果（兩邊一起）")
    overlay = st.session_state.wave_overlay
    if overlay and overlay.get("overlay"):
        st.plotly_chart(
            fig_overlay(
                overlay["overlay"],
                title=f"波形疊圖（{overlay.get('norm_method')}）",
                y_title=y_title,
            ),
            use_container_width=True,
            config={"displayModeBar": False},
        )
        if overlay.get("note"):
            st.caption(overlay["note"])
    else:
        empty_slot()
    card_close()


def tab_contractions() -> None:
    c1, c2, c3 = st.columns([1.4, 0.8, 1.8])
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

    left, right = st.columns(2)
    with left:
        card_open("Delsys 結果")
        result = st.session_state.contr_delsys
        if result:
            st.plotly_chart(
                fig_contractions(result, color=DELSYS_COLOR, title=result.get("filename", "Delsys")),
                use_container_width=True,
                config={"displayModeBar": False},
            )
            st.dataframe(contractions_to_rows(result.get("contractions") or []), use_container_width=True)
        else:
            empty_slot()
        card_close()
    with right:
        card_open("TXT 結果")
        results = st.session_state.contr_txt
        if results:
            fig = go.Figure()
            all_rows = []
            for i, result in enumerate(results):
                color = TXT_COLORS[i % len(TXT_COLORS)]
                fig.add_trace(
                    go.Scattergl(
                        x=result["times"],
                        y=result["values"],
                        mode="lines",
                        name=result.get("filename"),
                        line={"color": color, "width": 1.2},
                    )
                )
                for item in result.get("contractions") or []:
                    fig.add_vrect(x0=item["start"], x1=item["end"], fillcolor=color, opacity=0.12, line_width=0)
                    row = contractions_to_rows([item])[0]
                    row["file"] = result.get("filename")
                    all_rows.append(row)
            fig.update_layout(**plot_layout(title="TXT 收縮區間", y_title="Norm (robust z)", height=320))
            ys = []
            for result in results:
                ys.extend(result.get("values") or [])
            if ys:
                lo = float(np.percentile(ys, 0.5))
                hi = float(np.percentile(ys, 99.5))
                pad = max(0.5, 0.08 * (hi - lo))
                fig.update_yaxes(range=[lo - pad, hi + pad])
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
            st.dataframe(all_rows, use_container_width=True)
        else:
            empty_slot()
        card_close()

    render_export_panel(context="contractions")


def tab_features() -> None:
    c1, c2, c3, c4 = st.columns([1.2, 1.4, 0.7, 1.6])
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

    left, right = st.columns(2)
    with left:
        st.subheader("Delsys 特徵")
        data = st.session_state.feat_delsys
        if data:
            method = data.get("feature_method") or feature_method
            st.dataframe(feature_rows(data["result"]["features"], method), use_container_width=True)
            series_fig = plot_ttri_series(data["result"].get("series"), title=data["result"].get("filename", "Delsys"))
            if series_fig:
                st.plotly_chart(series_fig, use_container_width=True)
        else:
            st.info("尚未執行")
    with right:
        st.subheader("TXT 特徵")
        tables = st.session_state.feat_txt_tables
        if tables:
            for data in tables:
                method = data.get("feature_method") or feature_method
                st.markdown(f"**{data['result'].get('filename', 'TXT')}**")
                st.dataframe(feature_rows(data["result"]["features"], method), use_container_width=True)
                series_fig = plot_ttri_series(data["result"].get("series"), title=data["result"].get("filename", "TXT"))
                if series_fig:
                    st.plotly_chart(series_fig, use_container_width=True)
        else:
            st.info("尚未執行")

    st.subheader("差異對照 Δ")
    delta = st.session_state.feat_delta
    if delta:
        if delta.get("note"):
            st.caption(delta["note"])
        st.dataframe(delta_rows(delta.get("pairs") or []), use_container_width=True)
    else:
        st.info("執行「兩邊一起」後顯示")

    render_export_panel(context="features")


def render_export_panel(*, context: str) -> None:
    """Download PDF / CSV exports from current session results."""
    has_feat = bool(st.session_state.feat_delsys or st.session_state.feat_txt_tables or st.session_state.feat_delta)
    has_contr = bool(st.session_state.contr_delsys or st.session_state.contr_txt)
    if not has_feat and not has_contr:
        return

    st.markdown("---")
    st.subheader("匯出結果")
    st.caption("可下載 PDF 報告，或 CSV 壓縮檔（可用 Excel 開啟）。")

    meta = {
        "頁籤": "特徵" if context == "features" else "收縮區間",
        "Delsys": st.session_state.selected_delsys or "（未選）",
        "TXT": ", ".join(st.session_state.selected_txt or []) or "（未選）",
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
            feat_delta=st.session_state.feat_delta,
            contr_delsys=st.session_state.contr_delsys,
            contr_txt=st.session_state.contr_txt,
        )
        csv_zip = build_results_csv_zip(
            feat_delsys=st.session_state.feat_delsys,
            feat_txt_tables=st.session_state.feat_txt_tables,
            feat_delta=st.session_state.feat_delta,
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
    tab1, tab2, tab3 = st.tabs(["波形", "收縮區間", "特徵"])
    with tab1:
        tab_waveform()
    with tab2:
        tab_contractions()
    with tab3:
        tab_features()


main()
