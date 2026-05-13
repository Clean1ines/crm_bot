from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Literal, Mapping, Sequence, TypeAlias, cast

from src.domain.project_plane.json_types import JsonObject, json_value_from_unknown
from src.domain.project_plane.knowledge_compilation import KnowledgeEntryKind
from src.domain.project_plane.model_usage_views import ModelUsageMeasurement
from src.domain.project_plane.knowledge_semantic_markers import (
    BROAD_NOISY_PRICE_SYNONYMS,
)

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

PROMPT_VERSION_FAQ = "knowledge_preprocess_faq_v2"
PROMPT_VERSION_PRICE_LIST = "knowledge_preprocess_price_list_v2"
PROMPT_VERSION_INSTRUCTION = "knowledge_preprocess_instruction_v2"
SEMANTIC_MERGE_TIGHTENING_PROMPT_VERSION = "knowledge_semantic_merge_tightening_v1"

SemanticMergeAction: TypeAlias = Literal["merge", "keep_separate"]
SEMANTIC_MERGE_ACTION_MERGE = "merge"
SEMANTIC_MERGE_ACTION_KEEP_SEPARATE = "keep_separate"


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

    def to_chunk(self, *, entry_kind: KnowledgeEntryKind) -> JsonObject:
        return {
            "content": self.answer,
            "entry_kind": entry_kind.value,
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
        entry_kind = entry_kind_for_preprocessing_mode(self.mode)
        return [entry.to_chunk(entry_kind=entry_kind) for entry in self.entries]


@dataclass(frozen=True, slots=True)
class KnowledgePreprocessingExecutionResult:
    result: KnowledgePreprocessingResult
    usage: ModelUsageMeasurement | None = None


@dataclass(frozen=True, slots=True)
class KnowledgeEmbeddingTextMergeExecutionResult:
    embedding_text: str
    usage: ModelUsageMeasurement | None = None


@dataclass(frozen=True, slots=True)
class KnowledgeSemanticMergeCandidate:
    candidate_id: str
    title: str
    answer: str
    embedding_text: str
    questions: tuple[str, ...] = field(default_factory=tuple)
    synonyms: tuple[str, ...] = field(default_factory=tuple)
    tags: tuple[str, ...] = field(default_factory=tuple)
    source_ref_count: int = 0

    def to_payload(self) -> JsonObject:
        return {
            "candidate_id": self.candidate_id,
            "title": self.title,
            "answer": self.answer,
            "embedding_text": self.embedding_text,
            "questions": list(self.questions),
            "synonyms": list(self.synonyms),
            "tags": list(self.tags),
            "source_ref_count": self.source_ref_count,
        }


@dataclass(frozen=True, slots=True)
class KnowledgeSemanticMergeGroup:
    group_id: str
    candidates: tuple[KnowledgeSemanticMergeCandidate, ...]

    def to_payload(self) -> JsonObject:
        return {
            "group_id": self.group_id,
            "candidates": [candidate.to_payload() for candidate in self.candidates],
        }


@dataclass(frozen=True, slots=True)
class KnowledgeSemanticMergeDecision:
    group_id: str
    action: SemanticMergeAction
    candidate_ids: tuple[str, ...]
    survivor_title: str = ""
    merged_embedding_text: str = ""

    @property
    def is_merge(self) -> bool:
        return self.action == SEMANTIC_MERGE_ACTION_MERGE


@dataclass(frozen=True, slots=True)
class KnowledgeSemanticMergeTighteningResult:
    mode: KnowledgePreprocessingMode
    prompt_version: str
    model: str
    decisions: tuple[KnowledgeSemanticMergeDecision, ...]
    metrics: JsonObject = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class KnowledgeSemanticMergeExecutionResult:
    result: KnowledgeSemanticMergeTighteningResult
    usage: ModelUsageMeasurement | None = None


def entry_kind_for_preprocessing_mode(
    mode: KnowledgePreprocessingMode,
) -> KnowledgeEntryKind:
    if mode == MODE_FAQ:
        return KnowledgeEntryKind.FAQ_ANSWER
    if mode == MODE_PRICE_LIST:
        return KnowledgeEntryKind.PRICE_ANSWER
    if mode == MODE_INSTRUCTION:
        return KnowledgeEntryKind.PROCEDURE
    return KnowledgeEntryKind.ANSWER


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


def parse_embedding_text_merge_payload(
    payload: object,
    *,
    max_chars: int = 2400,
) -> str:
    if isinstance(payload, str):
        parsed = _loads_json_object(payload)
    elif isinstance(payload, Mapping):
        parsed = payload
    else:
        raise KnowledgePreprocessingValidationError(
            "Embedding text merge payload must be a JSON object"
        )

    raw_embedding_text = parsed.get("embedding_text")
    if not isinstance(raw_embedding_text, str):
        raise KnowledgePreprocessingValidationError(
            "Embedding text merge payload must contain embedding_text"
        )

    embedding_text = _compact_text(raw_embedding_text)
    if not embedding_text:
        raise KnowledgePreprocessingValidationError(
            "Embedding text merge payload contains empty embedding_text"
        )

    if len(embedding_text) > max_chars:
        return embedding_text[:max_chars].rstrip()

    return embedding_text


def parse_semantic_merge_tightening_payload(
    payload: object,
    *,
    mode: KnowledgePreprocessingMode,
    model: str,
    prompt_version: str = SEMANTIC_MERGE_TIGHTENING_PROMPT_VERSION,
    max_embedding_text_chars: int = 2400,
) -> KnowledgeSemanticMergeTighteningResult:
    if isinstance(payload, str):
        parsed = _loads_json_object(payload)
    elif isinstance(payload, Mapping):
        parsed = payload
    else:
        raise KnowledgePreprocessingValidationError(
            "Semantic merge tightening payload must be a JSON object"
        )

    decisions_payload = parsed.get("decisions")
    if not isinstance(decisions_payload, list):
        raise KnowledgePreprocessingValidationError(
            "Semantic merge tightening payload must contain decisions[]"
        )

    decisions: list[KnowledgeSemanticMergeDecision] = []
    for index, item in enumerate(decisions_payload):
        if not isinstance(item, Mapping):
            raise KnowledgePreprocessingValidationError(
                f"Semantic merge decision {index} must be an object"
            )
        decisions.append(
            _parse_semantic_merge_decision(
                item,
                index=index,
                max_embedding_text_chars=max_embedding_text_chars,
            )
        )

    metrics = parsed.get("metrics")
    return KnowledgeSemanticMergeTighteningResult(
        mode=mode,
        prompt_version=prompt_version,
        model=model,
        decisions=tuple(decisions),
        metrics=_json_object_from_mapping(metrics)
        if isinstance(metrics, Mapping)
        else {},
    )


def _parse_semantic_merge_decision(
    payload: Mapping[object, object],
    *,
    index: int,
    max_embedding_text_chars: int,
) -> KnowledgeSemanticMergeDecision:
    group_id = _required_text(payload, "group_id", index=index)
    action = _required_semantic_merge_action(payload.get("action"), index=index)
    candidate_ids = tuple(_string_list(payload.get("candidate_ids")))

    if not candidate_ids:
        raise KnowledgePreprocessingValidationError(
            f"Semantic merge decision {index} must contain candidate_ids[]"
        )

    survivor_title = _optional_text(payload.get("survivor_title"))
    merged_embedding_text = _optional_text(payload.get("merged_embedding_text"))

    if action == SEMANTIC_MERGE_ACTION_MERGE:
        if len(candidate_ids) < 2:
            raise KnowledgePreprocessingValidationError(
                f"Semantic merge decision {index} must merge at least 2 candidates"
            )
        if not survivor_title:
            raise KnowledgePreprocessingValidationError(
                f"Semantic merge decision {index} missing survivor_title"
            )
        if not merged_embedding_text:
            raise KnowledgePreprocessingValidationError(
                f"Semantic merge decision {index} missing merged_embedding_text"
            )

    if len(merged_embedding_text) > max_embedding_text_chars:
        merged_embedding_text = merged_embedding_text[
            :max_embedding_text_chars
        ].rstrip()

    return KnowledgeSemanticMergeDecision(
        group_id=group_id,
        action=action,
        candidate_ids=candidate_ids,
        survivor_title=survivor_title,
        merged_embedding_text=merged_embedding_text,
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
    _validate_query_surface(entry, mode=mode, index=index)

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


def _validate_query_surface(
    entry: KnowledgePreprocessingEntry,
    *,
    mode: KnowledgePreprocessingMode,
    index: int,
) -> None:
    """Require dense query surface from LLM preprocessing.

    This is intentionally enforced at the domain boundary because weak LLM
    output silently degrades retrieval quality for arbitrary customer phrasing.
    The generated phrases may paraphrase user intent, but must remain grounded
    in the source-backed entry.
    """

    min_questions = 3
    min_synonyms = 5
    min_tags = 2

    if len(entry.questions) < min_questions:
        raise KnowledgePreprocessingValidationError(
            f"Entry {index} in mode={mode} must contain at least "
            f"{min_questions} grounded questions"
        )

    if len(entry.synonyms) < min_synonyms:
        raise KnowledgePreprocessingValidationError(
            f"Entry {index} in mode={mode} must contain at least "
            f"{min_synonyms} grounded synonyms"
        )

    if len(entry.tags) < min_tags:
        raise KnowledgePreprocessingValidationError(
            f"Entry {index} in mode={mode} must contain at least "
            f"{min_tags} topical tags"
        )


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


def _required_semantic_merge_action(
    value: object,
    *,
    index: int,
) -> SemanticMergeAction:
    action = _optional_text(value)
    if action in {
        SEMANTIC_MERGE_ACTION_MERGE,
        SEMANTIC_MERGE_ACTION_KEEP_SEPARATE,
    }:
        return cast(SemanticMergeAction, action)

    raise KnowledgePreprocessingValidationError(
        f"Semantic merge decision {index} has unsupported action: {action}"
    )


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


def _reject_price_list_noisy_synonyms(
    synonyms: tuple[str, ...],
    *,
    index: int,
) -> None:
    normalized = {_compact_text(item.lower()) for item in synonyms}
    forbidden = sorted(BROAD_NOISY_PRICE_SYNONYMS & normalized)
    if forbidden:
        raise KnowledgePreprocessingValidationError(
            f"Price list entry {index} contains broad noisy synonyms: {', '.join(forbidden)}"
        )
