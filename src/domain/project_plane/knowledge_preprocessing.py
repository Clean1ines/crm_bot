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

PROMPT_VERSION_FAQ = "knowledge_answer_compiler_faq_v1"
ANSWER_MERGE_PROMPT_VERSION = "knowledge_answer_merge_v1"
PROMPT_VERSION_PRICE_LIST = "knowledge_preprocess_price_list_v2"
PROMPT_VERSION_INSTRUCTION = "knowledge_preprocess_instruction_v2"
SEMANTIC_MERGE_TIGHTENING_PROMPT_VERSION = "knowledge_semantic_merge_tightening_v2"

SemanticMergeAction: TypeAlias = Literal["merge", "keep_separate"]
AnswerResolutionAction: TypeAlias = Literal[
    "merge", "keep_separate", "conflict", "needs_review"
]
SEMANTIC_MERGE_ACTION_MERGE = "merge"
SEMANTIC_MERGE_ACTION_KEEP_SEPARATE = "keep_separate"
ANSWER_RESOLUTION_ACTION_CONFLICT = "conflict"
ANSWER_RESOLUTION_ACTION_NEEDS_REVIEW = "needs_review"


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
    match_kind: Literal["new", "known"] = "new"
    known_intent_id: str = ""
    source_chunk_indexes: tuple[int, ...] = field(default_factory=tuple)

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
class KnowledgeAnswerMergeExecutionResult:
    merge_allowed: bool
    answer: str
    question_variants: tuple[str, ...] = field(default_factory=tuple)
    usage: ModelUsageMeasurement | None = None


@dataclass(frozen=True, slots=True)
class KnowledgeQuestionIntentCard:
    entry_id: str
    title: str
    primary_question: str
    question_samples: tuple[str, ...] = field(default_factory=tuple)
    answer_digest: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)

    def to_payload(self) -> JsonObject:
        return {
            "intent_id": self.entry_id,
            "canonical_question": self.primary_question,
            "question_variants": list(self.question_samples),
            "answer_digest": self.answer_digest,
        }


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
class KnowledgeAnswerResolutionCase:
    case_id: str
    question_intent: str
    answers: tuple[KnowledgeAnswerResolutionOption, ...]

    def to_payload(self) -> JsonObject:
        return {
            "case_id": self.case_id,
            "question_intent": self.question_intent,
            "answers": [answer.to_payload() for answer in self.answers],
        }


@dataclass(frozen=True, slots=True)
class KnowledgeAnswerResolutionDecision:
    case_id: str
    action: AnswerResolutionAction
    canonical_answer: str = ""
    reason: str = ""
    confidence: float = 0.0


@dataclass(frozen=True, slots=True)
class KnowledgeSemanticMergeCandidate:
    candidate_id: str
    title: str
    answer: str
    embedding_text: str = ""
    questions: tuple[str, ...] = field(default_factory=tuple)
    synonyms: tuple[str, ...] = field(default_factory=tuple)
    tags: tuple[str, ...] = field(default_factory=tuple)
    source_ref_count: int = 0
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
class KnowledgeSemanticMergeGroup:
    group_id: str
    candidates: tuple[KnowledgeSemanticMergeCandidate, ...]
    question_intent: str = ""

    def to_answer_resolution_case(self) -> KnowledgeAnswerResolutionCase:
        return KnowledgeAnswerResolutionCase(
            case_id=self.group_id,
            question_intent=self.question_intent,
            answers=tuple(
                candidate.to_answer_resolution_option() for candidate in self.candidates
            ),
        )

    def to_payload(self) -> JsonObject:
        return self.to_answer_resolution_case().to_payload()


@dataclass(frozen=True, slots=True)
class KnowledgeSemanticMergeCanonicalCard:
    title: str
    canonical_question: str
    answer: str
    questions: tuple[str, ...] = field(default_factory=tuple)
    synonyms: tuple[str, ...] = field(default_factory=tuple)
    tags: tuple[str, ...] = field(default_factory=tuple)
    source_ref_ids: tuple[str, ...] = field(default_factory=tuple)
    source_chunk_indexes: tuple[int, ...] = field(default_factory=tuple)
    publishable: bool = True
    publishable_reason: str = ""
    publishable_classification: str = "publishable_customer_answer"


@dataclass(frozen=True, slots=True)
class KnowledgeSemanticMergeDecision:
    group_id: str
    action: SemanticMergeAction
    candidate_ids: tuple[str, ...]
    survivor_title: str = ""
    merged_embedding_text: str = ""
    canonical_card: KnowledgeSemanticMergeCanonicalCard | None = None

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
    parsed = _coerce_json_object(payload, "Preprocessing")
    entries_payload = parsed.get("fragments")
    legacy_entries_schema = False
    if entries_payload is None:
        entries_payload = parsed.get("entries")
        legacy_entries_schema = True
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
        entries.append(
            _parse_entry(
                item, mode=mode, index=index, legacy_schema=legacy_entries_schema
            )
        )

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


def parse_answer_merge_payload(payload: object) -> tuple[bool, str, tuple[str, ...]]:
    parsed = _coerce_json_object(payload, "Answer merge")
    merge_allowed = parsed.get("merge_allowed")
    if not isinstance(merge_allowed, bool):
        raise KnowledgePreprocessingValidationError(
            "Answer merge payload must contain boolean merge_allowed"
        )
    answer = _optional_text(parsed.get("answer"))
    question_variants = tuple(_string_list(parsed.get("question_variants")))
    if not merge_allowed:
        return False, "", ()
    if not answer:
        raise KnowledgePreprocessingValidationError(
            "Answer merge payload must contain answer when merge_allowed=true"
        )
    return True, answer, question_variants


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


def _semantic_merge_int_tuple(value: object) -> tuple[int, ...]:
    raw_values: tuple[object, ...]
    if isinstance(value, list | tuple):
        raw_values = tuple(value)
    else:
        raw_values = (value,)

    result: list[int] = []
    for item in raw_values:
        parsed: int | None = None
        if isinstance(item, bool) or item is None:
            parsed = None
        elif isinstance(item, int):
            parsed = item
        elif isinstance(item, float) and item.is_integer():
            parsed = int(item)
        elif isinstance(item, str) and item.strip().isdigit():
            parsed = int(item.strip())
        if parsed is not None and parsed not in result:
            result.append(parsed)
    return tuple(result)


def _parse_semantic_merge_canonical_card(
    payload: object,
    *,
    index: int,
) -> KnowledgeSemanticMergeCanonicalCard | None:
    if payload is None:
        return None
    if not isinstance(payload, Mapping):
        raise KnowledgePreprocessingValidationError(
            f"Semantic merge decision {index} canonical_card must be an object"
        )

    publishable = payload.get("publishable")
    if publishable is None:
        publishable = True
    if not isinstance(publishable, bool):
        raise KnowledgePreprocessingValidationError(
            f"Semantic merge decision {index} canonical_card.publishable must be boolean"
        )

    classification = _optional_text(payload.get("publishable_classification"))
    if not classification:
        classification = (
            "publishable_customer_answer" if publishable else "not_enough_evidence"
        )

    return KnowledgeSemanticMergeCanonicalCard(
        title=_optional_text(payload.get("title")),
        canonical_question=_optional_text(payload.get("canonical_question")),
        answer=_optional_text(payload.get("answer")),
        questions=tuple(_string_list(payload.get("questions"))),
        synonyms=tuple(_string_list(payload.get("synonyms"))),
        tags=tuple(_string_list(payload.get("tags"))),
        source_ref_ids=tuple(_string_list(payload.get("source_ref_ids"))),
        source_chunk_indexes=_semantic_merge_int_tuple(
            payload.get("source_chunk_indexes")
        ),
        publishable=publishable,
        publishable_reason=_optional_text(payload.get("publishable_reason")),
        publishable_classification=classification,
    )


def _parse_semantic_merge_decision(
    payload: Mapping[object, object],
    *,
    index: int,
    max_embedding_text_chars: int,
) -> KnowledgeSemanticMergeDecision:
    group_id = _optional_text(payload.get("case_id")) or _required_text(
        payload, "group_id", index=index
    )
    raw_action = _required_answer_resolution_action(payload.get("action"), index=index)
    action = cast(
        SemanticMergeAction,
        SEMANTIC_MERGE_ACTION_MERGE
        if raw_action == SEMANTIC_MERGE_ACTION_MERGE
        else SEMANTIC_MERGE_ACTION_KEEP_SEPARATE,
    )
    candidate_ids = tuple(_string_list(payload.get("candidate_ids")))
    canonical_answer = _optional_text(payload.get("canonical_answer"))
    legacy_answer = _optional_text(payload.get("merged_embedding_text"))
    merged_answer = canonical_answer or legacy_answer

    if action == SEMANTIC_MERGE_ACTION_MERGE:
        if not merged_answer:
            raise KnowledgePreprocessingValidationError(
                f"Semantic merge decision {index} missing canonical_answer"
            )
        if not candidate_ids:
            # Answer-only resolver output intentionally omits candidate_ids;
            # application code maps case_id back to the original answer options.
            candidate_ids = ()
    elif not candidate_ids:
        candidate_ids = ()

    if len(merged_answer) > max_embedding_text_chars:
        merged_answer = merged_answer[:max_embedding_text_chars].rstrip()

    return KnowledgeSemanticMergeDecision(
        group_id=group_id,
        action=action,
        candidate_ids=candidate_ids,
        survivor_title="",
        merged_embedding_text=merged_answer,
        canonical_card=None,
    )


def _json_object_from_mapping(value: Mapping[object, object]) -> JsonObject:
    return {str(key): json_value_from_unknown(item) for key, item in value.items()}


def build_embedding_text(entry: KnowledgePreprocessingEntry) -> str:
    parts = [
        entry.title,
        entry.canonical_question,
        " ".join(entry.questions),
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
    legacy_schema: bool = False,
) -> KnowledgePreprocessingEntry:
    match_payload = payload.get("match")
    match_kind = "new"
    known_intent_id = ""
    if isinstance(match_payload, Mapping):
        raw_match_kind = _optional_text(match_payload.get("kind"))
        if raw_match_kind in {"new", "known"}:
            match_kind = raw_match_kind
        known_intent_id = _optional_text(match_payload.get("known_intent_id"))
    variants = _string_list(payload.get("question_variants"))
    if not variants:
        variants = _string_list(payload.get("questions"))
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
    if legacy_schema:
        synonyms = tuple(_string_list(payload.get("synonyms")))
        tags = tuple(_string_list(payload.get("tags")))
    else:
        synonyms = questions
        tags = ()
    source_chunk_indexes = tuple(
        _non_negative_ints(payload.get("source_chunk_indexes"))
    )
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
        canonical_question=canonical_question,
        match_kind=cast(Literal["new", "known"], match_kind),
        known_intent_id=known_intent_id,
        source_chunk_indexes=source_chunk_indexes,
    )
    if legacy_schema:
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
            canonical_question=entry.canonical_question,
            match_kind=entry.match_kind,
            known_intent_id=entry.known_intent_id,
            source_chunk_indexes=entry.source_chunk_indexes,
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


def _required_answer_resolution_action(
    value: object,
    *,
    index: int,
) -> AnswerResolutionAction:
    action = _optional_text(value)
    if action in {
        SEMANTIC_MERGE_ACTION_MERGE,
        SEMANTIC_MERGE_ACTION_KEEP_SEPARATE,
        ANSWER_RESOLUTION_ACTION_CONFLICT,
        ANSWER_RESOLUTION_ACTION_NEEDS_REVIEW,
    }:
        return cast(AnswerResolutionAction, action)

    raise KnowledgePreprocessingValidationError(
        f"Semantic merge decision {index} has unsupported action: {action}"
    )


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
