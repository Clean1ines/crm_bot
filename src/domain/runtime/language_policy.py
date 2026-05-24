from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Literal

SupportedLanguage = Literal["ru", "en", "de", "es"]
LanguageHint = Literal["ru", "en", "de", "es", "unknown"]

SUPPORTED_LANGUAGES: tuple[SupportedLanguage, ...] = ("ru", "en", "de", "es")
_NEUTRAL_TOKENS = {"ai", "api", "crm", "saas", "rag", "llm", "telegram"}


@dataclass(frozen=True, slots=True)
class LanguagePolicyDecision:
    expected_language: LanguageHint
    actual_language: LanguageHint
    accepted: bool
    reason: str


def normalize_project_language(value: str | None) -> LanguageHint:
    normalized = (value or "").strip().lower()
    return normalized if normalized in SUPPORTED_LANGUAGES else "unknown"


def detect_language_hint(text: str) -> LanguageHint:
    compact = " ".join(text.strip().split())
    if not compact:
        return "unknown"

    tokenized = re.findall(r"[A-Za-zÀ-ÿА-Яа-яЁё]+", compact)
    tokens = [token for token in tokenized if token.lower() not in _NEUTRAL_TOKENS]
    signal_text = " ".join(tokens)

    cyr = len(re.findall(r"[А-Яа-яЁё]", signal_text))
    deu = len(re.findall(r"[ÄÖÜäöüß]", signal_text))
    esp = len(re.findall(r"[ÁÉÍÓÚÜÑáéíóúüñ]", signal_text))
    lat = len(re.findall(r"[A-Za-z]", signal_text)) + deu + esp

    total = cyr + lat
    if total < 6:
        return "unknown"
    if cyr / total >= 0.65:
        return "ru"
    if lat / total < 0.65:
        return "unknown"

    if deu >= 2 and deu >= esp + 1:
        return "de"
    if esp >= 2 and esp >= deu + 1:
        return "es"
    return "en"


def dominant_language(values: list[str]) -> LanguageHint:
    counts: dict[LanguageHint, int] = {"ru": 0, "en": 0, "de": 0, "es": 0, "unknown": 0}
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
