from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


SUBJECT_PATTERNS = (
    ("frank", "Frank"),
    ("rita", "Rita"),
    ("todd", "Todd"),
)

MUSCLE_PATTERNS = (
    ("腓腸", "腓腸肌"),
    ("gastroc", "腓腸肌"),
    ("脛前", "脛前肌"),
    ("tibialis", "脛前肌"),
    ("二頭", "二頭肌"),
    ("bicep", "二頭肌"),
    ("三頭", "三頭肌"),
    ("tricep", "三頭肌"),
)

SIDE_PATTERNS = (
    (" lc", "LC"),
    ("_lc", "LC"),
    ("-lc", "LC"),
    (" la", "LA"),
    ("_la", "LA"),
    (" ra", "RA"),
    ("_ra", "RA"),
)

LOAD_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(kg|KG|Kg)", re.IGNORECASE)
CHANNEL_RE = re.compile(r"(?:Exg)?Ch([12])(?:Data)?", re.IGNORECASE)
DATE_RE = re.compile(r"(?<!\d)(\d{1,2}-\d{1,2})(?!\d)")


@dataclass(frozen=True)
class FileTags:
    subject: str = ""
    side: str = ""
    muscle: str = ""
    load: str = ""
    channel: str = ""
    date: str = ""

    def score_against(self, other: FileTags) -> int:
        score = 0
        if self.subject and other.subject and self.subject == other.subject:
            score += 40
        if self.muscle and other.muscle and self.muscle == other.muscle:
            score += 35
        if self.side and other.side and self.side == other.side:
            score += 15
        if self.load and other.load and self.load == other.load:
            score += 10
        if self.channel and other.channel and self.channel == other.channel:
            score += 5
        if self.date and other.date and self.date == other.date:
            score += 20
        return score

    def group_key(self) -> tuple[str, str, str, str]:
        """Coarse key for multi-source grouping (subject/muscle/side/date)."""
        return (self.subject or "?", self.muscle or "?", self.side or "?", self.date or "")

    def as_dict(self) -> dict[str, str]:
        return {
            "subject": self.subject,
            "side": self.side,
            "muscle": self.muscle,
            "load": self.load,
            "channel": self.channel,
            "date": self.date,
        }


def _normalize_name(name: str) -> str:
    return name.lower().replace("（", "(").replace("）", ")")


def extract_tags(filename: str) -> FileTags:
    stem = filename.rsplit(".", 1)[0]
    lowered = _normalize_name(stem)

    subject = ""
    for key, label in SUBJECT_PATTERNS:
        if key in lowered:
            subject = label
            break

    muscle = ""
    for key, label in MUSCLE_PATTERNS:
        if key in lowered:
            muscle = label
            break

    side = ""
    padded = f" {lowered} "
    for key, label in SIDE_PATTERNS:
        if key in padded or key.strip("_-") in lowered.split():
            side = label
            break
    # Also catch compact forms like LC_frank / frankLC
    if not side:
        if re.search(r"(^|[^a-z])lc([^a-z]|$)", lowered):
            side = "LC"
        elif re.search(r"(^|[^a-z])la([^a-z]|$)", lowered):
            side = "LA"
        elif re.search(r"(^|[^a-z])ra([^a-z]|$)", lowered):
            side = "RA"
    # Chinese left/right (common in ZE1/ZE2 filenames)
    if not side:
        if "左" in stem:
            side = "左"
        elif "右" in stem:
            side = "右"

    load = ""
    load_match = LOAD_RE.search(stem)
    if load_match:
        load = f"{load_match.group(1)}KG"

    channel = ""
    channel_match = CHANNEL_RE.search(stem)
    if channel_match:
        channel = f"Ch{channel_match.group(1)}"

    date = ""
    date_match = DATE_RE.search(stem)
    if date_match:
        date = date_match.group(1)

    return FileTags(
        subject=subject,
        side=side,
        muscle=muscle,
        load=load,
        channel=channel,
        date=date,
    )


def suggest_pairs(
    delsys_files: list[dict[str, Any]],
    txt_files: list[dict[str, Any]],
    *,
    limit: int = 12,
) -> list[dict[str, Any]]:
    suggestions: list[dict[str, Any]] = []
    for left in delsys_files:
        left_tags = extract_tags(left["name"])
        ranked: list[tuple[int, dict[str, Any], FileTags]] = []
        for right in txt_files:
            right_tags = extract_tags(right["name"])
            score = left_tags.score_against(right_tags)
            if score <= 0:
                continue
            ranked.append((score, right, right_tags))
        ranked.sort(key=lambda item: (-item[0], item[1]["name"]))
        for score, right, right_tags in ranked[:3]:
            suggestions.append(
                {
                    "score": score,
                    "delsys": left["name"],
                    "txt": right["name"],
                    "delsys_tags": left_tags.as_dict(),
                    "txt_tags": right_tags.as_dict(),
                    "reason": _reason(left_tags, right_tags),
                }
            )

    suggestions.sort(key=lambda item: (-item["score"], item["delsys"], item["txt"]))
    return suggestions[:limit]


def suggest_for_selection(
    selected_name: str,
    selected_source: str,
    candidates: list[dict[str, Any]],
    *,
    limit: int = 8,
) -> list[dict[str, Any]]:
    selected_tags = extract_tags(selected_name)
    ranked: list[dict[str, Any]] = []
    for item in candidates:
        tags = extract_tags(item["name"])
        score = selected_tags.score_against(tags)
        if score <= 0:
            continue
        ranked.append(
            {
                "score": score,
                "name": item["name"],
                "source": item.get("source", ""),
                "tags": tags.as_dict(),
                "reason": _reason(selected_tags, tags),
                "selected_source": selected_source,
                "selected_name": selected_name,
            }
        )
    ranked.sort(key=lambda item: (-item["score"], item["name"]))
    return ranked[:limit]


def _reason(a: FileTags, b: FileTags) -> str:
    parts: list[str] = []
    if a.subject and a.subject == b.subject:
        parts.append(a.subject)
    if a.muscle and a.muscle == b.muscle:
        parts.append(a.muscle)
    if a.side and a.side == b.side:
        parts.append(a.side)
    if a.date and a.date == b.date:
        parts.append(a.date)
    if a.load and a.load == b.load:
        parts.append(a.load)
    if a.channel and a.channel == b.channel:
        parts.append(a.channel)
    return " / ".join(parts) if parts else "弱相關"


def _annotate(files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in files:
        tags = extract_tags(item["name"])
        row = dict(item)
        row["tags"] = tags
        out.append(row)
    return out


def _pick_best(
    anchor_tags: FileTags,
    candidates: list[dict[str, Any]],
    *,
    prefer_channel: bool = True,
) -> tuple[dict[str, Any] | None, int]:
    best: dict[str, Any] | None = None
    best_score = -1
    for item in candidates:
        tags: FileTags = item["tags"]
        score = anchor_tags.score_against(tags)
        if prefer_channel and anchor_tags.channel and tags.channel and anchor_tags.channel == tags.channel:
            score += 8
        if score > best_score:
            best_score = score
            best = item
    if best is None or best_score <= 0:
        return None, 0
    return best, best_score


def suggest_triple_pairs(
    delsys_files: list[dict[str, Any]],
    ze1_files: list[dict[str, Any]],
    ze2_files: list[dict[str, Any]],
    *,
    limit: int = 40,
    min_score: int = 40,
) -> list[dict[str, Any]]:
    """
    Scan all three sources and propose Delsys–ZE1–ZE2 combinations.

    Complete trios (all three present) are listed first; partial pairs
    (only two sources) follow so large datasets remain browsable.
    """
    delsys = _annotate(delsys_files)
    ze1 = _annotate(ze1_files)
    ze2 = _annotate(ze2_files)

    suggestions: list[dict[str, Any]] = []

    # Anchor on Delsys when available.
    for left in delsys:
        left_tags: FileTags = left["tags"]
        best_ze1, s1 = _pick_best(left_tags, ze1)
        best_ze2, s2 = _pick_best(left_tags, ze2)
        if not best_ze1 and not best_ze2:
            continue
        score = max(s1, s2)
        if best_ze1 and best_ze2:
            score = s1 + s2
        if score < min_score and not (best_ze1 and best_ze2):
            # Keep complete-ish matches even if individual scores are modest.
            if not (best_ze1 and best_ze2):
                continue
        completeness = ("complete" if best_ze1 and best_ze2 else "partial")
        reasons = []
        if best_ze1:
            reasons.append("ZE1:" + _reason(left_tags, best_ze1["tags"]))
        if best_ze2:
            reasons.append("ZE2:" + _reason(left_tags, best_ze2["tags"]))
        suggestions.append(
            {
                "score": score,
                "completeness": completeness,
                "delsys": left["name"],
                "ze1": best_ze1["name"] if best_ze1 else "",
                "ze2": best_ze2["name"] if best_ze2 else "",
                "delsys_tags": left_tags.as_dict(),
                "ze1_tags": best_ze1["tags"].as_dict() if best_ze1 else {},
                "ze2_tags": best_ze2["tags"].as_dict() if best_ze2 else {},
                "reason": " | ".join(reasons),
            }
        )

    # If no Delsys yet, still group ZE1↔ZE2 so user sees what can pair later.
    if not delsys and ze1 and ze2:
        for left in ze1:
            left_tags = left["tags"]
            best_ze2, s2 = _pick_best(left_tags, ze2)
            if not best_ze2 or s2 < min_score:
                continue
            suggestions.append(
                {
                    "score": s2,
                    "completeness": "partial",
                    "delsys": "",
                    "ze1": left["name"],
                    "ze2": best_ze2["name"],
                    "delsys_tags": {},
                    "ze1_tags": left_tags.as_dict(),
                    "ze2_tags": best_ze2["tags"].as_dict(),
                    "reason": "ZE1↔ZE2:" + _reason(left_tags, best_ze2["tags"]),
                }
            )

    # Also expose tag groups with file counts (useful when dataset is large).
    suggestions.sort(
        key=lambda item: (
            0 if item["completeness"] == "complete" else 1,
            -int(item["score"]),
            item.get("delsys") or "",
            item.get("ze1") or "",
            item.get("ze2") or "",
        )
    )
    return suggestions[:limit]


def scan_tag_groups(
    delsys_files: list[dict[str, Any]],
    ze1_files: list[dict[str, Any]],
    ze2_files: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Group files by subject/muscle/side/date across sources."""
    buckets: dict[tuple[str, str, str, str], dict[str, list[str]]] = {}
    for source, files in (
        ("delsys", delsys_files),
        ("ze1", ze1_files),
        ("ze2", ze2_files),
    ):
        for item in files:
            tags = extract_tags(item["name"])
            key = tags.group_key()
            if key == ("?", "?", "?", ""):
                continue
            bucket = buckets.setdefault(
                key, {"delsys": [], "ze1": [], "ze2": [], "tags": tags.as_dict()}
            )
            bucket[source].append(item["name"])

    rows: list[dict[str, Any]] = []
    for key, bucket in buckets.items():
        n_sources = sum(1 for s in ("delsys", "ze1", "ze2") if bucket[s])
        rows.append(
            {
                "subject": key[0],
                "muscle": key[1],
                "side": key[2],
                "date": key[3],
                "n_sources": n_sources,
                "n_delsys": len(bucket["delsys"]),
                "n_ze1": len(bucket["ze1"]),
                "n_ze2": len(bucket["ze2"]),
                "delsys": bucket["delsys"],
                "ze1": bucket["ze1"],
                "ze2": bucket["ze2"],
                "completeness": "complete" if n_sources == 3 else "partial",
            }
        )
    rows.sort(key=lambda r: (-int(r["n_sources"]), r["subject"], r["muscle"], r["side"], r["date"]))
    return rows
