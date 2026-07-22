"""Deterministic explicit human-handoff request detection."""

from __future__ import annotations

import re


_RU_EXPLICIT_PATTERNS = (
    r"\bпозов(?:и|ите)?\s+(?:мне\s+)?(?:менеджера|оператора|живого\s+человека)\b",
    r"\b(?:хочу|нужно|нужен|нужна|нужны|требуется)\s+(?:поговорить\s+с\s+)?(?:менеджер(?:ом|а)?|оператор(?:ом|а)?|жив(?:ой|ого)\s+человек(?:а|ом)?)\b",
    r"\b(?:соедини|соедините|переключи|переключите)\s+(?:меня\s+)?(?:с|на)\s+(?:менеджер(?:ом|а)?|оператор(?:ом|а)?|(?:жив(?:ым|ого)\s+)?человек(?:ом|а)?)\b",
    r"\b(?:передай|передайте)\s+(?:мой\s+)?(?:вопрос|диалог|чат|обращение)\s+(?:менеджеру|оператору|человеку)\b",
    r"\bможно\s+(?:связаться|поговорить)\s+с\s+(?:менеджер(?:ом)?|оператор(?:ом)?|человек(?:ом)?)\b",
)

_EN_EXPLICIT_PATTERNS = (
    r"\bcall\s+(?:a\s+)?(?:manager|operator|human)\b",
    r"\bconnect\s+me\s+(?:to|with)\s+(?:(?:a|an)\s+)?(?:manager|operator|human)\b",
    r"\b(?:i\s+)?want\s+to\s+(?:speak|talk)\s+to\s+(?:(?:a|an)\s+)?(?:manager|operator|human)\b",
    r"\b(?:i\s+)?need\s+(?:(?:a|an)\s+)?(?:manager|operator|human)\b",
    r"\btalk\s+to\s+(?:(?:a|an)\s+)?(?:manager|operator|human)\b",
    r"\btransfer\s+(?:me|this|the\s+question)\s+to\s+(?:(?:a|an)\s+)?(?:manager|operator|human)\b",
    r"\bcould\s+i\s+(?:speak|talk)\s+to\s+(?:(?:a|an)\s+)?(?:manager|operator|human)\b",
    r"\bcan\s+you\s+connect\s+me\s+with\s+(?:(?:a|an)\s+)?(?:manager|operator|human)\b",
    r"\bget\s+me\s+(?:(?:a|an)\s+)?(?:manager|operator|human)\b",
)

_RU_NATURAL_EXPLICIT_PATTERNS = (
    r"\b(?:а\s+)?можно\s+(?:позвать\s+)?(?:менеджера|оператора|человека)\??$",
    r"\bдайте\s+(?:мне\s+)?(?:менеджера|оператора|живого\s+человека)\b",
    r"\bсоедините,\s*пожалуйста,\s*с\s+(?:менеджером|оператором|человеком)\b",
    r"\bхочу\s+живого\s+(?:оператора|человека)\b",
)

_NEGATIVE_HANDOFF_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bне\s+зови(?:те)?\s+(?:менеджера|оператора|человека)\b",
        r"\bне\s+(?:соединяй|соединяйте|переключай|переключайте)\s+(?:меня\s+)?(?:с|на)\s+(?:менеджер(?:ом|а)?|оператор(?:ом|а)?|человек(?:ом|а)?)\b",
        r"\bне\s+хочу\s+(?:говорить|поговорить|разговаривать)\s+с\s+(?:менеджером|оператором|человеком)\b",
        r"\bне\s+(?:нужно|надо)\s+(?:звать|вызывать|соединять|переключать)\s+(?:меня\s+)?(?:с\s+|на\s+)?(?:менеджер(?:ом|а)?|оператор(?:ом|а)?|человек(?:ом|а)?)\b",
        r"\b(?:менеджера|оператора|человека)\s+звать\s+не\s+нужно\b",
        r"\bне\s+хочу\s+говорить\s+с\s+(?:менеджером|оператором|человеком)\b",
        r"\bбез\s+(?:менеджера|оператора|человека),?\s*пожалуйста\b",
        r"\bi\s+(?:do\s+not|don't)\s+want\s+to\s+(?:speak|talk)\s+to\s+(?:(?:a|an)\s+)?(?:manager|operator|human)\b",
        r"\bi\s+(?:do\s+not|don't)\s+want\s+(?:(?:a|an)\s+)?(?:manager|operator|human)\b",
        r"\bi\s+(?:do\s+not|don't)\s+need\s+(?:(?:a|an)\s+)?(?:manager|operator|human)\b",
        r"\b(?:do\s+not|don't)\s+(?:call|connect|get|transfer)\s+(?:me\s+)?(?:to\s+)?(?:(?:a|an)\s+)?(?:manager|operator|human)\b",
        r"\bplease\s+(?:do\s+not|don't)\s+(?:call|connect|get|transfer)\s+(?:me\s+)?(?:to\s+)?(?:(?:a|an)\s+)?(?:manager|operator|human)\b",
        r"\bno\s+need\s+to\s+call\s+(?:(?:a|an)\s+)?(?:manager|operator|human)\b",
    )
)

_EXPLICIT_HANDOFF_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in _RU_EXPLICIT_PATTERNS
    + _RU_NATURAL_EXPLICIT_PATTERNS
    + _EN_EXPLICIT_PATTERNS
)


def _normalize_text(text: str) -> str:
    return " ".join(str(text).replace("ё", "е").replace("’", "'").lower().split())


def is_explicit_handoff_request(text: str) -> bool:
    """Return True only for action requests to involve a human/manager."""
    normalized = _normalize_text(text)
    if not normalized:
        return False

    if any(pattern.search(normalized) for pattern in _NEGATIVE_HANDOFF_PATTERNS):
        return False

    return any(pattern.search(normalized) for pattern in _EXPLICIT_HANDOFF_PATTERNS)
