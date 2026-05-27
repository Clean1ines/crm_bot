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

KnowledgePreprocessingMode: TypeAlias = Literal["faq", "price_list"]

MODE_FAQ: KnowledgePreprocessingMode = "faq"
MODE_PRICE_LIST: KnowledgePreprocessingMode = "price_list"

ALLOWED_KNOWLEDGE_PREPROCESSING_MODES: frozenset[str] = frozenset(
    {MODE_FAQ, MODE_PRICE_LIST}
)

PREPROCESSING_STATUS_NOT_REQUESTED = "not_requested"
PREPROCESSING_STATUS_PROCESSING = "processing"
PREPROCESSING_STATUS_COMPLETED = "completed"
PREPROCESSING_STATUS_FAILED = "failed"

PROMPT_VERSION_FAQ = "knowledge_answer_compiler_faq_v1"
PROMPT_VERSION_PRICE_LIST = "knowledge_preprocess_price_list_v2"
ANSWER_RESOLUTION_PROMPT_VERSION = "knowledge_answer_resolution_v1"

AnswerResolutionDecisionAction: TypeAlias = Literal["merge", "keep_separate"]
AnswerResolutionAction: TypeAlias = Literal[
    "merge", "keep_separate", "conflict", "needs_review"
]
ANSWER_RESOLUTION_ACTION_MERGE = "merge"
ANSWER_RESOLUTION_ACTION_KEEP_SEPARATE = "keep_separate"
ANSWER_RESOLUTION_ACTION_CONFLICT = "conflict"
ANSWER_RESOLUTION_ACTION_NEEDS_REVIEW = "needs_review"
ANSWER_RESOLUTION_FORBIDDEN_OUTPUT_FIELDS: frozenset[str] = frozenset(
    {
        "candidate_ids",
        "group_id",
        "questions",
        "synonyms",
        "tags",
        "source_refs",
        "source_chunk_indexes",
        "source_excerpt",
        "embedding_text",
        "metadata",
        "cards",
        "entries",
        "canonical" + "_card",
    }
)


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
    canonical_question: str = ""
    source_chunk_indexes: tuple[int, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class KnowledgePreprocessingResult:
    mode: KnowledgePreprocessingMode
    prompt_version: str
    model: str
    entries: tuple[KnowledgePreprocessingEntry, ...]
    metrics: JsonObject = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class KnowledgePreprocessingExecutionResult:
    result: KnowledgePreprocessingResult
    usage: ModelUsageMeasurement | None = None


@dataclass(frozen=True, slots=True)
class KnowledgeAnswerResolutionOption:
    id: str
    answer: str
    source_excerpt: str = ""

    def to_payload(self) -> JsonObject:
        return {
            "id": self.id,
            "answer": self.answer,
            "source_excerpt": self.source_excerpt,
        }


@dataclass(frozen=True, slots=True)
class KnowledgeAnswerResolutionCandidate:
    candidate_id: str
    answer: str
    source_excerpt: str = ""

    def to_answer_resolution_option(self) -> KnowledgeAnswerResolutionOption:
        return KnowledgeAnswerResolutionOption(
            id=self.candidate_id,
            answer=self.answer,
            source_excerpt=self.source_excerpt,
        )

    def to_payload(self) -> JsonObject:
        return self.to_answer_resolution_option().to_payload()


@dataclass(frozen=True, slots=True)
class KnowledgeAnswerResolutionCase:
    case_id: str
    candidates: tuple[KnowledgeAnswerResolutionCandidate, ...]
    question_intent: str = ""
    expected_answer_language: str = ""

    @property
    def group_id(self) -> str:
        return self.case_id

    def to_payload(self) -> JsonObject:
        return {
            "case_id": self.case_id,
            "question_intent": self.question_intent,
            "expected_answer_language": self.expected_answer_language,
            "answers": [
                candidate.to_answer_resolution_option().to_payload()
                for candidate in self.candidates
            ],
        }


@dataclass(frozen=True, slots=True)
class KnowledgeAnswerResolutionDecision:
    case_id: str
    action: AnswerResolutionDecisionAction
    candidate_ids: tuple[str, ...]
    canonical_answer: str = ""
    reason: str = ""
    confidence: float = 0.0

    @property
    def group_id(self) -> str:
        return self.case_id

    @property
    def is_merge(self) -> bool:
        return self.action == ANSWER_RESOLUTION_ACTION_MERGE


@dataclass(frozen=True, slots=True)
class KnowledgeAnswerResolutionResult:
    mode: KnowledgePreprocessingMode
    prompt_version: str
    model: str
    decisions: tuple[KnowledgeAnswerResolutionDecision, ...]
    metrics: JsonObject = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class KnowledgeAnswerResolverExecutionResult:
    result: KnowledgeAnswerResolutionResult
    usage: ModelUsageMeasurement | None = None


def entry_kind_for_preprocessing_mode(
    mode: KnowledgePreprocessingMode,
) -> KnowledgeEntryKind:
    if mode == MODE_FAQ:
        return KnowledgeEntryKind.FAQ_ANSWER
    if mode == MODE_PRICE_LIST:
        return KnowledgeEntryKind.PRICE_ANSWER
    raise KnowledgePreprocessingValidationError(
        f"Unsupported knowledge preprocessing mode: {mode}"
    )


def normalize_preprocessing_mode(value: object) -> KnowledgePreprocessingMode:
    mode = str(value or MODE_FAQ).strip().lower()
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
    raise KnowledgePreprocessingValidationError(
        f"Unsupported knowledge preprocessing mode: {mode}"
    )


def parse_preprocessing_payload(
    payload: object,
    *,
    mode: KnowledgePreprocessingMode,
    model: str,
    prompt_version: str,
) -> KnowledgePreprocessingResult:
    if mode == MODE_FAQ:
        raise KnowledgePreprocessingValidationError(
            "Legacy fragments parser is forbidden for mode=faq; use retrieval surface compiler"
        )
    parsed = _coerce_json_object(payload, "Preprocessing")
    entries_payload = parsed.get("fragments")
    if not isinstance(entries_payload, list):
        raise KnowledgePreprocessingValidationError(
            "Preprocessing payload must contain fragments[]"
        )

    entries: list[KnowledgePreprocessingEntry] = []
    for index, item in enumerate(entries_payload):
        if not isinstance(item, Mapping):
            raise KnowledgePreprocessingValidationError(
                f"Fragment {index} must be an object"
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


def parse_answer_resolution_payload(
    payload: object,
    *,
    mode: KnowledgePreprocessingMode,
    model: str,
    prompt_version: str = ANSWER_RESOLUTION_PROMPT_VERSION,
    max_answer_chars: int = 2400,
) -> KnowledgeAnswerResolutionResult:
    if isinstance(payload, str):
        parsed = _loads_json_object(payload)
    elif isinstance(payload, Mapping):
        parsed = payload
    else:
        raise KnowledgePreprocessingValidationError(
            "Answer resolution payload must be a JSON object"
        )

    decisions_payload = parsed.get("decisions")
    if not isinstance(decisions_payload, list):
        raise KnowledgePreprocessingValidationError(
            "Answer resolution payload must contain decisions[]"
        )

    decisions: list[KnowledgeAnswerResolutionDecision] = []
    for index, item in enumerate(decisions_payload):
        if not isinstance(item, Mapping):
            raise KnowledgePreprocessingValidationError(
                f"Answer resolution decision {index} must be an object"
            )
        decisions.append(
            _parse_answer_resolution_decision(
                item,
                index=index,
                max_answer_chars=max_answer_chars,
            )
        )

    metrics = parsed.get("metrics")
    return KnowledgeAnswerResolutionResult(
        mode=mode,
        prompt_version=prompt_version,
        model=model,
        decisions=tuple(decisions),
        metrics=_json_object_from_mapping(metrics)
        if isinstance(metrics, Mapping)
        else {},
    )


def _parse_answer_resolution_decision(
    payload: Mapping[object, object],
    *,
    index: int,
    max_answer_chars: int,
) -> KnowledgeAnswerResolutionDecision:
    forbidden_fields = sorted(
        str(key)
        for key in payload
        if str(key) in ANSWER_RESOLUTION_FORBIDDEN_OUTPUT_FIELDS
    )
    if forbidden_fields:
        raise KnowledgePreprocessingValidationError(
            f"Answer resolution decision {index} contains forbidden fields: "
            f"{', '.join(forbidden_fields)}"
        )

    case_id = _required_text(payload, "case_id", index=index)
    raw_action = _required_answer_resolution_action(payload.get("action"), index=index)
    action = cast(
        AnswerResolutionDecisionAction,
        ANSWER_RESOLUTION_ACTION_MERGE
        if raw_action == ANSWER_RESOLUTION_ACTION_MERGE
        else ANSWER_RESOLUTION_ACTION_KEEP_SEPARATE,
    )
    canonical_answer = _optional_text(payload.get("canonical_answer"))
    reason = _optional_text(payload.get("reason"))
    confidence = _clamped_float(payload.get("confidence"))

    if action == ANSWER_RESOLUTION_ACTION_MERGE and not canonical_answer:
        raise KnowledgePreprocessingValidationError(
            f"Answer resolution decision {index} missing canonical_answer"
        )

    if len(canonical_answer) > max_answer_chars:
        canonical_answer = canonical_answer[:max_answer_chars].rstrip()

    return KnowledgeAnswerResolutionDecision(
        case_id=case_id,
        action=action,
        candidate_ids=(),
        canonical_answer=canonical_answer,
        reason=reason,
        confidence=confidence,
    )


def _json_object_from_mapping(value: Mapping[object, object]) -> JsonObject:
    return {str(key): json_value_from_unknown(item) for key, item in value.items()}


def build_embedding_text(entry: KnowledgePreprocessingEntry) -> str:
    parts = [
        entry.title,
        entry.canonical_question,
        " ".join(entry.questions),
        " ".join(entry.synonyms),
        " ".join(entry.tags),
        entry.answer,
    ]
    return _compact_text(" ".join(part for part in parts if part))


def _coerce_json_object(payload: object, label: str) -> Mapping[str, object]:
    if isinstance(payload, str):
        return _loads_json_object(payload)
    if isinstance(payload, Mapping):
        return payload
    raise KnowledgePreprocessingValidationError(
        f"{label} payload must be a JSON object"
    )


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
    variants = _string_list(payload.get("question_variants"))
    canonical_question = _optional_text(payload.get("canonical_question"))
    if not canonical_question and variants:
        canonical_question = variants[0]
    title = _optional_text(payload.get("title")) or canonical_question
    if not canonical_question:
        canonical_question = title
    answer = _optional_text(payload.get("answer_fragment")) or _required_text(
        payload, "answer", index=index
    )
    source_excerpt = _required_text(payload, "source_excerpt", index=index)

    questions = _dedupe_texts((canonical_question, *variants))
    synonyms = _dedupe_texts(_string_list(payload.get("synonyms")))
    tags: tuple[str, ...] = ()
    source_chunk_indexes = tuple(
        _non_negative_ints(payload.get("source_chunk_indexes"))
    )
    if mode == MODE_PRICE_LIST:
        _reject_price_list_noisy_synonyms(synonyms or questions, index=index)

    entry = KnowledgePreprocessingEntry(
        title=title,
        answer=answer,
        source_excerpt=source_excerpt,
        questions=questions,
        synonyms=synonyms,
        tags=tags,
        embedding_text="",
        canonical_question=canonical_question,
        source_chunk_indexes=source_chunk_indexes,
    )
    return KnowledgePreprocessingEntry(
        title=entry.title,
        answer=entry.answer,
        source_excerpt=entry.source_excerpt,
        questions=entry.questions,
        synonyms=entry.synonyms,
        tags=entry.tags,
        embedding_text=build_embedding_text(entry),
        canonical_question=entry.canonical_question,
        source_chunk_indexes=entry.source_chunk_indexes,
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


def _clamped_float(value: object) -> float:
    parsed: float
    if isinstance(value, bool) or value is None:
        return 0.0
    if isinstance(value, int | float):
        parsed = float(value)
    elif isinstance(value, str):
        try:
            parsed = float(value.strip())
        except ValueError:
            return 0.0
    else:
        return 0.0
    return max(0.0, min(1.0, parsed))


def _required_answer_resolution_action(
    value: object,
    *,
    index: int,
) -> AnswerResolutionAction:
    action = _optional_text(value)
    if action in {
        ANSWER_RESOLUTION_ACTION_MERGE,
        ANSWER_RESOLUTION_ACTION_KEEP_SEPARATE,
        ANSWER_RESOLUTION_ACTION_CONFLICT,
        ANSWER_RESOLUTION_ACTION_NEEDS_REVIEW,
    }:
        return cast(AnswerResolutionAction, action)

    raise KnowledgePreprocessingValidationError(
        f"Answer resolution decision {index} has unsupported action: {action}"
    )


def _required_answer_resolution_decision_action(
    value: object,
    *,
    index: int,
) -> AnswerResolutionDecisionAction:
    action = _optional_text(value)
    if action in {
        ANSWER_RESOLUTION_ACTION_MERGE,
        ANSWER_RESOLUTION_ACTION_KEEP_SEPARATE,
    }:
        return cast(AnswerResolutionDecisionAction, action)

    raise KnowledgePreprocessingValidationError(
        f"Answer resolution decision {index} has unsupported action: {action}"
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


def _dedupe_texts(values: Sequence[str]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _compact_text(value)
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            result.append(text)
    return tuple(result)


def _non_negative_ints(value: object) -> list[int]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        return []
    result: list[int] = []
    for item in value:
        if isinstance(item, bool):
            continue
        if isinstance(item, int) and item >= 0 and item not in result:
            result.append(item)
    return result
