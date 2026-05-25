from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Literal

SupportedLanguage = Literal["ru", "en", "de", "es"]
LanguageHint = Literal["ru", "en", "de", "es", "unknown"]

SUPPORTED_LANGUAGES: tuple[SupportedLanguage, ...] = ("ru", "en", "de", "es")
_NEUTRAL_TOKENS = {"ai", "api", "crm", "saas", "rag", "llm", "telegram"}

_DE_STOPWORDS = {
    "und",
    "oder",
    "nicht",
    "ist",
    "sind",
    "mit",
    "für",
    "bitte",
    "ich",
    "wir",
    "sie",
    "dass",
    "kein",
    "eine",
    "einen",
    "dem",
    "den",
    "der",
    "die",
    "das",
}
_ES_STOPWORDS = {
    "que",
    "para",
    "con",
    "por",
    "como",
    "hola",
    "gracias",
    "necesito",
    "quiero",
    "puede",
    "pueden",
    "tiene",
    "tienen",
    "usted",
    "ustedes",
    "el",
    "la",
    "los",
    "las",
    "de",
}
_EN_STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "please",
    "hello",
    "thanks",
    "need",
    "want",
    "your",
    "you",
    "can",
    "does",
    "this",
    "that",
}


@dataclass(frozen=True, slots=True)
class LanguagePolicyDecision:
    expected_language: LanguageHint
    actual_language: LanguageHint
    accepted: bool
    reason: str


def normalize_project_language(value: str | None) -> LanguageHint:
    normalized = (value or "").strip().lower()
    return normalized if normalized in SUPPORTED_LANGUAGES else "unknown"


def _token_signal_counts(tokens: list[str]) -> tuple[int, int, int]:
    de_hits = sum(1 for token in tokens if token in _DE_STOPWORDS)
    es_hits = sum(1 for token in tokens if token in _ES_STOPWORDS)
    en_hits = sum(1 for token in tokens if token in _EN_STOPWORDS)
    return de_hits, es_hits, en_hits


def detect_language_hint(text: str) -> LanguageHint:
    compact = " ".join(text.strip().split())
    if not compact:
        return "unknown"

    tokenized = [
        token.lower() for token in re.findall(r"[A-Za-zÀ-ÿА-Яа-яЁё]+", compact)
    ]
    tokens = [token for token in tokenized if token not in _NEUTRAL_TOKENS]
    signal_text = " ".join(tokens)

    cyr = len(re.findall(r"[А-Яа-яЁё]", signal_text))
    deu_diacritics = len(re.findall(r"[ÄÖÜäöüß]", signal_text))
    esp_diacritics = len(re.findall(r"[ÁÉÍÓÚÜÑáéíóúüñ]", signal_text))
    lat = len(re.findall(r"[A-Za-z]", signal_text)) + deu_diacritics + esp_diacritics

    total = cyr + lat
    if total < 6:
        if cyr >= 3 and cyr >= lat:
            return "ru"
        return "unknown"
    if cyr / total >= 0.65:
        return "ru"
    if cyr >= 3 and cyr > lat:
        return "ru"
    if lat / total < 0.65:
        return "unknown"

    de_hits, es_hits, en_hits = _token_signal_counts(tokens)

    if deu_diacritics >= 2 and deu_diacritics >= esp_diacritics + 1:
        return "de"
    if esp_diacritics >= 2 and esp_diacritics >= deu_diacritics + 1:
        return "es"

    if de_hits >= 2 and de_hits > es_hits and de_hits > en_hits:
        return "de"
    if es_hits >= 2 and es_hits > de_hits and es_hits > en_hits:
        return "es"

    return "en"


def dominant_language(values: list[str]) -> LanguageHint:
    counts: dict[LanguageHint, int] = {
        "ru": 0,
        "en": 0,
        "de": 0,
        "es": 0,
        "unknown": 0,
    }
    for value in values:
        counts[detect_language_hint(value)] += 1

    known = {k: v for k, v in counts.items() if k != "unknown" and v > 0}
    if not known:
        return "unknown"
    sorted_items = sorted(known.items(), key=lambda item: item[1], reverse=True)
    top_lang, top_count = sorted_items[0]
    second_count = sorted_items[1][1] if len(sorted_items) > 1 else 0
    if top_count == second_count:
        return "unknown"
    known_total = sum(known.values())
    if top_count / known_total < 0.66:
        return "unknown"
    return top_lang


def validate_language(
    *, expected: LanguageHint, actual_text: str
) -> LanguagePolicyDecision:
    actual = detect_language_hint(actual_text)
    if expected == "unknown":
        return LanguagePolicyDecision(expected, actual, False, "expected_unknown")
    if actual == "unknown":
        return LanguagePolicyDecision(expected, actual, False, "actual_unknown")
    if expected != actual:
        return LanguagePolicyDecision(expected, actual, False, "mismatch")
    return LanguagePolicyDecision(expected, actual, True, "ok")
