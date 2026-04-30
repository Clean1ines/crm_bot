from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Literal, Mapping, Sequence, TypeAlias, cast

from src.domain.project_plane.json_types import JsonObject, json_value_from_unknown

KnowledgePreprocessingMode: TypeAlias = Literal[
    "plain", "faq", "price_list", "instruction"
]

MODE_PLAIN = "plain"
MODE_FAQ = "faq"
MODE_PRICE_LIST = "price_list"
MODE_INSTRUCTION = "instruction"

ALLOWED_KNOWLEDGE_PREPROCESSING_MODES: frozenset[str] = frozenset(
    {MODE_PLAIN, MODE_FAQ, MODE_PRICE_LIST, MODE_INSTRUCTION}
)

PREPROCESSING_STATUS_NOT_REQUESTED = "not_requested"
PREPROCESSING_STATUS_PROCESSING = "processing"
PREPROCESSING_STATUS_COMPLETED = "completed"
PREPROCESSING_STATUS_FAILED = "failed"

PROMPT_VERSION_FAQ = "knowledge_preprocess_faq_v1"
PROMPT_VERSION_PRICE_LIST = "knowledge_preprocess_price_list_v1"
PROMPT_VERSION_INSTRUCTION = "knowledge_preprocess_instruction_v1"


class KnowledgePreprocessingValidationError(ValueError):
    """Raised when LLM preprocessing output is not safe to persist."""


@dataclass(frozen=True, slots=True)
class KnowledgePreprocessingEntry:
    title: str
    answer: str
    source_excerpt: str
    questions: tuple[str, ...] = field(default_factory=tuple)
    synonyms: tuple[str, ...] = field(default_factory=tuple)
    tags: tuple[str, ...] = field(default_factory=tuple)
    embedding_text: str = ""

    def to_chunk(self, *, entry_type: str) -> JsonObject:
        return {
            "content": self.answer,
            "entry_type": entry_type,
            "title": self.title,
            "source_excerpt": self.source_excerpt,
            "questions": list(self.questions),
            "synonyms": list(self.synonyms),
            "tags": list(self.tags),
            "embedding_text": self.embedding_text or build_embedding_text(self),
        }


@dataclass(frozen=True, slots=True)
class KnowledgePreprocessingResult:
    mode: KnowledgePreprocessingMode
    prompt_version: str
    model: str
    entries: tuple[KnowledgePreprocessingEntry, ...]
    metrics: JsonObject = field(default_factory=dict)

    def to_chunks(self) -> list[JsonObject]:
        return [entry.to_chunk(entry_type=self.mode) for entry in self.entries]


def normalize_preprocessing_mode(value: object) -> KnowledgePreprocessingMode:
    mode = str(value or MODE_PLAIN).strip().lower()
    if mode not in ALLOWED_KNOWLEDGE_PREPROCESSING_MODES:
        allowed = ", ".join(sorted(ALLOWED_KNOWLEDGE_PREPROCESSING_MODES))
        raise KnowledgePreprocessingValidationError(
            f"Unsupported knowledge preprocessing mode: {mode}. Allowed: {allowed}"
        )
    return cast(KnowledgePreprocessingMode, mode)


def prompt_version_for_mode(mode: KnowledgePreprocessingMode) -> str:
    if mode == MODE_FAQ:
        return PROMPT_VERSION_FAQ
    if mode == MODE_PRICE_LIST:
        return PROMPT_VERSION_PRICE_LIST
    if mode == MODE_INSTRUCTION:
        return PROMPT_VERSION_INSTRUCTION
    return "plain"


def parse_preprocessing_payload(
    payload: object,
    *,
    mode: KnowledgePreprocessingMode,
    model: str,
    prompt_version: str,
) -> KnowledgePreprocessingResult:
    if isinstance(payload, str):
        parsed = _loads_json_object(payload)
    elif isinstance(payload, Mapping):
        parsed = payload
    else:
        raise KnowledgePreprocessingValidationError(
            "Preprocessing payload must be a JSON object"
        )

    entries_payload = parsed.get("entries")
    if not isinstance(entries_payload, list):
        raise KnowledgePreprocessingValidationError(
            "Preprocessing payload must contain entries[]"
        )

    entries: list[KnowledgePreprocessingEntry] = []
    for index, item in enumerate(entries_payload):
        if not isinstance(item, Mapping):
            raise KnowledgePreprocessingValidationError(
                f"Entry {index} must be an object"
            )
        entries.append(_parse_entry(item, mode=mode, index=index))

    metrics = parsed.get("metrics")
    return KnowledgePreprocessingResult(
        mode=mode,
        prompt_version=prompt_version,
        model=model,
        entries=tuple(entries),
        metrics=_json_object_from_mapping(metrics)
        if isinstance(metrics, Mapping)
        else {},
    )


def _json_object_from_mapping(value: Mapping[object, object]) -> JsonObject:
    return {str(key): json_value_from_unknown(item) for key, item in value.items()}


def build_embedding_text(entry: KnowledgePreprocessingEntry) -> str:
    parts = [
        entry.title,
        entry.answer,
        entry.source_excerpt,
        " ".join(entry.questions),
        " ".join(entry.synonyms),
        " ".join(entry.tags),
    ]
    return _compact_text(" ".join(part for part in parts if part))


def _loads_json_object(text: str) -> Mapping[str, object]:
    cleaned = _strip_json_fence(text)
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise KnowledgePreprocessingValidationError(
            f"Invalid preprocessing JSON: {exc}"
        ) from exc

    if not isinstance(payload, Mapping):
        raise KnowledgePreprocessingValidationError(
            "Preprocessing JSON root must be an object"
        )
    return cast(Mapping[str, object], payload)


def _strip_json_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE)
        stripped = re.sub(r"\s*```$", "", stripped)
    return stripped.strip()


def _parse_entry(
    payload: Mapping[object, object],
    *,
    mode: KnowledgePreprocessingMode,
    index: int,
) -> KnowledgePreprocessingEntry:
    title = _required_text(payload, "title", index=index)
    answer = _required_text(payload, "answer", index=index)
    source_excerpt = _required_text(payload, "source_excerpt", index=index)

    questions = tuple(_string_list(payload.get("questions")))
    synonyms = tuple(_string_list(payload.get("synonyms")))
    tags = tuple(_string_list(payload.get("tags")))
    embedding_text = _optional_text(payload.get("embedding_text"))

    if mode == MODE_PRICE_LIST:
        _reject_price_list_noisy_synonyms(synonyms, index=index)

    entry = KnowledgePreprocessingEntry(
        title=title,
        answer=answer,
        source_excerpt=source_excerpt,
        questions=questions,
        synonyms=synonyms,
        tags=tags,
        embedding_text=embedding_text,
    )

    if not entry.embedding_text:
        return KnowledgePreprocessingEntry(
            title=entry.title,
            answer=entry.answer,
            source_excerpt=entry.source_excerpt,
            questions=entry.questions,
            synonyms=entry.synonyms,
            tags=entry.tags,
            embedding_text=build_embedding_text(entry),
        )

    return entry


def _required_text(
    payload: Mapping[object, object],
    key: str,
    *,
    index: int,
) -> str:
    text = _optional_text(payload.get(key))
    if not text:
        raise KnowledgePreprocessingValidationError(
            f"Entry {index} missing required field: {key}"
        )
    return text


def _optional_text(value: object) -> str:
    if isinstance(value, bool) or value is None:
        return ""
    if isinstance(value, str | int | float):
        return _compact_text(str(value))
    return ""


def _string_list(value: object) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        return []

    result: list[str] = []
    for item in value:
        text = _optional_text(item)
        if text:
            result.append(text)
    return result


def _compact_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _reject_price_list_noisy_synonyms(synonyms: tuple[str, ...], *, index: int) -> None:
    noisy = {
        "че по цене",
        "что по цене",
        "price pls",
        "price please",
        "скока",
        "сколько стоит",
        "how much this",
        "how much",
        "cost",
        "price",
        "pricing",
    }
    normalized = {_compact_text(item.lower()) for item in synonyms}
    forbidden = sorted(normalized & noisy)
    if forbidden:
        raise KnowledgePreprocessingValidationError(
            f"Price list entry {index} contains broad noisy synonyms: {', '.join(forbidden)}"
        )
