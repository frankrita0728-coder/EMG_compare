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
# Shaving / hair-removal condition markers in filenames.
SHAVE_AFTER_RE = re.compile(
    r"(刮腿毛後|刮毛後|剃毛後|after[_\-]?shave|shaved|post[_\-]?shave)",
    re.IGNORECASE,
)
SHAVE_BEFORE_RE = re.compile(
    r"(刮腿毛前|刮毛前|剃毛前|before[_\-]?shave|unshaved|pre[_\-]?shave)",
    re.IGNORECASE,
)

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

# Canonical study sites: both sides × tibialis anterior + gastrocnemius.
STUDY_MUSCLE_SITES: tuple[tuple[str, str], ...] = (
    ("左", "脛前肌"),
    ("右", "脛前肌"),
    ("左", "腓腸肌"),
    ("右", "腓腸肌"),
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
    condition: str = ""  # "", "unshaved", "shaved"

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
        if self.condition and other.condition and self.condition == other.condition:
            score += 12
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
            "condition": self.condition,
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

    condition = ""
    if SHAVE_AFTER_RE.search(stem) or SHAVE_AFTER_RE.search(lowered):
        condition = "shaved"
    elif SHAVE_BEFORE_RE.search(stem) or SHAVE_BEFORE_RE.search(lowered):
        condition = "unshaved"
    elif "刮腿毛" in stem or "刮毛" in stem or "剃毛" in stem:
        # Bare marker without 前/後 → treat as after-shave condition label.
        condition = "shaved"

    return FileTags(
        subject=subject,
        side=side,
        muscle=muscle,
        load=load,
        channel=channel,
        date=date,
        session=session,
        trial=trial,
        condition=condition,
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


def _pair_identity(tags: FileTags) -> tuple[str, str, str, str, str]:
    """Strict 1:1 identity: subject/muscle/side/session/trial."""
    return (
        tags.subject or "?",
        tags.muscle or "?",
        normalize_side(tags.side) or tags.side or "?",
        tags.session or "",
        tags.trial or "",
    )


def pick_one_by_name(
    anchor_name: str,
    candidates: list[dict[str, Any]],
    source: str,
    *,
    used: set[str] | None = None,
    require_session: bool = True,
    min_score: int = 90,
) -> tuple[str, int, str]:
    """
    Pick exactly one candidate by filename-tag consistency (1:1).

    Requires matching subject + muscle + side. If the anchor has a session
    code (e.g. a09) and require_session=True, the candidate must share it —
    no cross-date fallback.
    """
    used = used or set()
    anchor = extract_tags(anchor_name)
    if not anchor.subject or not anchor.muscle or not anchor.side:
        return "", 0, "錨點檔名標籤不足"

    ranked: list[tuple[int, str, str]] = []
    for item in candidates:
        name = item["name"]
        if name in used:
            continue
        tags = extract_tags(name)
        if tags.subject != anchor.subject:
            continue
        if tags.muscle != anchor.muscle:
            continue
        if normalize_side(tags.side) != normalize_side(anchor.side):
            continue
        if require_session and anchor.session:
            if tags.session != anchor.session:
                continue
        if anchor.trial and tags.trial and tags.trial != anchor.trial:
            # Allow, but penalize — still 1:1 by session/site when trial missing on one side.
            pass

        score = anchor.score_against(tags)
        hint = recommended_channel(source, side=tags.side, muscle=tags.muscle)
        if hint and tags.channel == hint:
            score += 25
        elif hint and tags.channel and tags.channel != hint:
            score -= 8
        reason = _reason(anchor, tags)
        if hint:
            reason = f"{reason}｜建議{source.upper()} {hint}"
        ranked.append((score, name, reason))

    ranked.sort(key=lambda row: (-row[0], row[1]))
    if not ranked or ranked[0][0] < min_score:
        return "", 0, "無符合一對一檔名條件"
    best_score, best_name, best_reason = ranked[0]
    return best_name, best_score, best_reason


def match_devices_for_delsys(
    delsys_item: dict[str, Any],
    ze1_files: list[dict[str, Any]],
    ze2_files: list[dict[str, Any]],
    *,
    used_ze1: set[str] | None = None,
    used_ze2: set[str] | None = None,
    require_session: bool = True,
) -> dict[str, Any]:
    """
    Match at most one ZE1 and one ZE2 to one Delsys CSV by filename tags (1:1).

    Strict mode: same subject/muscle/side, and same session when Delsys has one.
    """
    left_tags = extract_tags(delsys_item["name"])
    ze1_name, ze1_score, ze1_reason = pick_one_by_name(
        delsys_item["name"], ze1_files, "ze1", used=used_ze1, require_session=require_session
    )
    # ZE2 filenames usually lack session codes like a09 — pair 1:1 by site tags only.
    ze2_name, ze2_score, ze2_reason = pick_one_by_name(
        delsys_item["name"],
        ze2_files,
        "ze2",
        used=used_ze2,
        require_session=False,
    )
    if used_ze1 is not None and ze1_name:
        used_ze1.add(ze1_name)
    if used_ze2 is not None and ze2_name:
        used_ze2.add(ze2_name)

    n_sources = 1 + (1 if ze1_name else 0) + (1 if ze2_name else 0)
    notes = []
    if ze1_name:
        notes.append(f"ZE1一對一 score={ze1_score}（{ze1_reason}）")
    else:
        notes.append(f"ZE1未配對：{ze1_reason}")
    if ze2_name:
        notes.append(f"ZE2一對一 score={ze2_score}（{ze2_reason}）")
    else:
        notes.append(f"ZE2未配對：{ze2_reason}")

    return {
        "status": "可比對" if (ze1_name or ze2_name) else "不足",
        "completeness": (
            "complete"
            if ze1_name and ze2_name
            else ("partial" if (ze1_name or ze2_name) else "none")
        ),
        "subject": left_tags.subject,
        "muscle": left_tags.muscle,
        "side": left_tags.side,
        "session": left_tags.session,
        "date": left_tags.date,
        "trial": left_tags.trial,
        "channel_hint": channel_hint_label(left_tags.side, left_tags.muscle),
        "delsys": delsys_item["name"],
        "ze1": ze1_name,
        "ze2": ze2_name,
        "ze1_all": ze1_name,
        "ze2_all": ze2_name,
        "ze1_score": ze1_score,
        "ze2_score": ze2_score,
        "n_sources": n_sources,
        "match_note": "；".join(notes),
    }


def build_one_to_one_pairs(
    delsys_files: list[dict[str, Any]],
    ze1_files: list[dict[str, Any]],
    ze2_files: list[dict[str, Any]],
    *,
    require_session: bool = True,
) -> list[dict[str, Any]]:
    """
    Build exclusive 1:1 Delsys↔ZE1 / Delsys↔ZE2 pairs.

    Higher-scoring Delsys anchors claim device files first so each device
    file is used at most once.
    """
    used_ze1: set[str] = set()
    used_ze2: set[str] = set()
    # Rank Delsys by how uniquely tagged they are (session/trial first).
    ranked_delsys = sorted(
        delsys_files,
        key=lambda item: (
            0 if extract_tags(item["name"]).session else 1,
            0 if extract_tags(item["name"]).trial else 1,
            item["name"],
        ),
    )
    pairs: list[dict[str, Any]] = []
    for item in ranked_delsys:
        row = match_devices_for_delsys(
            item,
            ze1_files,
            ze2_files,
            used_ze1=used_ze1,
            used_ze2=used_ze2,
            require_session=require_session,
        )
        if row["status"] == "可比對":
            pairs.append(row)
    return pairs


def _site_status(bucket: dict[str, list[str]]) -> str:
    has_delsys = bool(bucket["delsys"])
    has_device = bool(bucket["ze1"] or bucket["ze2"])
    if has_delsys and has_device:
        return "可比對"
    if has_delsys:
        return "僅 Delsys"
    if has_device:
        return "待補 Delsys"
    return "不足"


def _site_row(subject: str, muscle: str, side: str, bucket: dict[str, list[str]]) -> dict[str, Any]:
    ze1_pref = prefer_recommended_files(bucket["ze1"], "ze1")
    ze2_pref = prefer_recommended_files(bucket["ze2"], "ze2")
    return {
        "status": _site_status(bucket),
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


def enumerate_muscle_sites(
    delsys_files: list[dict[str, Any]],
    ze1_files: list[dict[str, Any]],
    ze2_files: list[dict[str, Any]],
    *,
    ensure_study_sites: bool = True,
) -> list[dict[str, Any]]:
    """
    One row per subject/muscle/side site across all sources.

    Sites without Delsys stay listed so other muscle groups are still processed.
    When ensure_study_sites is True, every discovered subject also gets the four
    canonical sites (L/R × tibialis/gastroc) even if no files exist yet.
    """
    buckets: dict[tuple[str, str, str], dict[str, list[str]]] = {}
    subjects: set[str] = set()
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
            subjects.add(key[0])
            bucket = buckets.setdefault(key, {"delsys": [], "ze1": [], "ze2": []})
            bucket[source].append(item["name"])

    if ensure_study_sites and subjects:
        for subject in subjects:
            for side, muscle in STUDY_MUSCLE_SITES:
                buckets.setdefault(
                    (subject, muscle, side),
                    {"delsys": [], "ze1": [], "ze2": []},
                )

    rows: list[dict[str, Any]] = []
    for key, bucket in sorted(buckets.items()):
        subject, muscle, side = key
        rows.append(_site_row(subject, muscle, side, bucket))
    return rows


def build_name_consistency_inventory(
    delsys_files: list[dict[str, Any]],
    ze1_files: list[dict[str, Any]],
    ze2_files: list[dict[str, Any]],
    *,
    require_session: bool = True,
) -> dict[str, Any]:
    """
    Organize CSV/TXT files by filename-tag consistency for 1:1 comparison.

    Each Delsys CSV claims at most one ZE1 and one ZE2 (exclusive).
    When Delsys has a session code (a09), device files must share it.
    """
    groups = scan_tag_groups(delsys_files, ze1_files, ze2_files)
    triples = suggest_triple_pairs(delsys_files, ze1_files, ze2_files, limit=100)
    delsys_ze1 = suggest_pairs(delsys_files, ze1_files, limit=50)
    sites = enumerate_muscle_sites(delsys_files, ze1_files, ze2_files)
    comparable = build_one_to_one_pairs(
        delsys_files, ze1_files, ze2_files, require_session=require_session
    )

    matched_names: set[str] = set()
    for row in comparable:
        for field in ("delsys", "ze1", "ze2", "ze1_all", "ze2_all"):
            name = row.get(field) or ""
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


def files_for_site(
    files: list[dict[str, Any]],
    *,
    subject: str,
    muscle: str,
    side: str,
) -> list[dict[str, Any]]:
    side_n = normalize_side(side)
    out: list[dict[str, Any]] = []
    for item in files:
        tags = extract_tags(item["name"])
        if tags.subject != subject:
            continue
        if tags.muscle != muscle:
            continue
        if normalize_side(tags.side) != side_n:
            continue
        out.append(item)
    return out


def pick_delsys_reference(
    delsys_files: list[dict[str, Any]],
    *,
    subject: str,
    muscle: str,
    side: str,
    preferred_session: str = "",
) -> dict[str, Any] | None:
    """Pick one Delsys CSV for a muscle site; prefer matching session when present."""
    candidates = files_for_site(delsys_files, subject=subject, muscle=muscle, side=side)
    if not candidates:
        return None
    if preferred_session:
        sess = [
            item
            for item in candidates
            if extract_tags(item["name"]).session == preferred_session
        ]
        if sess:
            return sess[0]
    # Prefer untagged / generic Delsys, else first alphabetical.
    generic = [item for item in candidates if not extract_tags(item["name"]).session]
    pool = generic or candidates
    pool = sorted(pool, key=lambda item: item["name"])
    return pool[0]


def pick_ze1_by_session(
    ze1_files: list[dict[str, Any]],
    *,
    subject: str,
    muscle: str,
    side: str,
    session: str,
    condition: str = "",
) -> dict[str, Any] | None:
    """Pick one ZE1 file for site + session (a09/a10), optional shave condition."""
    candidates = files_for_site(ze1_files, subject=subject, muscle=muscle, side=side)
    matched = [
        item
        for item in candidates
        if extract_tags(item["name"]).session == session
    ]
    if condition:
        cond = [
            item
            for item in matched
            if extract_tags(item["name"]).condition == condition
        ]
        # If asking unshaved and none tagged, fall back to session files without shaved marker.
        if cond:
            matched = cond
        elif condition == "unshaved":
            matched = [
                item
                for item in matched
                if extract_tags(item["name"]).condition != "shaved"
            ]
        else:
            matched = cond
    if not matched:
        return None
    preferred = prefer_recommended_files([item["name"] for item in matched], "ze1")
    preferred_set = set(preferred)
    ranked = [item for item in matched if item["name"] in preferred_set] or matched
    return sorted(ranked, key=lambda item: item["name"])[0]


def pick_ze2_for_site(
    ze2_files: list[dict[str, Any]],
    *,
    subject: str,
    muscle: str,
    side: str,
) -> dict[str, Any] | None:
    candidates = files_for_site(ze2_files, subject=subject, muscle=muscle, side=side)
    if not candidates:
        return None
    preferred = prefer_recommended_files([item["name"] for item in candidates], "ze2")
    preferred_set = set(preferred)
    ranked = [item for item in candidates if item["name"] in preferred_set] or candidates
    return sorted(ranked, key=lambda item: item["name"])[0]


def plan_device_compares(
    delsys_files: list[dict[str, Any]],
    ze1_files: list[dict[str, Any]],
    ze2_files: list[dict[str, Any]],
    *,
    sessions: tuple[str, ...] = ("a09", "a10"),
) -> list[dict[str, Any]]:
    """
    Plan per-muscle device compares: a09 vs Delsys, a10 vs Delsys, ZE2 vs Delsys.
    """
    sites = enumerate_muscle_sites(delsys_files, ze1_files, ze2_files)
    plans: list[dict[str, Any]] = []
    for site in sites:
        subject, muscle, side = site["subject"], site["muscle"], site["side"]
        for session in sessions:
            delsys = pick_delsys_reference(
                delsys_files,
                subject=subject,
                muscle=muscle,
                side=side,
                preferred_session=session,
            )
            ze1 = pick_ze1_by_session(
                ze1_files,
                subject=subject,
                muscle=muscle,
                side=side,
                session=session,
                condition="unshaved",  # device arm excludes explicit shaved files when possible
            )
            # If no unshaved-tagged file, retry without condition filter.
            if ze1 is None:
                ze1 = pick_ze1_by_session(
                    ze1_files,
                    subject=subject,
                    muscle=muscle,
                    side=side,
                    session=session,
                    condition="",
                )
            plans.append(
                {
                    "analysis": "device_compare",
                    "compare": f"{session}_vs_delsys",
                    "subject": subject,
                    "muscle": muscle,
                    "side": side,
                    "session": session,
                    "delsys": delsys["name"] if delsys else "",
                    "device": "ze1",
                    "device_file": ze1["name"] if ze1 else "",
                    "status": "ready" if (delsys and ze1) else "missing_files",
                }
            )
        delsys = pick_delsys_reference(
            delsys_files, subject=subject, muscle=muscle, side=side, preferred_session=""
        )
        ze2 = pick_ze2_for_site(ze2_files, subject=subject, muscle=muscle, side=side)
        plans.append(
            {
                "analysis": "device_compare",
                "compare": "ze2_vs_delsys",
                "subject": subject,
                "muscle": muscle,
                "side": side,
                "session": "",
                "delsys": delsys["name"] if delsys else "",
                "device": "ze2",
                "device_file": ze2["name"] if ze2 else "",
                "status": "ready" if (delsys and ze2) else "missing_files",
            }
        )
    return plans


def plan_shave_compares(
    delsys_files: list[dict[str, Any]],
    ze1_files: list[dict[str, Any]],
    *,
    session: str = "a09",
) -> list[dict[str, Any]]:
    """
    Plan shaving compares: a09 vs Delsys, and shaved-a09 vs Delsys, per muscle.
    """
    sites = enumerate_muscle_sites(delsys_files, ze1_files, [])
    plans: list[dict[str, Any]] = []
    for site in sites:
        subject, muscle, side = site["subject"], site["muscle"], site["side"]
        delsys = pick_delsys_reference(
            delsys_files,
            subject=subject,
            muscle=muscle,
            side=side,
            preferred_session=session,
        )
        before = pick_ze1_by_session(
            ze1_files,
            subject=subject,
            muscle=muscle,
            side=side,
            session=session,
            condition="unshaved",
        )
        if before is None:
            before = pick_ze1_by_session(
                ze1_files,
                subject=subject,
                muscle=muscle,
                side=side,
                session=session,
                condition="",
            )
            # Avoid using an explicitly shaved file as "before".
            if before and extract_tags(before["name"]).condition == "shaved":
                before = None
        after = pick_ze1_by_session(
            ze1_files,
            subject=subject,
            muscle=muscle,
            side=side,
            session=session,
            condition="shaved",
        )
        plans.append(
            {
                "analysis": "shave_compare",
                "compare": f"{session}_before_vs_delsys",
                "subject": subject,
                "muscle": muscle,
                "side": side,
                "session": session,
                "condition": "unshaved",
                "delsys": delsys["name"] if delsys else "",
                "device": "ze1",
                "device_file": before["name"] if before else "",
                "status": "ready" if (delsys and before) else "missing_files",
            }
        )
        plans.append(
            {
                "analysis": "shave_compare",
                "compare": f"{session}_after_shave_vs_delsys",
                "subject": subject,
                "muscle": muscle,
                "side": side,
                "session": session,
                "condition": "shaved",
                "delsys": delsys["name"] if delsys else "",
                "device": "ze1",
                "device_file": after["name"] if after else "",
                "status": "ready" if (delsys and after) else "missing_files",
            }
        )
    return plans

