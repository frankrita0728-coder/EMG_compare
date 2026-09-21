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
    shutil.copy2(xlsx, out_dir / "source_list.xlsx")

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

                if purpose == "刮腿毛" and ref_is_txt and exp_is_txt:
                    result = build_feature_compare_txt_pair(
                        ref_path.name,
                        exp_path.name,
                        expected_count=3,
                        contraction_method="ze1_schmitt",
                        feature_method="ttri",
                    )
                elif device_note == "ze2" and ref_is_csv and exp_is_txt:
                    result = build_feature_compare_ze2(
                        ref_path.name,
                        exp_path.name,
                        expected_count=3,
                        contraction_method="ze1_schmitt",
                        feature_method="ttri",
                        ze2_sample_rate=float(ZE2_DEFAULT_FS),
                        ze2_mv_per_count=float(ZE2_MV_PER_COUNT),
                        apply_bandpass=True,
                    )
                elif ref_is_csv and exp_is_txt:
                    result = build_feature_compare(
                        ref_path.name,
                        exp_path.name,
                        expected_count=3,
                        contraction_method="ze1_schmitt",
                        feature_method="ttri",
                    )
                elif ref_is_txt and exp_is_txt:
                    result = build_feature_compare_txt_pair(
                        ref_path.name,
                        exp_path.name,
                        expected_count=3,
                        contraction_method="ze1_schmitt",
                        feature_method="ttri",
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
        summary_row = {
            "row": row_i,
            "status": status,
            "site": site,
            "purpose": purpose,
            "device_note": device_note,
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
            "note": note,
            "json": str(out_json.relative_to(out_dir)) if status == "done" else "",
        }
        if status == "done" and out_json.exists():
            payload = json.loads(out_json.read_text(encoding="utf-8"))
            summary_row["ref_count"] = payload.get("ref_count", "")
            summary_row["exp_count"] = payload.get("exp_count", "")
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
        "| # | 狀態 | 部位 | 目的 | 裝置 | RMS Pearson r | RMS ICC | iEMG Pearson r | iEMG ICC | TTRI RMS r |",
        "|---|------|------|------|------|---------------|---------|----------------|----------|------------|",
    ]
    for r in summary_rows:
        readme_lines.append(
            f"| {r['row']} | {r['status']} | {r['site']} | {r['purpose']} | {r['device_note']} | "
            f"{r['rms_pearson_r']} | {r['rms_icc']} | {r['iemg_pearson_r']} | {r['iemg_icc']} | "
            f"{r['ttri_rms_r']} |"
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

    return out_dir


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
