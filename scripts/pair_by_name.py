#!/usr/bin/env python3
"""Scan data/ CSV+TXT by name consistency, write inventory, run ZE1/ZE2 compares."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from compare import build_feature_compare, build_feature_compare_ze2
from pairing import build_name_consistency_inventory, extract_tags
from parsers.delsys import list_delsys_files
from parsers.txt_device import list_txt_files
from parsers.ze2_txt import DEFAULT_SAMPLE_RATE as ZE2_DEFAULT_FS
from parsers.ze2_txt import ZE2_MV_PER_COUNT, list_ze2_files

OUT_DIR = ROOT / "data" / "pairing_results"


def write_inventory(inv: dict) -> tuple[Path, Path]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    md_path = OUT_DIR / "name_consistency_inventory.md"
    csv_path = OUT_DIR / "name_consistency_pairs.csv"

    lines = [
        "# 名稱一致性配對清單",
        "",
        f"- Delsys：{inv['counts']['delsys']}　ZE1：{inv['counts']['ze1']}　ZE2：{inv['counts']['ze2']}",
        f"- 可比對分組：{inv['counts']['comparable_groups']}",
        "",
        "## 可比對組合（依檔名標籤）",
        "",
        "| 狀態 | 完整度 | 受試者 | 肌肉 | 側 | 場次 | 日期 | 通道建議 | Delsys | ZE1（建議Ch優先） | ZE2（建議Ch優先） | 備註 |",
        "|------|--------|--------|------|----|------|------|----------|--------|-------------------|-------------------|------|",
    ]
    for row in inv["comparable"]:
        lines.append(
            "| {status} | {completeness} | {subject} | {muscle} | {side} | {session} | {date} | {channel_hint} | `{delsys}` | `{ze1}` | `{ze2}` | {note} |".format(
                status=row["status"],
                completeness=row["completeness"],
                subject=row["subject"],
                muscle=row["muscle"],
                side=row["side"],
                session=row["session"] or "—",
                date=row["date"] or "—",
                channel_hint=row["channel_hint"] or "—",
                delsys=row["delsys"] or "—",
                ze1=row["ze1"] or "—",
                ze2=row["ze2"] or "—",
                note=row.get("match_note") or "—",
            )
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

    unmatched = inv["unmatched"]
    lines.extend(["", "## 尚未納入可比對分組", ""])
    for src in ("delsys", "ze1", "ze2"):
        names = unmatched.get(src) or []
        lines.append(f"### {src.upper()}（{len(names)}）")
        if not names:
            lines.append("- （無）")
        else:
            for name in names:
                tags = extract_tags(name)
                lines.append(f"- `{name}` → {tags.as_dict()}")
        lines.append("")

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

    return md_path, csv_path


def _slim_result(result: dict, *, device: str, device_name: str, row: dict) -> dict:
    return {
        "delsys": row.get("delsys"),
        "device": device,
        "device_file": device_name,
        "session": row.get("session"),
        "subject": row.get("subject"),
        "muscle": row.get("muscle"),
        "side": row.get("side"),
        "channel_hint": row.get("channel_hint"),
        "match_note": row.get("match_note"),
        "contraction_method": result.get("contraction_method"),
        "feature_method": result.get("feature_method"),
        "metrics": result.get("metrics"),
        "pairs": result.get("pairs"),
        "correlation": result.get("correlation"),
        "interval_agreement": result.get("interval_agreement"),
        "note": result.get("note"),
    }


def run_matched_compares(inv: dict) -> list[Path]:
    """Run TTRI + Schmitt feature compare for Delsys–ZE1 and Delsys–ZE2 pairs."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for idx, row in enumerate(inv["comparable"], start=1):
        delsys = (row.get("delsys") or "").split("; ")[0].strip()
        if not delsys or delsys == "—":
            continue
        stem = row.get("session") or f"pair{idx:02d}"

        ze1 = (row.get("ze1") or "").split("; ")[0].strip()
        if ze1 and ze1 != "—":
            result = build_feature_compare(
                delsys,
                ze1,
                expected_count=3,
                contraction_method="ze1_schmitt",
                feature_method="ttri",
            )
            out = OUT_DIR / f"compare_{idx:02d}_{stem}_ze1.json"
            out.write_text(
                json.dumps(_slim_result(result, device="ze1", device_name=ze1, row=row), ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
            written.append(out)

        ze2 = (row.get("ze2") or "").split("; ")[0].strip()
        if ze2 and ze2 != "—":
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
            out = OUT_DIR / f"compare_{idx:02d}_{stem}_ze2.json"
            out.write_text(
                json.dumps(_slim_result(result, device="ze2", device_name=ze2, row=row), ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
            written.append(out)

    return written


def main() -> None:
    delsys = list_delsys_files()
    ze1 = list_txt_files()
    ze2 = list_ze2_files()
    inv = build_name_consistency_inventory(delsys, ze1, ze2)
    md_path, csv_path = write_inventory(inv)
    compare_paths = run_matched_compares(inv)
    print(f"inventory: {md_path}")
    print(f"pairs csv: {csv_path}")
    print(f"comparable groups: {inv['counts']['comparable_groups']}")
    for row in inv["comparable"]:
        print(
            f"pair: D={row.get('delsys')} | ZE1={row.get('ze1') or '—'} | ZE2={row.get('ze2') or '—'} | {row.get('match_note')}"
        )
    for p in compare_paths:
        print(f"compare: {p}")


if __name__ == "__main__":
    main()
