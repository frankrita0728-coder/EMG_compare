#!/usr/bin/env python3
"""Scan data/ by name consistency; compare muscle sites (optionally one session folder)."""

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
from features import analyze_signal_features, compare_feature_rows, feature_correlations, interval_agreement
from pairing import build_name_consistency_inventory
from parsers.delsys import list_delsys_files
from parsers.txt_device import list_txt_files
from parsers.ze2_txt import DEFAULT_SAMPLE_RATE as ZE2_DEFAULT_FS
from parsers.ze2_txt import ZE2_MV_PER_COUNT, list_ze2_files, load_ze2_emg

OUT_DIR = ROOT / "data" / "pairing_results"


def _slug(*parts: str) -> str:
    text = "_".join(p for p in parts if p)
    text = re.sub(r"[^\w\u4e00-\u9fff\-]+", "_", text)
    return text.strip("_") or "site"


def _filter_by_session(files: list[dict[str, Any]], session: str | None) -> list[dict[str, Any]]:
    """Keep files under a session folder (e.g. 2609-09) or whose name starts with it."""
    if not session:
        return files
    key = session.strip()
    out: list[dict[str, Any]] = []
    for item in files:
        path = str(item.get("path") or "").replace("\\", "/")
        name = str(item.get("name") or "")
        if f"/{key}/" in f"/{path}" or path.endswith(f"/{key}") or name.startswith(key):
            out.append(item)
    return out


def _list_session_files(session: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Prefer files physically inside */{session}/ folders.

    Global list_* helpers dedupe by filename, so session copies can be skipped;
    this rescans the session directories directly.
    """
    from paths import DATA_DELSYS, DATA_TXT, DATA_ZE2

    def _scan(root: Path, pattern: str, source: str) -> list[dict[str, Any]]:
        folder = root / session
        if not folder.is_dir():
            return []
        files: list[dict[str, Any]] = []
        for path in sorted(folder.rglob(pattern), key=lambda p: p.name.lower()):
            files.append(
                {
                    "name": path.name,
                    "path": str(path),
                    "source": source,
                    "label": path.stem,
                }
            )
        return files

    return (
        _scan(DATA_DELSYS, "*.csv", "delsys"),
        _scan(DATA_TXT, "*.txt", "txt"),
        _scan(DATA_ZE2, "*.txt", "ze2"),
    )


def write_inventory(inv: dict, out_dir: Path) -> tuple[Path, Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / "name_consistency_inventory.md"
    csv_path = out_dir / "name_consistency_pairs.csv"
    sites_csv = out_dir / "muscle_sites.csv"

    lines = [
        "# 名稱一致性一對一配對清單",
        "",
        f"- Delsys：{inv['counts']['delsys']}　ZE1：{inv['counts']['ze1']}　ZE2：{inv['counts']['ze2']}",
        f"- 肌群部位：{inv['counts'].get('muscle_sites', 0)}　一對一可比對：{inv['counts']['comparable_groups']}",
        "",
        "> 規則：每個 Delsys CSV 最多配 **1 個 ZE1**、**1 個 ZE2**；需同受試者／肌肉／側；若檔名有場次碼（如 a09）則必須相同。",
        "",
        "## 全肌群部位總表",
        "",
        "| 狀態 | 受試者 | 肌肉 | 側 | 通道建議 | Delsys | ZE1（建議Ch） | ZE2（建議Ch） |",
        "|------|--------|------|----|----------|--------|---------------|---------------|",
    ]
    for site in inv.get("sites") or []:
        lines.append(
            "| {status} | {subject} | {muscle} | {side} | {hint} | `{delsys}` | `{ze1}` | `{ze2}` |".format(
                status=site["status"],
                subject=site["subject"],
                muscle=site["muscle"],
                side=site["side"],
                hint=site.get("channel_hint") or "—",
                delsys="; ".join(site.get("delsys") or []) or "—",
                ze1="; ".join(site.get("ze1_preferred") or []) or "—",
                ze2="; ".join(site.get("ze2_preferred") or []) or "—",
            )
        )

    lines.extend(
        [
            "",
            "## 一對一可比對組合（Delsys ↔ ZE1 / ZE2）",
            "",
            "| 狀態 | 完整度 | 受試者 | 肌肉 | 側 | 場次 | 日期 | Delsys | ZE1 | ZE2 | 備註 |",
            "|------|--------|--------|------|----|------|------|--------|-----|-----|------|",
        ]
    )
    for row in inv["comparable"]:
        lines.append(
            "| {status} | {completeness} | {subject} | {muscle} | {side} | {session} | {date} | `{delsys}` | `{ze1}` | `{ze2}` | {note} |".format(
                status=row["status"],
                completeness=row["completeness"],
                subject=row["subject"],
                muscle=row["muscle"],
                side=row["side"],
                session=row["session"] or "—",
                date=row["date"] or "—",
                delsys=row["delsys"] or "—",
                ze1=row["ze1"] or "—",
                ze2=row["ze2"] or "—",
                note=row.get("match_note") or "—",
            )
        )

    pending = [s for s in (inv.get("sites") or []) if s["status"] == "待補 Delsys"]
    lines.extend(["", "## 待補 Delsys CSV 才能完整比對", ""])
    if not pending:
        lines.append("- （無）")
    else:
        for s in pending:
            lines.append(
                f"- **{s['subject']} {s['side']}{s['muscle']}**：請放入對應 Delsys CSV；"
                f"目前 ZE2 建議檔 `{'; '.join(s.get('ze2_preferred') or []) or '—'}`"
            )

    lines.extend(["", "## Delsys ↔ ZE1 建議分數", ""])
    for item in inv["delsys_ze1"][:20]:
        lines.append(
            f"- score={item['score']}｜`{item['delsys']}` ↔ `{item['txt']}`｜{item.get('reason') or ''}"
        )

    lines.extend(["", "## Delsys ↔ ZE2／三方建議", ""])
    for item in inv["triples"][:20]:
        lines.append(
            f"- [{item['completeness']}] score={item['score']}｜"
            f"D:`{item.get('delsys') or '—'}` × ZE1:`{item.get('ze1') or '—'}` × ZE2:`{item.get('ze2') or '—'}`｜"
            f"{item.get('channel_hint') or item.get('reason') or ''}"
        )

    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "status",
                "completeness",
                "subject",
                "muscle",
                "side",
                "session",
                "date",
                "channel_hint",
                "delsys",
                "ze1",
                "ze2",
                "match_note",
            ],
        )
        writer.writeheader()
        for row in inv["comparable"]:
            writer.writerow({k: row.get(k, "") for k in writer.fieldnames})

    with sites_csv.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "status",
                "subject",
                "muscle",
                "side",
                "channel_hint",
                "delsys",
                "ze1_preferred",
                "ze2_preferred",
                "n_delsys",
                "n_ze1",
                "n_ze2",
            ],
        )
        writer.writeheader()
        for site in inv.get("sites") or []:
            writer.writerow(
                {
                    "status": site["status"],
                    "subject": site["subject"],
                    "muscle": site["muscle"],
                    "side": site["side"],
                    "channel_hint": site.get("channel_hint") or "",
                    "delsys": "; ".join(site.get("delsys") or []),
                    "ze1_preferred": "; ".join(site.get("ze1_preferred") or []),
                    "ze2_preferred": "; ".join(site.get("ze2_preferred") or []),
                    "n_delsys": site.get("n_delsys", 0),
                    "n_ze1": site.get("n_ze1", 0),
                    "n_ze2": site.get("n_ze2", 0),
                }
            )

    return md_path, csv_path, sites_csv


def _slim_result(result: dict, *, device: str, device_name: str, meta: dict) -> dict:
    return {
        **meta,
        "device": device,
        "device_file": device_name,
        "contraction_method": result.get("contraction_method"),
        "feature_method": result.get("feature_method"),
        "metrics": result.get("metrics"),
        "pairs": result.get("pairs"),
        "features": result.get("features"),
        "count": result.get("count"),
        "correlation": result.get("correlation"),
        "interval_agreement": result.get("interval_agreement"),
        "note": result.get("note"),
    }


def _analyze_ze2_solo(filename: str) -> dict:
    data = load_ze2_emg(
        filename,
        for_plot=False,
        sample_rate=float(ZE2_DEFAULT_FS),
        mv_per_count=float(ZE2_MV_PER_COUNT),
        apply_bandpass=True,
    )
    feat = analyze_signal_features(
        data["times"],
        data["values"],
        sample_rate=data["sample_rate"],
        expected_count=3,
        contraction_method="ze1_schmitt",
        feature_method="ttri",
        source="ze2",
    )
    return {
        "mode": "ze2_solo",
        "filename": filename,
        "sample_rate": data["sample_rate"],
        "unit": data.get("unit"),
        "contraction_method": "ze1_schmitt",
        "feature_method": "ttri",
        "metrics": feat.get("metrics"),
        "features": feat.get("features"),
        "count": feat.get("count"),
        "contractions": feat.get("contractions"),
    }


def run_all_site_analyses(inv: dict, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    summary_rows: list[dict] = []

    for idx, row in enumerate(inv["comparable"], start=1):
        delsys = (row.get("delsys") or "").split("; ")[0].strip()
        if not delsys:
            continue
        stem = _slug(row.get("session") or f"pair{idx:02d}", row.get("side", ""), row.get("muscle", ""))
        meta = {
            "delsys": delsys,
            "session": row.get("session"),
            "subject": row.get("subject"),
            "muscle": row.get("muscle"),
            "side": row.get("side"),
            "channel_hint": row.get("channel_hint"),
            "match_note": row.get("match_note"),
            "status": "可比對",
        }
        ze1 = (row.get("ze1") or "").split("; ")[0].strip()
        if ze1:
            result = build_feature_compare(
                delsys,
                ze1,
                expected_count=3,
                contraction_method="ze1_schmitt",
                feature_method="ttri",
            )
            out = out_dir / f"compare_{idx:02d}_{stem}_ze1.json"
            out.write_text(
                json.dumps(_slim_result(result, device="ze1", device_name=ze1, meta=meta), ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
            written.append(out)
            summary_rows.append(
                {
                    "status": "可比對",
                    "subject": row.get("subject"),
                    "muscle": row.get("muscle"),
                    "side": row.get("side"),
                    "device": "ze1",
                    "file": ze1,
                    "correlation_iemg": (result.get("correlation") or {}).get("iemg"),
                    "correlation_rms": (result.get("correlation") or {}).get("rms"),
                    "n_pairs": len(result.get("pairs") or []),
                }
            )

        ze2 = (row.get("ze2") or "").split("; ")[0].strip()
        if ze2:
            result = build_feature_compare_ze2(
                delsys,
                ze2,
                expected_count=3,
                contraction_method="ze1_schmitt",
                feature_method="ttri",
                ze2_sample_rate=float(ZE2_DEFAULT_FS),
                ze2_mv_per_count=float(ZE2_MV_PER_COUNT),
                apply_bandpass=True,
            )
            out = out_dir / f"compare_{idx:02d}_{stem}_ze2.json"
            out.write_text(
                json.dumps(_slim_result(result, device="ze2", device_name=ze2, meta=meta), ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
            written.append(out)
            summary_rows.append(
                {
                    "status": "可比對",
                    "subject": row.get("subject"),
                    "muscle": row.get("muscle"),
                    "side": row.get("side"),
                    "device": "ze2",
                    "file": ze2,
                    "correlation_iemg": (result.get("correlation") or {}).get("iemg"),
                    "correlation_rms": (result.get("correlation") or {}).get("rms"),
                    "n_pairs": len(result.get("pairs") or []),
                }
            )

    site_idx = 0
    for site in inv.get("sites") or []:
        if site["status"] == "可比對":
            continue
        prefs = list(site.get("ze2_preferred") or [])
        if not prefs:
            continue
        site_idx += 1
        stem = _slug(site.get("subject", ""), site.get("side", ""), site.get("muscle", ""))
        for j, ze2_name in enumerate(prefs, start=1):
            solo = _analyze_ze2_solo(ze2_name)
            meta = {
                "delsys": None,
                "status": site["status"],
                "subject": site.get("subject"),
                "muscle": site.get("muscle"),
                "side": site.get("side"),
                "channel_hint": site.get("channel_hint"),
                "match_note": "無對應 Delsys；先輸出 ZE2 單獨特徵",
            }
            out = out_dir / f"site_{site_idx:02d}_{stem}_ze2_{j:02d}.json"
            payload = {**meta, **solo, "device": "ze2", "device_file": ze2_name}
            out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
            written.append(out)
            feats = solo.get("features") or []
            mean_aemg = None
            mean_rms = None
            if feats:
                avals = [f.get("aemg") for f in feats if f.get("aemg") is not None]
                rvals = [f.get("rms") for f in feats if f.get("rms") is not None]
                mean_aemg = sum(avals) / len(avals) if avals else None
                mean_rms = sum(rvals) / len(rvals) if rvals else None
            summary_rows.append(
                {
                    "status": site["status"],
                    "subject": site.get("subject"),
                    "muscle": site.get("muscle"),
                    "side": site.get("side"),
                    "device": "ze2_solo",
                    "file": ze2_name,
                    "correlation_iemg": None,
                    "correlation_rms": None,
                    "n_pairs": solo.get("count"),
                    "mean_aemg": mean_aemg,
                    "mean_rms": mean_rms,
                }
            )

        if len(prefs) >= 2:
            left = load_ze2_emg(
                prefs[0], for_plot=False, sample_rate=float(ZE2_DEFAULT_FS),
                mv_per_count=float(ZE2_MV_PER_COUNT), apply_bandpass=True,
            )
            right = load_ze2_emg(
                prefs[1], for_plot=False, sample_rate=float(ZE2_DEFAULT_FS),
                mv_per_count=float(ZE2_MV_PER_COUNT), apply_bandpass=True,
            )
            left_feat = analyze_signal_features(
                left["times"], left["values"], sample_rate=left["sample_rate"],
                expected_count=3, contraction_method="ze1_schmitt", feature_method="ttri", source="ze2",
            )
            right_feat = analyze_signal_features(
                right["times"], right["values"], sample_rate=right["sample_rate"],
                expected_count=3, contraction_method="ze1_schmitt", feature_method="ttri", source="ze2",
            )
            pairs = compare_feature_rows(left_feat["features"], right_feat["features"], metrics=left_feat["metrics"])
            corr = feature_correlations(left_feat["features"], right_feat["features"], metrics=left_feat["metrics"])
            agree = interval_agreement(left_feat["features"], right_feat["features"], metrics=left_feat["metrics"])
            out = out_dir / f"site_{site_idx:02d}_{stem}_ze2_session_compare.json"
            out.write_text(
                json.dumps(
                    {
                        "mode": "ze2_session_compare",
                        "status": site["status"],
                        "subject": site.get("subject"),
                        "muscle": site.get("muscle"),
                        "side": site.get("side"),
                        "left": prefs[0],
                        "right": prefs[1],
                        "note": "同肌群多筆 ZE2（尚無 Delsys）之場次一致性",
                        "pairs": pairs,
                        "correlation": corr,
                        "interval_agreement": agree,
                    },
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                ),
                encoding="utf-8",
            )
            written.append(out)

    summary_path = out_dir / "all_muscles_summary.csv"
    fieldnames = [
        "status", "subject", "muscle", "side", "device", "file",
        "correlation_iemg", "correlation_rms", "n_pairs", "mean_aemg", "mean_rms",
    ]
    with summary_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in summary_rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})
    written.append(summary_path)
    return written


def run_session(session: str | None) -> None:
    if session:
        delsys, ze1, ze2 = _list_session_files(session)
        # Fallback: also include name-prefix matches from global lists (e.g. flat files).
        if not delsys:
            delsys = _filter_by_session(list_delsys_files(), session)
        if not ze1:
            ze1 = _filter_by_session(list_txt_files(), session)
        if not ze2:
            ze2 = _filter_by_session(list_ze2_files(), session)
        out_dir = OUT_DIR / session
    else:
        delsys = list_delsys_files()
        ze1 = list_txt_files()
        ze2 = list_ze2_files()
        out_dir = OUT_DIR
    inv = build_name_consistency_inventory(delsys, ze1, ze2)
    md_path, csv_path, sites_csv = write_inventory(inv, out_dir)
    compare_paths = run_all_site_analyses(inv, out_dir)
    label = session or "ALL"
    print(f"[{label}] files D={len(delsys)} Z1={len(ze1)} Z2={len(ze2)}")
    print(f"[{label}] inventory: {md_path}")
    print(f"[{label}] pairs csv: {csv_path}")
    print(f"[{label}] sites csv: {sites_csv}")
    print(f"[{label}] muscle sites: {inv['counts'].get('muscle_sites')} comparable: {inv['counts']['comparable_groups']}")
    for site in inv.get("sites") or []:
        print(
            f"[{label}] site [{site['status']}] {site['subject']} {site['side']}{site['muscle']} "
            f"D={len(site.get('delsys') or [])} Z1={len(site.get('ze1_preferred') or [])} "
            f"Z2={len(site.get('ze2_preferred') or [])}"
        )
    for p in compare_paths:
        print(f"[{label}] out: {p}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Pair and compare EMG files by name consistency")
    parser.add_argument(
        "--session",
        action="append",
        default=[],
        help="Session folder name to analyze (e.g. 2609-09). Repeatable. Default: all files.",
    )
    args = parser.parse_args()
    sessions = args.session or [None]
    for session in sessions:
        run_session(session)


if __name__ == "__main__":
    main()
