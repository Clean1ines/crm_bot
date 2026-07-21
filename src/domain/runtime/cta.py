from typing import Literal

from src.domain.runtime.language_policy import LanguageHint


CONTINUE_EXPLANATION_CTA = "continue_explanation"
ACTION_CTAS = frozenset({"call_manager", "book_consultation"})
CONVERSATIONAL_CTAS = frozenset({CONTINUE_EXPLANATION_CTA})
PENDING_CTAS = ACTION_CTAS | CONVERSATIONAL_CTAS
NO_CTA_VALUES = frozenset({"", "none"})
AFFIRMATIVE_REPLIES = frozenset(
    {
        "да",
        "ага",
        "угу",
        "ок",
        "окей",
        "конечно",
        "yes",
        "yep",
        "sure",
        "ja",
        "sí",
        "si",
    }
)
NEGATIVE_REPLIES = frozenset({"нет", "неа", "не", "no", "nope", "nein"})
SHORT_REPLY_LANGUAGES: dict[str, LanguageHint] = {
    "да": "ru",
    "ага": "ru",
    "угу": "ru",
    "ок": "ru",
    "окей": "ru",
    "конечно": "ru",
    "нет": "ru",
    "неа": "ru",
    "не": "ru",
    "yes": "en",
    "yep": "en",
    "sure": "en",
    "no": "en",
    "nope": "en",
    "ja": "de",
    "nein": "de",
    "sí": "es",
    "si": "es",
}

ShortReplyKind = Literal["affirmative", "negative"]


def normalize_cta(value: object) -> str | None:
    if value is None:
        return None

    text = str(value).strip().lower()
    if text in NO_CTA_VALUES:
        return None
    return text


def is_action_cta(value: object) -> bool:
    normalized = normalize_cta(value)
    return normalized in ACTION_CTAS


def is_conversational_cta(value: object) -> bool:
    normalized = normalize_cta(value)
    return normalized in CONVERSATIONAL_CTAS


def is_pending_cta(value: object) -> bool:
    normalized = normalize_cta(value)
    return normalized in PENDING_CTAS


def normalize_short_reply_kind(text: str) -> ShortReplyKind | None:
    normalized = normalize_short_reply_text(text)
    if normalized is None:
        return None
    if normalized in AFFIRMATIVE_REPLIES:
        return "affirmative"
    if normalized in NEGATIVE_REPLIES:
        return "negative"
    return None


def normalize_short_reply_language(text: str) -> LanguageHint:
    normalized = normalize_short_reply_text(text)
    if normalized is None:
        return "unknown"
    return SHORT_REPLY_LANGUAGES.get(normalized, "unknown")


def normalize_short_reply_text(text: str) -> str | None:
    normalized = " ".join(str(text).strip().lower().split())
    return normalized or None
