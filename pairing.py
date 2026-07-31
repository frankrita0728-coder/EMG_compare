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
CHANNEL_RE = re.compile(r"ExgCh([12])", re.IGNORECASE)


@dataclass(frozen=True)
class FileTags:
    subject: str = ""
    side: str = ""
    muscle: str = ""
    load: str = ""
    channel: str = ""

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
        return score

    def as_dict(self) -> dict[str, str]:
        return {
            "subject": self.subject,
            "side": self.side,
            "muscle": self.muscle,
            "load": self.load,
            "channel": self.channel,
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

    load = ""
    load_match = LOAD_RE.search(stem)
    if load_match:
        load = f"{load_match.group(1)}KG"

    channel = ""
    channel_match = CHANNEL_RE.search(stem)
    if channel_match:
        channel = f"Ch{channel_match.group(1)}"

    return FileTags(subject=subject, side=side, muscle=muscle, load=load, channel=channel)


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
    if a.load and a.load == b.load:
        parts.append(a.load)
    return " / ".join(parts) if parts else "弱相關"
