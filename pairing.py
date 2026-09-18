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
# Folder/prefix style dates like 2609-10 (YYMM-DD) → MM-DD
YYMM_DATE_RE = re.compile(r"(?<!\d)\d{2}(\d{2})-(\d{1,2})(?!\d)")
SESSION_RE = re.compile(r"(?:^|[_\s(\-])a(\d{2})(?:[_\s)\-]|$)", re.IGNORECASE)
TRIAL_RE = re.compile(r"(?:_with)?(?:_a\d{2})?_(\d+)$", re.IGNORECASE)

# Clinical channel hints (ZE2 is the inverse of ZE1).
# Keys: (side_norm, muscle) → ZE1 recommended channel.
ZE1_CHANNEL_HINTS: dict[tuple[str, str], str] = {
    ("左", "脛前肌"): "Ch1",
    ("左", "腓腸肌"): "Ch2",
    ("右", "脛前肌"): "Ch2",
    ("右", "腓腸肌"): "Ch1",
}

CHANNEL_HINT_ROWS: tuple[dict[str, str], ...] = (
    {"部位": "左脛前肌", "ZE1": "Ch1", "ZE2": "Ch2"},
    {"部位": "左腓腸肌", "ZE1": "Ch2", "ZE2": "Ch1"},
    {"部位": "右脛前肌", "ZE1": "Ch2", "ZE2": "Ch1"},
    {"部位": "右腓腸肌", "ZE1": "Ch1", "ZE2": "Ch2"},
)


def normalize_side(side: str) -> str:
    """Map filename side tags to 左/右 used by channel hints."""
    s = (side or "").strip()
    if s in {"左", "LA", "LC", "L", "left", "Left"}:
        return "左"
    if s in {"右", "RA", "RC", "R", "right", "Right"}:
        return "右"
    return s


def recommended_channel(source: str, *, side: str = "", muscle: str = "") -> str:
    """
    Return suggested Ch1/Ch2 for ZE1 or ZE2 given side + muscle.

    ZE1 rules are explicit; ZE2 is the opposite channel.
    """
    side_n = normalize_side(side)
    muscle_n = (muscle or "").strip()
    if not side_n or not muscle_n:
        return ""
    ze1 = ZE1_CHANNEL_HINTS.get((side_n, muscle_n), "")
    if not ze1:
        return ""
    src = (source or "").strip().lower()
    if src in {"ze1", "txt", "txt_device"}:
        return ze1
    if src in {"ze2", "ze2_txt"}:
        return "Ch2" if ze1 == "Ch1" else "Ch1"
    return ""


def channel_hint_label(side: str = "", muscle: str = "") -> str:
    """Human-readable ZE1/ZE2 channel suggestion for a site."""
    side_n = normalize_side(side)
    muscle_n = (muscle or "").strip()
    if not side_n or not muscle_n:
        return ""
    ze1 = recommended_channel("ze1", side=side_n, muscle=muscle_n)
    ze2 = recommended_channel("ze2", side=side_n, muscle=muscle_n)
    if not ze1:
        return ""
    return f"{side_n}{muscle_n} → ZE1 {ze1}／ZE2 {ze2}"


def prefer_recommended_files(names: list[str], source: str) -> list[str]:
    """
    Prefer files whose channel matches the muscle/side hint.

    If none match (or hints cannot be inferred), return the original list.
    """
    if not names:
        return []
    matched: list[str] = []
    for name in names:
        tags = extract_tags(name)
        hint = recommended_channel(source, side=tags.side, muscle=tags.muscle)
        if hint and tags.channel == hint:
            matched.append(name)
    return matched if matched else list(names)


@dataclass(frozen=True)
class FileTags:
    subject: str = ""
    side: str = ""
    muscle: str = ""
    load: str = ""
    channel: str = ""
    date: str = ""
    session: str = ""
    trial: str = ""

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
        if self.session and other.session and self.session == other.session:
            score += 30
        if self.trial and other.trial and self.trial == other.trial:
            score += 8
        return score

    def group_key(self) -> tuple[str, str, str, str]:
        """
        Coarse key for multi-source grouping.

        Prefer session code (e.g. a09) over calendar date when present, so
        Delsys/ZE1/ZE2 from the same capture still group across day labels.
        """
        bucket = f"sess:{self.session}" if self.session else (self.date or "")
        return (self.subject or "?", self.muscle or "?", self.side or "?", bucket)

    def as_dict(self) -> dict[str, str]:
        return {
            "subject": self.subject,
            "side": self.side,
            "muscle": self.muscle,
            "load": self.load,
            "channel": self.channel,
            "date": self.date,
            "session": self.session,
            "trial": self.trial,
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
    else:
        yymm = YYMM_DATE_RE.search(stem)
        if yymm:
            date = f"{int(yymm.group(1)):02d}-{int(yymm.group(2)):02d}"

    session = ""
    session_match = SESSION_RE.search(lowered)
    if session_match:
        session = f"a{session_match.group(1)}"

    trial = ""
    trial_match = TRIAL_RE.search(stem)
    if trial_match:
        trial = trial_match.group(1)

    return FileTags(
        subject=subject,
        side=side,
        muscle=muscle,
        load=load,
        channel=channel,
        date=date,
        session=session,
        trial=trial,
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
    if a.session and a.session == b.session:
        parts.append(a.session)
    if a.date and a.date == b.date:
        parts.append(a.date)
    if a.load and a.load == b.load:
        parts.append(a.load)
    if a.channel and a.channel == b.channel:
        parts.append(a.channel)
    if a.trial and a.trial == b.trial:
        parts.append(f"#{a.trial}")
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
    source: str = "",
) -> tuple[dict[str, Any] | None, int]:
    best: dict[str, Any] | None = None
    best_score = -1
    # Prefer clinical channel for the site (muscle+side), falling back to anchor side/muscle.
    for item in candidates:
        tags: FileTags = item["tags"]
        score = anchor_tags.score_against(tags)
        if prefer_channel and anchor_tags.channel and tags.channel and anchor_tags.channel == tags.channel:
            score += 8
        if source:
            hint = recommended_channel(
                source,
                side=tags.side or anchor_tags.side,
                muscle=tags.muscle or anchor_tags.muscle,
            )
            if hint and tags.channel == hint:
                score += 25
            elif hint and tags.channel and tags.channel != hint:
                score -= 10
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
        best_ze1, s1 = _pick_best(left_tags, ze1, source="ze1")
        best_ze2, s2 = _pick_best(left_tags, ze2, source="ze2")
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
        hint = channel_hint_label(left_tags.side, left_tags.muscle)
        reasons = []
        if best_ze1:
            reasons.append("ZE1:" + _reason(left_tags, best_ze1["tags"]))
        if best_ze2:
            reasons.append("ZE2:" + _reason(left_tags, best_ze2["tags"]))
        if hint:
            reasons.append(hint)
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
                "channel_hint": hint,
                "reason": " | ".join(reasons),
            }
        )

    # If no Delsys yet, still group ZE1↔ZE2 so user sees what can pair later.
    if not delsys and ze1 and ze2:
        for left in ze1:
            left_tags = left["tags"]
            # Prefer ZE1 files that already match the clinical channel hint.
            ze1_hint = recommended_channel("ze1", side=left_tags.side, muscle=left_tags.muscle)
            if ze1_hint and left_tags.channel and left_tags.channel != ze1_hint:
                continue
            best_ze2, s2 = _pick_best(left_tags, ze2, source="ze2")
            if not best_ze2 or s2 < min_score:
                continue
            hint = channel_hint_label(left_tags.side, left_tags.muscle)
            reason = "ZE1↔ZE2:" + _reason(left_tags, best_ze2["tags"])
            if hint:
                reason = f"{reason} | {hint}"
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
                    "channel_hint": hint,
                    "reason": reason,
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
        side, muscle = key[2], key[1]
        bucket_label = key[3]
        session = bucket_label[5:] if bucket_label.startswith("sess:") else ""
        date = "" if session else bucket_label
        tags_dict = dict(bucket.get("tags") or {})
        if session:
            tags_dict["session"] = session
        hint = channel_hint_label(side, muscle)
        ze1_ch = recommended_channel("ze1", side=side, muscle=muscle)
        ze2_ch = recommended_channel("ze2", side=side, muscle=muscle)
        rows.append(
            {
                "subject": key[0],
                "muscle": key[1],
                "side": key[2],
                "date": date or tags_dict.get("date", ""),
                "session": session or tags_dict.get("session", ""),
                "bucket": bucket_label,
                "n_sources": n_sources,
                "n_delsys": len(bucket["delsys"]),
                "n_ze1": len(bucket["ze1"]),
                "n_ze2": len(bucket["ze2"]),
                "delsys": bucket["delsys"],
                "ze1": bucket["ze1"],
                "ze2": bucket["ze2"],
                "ze1_preferred": prefer_recommended_files(bucket["ze1"], "ze1"),
                "ze2_preferred": prefer_recommended_files(bucket["ze2"], "ze2"),
                "ze1_channel_hint": ze1_ch,
                "ze2_channel_hint": ze2_ch,
                "channel_hint": hint,
                "completeness": "complete" if n_sources == 3 else "partial",
            }
        )
    rows.sort(
        key=lambda r: (
            -int(r["n_sources"]),
            r["subject"],
            r["muscle"],
            r["side"],
            r.get("session") or "",
            r.get("date") or "",
        )
    )
    return rows


def _site_key(tags: FileTags) -> tuple[str, str, str]:
    return (tags.subject or "?", tags.muscle or "?", normalize_side(tags.side) or tags.side or "?")


def match_devices_for_delsys(
    delsys_item: dict[str, Any],
    ze1_files: list[dict[str, Any]],
    ze2_files: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Match ZE1/ZE2 to one Delsys CSV by subject/muscle/side.

    Prefer same session, then recommended channel; keep cross-date ZE2 when
    the site tags still agree (common when ZE2 lacks a09-style session codes).
    """
    left_tags = extract_tags(delsys_item["name"])
    left_site = _site_key(left_tags)

    def _collect(candidates: list[dict[str, Any]], source: str) -> tuple[list[str], list[str]]:
        same_site: list[str] = []
        for item in candidates:
            tags = extract_tags(item["name"])
            if _site_key(tags) != left_site:
                continue
            if left_site[0] == "?":
                continue
            same_site.append(item["name"])
        if not same_site:
            return [], []
        # Prefer same session when available.
        if left_tags.session:
            sess_hits = [
                name
                for name in same_site
                if extract_tags(name).session == left_tags.session
            ]
            pool = sess_hits or same_site
        else:
            pool = same_site
        preferred = prefer_recommended_files(pool, source)
        return preferred, same_site

    ze1_pref, ze1_all = _collect(ze1_files, "ze1")
    ze2_pref, ze2_all = _collect(ze2_files, "ze2")
    n_sources = 1 + (1 if ze1_all else 0) + (1 if ze2_all else 0)
    return {
        "status": "可比對" if (ze1_all or ze2_all) else "不足",
        "completeness": "complete" if (ze1_all and ze2_all) else ("partial" if (ze1_all or ze2_all) else "none"),
        "subject": left_tags.subject,
        "muscle": left_tags.muscle,
        "side": left_tags.side,
        "session": left_tags.session,
        "date": left_tags.date,
        "channel_hint": channel_hint_label(left_tags.side, left_tags.muscle),
        "delsys": delsys_item["name"],
        "ze1": "; ".join(ze1_pref),
        "ze2": "; ".join(ze2_pref),
        "ze1_all": "; ".join(ze1_all),
        "ze2_all": "; ".join(ze2_all),
        "n_sources": n_sources,
        "match_note": (
            "ZE2 依受試者/肌肉/側配對"
            + ("（跨日期／無場次碼）" if ze2_all and left_tags.session and not any(
                extract_tags(n).session == left_tags.session for n in ze2_all
            ) else "")
        ),
    }


def enumerate_muscle_sites(
    delsys_files: list[dict[str, Any]],
    ze1_files: list[dict[str, Any]],
    ze2_files: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    One row per subject/muscle/side site across all sources.

    Sites without Delsys stay listed so other muscle groups are still processed.
    """
    buckets: dict[tuple[str, str, str], dict[str, list[str]]] = {}
    for source, files in (
        ("delsys", delsys_files),
        ("ze1", ze1_files),
        ("ze2", ze2_files),
    ):
        for item in files:
            tags = extract_tags(item["name"])
            key = _site_key(tags)
            if key[0] == "?" or key[1] == "?" or key[2] == "?":
                continue
            bucket = buckets.setdefault(key, {"delsys": [], "ze1": [], "ze2": []})
            bucket[source].append(item["name"])

    rows: list[dict[str, Any]] = []
    for key, bucket in sorted(buckets.items()):
        subject, muscle, side = key
        ze1_pref = prefer_recommended_files(bucket["ze1"], "ze1")
        ze2_pref = prefer_recommended_files(bucket["ze2"], "ze2")
        has_delsys = bool(bucket["delsys"])
        has_device = bool(bucket["ze1"] or bucket["ze2"])
        if has_delsys and has_device:
            status = "可比對"
        elif has_delsys:
            status = "僅 Delsys"
        elif has_device:
            status = "待補 Delsys"
        else:
            status = "不足"
        rows.append(
            {
                "status": status,
                "subject": subject,
                "muscle": muscle,
                "side": side,
                "channel_hint": channel_hint_label(side, muscle),
                "ze1_channel_hint": recommended_channel("ze1", side=side, muscle=muscle),
                "ze2_channel_hint": recommended_channel("ze2", side=side, muscle=muscle),
                "delsys": bucket["delsys"],
                "ze1": bucket["ze1"],
                "ze2": bucket["ze2"],
                "ze1_preferred": ze1_pref,
                "ze2_preferred": ze2_pref,
                "n_delsys": len(bucket["delsys"]),
                "n_ze1": len(bucket["ze1"]),
                "n_ze2": len(bucket["ze2"]),
            }
        )
    return rows


def build_name_consistency_inventory(
    delsys_files: list[dict[str, Any]],
    ze1_files: list[dict[str, Any]],
    ze2_files: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Organize CSV/TXT files by name-tag consistency for comparison.

    Each Delsys CSV gets ZE1/ZE2 matches by subject/muscle/side (session
    preferred when present). ZE2 may match across dates when session codes
    are missing from ZE2 filenames.
    """
    groups = scan_tag_groups(delsys_files, ze1_files, ze2_files)
    triples = suggest_triple_pairs(delsys_files, ze1_files, ze2_files, limit=100)
    delsys_ze1 = suggest_pairs(delsys_files, ze1_files, limit=50)
    sites = enumerate_muscle_sites(delsys_files, ze1_files, ze2_files)

    comparable: list[dict[str, Any]] = []
    for item in delsys_files:
        row = match_devices_for_delsys(item, ze1_files, ze2_files)
        if row["status"] == "可比對":
            comparable.append(row)

    # Also keep pure tag-bucket groups that already include Delsys + device
    # (useful when multiple Delsys share a bucket).
    seen_delsys = {row["delsys"] for row in comparable}
    for g in groups:
        if not g["n_delsys"] or not (g["n_ze1"] or g["n_ze2"]):
            continue
        for dname in g["delsys"]:
            if dname in seen_delsys:
                # Enrich existing row with any bucket ZE2 still missing.
                for row in comparable:
                    if row["delsys"] != dname:
                        continue
                    if not row.get("ze2") and (g.get("ze2_preferred") or g["ze2"]):
                        row["ze2"] = "; ".join(g.get("ze2_preferred") or g["ze2"])
                        row["ze2_all"] = "; ".join(g["ze2"])
                        row["completeness"] = (
                            "complete" if row.get("ze1") and row.get("ze2") else row["completeness"]
                        )
                continue

    matched_names: set[str] = set()
    for row in comparable:
        for field in ("delsys", "ze1", "ze2", "ze1_all", "ze2_all"):
            for name in (row.get(field) or "").split("; "):
                if name:
                    matched_names.add(name)
    for site in sites:
        for field in ("delsys", "ze1", "ze2"):
            for name in site.get(field) or []:
                matched_names.add(name)

    unmatched = {
        "delsys": [f["name"] for f in delsys_files if f["name"] not in matched_names],
        "ze1": [f["name"] for f in ze1_files if f["name"] not in matched_names],
        "ze2": [
            f["name"]
            for f in ze2_files
            if f["name"] not in matched_names and extract_tags(f["name"]).subject
        ],
    }

    return {
        "groups": groups,
        "sites": sites,
        "comparable": comparable,
        "triples": triples,
        "delsys_ze1": delsys_ze1,
        "unmatched": unmatched,
        "counts": {
            "delsys": len(delsys_files),
            "ze1": len(ze1_files),
            "ze2": len(ze2_files),
            "comparable_groups": len(comparable),
            "muscle_sites": len(sites),
        },
    }
