from __future__ import annotations

import threading
import webbrowser

from flask import Flask, jsonify, render_template, request

from compare import (
    build_contraction_compare,
    build_contraction_single,
    build_feature_compare,
    build_feature_single,
    build_waveform_compare,
    build_waveform_overlay,
    build_waveform_single,
)
from pairing import extract_tags, suggest_for_selection, suggest_pairs
from parsers.delsys import list_delsys_files
from parsers.txt_device import list_txt_files
from paths import DATA_DELSYS, DATA_TXT, RESOURCE_DIR, ensure_data_dirs

HOST = "127.0.0.1"
PORT = 8080

app = Flask(
    __name__,
    template_folder=str(RESOURCE_DIR / "templates"),
    static_folder=str(RESOURCE_DIR / "static"),
)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/files")
def api_files():
    ensure_data_dirs()
    delsys = list_delsys_files()
    txt = list_txt_files()
    return jsonify(
        {
            "delsys": delsys,
            "txt": txt,
            "paths": {
                "delsys": str(DATA_DELSYS),
                "txt": str(DATA_TXT),
            },
        }
    )


@app.route("/api/tags/<source>/<path:filename>")
def api_tags(source: str, filename: str):
    if source not in {"delsys", "txt"}:
        return jsonify({"error": "未知來源"}), 400
    return jsonify({"filename": filename, "source": source, "tags": extract_tags(filename).as_dict()})


@app.route("/api/suggest")
def api_suggest():
    delsys = list_delsys_files()
    txt = list_txt_files()
    selected_source = (request.args.get("source") or "").strip()
    selected_name = (request.args.get("filename") or "").strip()

    if selected_source and selected_name:
        if selected_source == "delsys":
            items = suggest_for_selection(selected_name, "delsys", txt)
        elif selected_source == "txt":
            items = suggest_for_selection(selected_name, "txt", delsys)
        else:
            return jsonify({"error": "未知來源"}), 400
        return jsonify({"suggestions": items, "mode": "for_selection"})

    return jsonify({"suggestions": suggest_pairs(delsys, txt), "mode": "global"})


@app.route("/api/analyze/waveform", methods=["POST"])
def api_analyze_waveform():
    payload = request.get_json(silent=True) or {}
    source = payload.get("source")
    filename = payload.get("filename")
    method = payload.get("norm_method") or "zscore"
    year = payload.get("year")
    year_i = int(year) if year not in (None, "") else None
    if source not in {"delsys", "txt"} or not filename:
        return jsonify({"error": "請指定 source 與 filename"}), 400
    try:
        return jsonify(
            build_waveform_single(source, filename, norm_method=method, year=year_i)
        )
    except (FileNotFoundError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/api/analyze/contractions", methods=["POST"])
def api_analyze_contractions():
    payload = request.get_json(silent=True) or {}
    source = payload.get("source")
    filename = payload.get("filename")
    expected_count = int(payload.get("expected_count") or 3)
    contraction_method = payload.get("contraction_method") or "rms_peak"
    if source not in {"delsys", "txt"} or not filename:
        return jsonify({"error": "請指定 source 與 filename"}), 400
    try:
        return jsonify(
            build_contraction_single(
                source,
                filename,
                expected_count=expected_count,
                contraction_method=contraction_method,
            )
        )
    except (FileNotFoundError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/api/analyze/features", methods=["POST"])
def api_analyze_features():
    payload = request.get_json(silent=True) or {}
    source = payload.get("source")
    filename = payload.get("filename")
    expected_count = int(payload.get("expected_count") or 3)
    contraction_method = payload.get("contraction_method") or "rms_peak"
    feature_method = payload.get("feature_method") or "spectral"
    if source not in {"delsys", "txt"} or not filename:
        return jsonify({"error": "請指定 source 與 filename"}), 400
    try:
        return jsonify(
            build_feature_single(
                source,
                filename,
                expected_count=expected_count,
                contraction_method=contraction_method,
                feature_method=feature_method,
            )
        )
    except (FileNotFoundError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/api/compare/waveform", methods=["POST"])
def api_compare_waveform():
    payload = request.get_json(silent=True) or {}
    delsys_name = payload.get("delsys")
    txt_name = payload.get("txt")
    txt_names = payload.get("txt_list") or ([] if not txt_name else [txt_name])
    method = payload.get("norm_method") or "zscore"
    align_by_start = payload.get("align_by_start")
    if align_by_start is None:
        align_by_start = True
    align_by_start = bool(align_by_start)

    if not delsys_name or not txt_names:
        return jsonify({"error": "請選擇 Delsys 與至少一個 TXT 檔案"}), 400
    try:
        if len(txt_names) == 1 and payload.get("txt_list") is None:
            return jsonify(
                build_waveform_compare(
                    delsys_name,
                    txt_names[0],
                    norm_method=method,
                    align_by_start=align_by_start,
                )
            )
        return jsonify(
            build_waveform_overlay(
                delsys_name,
                list(txt_names),
                norm_method=method,
                align_by_start=align_by_start,
            )
        )
    except (FileNotFoundError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/api/compare/contractions", methods=["POST"])
def api_compare_contractions():
    payload = request.get_json(silent=True) or {}
    delsys_name = payload.get("delsys")
    txt_name = payload.get("txt")
    expected_count = int(payload.get("expected_count") or 3)
    contraction_method = payload.get("contraction_method") or "rms_peak"
    if not delsys_name or not txt_name:
        return jsonify({"error": "請選擇 Delsys 與 TXT 檔案"}), 400
    try:
        return jsonify(
            build_contraction_compare(
                delsys_name,
                txt_name,
                expected_count=expected_count,
                contraction_method=contraction_method,
            )
        )
    except (FileNotFoundError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/api/compare/features", methods=["POST"])
def api_compare_features():
    payload = request.get_json(silent=True) or {}
    delsys_name = payload.get("delsys")
    txt_name = payload.get("txt")
    expected_count = int(payload.get("expected_count") or 3)
    contraction_method = payload.get("contraction_method") or "rms_peak"
    feature_method = payload.get("feature_method") or "spectral"
    if not delsys_name or not txt_name:
        return jsonify({"error": "請選擇 Delsys 與 TXT 檔案"}), 400
    try:
        return jsonify(
            build_feature_compare(
                delsys_name,
                txt_name,
                expected_count=expected_count,
                contraction_method=contraction_method,
                feature_method=feature_method,
            )
        )
    except (FileNotFoundError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 400


def _open_browser() -> None:
    webbrowser.open(f"http://{HOST}:{PORT}/")


if __name__ == "__main__":
    ensure_data_dirs()
    print(f"EMG Compare 啟動中：http://{HOST}:{PORT}/")
    threading.Timer(1.2, _open_browser).start()
    app.run(host=HOST, port=PORT, debug=True, use_reloader=False)
