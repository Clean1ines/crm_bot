"""
Utilities for building retrieval-oriented embedding text.

The embedding text is intentionally richer than the visible chunk text:
it repeats section titles, question-like lines and keyword-like markers so
semantic search has more anchors for short user queries.
"""

from __future__ import annotations

import re


_HEADING_RE = re.compile(
    r"^\s*(?:#{1,6}\s+|\d{1,3}[.)]\s+)?(?P<title>[A-ZА-ЯЁ0-9][^\n]{3,120})\s*$"
)
_QUESTION_RE = re.compile(
    r"(^|\s)(что|как|можно|сколько|когда|где|зачем|почему|кто|какие|какая|какой|can|how|what|when|where|why)\b",
    re.IGNORECASE,
)
_BULLET_RE = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+(?P<item>.+?)\s*$")
_WS_RE = re.compile(r"\s+")


def normalize_text(value: str) -> str:
    return _WS_RE.sub(" ", value).strip()


def extract_title(text: str) -> str | None:
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = _HEADING_RE.match(line)
        if not match:
            continue
        title = normalize_text(match.group("title"))
        if len(title) >= 4:
            return title
    return None


def extract_question_aliases(text: str, *, limit: int = 12) -> list[str]:
    aliases: list[str] = []
    seen: set[str] = set()

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        bullet = _BULLET_RE.match(line)
        candidate = bullet.group("item") if bullet else line
        candidate = normalize_text(candidate.strip("-–—:;. "))

        if not candidate:
            continue

        looks_like_question = "?" in candidate or _QUESTION_RE.search(candidate)
        short_enough = 5 <= len(candidate) <= 140

        if looks_like_question and short_enough:
            key = candidate.casefold()
            if key not in seen:
                seen.add(key)
                aliases.append(candidate)

        if len(aliases) >= limit:
            break

    return aliases


def extract_keyword_markers(text: str, *, limit: int = 24) -> list[str]:
    normalized = normalize_text(text)
    tokens = re.findall(r"[A-Za-zА-Яа-яЁё0-9][A-Za-zА-Яа-яЁё0-9+/#.-]{2,}", normalized)

    stop = {
        "это",
        "как",
        "что",
        "для",
        "или",
        "если",
        "при",
        "где",
        "над",
        "под",
        "the",
        "and",
        "for",
        "with",
        "that",
        "this",
        "you",
        "are",
    }

    result: list[str] = []
    seen: set[str] = set()

    for token in tokens:
        key = token.casefold()
        if key in stop:
            continue
        if key in seen:
            continue
        seen.add(key)
        result.append(token)
        if len(result) >= limit:
            break

    return result


def build_embedding_text(
    *,
    content: str,
    title: str | None = None,
    content_type: str | None = None,
    source_name: str | None = None,
) -> str:
    clean_content = normalize_text(content)
    detected_title = title or extract_title(content)
    aliases = extract_question_aliases(content)
    keywords = extract_keyword_markers(content)

    parts: list[str] = []

    if detected_title:
        parts.append(f"Title: {detected_title}")

    if content_type:
        parts.append(f"Type: {content_type}")

    if source_name:
        parts.append(f"Source: {source_name}")

    if aliases:
        parts.append("Questions: " + "; ".join(aliases))

    if keywords:
        parts.append("Keywords: " + ", ".join(keywords))

    parts.append("Content: " + clean_content)

    return "\n".join(parts).strip()
