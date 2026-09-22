#!/usr/bin/env python3
"""Run comparisons from the ZE1 pair list Excel (裝置比對 / 刮腿毛 / 疲勞)."""

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from compare import (  # noqa: E402
    _attach_correlation_stats,
    build_feature_compare,
    build_feature_compare_ze2,
)
from features import analyze_signal_features, compare_feature_rows  # noqa: E402
from parsers.txt_device import TXT_MV_PER_COUNT, load_txt_emg  # noqa: E402
from parsers.ze2_txt import DEFAULT_SAMPLE_RATE as ZE2_DEFAULT_FS  # noqa: E402
from parsers.ze2_txt import ZE2_MV_PER_COUNT  # noqa: E402

OUT_ROOT = ROOT / "data" / "pairing_results" / "2609-21_ZE1_list"

# Analysis recipe for ZE1 list runs. Fatigue uses 10 contractions; others use 3.
ANALYSIS_CONFIG: dict[str, Any] = {
    "contraction_method": "ze1_schmitt",
    "contraction_method_label": "ZE1 施密特觸發（Schmitt trigger）",
    "feature_method": "ttri",
    "feature_method_label": "TTRI（AEMG + 滑動窗 RMS/iEMG/MPF/MDF）",
    "expected_count_default": 3,
    "expected_count_by_purpose": {
        "裝置比對": 3,
        "刮腿毛": 3,
        "疲勞": 10,
    },
    "agreement_stats": ["Pearson r", "ICC(A,1)"],
    "agreement_scope": "跨收縮區間特徵（同 index 配對）",
    "series_correlation": "TTRI 滑動窗 Pearson r（僅 Delsys/對照收縮區間內）",
    "ze1_scale": f"TXT × {TXT_MV_PER_COUNT} mV/count",
    "ze2_sample_rate_hz": float(ZE2_DEFAULT_FS),
    "ze2_mv_per_count": float(ZE2_MV_PER_COUNT),
    "ze2_bandpass": "20–400 Hz（apply_bandpass=True）",
    "pipeline": {
        "裝置比對_a09_a10": "build_feature_compare(Delsys CSV × ZE1 TXT)",
        "裝置比對_ze2": "build_feature_compare_ze2(Delsys CSV × ZE2 TXT)",
        "刮腿毛": "build_feature_compare_txt_pair(ZE1 TXT × ZE1 TXT)",
        "疲勞": "build_feature_compare(Delsys CSV × ZE1 TXT；expected_count=10)",
    },
}


def expected_count_for(purpose: str) -> int:
    mapping = ANALYSIS_CONFIG.get("expected_count_by_purpose") or {}
    if purpose in mapping:
        return int(mapping[purpose])
    return int(ANALYSIS_CONFIG.get("expected_count_default") or 3)


def _write_analysis_method(out_dir: Path, *, xlsx_name: str) -> None:
    cfg = ANALYSIS_CONFIG
    by_purpose = cfg.get("expected_count_by_purpose") or {}
    purpose_rows = "\n".join(
        f"| {name} | **{count}** |" for name, count in by_purpose.items()
    )
    text = f"""# 分析設定（本批結果用此配方）

來源清單：`{xlsx_name}`

## 參數

| 項目 | 值 |
|------|----|
| 收縮判斷 | `{cfg['contraction_method']}` — {cfg['contraction_method_label']} |
| 特徵計算 | `{cfg['feature_method']}` — {cfg['feature_method_label']} |
| 區間一致性 | {', '.join(cfg['agreement_stats'])}；{cfg['agreement_scope']} |
| 序列相關 | {cfg['series_correlation']} |
| ZE1 換算 | {cfg['ze1_scale']} |
| ZE2 取樣率 | {cfg['ze2_sample_rate_hz']} Hz |
| ZE2 換算 | ×{cfg['ze2_mv_per_count']} mV/count |
| ZE2 濾波 | {cfg['ze2_bandpass']} |

## 預期收縮次數（依實驗目的）

| 實驗目的 | expected_count |
|----------|----------------|
{purpose_rows}
| （其他／未列） | **{cfg['expected_count_default']}** |

> 疲勞分析固定抓 **10 次收縮**；裝置比對／刮腿毛為 **3 次**。

## 各實驗目的呼叫的函式

| 實驗目的 | 管線 |
|----------|------|
| 裝置比對（a09 / a10） | `{cfg['pipeline']['裝置比對_a09_a10']}` |
| 裝置比對（ze2） | `{cfg['pipeline']['裝置比對_ze2']}` |
| 刮腿毛 | `{cfg['pipeline']['刮腿毛']}` |
| 疲勞 | `{cfg['pipeline']['疲勞']}` |

## 輸出欄位說明（summary.csv）

- `rms_pearson_r` / `rms_icc` / `iemg_pearson_r` / `iemg_icc`：收縮區間一致性
- `ttri_rms_r` / `ttri_iemg_r`：TTRI 滑動窗序列 Pearson r
- `ref_count` / `exp_count`：對照組／實驗組偵測到的收縮段數
- `contraction_method` / `feature_method` / `expected_count`：本列實際使用的分析參數
- `fatigue_visible` / `fatigue_ref` / `fatigue_exp`：僅「疲勞」列——這一次能否看出疲勞（綜合／對照／實驗）

## 獨立匯出

重跑後會額外產生 **`analysis_results.xlsx`**（可單獨帶走）：
- 工作表 `總覽`：全列摘要（含一致性、疲勞可視）
- 工作表 `疲勞可視`：僅疲勞列 + 判定依據
- 工作表 `區間特徵`：每段收縮的對照／實驗特徵
- 工作表 `區間一致性`：各指標 Pearson r / ICC

Streamlit「特徵」分頁載入 Excel 清單分析後，也可直接下載同一格式。

## 疲勞可視性（僅 purpose=疲勞）

跨連續收縮看 **MPF／MDF 是否下降**（頻譜向低頻移動＝典型 EMG 疲勞訊號）；
RMS／AEMG 上升為輔助證據。詳細規則見 `FATIGUE_VISIBILITY.md`。

重跑指令：

```bash
python3 scripts/run_ze1_list_compare.py --xlsx <list.xlsx>
```
"""
    (out_dir / "ANALYSIS_METHOD.md").write_text(text, encoding="utf-8")
    (out_dir / "analysis_config.json").write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _slug(*parts: str) -> str:
    text = "_".join(str(p) for p in parts if p)
    return re.sub(r"[^\w\u4e00-\u9fff\-]+", "_", text).strip("_") or "item"


def _index_data_files() -> dict[str, Path]:
    by_lower: dict[str, Path] = {}
    for path in (ROOT / "data").rglob("*"):
        if path.is_file():
            by_lower.setdefault(path.name.lower(), path)
    return by_lower


def resolve_name(name: str | None, index: dict[str, Path]) -> Path | None:
    if not name or not str(name).strip():
        return None
    raw = str(name).strip()
    exact = list((ROOT / "data").rglob(raw))
    if exact:
        return exact[0]
    return index.get(raw.lower())


def build_feature_compare_txt_pair(
    left_name: str,
    right_name: str,
    *,
    expected_count: int = 3,
    contraction_method: str = "ze1_schmitt",
    feature_method: str = "ttri",
) -> dict[str, Any]:
    """ZE1 TXT vs ZE1 TXT (e.g. unshaved vs shaved)."""
    left = load_txt_emg(left_name, for_plot=False)
    right = load_txt_emg(right_name, for_plot=False)
    left_feat = analyze_signal_features(
        left["times"],
        left["values"],
        sample_rate=left["sample_rate"],
        expected_count=expected_count,
        contraction_method=contraction_method,
        feature_method=feature_method,
        source="txt",
    )
    right_feat = analyze_signal_features(
        right["times"],
        right["values"],
        sample_rate=right["sample_rate"],
        expected_count=expected_count,
        contraction_method=contraction_method,
        feature_method=feature_method,
        source="txt",
    )
    pairs = compare_feature_rows(
        left_feat["features"],
        right_feat["features"],
        metrics=left_feat["metrics"],
    )
    result = {
        "mode": "features",
        "device": "ze1_vs_ze1",
        "expected_count": expected_count,
        "contraction_method": contraction_method,
        "feature_method": feature_method,
        "metrics": left_feat["metrics"],
        "delsys": {
            # Reuse left slot as "reference" so existing exporters keep working.
            "filename": left["filename"],
            "signal_name": left["signal_name"],
            "sample_rate": left["sample_rate"],
            "unit": left["unit"],
            "features": left_feat["features"],
            "count": left_feat["count"],
            "role": "reference_ze1",
        },
        "txt": {
            "filename": right["filename"],
            "signal_name": right["signal_name"],
            "sample_rate": right["sample_rate"],
            "unit": right["unit"],
            "features": right_feat["features"],
            "count": right_feat["count"],
            "role": "experiment_ze1",
        },
        "ze1": {
            "filename": right["filename"],
            "signal_name": right["signal_name"],
            "sample_rate": right["sample_rate"],
            "unit": right["unit"],
            "features": right_feat["features"],
            "count": right_feat["count"],
        },
        "pairs": pairs,
        "note": (
            f"ZE1×ZE1 比對（皆 ×{TXT_MV_PER_COUNT} mV/count）；"
            "左欄為對照組 TXT，右欄為實驗組 TXT。"
        ),
    }
    return _attach_correlation_stats(
        result, left=left, right=right, left_feat=left_feat, right_feat=right_feat
    )


def _slim(result: dict[str, Any], meta: dict[str, Any]) -> dict[str, Any]:
    return {
        **meta,
        "contraction_method": result.get("contraction_method"),
        "feature_method": result.get("feature_method"),
        "metrics": result.get("metrics"),
        "pairs": result.get("pairs"),
        "correlation": result.get("correlation"),
        "interval_agreement": result.get("interval_agreement"),
        "fatigue_visibility": result.get("fatigue_visibility"),
        "note": result.get("note"),
        "ref_count": (result.get("delsys") or {}).get("count"),
        "exp_count": (
            (result.get("ze2") or result.get("ze1") or result.get("txt") or {}).get("count")
        ),
    }


def _agreement_map(result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("metric")): row
        for row in (result.get("interval_agreement") or [])
        if isinstance(row, dict) and row.get("metric")
    }


def run_list(xlsx: Path, out_dir: Path) -> Path:
    try:
        import openpyxl
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("需要 openpyxl：pip install openpyxl") from exc

    out_dir.mkdir(parents=True, exist_ok=True)
    # Fresh run: drop previous purpose folders / summaries, keep directory itself.
    for child in list(out_dir.iterdir()):
        if child.is_dir():
            shutil.rmtree(child)
        elif child.name not in {
            "NOTES.md",
            "PROBLEM_THRESHOLDS.md",
            "FATIGUE_VISIBILITY.md",
        }:
            child.unlink(missing_ok=True)
    shutil.copy2(xlsx, out_dir / "source_list.xlsx")
    _write_analysis_method(out_dir, xlsx_name=xlsx.name)

    wb = openpyxl.load_workbook(xlsx, data_only=True)
    ws = wb.active
    index = _index_data_files()

    summary_rows: list[dict[str, Any]] = []

    for row_i, row in enumerate(ws.iter_rows(values_only=True), start=1):
        if row_i == 1:
            continue
        site, ref_name, exp_name, device_note, purpose = (list(row) + [None] * 5)[:5]
        site = str(site or "").strip()
        purpose = str(purpose or "").strip()
        device_note = str(device_note or "").strip().lower()
        ref_raw = str(ref_name).strip() if ref_name else ""
        exp_raw = str(exp_name).strip() if exp_name else ""

        ref_path = resolve_name(ref_raw, index)
        exp_path = resolve_name(exp_raw, index)

        meta = {
            "row": row_i,
            "site": site,
            "purpose": purpose,
            "device_note": device_note,
            "ref_listed": ref_raw,
            "exp_listed": exp_raw,
            "ref_resolved": ref_path.name if ref_path else "",
            "exp_resolved": exp_path.name if exp_path else "",
        }

        purpose_dir = out_dir / _slug(purpose or "unknown")
        site_dir = purpose_dir / _slug(site or "site")
        site_dir.mkdir(parents=True, exist_ok=True)
        out_stem = _slug(f"r{row_i:02d}", device_note or "na", Path(exp_raw).stem[:48] or "exp")
        out_json = site_dir / f"{out_stem}.json"

        status = "pending"
        corr = {}
        agreement: dict[str, dict[str, Any]] = {}
        note = ""

        if not ref_path or not exp_path:
            status = "missing_files"
            note = f"缺檔 ref={bool(ref_path)} exp={bool(exp_path)}"
            (site_dir / f"{out_stem}.missing.txt").write_text(
                json.dumps(meta, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        else:
            try:
                ref_is_csv = ref_path.suffix.lower() == ".csv"
                exp_is_txt = exp_path.suffix.lower() == ".txt"
                ref_is_txt = ref_path.suffix.lower() == ".txt"
                expected = expected_count_for(purpose)
                meta["expected_count"] = expected

                if purpose == "刮腿毛" and ref_is_txt and exp_is_txt:
                    result = build_feature_compare_txt_pair(
                        ref_path.name,
                        exp_path.name,
                        expected_count=expected,
                        contraction_method=str(ANALYSIS_CONFIG["contraction_method"]),
                        feature_method=str(ANALYSIS_CONFIG["feature_method"]),
                    )
                elif device_note == "ze2" and ref_is_csv and exp_is_txt:
                    result = build_feature_compare_ze2(
                        ref_path.name,
                        exp_path.name,
                        expected_count=expected,
                        contraction_method=str(ANALYSIS_CONFIG["contraction_method"]),
                        feature_method=str(ANALYSIS_CONFIG["feature_method"]),
                        ze2_sample_rate=float(ANALYSIS_CONFIG["ze2_sample_rate_hz"]),
                        ze2_mv_per_count=float(ANALYSIS_CONFIG["ze2_mv_per_count"]),
                        apply_bandpass=True,
                    )
                elif ref_is_csv and exp_is_txt:
                    result = build_feature_compare(
                        ref_path.name,
                        exp_path.name,
                        expected_count=expected,
                        contraction_method=str(ANALYSIS_CONFIG["contraction_method"]),
                        feature_method=str(ANALYSIS_CONFIG["feature_method"]),
                    )
                elif ref_is_txt and exp_is_txt:
                    result = build_feature_compare_txt_pair(
                        ref_path.name,
                        exp_path.name,
                        expected_count=expected,
                        contraction_method=str(ANALYSIS_CONFIG["contraction_method"]),
                        feature_method=str(ANALYSIS_CONFIG["feature_method"]),
                    )
                else:
                    raise ValueError(
                        f"不支援的檔案類型組合：{ref_path.suffix} vs {exp_path.suffix}"
                    )

                payload = _slim(result, meta)
                out_json.write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2, default=str),
                    encoding="utf-8",
                )
                corr = result.get("correlation") or {}
                agreement = _agreement_map(result)
                status = "done"
            except Exception as exc:  # noqa: BLE001 - collect per-row failures
                status = f"error:{exc}"
                (site_dir / f"{out_stem}.error.txt").write_text(str(exc), encoding="utf-8")
                note = str(exc)

        rms = agreement.get("rms") or {}
        iemg = agreement.get("iemg") or {}
        fatigue = {}
        if status == "done" and out_json.exists():
            # Will fill below after payload load; placeholder for field order.
            pass
        summary_row = {
            "row": row_i,
            "status": status,
            "site": site,
            "purpose": purpose,
            "device_note": device_note,
            "contraction_method": ANALYSIS_CONFIG["contraction_method"],
            "feature_method": ANALYSIS_CONFIG["feature_method"],
            "expected_count": expected_count_for(purpose),
            "ref": meta["ref_resolved"] or ref_raw,
            "exp": meta["exp_resolved"] or exp_raw,
            "ref_count": "",
            "exp_count": "",
            "rms_pearson_r": rms.get("pearson_r", ""),
            "rms_icc": rms.get("icc", ""),
            "iemg_pearson_r": iemg.get("pearson_r", ""),
            "iemg_icc": iemg.get("icc", ""),
            "ttri_rms_r": corr.get("rms", ""),
            "ttri_iemg_r": corr.get("iemg", ""),
            "fatigue_visible": "",
            "fatigue_ref": "",
            "fatigue_exp": "",
            "note": note,
            "json": str(out_json.relative_to(out_dir)) if status == "done" else "",
        }
        if status == "done" and out_json.exists():
            payload = json.loads(out_json.read_text(encoding="utf-8"))
            summary_row["ref_count"] = payload.get("ref_count", "")
            summary_row["exp_count"] = payload.get("exp_count", "")
            fatigue = payload.get("fatigue_visibility") or {}
            if purpose == "疲勞" and fatigue:
                summary_row["fatigue_visible"] = fatigue.get("visible", "")
                summary_row["fatigue_ref"] = (fatigue.get("ref") or {}).get("visible", "")
                summary_row["fatigue_exp"] = (fatigue.get("exp") or {}).get("visible", "")
        summary_rows.append(summary_row)
        print(f"[{row_i:02d}] {status} | {purpose} | {site} | {device_note}")

    readme_lines = [
        "# 2609-21 ZE1 比對檔案 list 執行結果",
        "",
        f"來源：`{xlsx.name}`",
        "",
        f"- 完成：{sum(1 for r in summary_rows if r['status'] == 'done')}",
        f"- 缺檔：{sum(1 for r in summary_rows if r['status'] == 'missing_files')}",
        f"- 錯誤：{sum(1 for r in summary_rows if str(r['status']).startswith('error'))}",
        "",
        "## 分析設定（本批）",
        "",
        f"- 收縮判斷：`{ANALYSIS_CONFIG['contraction_method']}`（{ANALYSIS_CONFIG['contraction_method_label']}）",
        f"- 特徵計算：`{ANALYSIS_CONFIG['feature_method']}`（{ANALYSIS_CONFIG['feature_method_label']}）",
        f"- 預期收縮：裝置比對／刮腿毛 = **3**；疲勞 = **10**",
        f"- 統計：區間 Pearson r + ICC(A,1)；另算 TTRI 滑動窗 Pearson r",
        f"- 疲勞可視性：跨收縮 MPF/MDF 下降（振幅 RMS/AEMG 上升為輔助）→ 是／弱／否",
        "",
        "詳見 [`ANALYSIS_METHOD.md`](ANALYSIS_METHOD.md) / [`analysis_config.json`](analysis_config.json)。",
        "",
        "| # | 狀態 | 部位 | 目的 | 裝置 | RMS Pearson r | RMS ICC | iEMG Pearson r | iEMG ICC | TTRI RMS r | 疲勞可視 |",
        "|---|------|------|------|------|---------------|---------|----------------|----------|------------|----------|",
    ]
    for r in summary_rows:
        readme_lines.append(
            f"| {r['row']} | {r['status']} | {r['site']} | {r['purpose']} | {r['device_note']} | "
            f"{r['rms_pearson_r']} | {r['rms_icc']} | {r['iemg_pearson_r']} | {r['iemg_icc']} | "
            f"{r['ttri_rms_r']} | {r.get('fatigue_visible') or '—'} |"
        )
    fatigue_rows = [r for r in summary_rows if r.get("purpose") == "疲勞"]
    if fatigue_rows:
        readme_lines.extend(
            [
                "",
                "## 疲勞：這一次能否看出疲勞",
                "",
                "判定規則見 `FATIGUE_VISIBILITY.md`（MPF/MDF 跨收縮下降為主）。",
                "",
                "| # | 部位 | 綜合 | 對照組(Delsys) | 實驗組(TXT) |",
                "|---|------|------|----------------|-------------|",
            ]
        )
        for r in fatigue_rows:
            readme_lines.append(
                f"| {r['row']} | {r['site']} | {r.get('fatigue_visible') or '—'} | "
                f"{r.get('fatigue_ref') or '—'} | {r.get('fatigue_exp') or '—'} |"
            )
    readme_lines.extend(
        [
            "",
            "## 檔案對照",
            "",
            "詳見 `summary.csv` 與各目的資料夾內 JSON。",
            "",
            "- `裝置比對`：Delsys CSV × ZE1/ZE2 TXT",
            "- `刮腿毛`：ZE1 對照 TXT × ZE1 去腿毛 TXT",
            "- `疲勞`：Delsys CSV × ZE1 疲勞 TXT",
            "",
        ]
    )
    (out_dir / "README.md").write_text("\n".join(readme_lines), encoding="utf-8")

    summary_csv = out_dir / "summary.csv"
    fields = list(summary_rows[0].keys()) if summary_rows else []
    with summary_csv.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in summary_rows:
            writer.writerow(row)

    _write_fatigue_visibility_doc(out_dir, summary_rows)

    # Standalone workbook (總覽 / 疲勞可視 / 區間特徵 / 區間一致性) — easy to take away.
    try:
        from pair_list import export_pair_list_results_xlsx

        payloads: list[dict[str, Any]] = []
        for row in summary_rows:
            rel = row.get("json") or ""
            if not rel:
                continue
            jp = out_dir / str(rel)
            if jp.exists():
                payloads.append(json.loads(jp.read_text(encoding="utf-8")))
        xlsx_path = out_dir / "analysis_results.xlsx"
        export_pair_list_results_xlsx(
            summary_rows, result_payloads=payloads, out_path=xlsx_path
        )
        print(f"export: {xlsx_path}")
        try:
            from export_report import build_pair_list_pdf

            pdf_path = out_dir / "analysis_results.pdf"
            pdf_path.write_bytes(
                build_pair_list_pdf(
                    summary_rows,
                    result_payloads=payloads,
                    title="2609-21 ZE1 清單分析結果報告",
                )
            )
            print(f"pdf: {pdf_path}")
        except Exception as pdf_exc:  # noqa: BLE001
            print(f"pdf export skipped: {pdf_exc}")
    except Exception as exc:  # noqa: BLE001
        print(f"standalone export skipped: {exc}")

    return out_dir


def _write_fatigue_visibility_doc(out_dir: Path, summary_rows: list[dict[str, Any]]) -> None:
    """Write FATIGUE_VISIBILITY.md from fatigue summary + JSON evidence."""
    from features import (
        FATIGUE_AMP_PCT_MIN,
        FATIGUE_AMP_R_MIN,
        FATIGUE_MIN_SEGMENTS,
        FATIGUE_SPECTRAL_PCT_MAX,
        FATIGUE_SPECTRAL_R_MAX,
    )

    lines = [
        "# 疲勞可視性：這一次能否看出疲勞",
        "",
        "針對「疲勞」目的的每一組（通常 10 次收縮），依收縮序看特徵趨勢。",
        "",
        "## 判定規則",
        "",
        f"- 至少 **{FATIGUE_MIN_SEGMENTS}** 段收縮才評斷。",
        f"- **頻譜疲勞（主）**：MPF 或 MDF 對收縮序 Pearson r ≤ **{FATIGUE_SPECTRAL_R_MAX}**，"
        f"且前三分之一 → 後三分之一相對變化 ≤ **{FATIGUE_SPECTRAL_PCT_MAX}%**。",
        f"- **振幅輔助**：RMS 或 AEMG r ≥ **{FATIGUE_AMP_R_MIN}** 且變化 ≥ **{FATIGUE_AMP_PCT_MIN}%**。",
        "- **是**：兩項頻譜都達標，或一項頻譜 + 一項振幅。",
        "- **弱／不明顯**：僅一項達標。",
        "- **否**：都未達標。",
        "",
        "## 本批結果",
        "",
        "| # | 部位 | 綜合 | Delsys | TXT | 依據摘要 |",
        "|---|------|------|--------|-----|----------|",
    ]
    for r in summary_rows:
        if r.get("purpose") != "疲勞" or r.get("status") != "done":
            continue
        evidence = ""
        jp = r.get("json")
        if jp:
            path = out_dir / str(jp)
            if path.exists():
                payload = json.loads(path.read_text(encoding="utf-8"))
                fv = payload.get("fatigue_visibility") or {}
                bits: list[str] = []
                for side_key, tag in (("ref", "D"), ("exp", "T")):
                    side = fv.get(side_key) or {}
                    ev = side.get("evidence") or []
                    if ev:
                        bits.append(f"{tag}: " + "; ".join(ev[:2]))
                evidence = " / ".join(bits) if bits else (fv.get("summary") or "")
        lines.append(
            f"| {r['row']} | {r['site']} | {r.get('fatigue_visible') or '—'} | "
            f"{r.get('fatigue_ref') or '—'} | {r.get('fatigue_exp') or '—'} | {evidence} |"
        )
    lines.append("")
    (out_dir / "FATIGUE_VISIBILITY.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--xlsx",
        type=Path,
        default=Path(
            "/home/ubuntu/.cursor/projects/workspace/uploads/2609-21_ZE1____list_f732.xlsx"
        ),
    )
    parser.add_argument("--out", type=Path, default=OUT_ROOT)
    args = parser.parse_args()
    out = run_list(args.xlsx, args.out)
    print(f"output: {out}")
    print(f"summary: {out / 'summary.csv'}")
    print(f"readme: {out / 'README.md'}")


if __name__ == "__main__":
    main()
