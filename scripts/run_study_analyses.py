#!/usr/bin/env python3
"""Run study analyses: device compare (a09/a10/ZE2 vs Delsys) and shave compare."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from compare import build_feature_compare, build_feature_compare_ze2
from pairing import plan_device_compares, plan_shave_compares
from parsers.delsys import list_delsys_files
from parsers.txt_device import list_txt_files
from parsers.ze2_txt import DEFAULT_SAMPLE_RATE as ZE2_DEFAULT_FS
from parsers.ze2_txt import ZE2_MV_PER_COUNT, list_ze2_files
from paths import DATA_DELSYS, DATA_TXT, DATA_ZE2

OUT_ROOT = ROOT / "data" / "pairing_results"


def _slug(*parts: str) -> str:
    text = "_".join(p for p in parts if p)
    return re.sub(r"[^\w\u4e00-\u9fff\-]+", "_", text).strip("_") or "item"


def _list_session_or_all(session: str | None) -> tuple[list, list, list]:
    if not session:
        return list_delsys_files(), list_txt_files(), list_ze2_files()

    def scan(root: Path, pattern: str, source: str) -> list[dict[str, Any]]:
        folder = root / session
        if not folder.is_dir():
            return []
        return [
            {"name": p.name, "path": str(p), "source": source, "label": p.stem}
            for p in sorted(folder.rglob(pattern), key=lambda x: x.name.lower())
        ]

    delsys = scan(DATA_DELSYS, "*.csv", "delsys") or [
        f for f in list_delsys_files() if session in str(f.get("path", "")) or f["name"].startswith(session)
    ]
    ze1 = scan(DATA_TXT, "*.txt", "txt") or [
        f for f in list_txt_files() if session in str(f.get("path", "")) or session in f["name"]
    ]
    ze2 = scan(DATA_ZE2, "*.txt", "ze2") or [
        f for f in list_ze2_files() if session in str(f.get("path", ""))
    ]
    return delsys, ze1, ze2


def _slim(result: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    return {
        **plan,
        "contraction_method": result.get("contraction_method"),
        "feature_method": result.get("feature_method"),
        "metrics": result.get("metrics"),
        "pairs": result.get("pairs"),
        "correlation": result.get("correlation"),
        "interval_agreement": result.get("interval_agreement"),
        "note": result.get("note"),
    }


def _run_one(plan: dict[str, Any]) -> dict[str, Any] | None:
    if plan.get("status") != "ready":
        return None
    delsys = plan["delsys"]
    device_file = plan["device_file"]
    if plan["device"] == "ze1":
        return build_feature_compare(
            delsys,
            device_file,
            expected_count=3,
            contraction_method="ze1_schmitt",
            feature_method="ttri",
        )
    return build_feature_compare_ze2(
        delsys,
        device_file,
        expected_count=3,
        contraction_method="ze1_schmitt",
        feature_method="ttri",
        ze2_sample_rate=float(ZE2_DEFAULT_FS),
        ze2_mv_per_count=float(ZE2_MV_PER_COUNT),
        apply_bandpass=True,
    )


def _write_plan_table(path: Path, plans: list[dict[str, Any]]) -> None:
    if not plans:
        path.write_text("（無計畫列）\n", encoding="utf-8")
        return
    keys = list(plans[0].keys())
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=keys)
        writer.writeheader()
        for row in plans:
            writer.writerow(row)


def run_study(session_folder: str) -> Path:
    delsys, ze1, ze2 = _list_session_or_all(session_folder)
    out_dir = OUT_ROOT / session_folder
    device_dir = out_dir / "01_device_compare"
    shave_dir = out_dir / "02_shave_compare"
    device_dir.mkdir(parents=True, exist_ok=True)
    shave_dir.mkdir(parents=True, exist_ok=True)

    device_plans = plan_device_compares(delsys, ze1, ze2, sessions=("a09", "a10"))
    shave_plans = plan_shave_compares(delsys, ze1, session="a09")
    _write_plan_table(device_dir / "plan.csv", device_plans)
    _write_plan_table(shave_dir / "plan.csv", shave_plans)

    summary_rows: list[dict[str, Any]] = []

    # --- 1) Device compares: a09 / a10 / ZE2 vs Delsys per muscle ---
    device_lines = [
        "# 裝置比對（每個肌群）",
        "",
        "- a09 vs Delsys",
        "- a10 vs Delsys",
        "- ZE2 vs Delsys",
        "",
        f"掃描：Delsys {len(delsys)}、ZE1 {len(ze1)}、ZE2 {len(ze2)}",
        "",
        "| 狀態 | 肌群 | 比對 | Delsys | 裝置檔 |",
        "|------|------|------|--------|--------|",
    ]
    for plan in device_plans:
        site = _slug(plan["side"], plan["muscle"])
        site_dir = device_dir / site
        site_dir.mkdir(parents=True, exist_ok=True)
        out_name = f"{plan['compare']}.json"
        status = plan["status"]
        corr_iemg = corr_rms = ""
        if plan["status"] == "ready":
            try:
                result = _run_one(plan)
                assert result is not None
                payload = _slim(result, plan)
                (site_dir / out_name).write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2, default=str),
                    encoding="utf-8",
                )
                corr = result.get("correlation") or {}
                corr_iemg = corr.get("iemg")
                corr_rms = corr.get("rms")
                status = "done"
            except Exception as exc:  # noqa: BLE001 - collect per-file failures
                status = f"error:{exc}"
                (site_dir / out_name.replace(".json", ".error.txt")).write_text(str(exc), encoding="utf-8")
        device_lines.append(
            f"| {status} | {plan['side']}{plan['muscle']} | {plan['compare']} | "
            f"`{plan['delsys'] or '—'}` | `{plan['device_file'] or '—'}` |"
        )
        summary_rows.append(
            {
                "analysis": "device_compare",
                "muscle_site": f"{plan['side']}{plan['muscle']}",
                "compare": plan["compare"],
                "status": status,
                "delsys": plan.get("delsys") or "",
                "device_file": plan.get("device_file") or "",
                "correlation_iemg": corr_iemg,
                "correlation_rms": corr_rms,
            }
        )
    (device_dir / "README.md").write_text("\n".join(device_lines) + "\n", encoding="utf-8")

    # --- 2) Shave compares: a09 before / after vs Delsys ---
    shave_lines = [
        "# 刮腿毛比對",
        "",
        "- a09（刮毛前／未標示刮毛） vs Delsys",
        "- a09 刮腿毛後 vs Delsys",
        "",
        "| 狀態 | 肌群 | 比對 | Delsys | ZE1 |",
        "|------|------|------|--------|-----|",
    ]
    for plan in shave_plans:
        site = _slug(plan["side"], plan["muscle"])
        site_dir = shave_dir / site
        site_dir.mkdir(parents=True, exist_ok=True)
        out_name = f"{plan['compare']}.json"
        status = plan["status"]
        corr_iemg = corr_rms = ""
        if plan["status"] == "ready":
            try:
                result = _run_one(plan)
                assert result is not None
                payload = _slim(result, plan)
                (site_dir / out_name).write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2, default=str),
                    encoding="utf-8",
                )
                corr = result.get("correlation") or {}
                corr_iemg = corr.get("iemg")
                corr_rms = corr.get("rms")
                status = "done"
            except Exception as exc:  # noqa: BLE001
                status = f"error:{exc}"
                (site_dir / out_name.replace(".json", ".error.txt")).write_text(str(exc), encoding="utf-8")
        shave_lines.append(
            f"| {status} | {plan['side']}{plan['muscle']} | {plan['compare']} | "
            f"`{plan['delsys'] or '—'}` | `{plan['device_file'] or '—'}` |"
        )
        summary_rows.append(
            {
                "analysis": "shave_compare",
                "muscle_site": f"{plan['side']}{plan['muscle']}",
                "compare": plan["compare"],
                "status": status,
                "delsys": plan.get("delsys") or "",
                "device_file": plan.get("device_file") or "",
                "correlation_iemg": corr_iemg,
                "correlation_rms": corr_rms,
            }
        )
    (shave_dir / "README.md").write_text("\n".join(shave_lines) + "\n", encoding="utf-8")

    summary_csv = out_dir / "study_summary.csv"
    with summary_csv.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "analysis",
                "muscle_site",
                "compare",
                "status",
                "delsys",
                "device_file",
                "correlation_iemg",
                "correlation_rms",
            ],
        )
        writer.writeheader()
        for row in summary_rows:
            writer.writerow(row)

    index = out_dir / "STUDY_INDEX.md"
    done = sum(1 for r in summary_rows if r["status"] == "done")
    missing = sum(1 for r in summary_rows if r["status"] == "missing_files")
    index.write_text(
        "\n".join(
            [
                f"# {session_folder} 研究分析索引",
                "",
                "## 分析項目",
                "1. **裝置比對**（每肌群）：a09 vs Delsys、a10 vs Delsys、ZE2 vs Delsys → `01_device_compare/`",
                "2. **刮腿毛比對**：a09 vs Delsys、刮腿毛後 a09 vs Delsys → `02_shave_compare/`",
                "",
                f"- 完成：{done}",
                f"- 缺檔：{missing}",
                f"- 摘要：`study_summary.csv`",
                "",
                "詳見各資料夾 README 與 plan.csv。",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return out_dir


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session", default="2609-09", help="Session folder name under data/*/")
    args = parser.parse_args()
    out = run_study(args.session)
    print(f"study output: {out}")
    print(f"index: {out / 'STUDY_INDEX.md'}")
    print(f"summary: {out / 'study_summary.csv'}")


if __name__ == "__main__":
    main()
