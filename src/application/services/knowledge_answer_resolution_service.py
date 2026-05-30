from __future__ import annotations

import hashlib
import re
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, replace

from src.application.ports.knowledge_port import (
    KnowledgePreprocessorPort,
)
from src.domain.project_plane.json_types import JsonObject, JsonValue
from src.domain.project_plane.knowledge_preprocessing import (
    KnowledgeAnswerResolutionCandidate,
    KnowledgeAnswerResolutionCase,
    KnowledgeAnswerResolutionDecision,
    KnowledgePreprocessingEntry,
    KnowledgePreprocessingMode,
    build_embedding_text,
)
from src.domain.runtime.language_policy import detect_language_hint, dominant_language


KCD_STAGE_K_ANSWER_DIGEST_MAX_CHARS = 220
KCD_STAGE_K8_ANSWER_RESOLUTION_MAX_GROUPS = 24
KCD_STAGE_K8_ANSWER_RESOLUTION_MAX_GROUP_SIZE = 2
KCD_STAGE_K8_ANSWER_RESOLUTION_CANDIDATE_ANSWER_MAX_CHARS = 900
KCD_STAGE_K8_ANSWER_RESOLUTION_MIN_TOKEN_CHARS = 3
KCD_STAGE_K_MERGED_QUESTION_LIMIT = 40
KCD_STAGE_K_MERGED_SYNONYM_LIMIT = 64
KCD_STAGE_K_MERGED_TAG_LIMIT = 32
KCD_STAGE_K_MERGED_ANSWER_MAX_CHARS = 3600
KCD_STAGE_K_MERGED_SOURCE_EXCERPT_MAX_CHARS = 7000
KCD_STAGE_K_MERGED_EMBEDDING_TEXT_MAX_CHARS = 2400
KCD_STAGE_K8_REJECT_MERGE_REMOVED_UNIT_RATIO = 0.55


@dataclass(frozen=True, slots=True)
class _AnswerResolutionSuspectPair:
    left_index: int
    right_index: int
    score: float


@dataclass(frozen=True, slots=True)
class _DeterministicAnswerUnitMergeResult:
    answer: str
    strategy: str
    left_unit_count: int
    right_unit_count: int
    merged_unit_count: int
    overlap_unit_count: int


@dataclass(frozen=True, slots=True)
class _AnswerResolutionCleanupResult:
    text: str
    original_unit_count: int
    kept_unit_count: int

    @property
    def removed_unit_count(self) -> int:
        return max(0, self.original_unit_count - self.kept_unit_count)


def _clean_optional_text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.strip().split())


def _text_tuple(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        candidates: tuple[object, ...] = (value,)
    elif isinstance(value, tuple):
        candidates = value
    elif isinstance(value, list):
        candidates = tuple(value)
    else:
        return ()

    result: list[str] = []
    for item in candidates:
        cleaned = _clean_optional_text(item)
        if cleaned and cleaned not in result:
            result.append(cleaned)
    return tuple(result)


def answer_digest(
    value: str, *, max_chars: int = KCD_STAGE_K_ANSWER_DIGEST_MAX_CHARS
) -> str:
    text = _clean_optional_text(value)
    if len(text) <= max_chars:
        return text
    trimmed = text[:max_chars].rsplit(" ", 1)[0].strip()
    return trimmed or text[:max_chars].strip()


def _question_intent_primary_question(entry: KnowledgePreprocessingEntry) -> str:
    if entry.canonical_question:
        return entry.canonical_question
    for question in _text_tuple(entry.questions):
        if question:
            return question
    return answer_digest(entry.answer)


def json_metric_int(metrics: Mapping[str, JsonValue], key: str) -> int:
    value = metrics.get(key)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return 0


def _merge_text_tuple_values(
    *groups: tuple[str, ...],
) -> tuple[str, ...]:
    result: list[str] = []
    for group in groups:
        for value in group:
            cleaned = _clean_optional_text(value)
            if cleaned and cleaned not in result:
                result.append(cleaned)
    return tuple(result)


def _merge_int_tuple_values(*groups: tuple[int, ...]) -> tuple[int, ...]:
    result: list[int] = []
    for group in groups:
        for value in group:
            if value not in result:
                result.append(value)
    return tuple(result)


def _normalized_answer_topic_key(value: str) -> str:
    text = value.lower().replace("ё", "е")
    text = re.sub(r"[^0-9a-zа-я]+", " ", text)
    return " ".join(text.split())


def merge_answer_text(left: str, right: str) -> str:
    left_clean = _clean_optional_text(left)
    right_clean = _clean_optional_text(right)

    if not left_clean:
        return right_clean
    if not right_clean:
        return left_clean

    left_normalized = _normalized_answer_topic_key(left_clean)
    right_normalized = _normalized_answer_topic_key(right_clean)

    if left_normalized == right_normalized:
        return left_clean
    if right_normalized and right_normalized in left_normalized:
        return left_clean
    if left_normalized and left_normalized in right_normalized:
        return right_clean

    unit_merge = merge_answer_units_deterministically(left_clean, right_clean)
    if unit_merge is not None:
        return _cleanup_answer_resolution_text(unit_merge.answer)

    return _cleanup_answer_resolution_text(f"{left_clean}\n\n{right_clean}")


def _merge_source_excerpt_text(
    *entries: KnowledgePreprocessingEntry,
) -> str:
    excerpts: list[str] = []

    for entry in entries:
        for excerpt in source_excerpts_from_preprocessing_entry(entry):
            if excerpt and excerpt not in excerpts:
                excerpts.append(excerpt)

    return "\n\n".join(excerpts)


def limit_compiled_text(value: str, *, max_chars: int) -> str:
    cleaned = _clean_optional_text(value)
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[:max_chars].rstrip()


def _merge_limited_text_tuple_values(
    *groups: tuple[str, ...],
    limit: int,
) -> tuple[str, ...]:
    return _merge_text_tuple_values(*groups)[:limit]


def merge_entry_fields_deterministically(
    *,
    existing_entry: KnowledgePreprocessingEntry,
    incoming_entry: KnowledgePreprocessingEntry,
    merged_answer: str,
    merged_question_variants: tuple[str, ...] = (),
) -> KnowledgePreprocessingEntry:
    answer = limit_compiled_text(
        merged_answer
        or merge_answer_text(existing_entry.answer, incoming_entry.answer),
        max_chars=KCD_STAGE_K_MERGED_ANSWER_MAX_CHARS,
    )
    source_excerpt = limit_compiled_text(
        _merge_source_excerpt_text(existing_entry, incoming_entry),
        max_chars=KCD_STAGE_K_MERGED_SOURCE_EXCERPT_MAX_CHARS,
    )
    merged_questions = _merge_limited_text_tuple_values(
        _text_tuple(existing_entry.questions),
        _text_tuple(incoming_entry.questions),
        _text_tuple(merged_question_variants),
        limit=KCD_STAGE_K_MERGED_QUESTION_LIMIT,
    )
    merged_synonyms = _merge_limited_text_tuple_values(
        _text_tuple(existing_entry.synonyms),
        _text_tuple(incoming_entry.synonyms),
        limit=KCD_STAGE_K_MERGED_SYNONYM_LIMIT,
    )
    merged_tags = _merge_limited_text_tuple_values(
        _text_tuple(existing_entry.tags),
        _text_tuple(incoming_entry.tags),
        limit=KCD_STAGE_K_MERGED_TAG_LIMIT,
    )
    compatibility_entry = KnowledgePreprocessingEntry(
        title=_clean_optional_text(existing_entry.title)
        or _clean_optional_text(incoming_entry.title),
        answer=answer,
        source_excerpt=source_excerpt,
        questions=merged_questions,
        synonyms=merged_synonyms,
        tags=merged_tags,
        canonical_question=existing_entry.canonical_question
        or _question_intent_primary_question(existing_entry),
    )
    embedding_text = limit_compiled_text(
        build_embedding_text(compatibility_entry),
        max_chars=KCD_STAGE_K_MERGED_EMBEDDING_TEXT_MAX_CHARS,
    )

    return KnowledgePreprocessingEntry(
        title=_clean_optional_text(existing_entry.title)
        or _clean_optional_text(incoming_entry.title),
        answer=answer,
        source_excerpt=source_excerpt,
        questions=merged_questions,
        synonyms=merged_synonyms,
        tags=merged_tags,
        embedding_text=embedding_text,
        canonical_question=compatibility_entry.canonical_question,
        source_chunk_indexes=_merge_int_tuple_values(
            existing_entry.source_chunk_indexes,
            incoming_entry.source_chunk_indexes,
        ),
    )


def source_excerpt_to_text(value: object) -> str:
    if isinstance(value, tuple):
        return "\n\n".join(
            _clean_optional_text(str(part))
            for part in value
            if _clean_optional_text(str(part))
        )
    return _clean_optional_text(str(value or ""))


def source_excerpts_from_preprocessing_entry(
    entry: KnowledgePreprocessingEntry,
) -> tuple[str, ...]:
    normalized = entry.source_excerpt.replace("\r\n", "\n").replace("\r", "\n")
    parts = tuple(part.strip() for part in normalized.split("\n\n"))
    return _text_tuple(parts)


def _answer_resolution_candidate_id(index: int) -> str:
    return f"entry-{index}"


def build_answer_resolution_candidate_index(candidate_id: str) -> int | None:
    prefix = "entry-"
    if not candidate_id.startswith(prefix):
        return None

    raw_index = candidate_id[len(prefix) :]
    if not raw_index.isdigit():
        return None

    return int(raw_index)


def tokenize_answer_resolution_text(value: str) -> tuple[str, ...]:
    text = value.lower().replace("ё", "е")
    tokens = (
        token
        for token in re.findall(r"[0-9a-zа-я]+", text)
        if len(token) >= KCD_STAGE_K8_ANSWER_RESOLUTION_MIN_TOKEN_CHARS
    )
    return tuple(dict.fromkeys(tokens))


def _answer_resolution_entry_text(entry: KnowledgePreprocessingEntry) -> str:
    return " ".join(
        part
        for part in (
            entry.title,
            entry.canonical_question,
            " ".join(_text_tuple(entry.questions)),
        )
        if _clean_optional_text(part)
    )


def _answer_resolution_entry_tokens(
    entry: KnowledgePreprocessingEntry,
) -> tuple[str, ...]:
    return tokenize_answer_resolution_text(_answer_resolution_entry_text(entry))


def calculate_answer_resolution_token_similarity(
    left: tuple[str, ...],
    right: tuple[str, ...],
) -> float:
    left_set = set(left)
    right_set = set(right)

    if not left_set or not right_set:
        return 0.0

    return len(left_set & right_set) / len(left_set | right_set)


def _answer_resolution_token_overlap_coverage(
    left: tuple[str, ...],
    right: tuple[str, ...],
) -> float:
    left_set = set(left)
    right_set = set(right)

    if not left_set or not right_set:
        return 0.0

    return len(left_set & right_set) / min(len(left_set), len(right_set))


def _answer_resolution_primary_intent_tokens(
    entry: KnowledgePreprocessingEntry,
) -> tuple[str, ...]:
    primary_intent = _clean_optional_text(
        entry.canonical_question or _question_intent_primary_question(entry)
    )
    if primary_intent:
        return tokenize_answer_resolution_text(primary_intent)

    return tokenize_answer_resolution_text(entry.title)


def _answer_resolution_same_intent_summary_score(
    left: KnowledgePreprocessingEntry,
    right: KnowledgePreprocessingEntry,
) -> float:
    """Score generic same-intent summary/full-answer candidates.

    This does not merge entries deterministically. It only decides whether the
    pair is worth sending to the LLM answer resolver. The rule is topic-agnostic:
    it uses question/intent overlap, answer token coverage and asymmetric answer
    length, not domain keyword dictionaries.
    """

    left_answer = _clean_optional_text(left.answer)
    right_answer = _clean_optional_text(right.answer)
    if not left_answer or not right_answer:
        return 0.0

    left_answer_tokens = tokenize_answer_resolution_text(left_answer)
    right_answer_tokens = tokenize_answer_resolution_text(right_answer)
    if len(left_answer_tokens) < 4 or len(right_answer_tokens) < 4:
        return 0.0

    primary_intent_coverage = _answer_resolution_token_overlap_coverage(
        _answer_resolution_primary_intent_tokens(left),
        _answer_resolution_primary_intent_tokens(right),
    )
    broad_intent_coverage = _answer_resolution_token_overlap_coverage(
        _answer_resolution_question_intent_tokens(left),
        _answer_resolution_question_intent_tokens(right),
    )
    answer_coverage = _answer_resolution_token_overlap_coverage(
        left_answer_tokens,
        right_answer_tokens,
    )

    shortest_answer_length = max(1, min(len(left_answer), len(right_answer)))
    longest_answer_length = max(len(left_answer), len(right_answer))
    length_ratio = longest_answer_length / shortest_answer_length

    intent_coverage = max(primary_intent_coverage, broad_intent_coverage)

    if intent_coverage < 0.62:
        return 0.0
    if answer_coverage < 0.34:
        return 0.0
    if length_ratio < 1.35 and answer_coverage < 0.56:
        return 0.0

    length_bonus = min(length_ratio, 4.0) / 4.0
    score = (intent_coverage * 0.48) + (answer_coverage * 0.42) + (length_bonus * 0.10)
    return min(0.94, max(0.24, score))


def _answer_resolution_question_intent_text(entry: KnowledgePreprocessingEntry) -> str:
    return " ".join(
        part
        for part in (
            entry.title,
            entry.canonical_question,
            " ".join(_text_tuple(entry.questions)),
        )
        if _clean_optional_text(part)
    )


def _answer_resolution_question_intent_tokens(
    entry: KnowledgePreprocessingEntry,
) -> tuple[str, ...]:
    return tokenize_answer_resolution_text(
        _answer_resolution_question_intent_text(entry)
    )


def _answer_resolution_entry_pair_score(
    left: KnowledgePreprocessingEntry,
    right: KnowledgePreprocessingEntry,
) -> float:
    left_title = _normalized_answer_topic_key(left.title)
    right_title = _normalized_answer_topic_key(right.title)

    if left_title and right_title and left_title == right_title:
        return 1.0
    if (
        left_title
        and right_title
        and (left_title in right_title or right_title in left_title)
    ):
        return 0.92

    title_score = calculate_answer_resolution_token_similarity(
        tokenize_answer_resolution_text(left_title),
        tokenize_answer_resolution_text(right_title),
    )
    question_score = calculate_answer_resolution_token_similarity(
        _answer_resolution_question_intent_tokens(left),
        _answer_resolution_question_intent_tokens(right),
    )
    full_score = calculate_answer_resolution_token_similarity(
        _answer_resolution_entry_tokens(left),
        _answer_resolution_entry_tokens(right),
    )

    return max(title_score, question_score * 1.15, full_score)


def _answer_resolution_entries_are_suspects(
    left: KnowledgePreprocessingEntry,
    right: KnowledgePreprocessingEntry,
) -> bool:
    return _answer_resolution_entry_pair_score(left, right) >= 0.24


def _answer_resolution_limited_text_tuple(
    value: object,
    *,
    limit: int,
    max_chars: int = 140,
) -> tuple[str, ...]:
    result: list[str] = []
    for item in _text_tuple(value):
        cleaned = limit_compiled_text(item, max_chars=max_chars)
        if cleaned and cleaned not in result:
            result.append(cleaned)
        if len(result) >= limit:
            break
    return tuple(result)


def _answer_resolution_candidate_from_entry(
    *,
    index: int,
    entry: KnowledgePreprocessingEntry,
) -> KnowledgeAnswerResolutionCandidate:
    """Build an answer-only option for unresolved answer resolution."""

    return KnowledgeAnswerResolutionCandidate(
        candidate_id=_answer_resolution_candidate_id(index),
        answer=limit_compiled_text(
            _clean_optional_text(entry.answer),
            max_chars=KCD_STAGE_K8_ANSWER_RESOLUTION_CANDIDATE_ANSWER_MAX_CHARS,
        ),
        source_excerpt=limit_compiled_text(
            _merge_source_excerpt_text(entry),
            max_chars=KCD_STAGE_K8_ANSWER_RESOLUTION_CANDIDATE_ANSWER_MAX_CHARS,
        ),
    )


def _answer_resolution_question_intent(
    *entries: KnowledgePreprocessingEntry,
) -> str:
    intent_parts: list[str] = []
    for entry in entries:
        primary = _clean_optional_text(
            entry.canonical_question or _question_intent_primary_question(entry)
        )
        title = _clean_optional_text(entry.title)
        for value in (primary, title):
            if value and value not in intent_parts:
                intent_parts.append(value)
    return limit_compiled_text(
        " / ".join(intent_parts),
        max_chars=280,
    )


def _answer_resolution_suspect_pairs_from_entries(
    entries: Sequence[KnowledgePreprocessingEntry],
) -> tuple[_AnswerResolutionSuspectPair, ...]:
    pairs: list[_AnswerResolutionSuspectPair] = []

    for left_index, left_entry in enumerate(entries):
        for right_index in range(left_index + 1, len(entries)):
            lexical_score = _answer_resolution_entry_pair_score(
                left_entry, entries[right_index]
            )
            semantic_score = _answer_resolution_same_intent_summary_score(
                left_entry,
                entries[right_index],
            )
            score = max(lexical_score, semantic_score)
            if score >= 0.24:
                pairs.append(
                    _AnswerResolutionSuspectPair(
                        left_index=left_index,
                        right_index=right_index,
                        score=score,
                    )
                )

    return tuple(
        sorted(
            pairs,
            key=lambda pair: (-pair.score, pair.left_index, pair.right_index),
        )
    )


def _answer_resolution_case_components_from_pairs(
    *,
    entry_count: int,
    pairs: Sequence[_AnswerResolutionSuspectPair],
) -> tuple[tuple[int, ...], ...]:
    if entry_count < 2 or not pairs:
        return ()

    parent = list(range(entry_count))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root == right_root:
            return
        if left_root < right_root:
            parent[right_root] = left_root
        else:
            parent[left_root] = right_root

    for pair in pairs:
        union(pair.left_index, pair.right_index)

    component_by_root: dict[int, list[int]] = {}
    for index in range(entry_count):
        root = find(index)
        component_by_root.setdefault(root, []).append(index)

    best_score_by_component: dict[tuple[int, ...], float] = {}
    for component_indexes in component_by_root.values():
        component = tuple(sorted(component_indexes))
        if len(component) < 2:
            continue
        best_score_by_component[component] = max(
            pair.score
            for pair in pairs
            if pair.left_index in component and pair.right_index in component
        )

    return tuple(
        component
        for component, _score in sorted(
            best_score_by_component.items(),
            key=lambda item: (-item[1], item[0]),
        )
    )


def build_answer_resolution_cases_from_entries(
    entries: Sequence[KnowledgePreprocessingEntry],
) -> tuple[KnowledgeAnswerResolutionCase, ...]:
    if len(entries) < 2:
        return ()

    pairs = _answer_resolution_suspect_pairs_from_entries(entries)
    components = _answer_resolution_case_components_from_pairs(
        entry_count=len(entries),
        pairs=pairs,
    )

    cases: list[KnowledgeAnswerResolutionCase] = []
    for component in components[:KCD_STAGE_K8_ANSWER_RESOLUTION_MAX_GROUPS]:
        digest = hashlib.sha256(
            ",".join(
                _answer_resolution_candidate_id(index) for index in component
            ).encode("utf-8")
        ).hexdigest()[:12]
        cases.append(
            KnowledgeAnswerResolutionCase(
                case_id=f"answer-resolution-case-{digest}",
                question_intent=_answer_resolution_question_intent(
                    *(entries[index] for index in component)
                ),
                expected_answer_language=_answer_resolution_component_language_hint(
                    *(entries[index] for index in component)
                ),
                candidates=tuple(
                    _answer_resolution_candidate_from_entry(
                        index=index,
                        entry=entries[index],
                    )
                    for index in component
                ),
            )
        )

    return tuple(cases)


def build_answer_resolution_survivor_index(
    *,
    decision: KnowledgeAnswerResolutionDecision,
    candidate_indexes: tuple[int, ...],
    entries: Sequence[KnowledgePreprocessingEntry],
) -> int:
    return candidate_indexes[0]


def fingerprint_answer_resolution_text(value: str) -> str:
    return " ".join(
        re.sub(r"[^0-9a-zа-яё]+", " ", value.lower().replace("ё", "е")).split()
    )


def _answer_resolution_text_units(value: str) -> tuple[str, ...]:
    compact = _clean_optional_text(value)
    if not compact:
        return ()

    units = re.split(r"(?<=[.!?])\s+|[\n;]+", compact)
    return tuple(
        _clean_optional_text(unit) for unit in units if _clean_optional_text(unit)
    )


def _answer_unit_fingerprint(value: str) -> str:
    return fingerprint_answer_resolution_text(value)


def _answer_units_by_fingerprint(value: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for unit in _answer_resolution_text_units(value):
        fingerprint = _answer_unit_fingerprint(unit)
        if fingerprint and fingerprint not in result:
            result[fingerprint] = unit
    return result


def merge_answer_units_deterministically(
    left: str,
    right: str,
    *,
    allow_disjoint_union: bool = False,
) -> _DeterministicAnswerUnitMergeResult | None:
    """Merge authoritative answer text by atomic-ish answer units.

    This is deterministic-first canonicalization. It does not decide semantic
    paraphrase equivalence; it only handles exact unit equality, subset/superset,
    exact overlap union, and same-intent complementary union when the caller has
    already proven same question-intent.
    """

    left_units = _answer_units_by_fingerprint(left)
    right_units = _answer_units_by_fingerprint(right)
    left_keys = set(left_units)
    right_keys = set(right_units)

    if not left_keys or not right_keys:
        return None

    if left_keys == right_keys:
        return _DeterministicAnswerUnitMergeResult(
            answer=_clean_optional_text(left),
            strategy="exact_answer_units",
            left_unit_count=len(left_keys),
            right_unit_count=len(right_keys),
            merged_unit_count=len(left_keys),
            overlap_unit_count=len(left_keys),
        )

    if left_keys < right_keys:
        return _DeterministicAnswerUnitMergeResult(
            answer=_clean_optional_text(right),
            strategy="answer_unit_subset_superset",
            left_unit_count=len(left_keys),
            right_unit_count=len(right_keys),
            merged_unit_count=len(right_keys),
            overlap_unit_count=len(left_keys & right_keys),
        )

    if right_keys < left_keys:
        return _DeterministicAnswerUnitMergeResult(
            answer=_clean_optional_text(left),
            strategy="answer_unit_subset_superset",
            left_unit_count=len(left_keys),
            right_unit_count=len(right_keys),
            merged_unit_count=len(left_keys),
            overlap_unit_count=len(left_keys & right_keys),
        )

    overlap = left_keys & right_keys
    if not overlap and not allow_disjoint_union:
        return None

    merged_units: list[str] = list(left_units.values())
    for fingerprint, unit in right_units.items():
        if fingerprint not in left_keys:
            merged_units.append(unit)

    strategy = (
        "same_intent_complementary_answer_unit_union"
        if not overlap
        else "answer_unit_overlap_union"
    )
    return _DeterministicAnswerUnitMergeResult(
        answer=_clean_optional_text("\n".join(merged_units)),
        strategy=strategy,
        left_unit_count=len(left_keys),
        right_unit_count=len(right_keys),
        merged_unit_count=len({*left_keys, *right_keys}),
        overlap_unit_count=len(overlap),
    )


def cleanup_answer_resolution_text_with_metrics(
    value: str,
) -> _AnswerResolutionCleanupResult:
    units = _answer_resolution_text_units(value)
    if not units:
        cleaned = _clean_optional_text(value)
        count = 1 if cleaned else 0
        return _AnswerResolutionCleanupResult(
            text=cleaned,
            original_unit_count=count,
            kept_unit_count=count,
        )

    cleaned_text = _cleanup_answer_resolution_text(value)
    kept_units = _answer_resolution_text_units(cleaned_text)
    return _AnswerResolutionCleanupResult(
        text=cleaned_text,
        original_unit_count=len(units),
        kept_unit_count=len(kept_units),
    )


def _cleanup_answer_resolution_text(value: str) -> str:
    """Remove deterministic exact/near sentence duplicates from answer text."""

    units = _answer_resolution_text_units(value)
    if not units:
        return _clean_optional_text(value)

    kept: list[str] = []
    fingerprints: list[str] = []

    for unit in units:
        fingerprint = fingerprint_answer_resolution_text(unit)
        if not fingerprint:
            continue

        is_duplicate = False
        for existing in fingerprints:
            if fingerprint == existing:
                is_duplicate = True
                break
            if len(fingerprint) >= 48 and fingerprint in existing:
                is_duplicate = True
                break
            if len(existing) >= 48 and existing in fingerprint:
                is_duplicate = True
                break

        if is_duplicate:
            continue

        fingerprints.append(fingerprint)
        kept.append(unit)

    return _clean_optional_text(" ".join(kept))


def is_noisy_answer_resolution_decision(
    decision: KnowledgeAnswerResolutionDecision,
) -> bool:
    if not decision.is_merge or not decision.canonical_answer:
        return False

    cleanup = cleanup_answer_resolution_text_with_metrics(decision.canonical_answer)
    if cleanup.original_unit_count < 3:
        return False

    return (
        cleanup.removed_unit_count / cleanup.original_unit_count
    ) >= KCD_STAGE_K8_REJECT_MERGE_REMOVED_UNIT_RATIO


def reject_noisy_answer_resolution_decisions(
    decisions: Sequence[KnowledgeAnswerResolutionDecision],
) -> tuple[KnowledgeAnswerResolutionDecision, ...]:
    filtered: list[KnowledgeAnswerResolutionDecision] = []

    for decision in decisions:
        if not is_noisy_answer_resolution_decision(decision):
            filtered.append(decision)
            continue

        filtered.append(
            KnowledgeAnswerResolutionDecision(
                case_id=decision.group_id,
                action="keep_separate",
                candidate_ids=decision.candidate_ids,
                canonical_answer="",
            )
        )

    return tuple(filtered)


def apply_answer_resolution_decision_to_entry(
    *,
    entry: KnowledgePreprocessingEntry,
    decision: KnowledgeAnswerResolutionDecision,
) -> KnowledgePreprocessingEntry:
    answer = limit_compiled_text(
        _clean_optional_text(decision.canonical_answer) or entry.answer,
        max_chars=KCD_STAGE_K_MERGED_ANSWER_MAX_CHARS,
    )
    compatibility_entry = KnowledgePreprocessingEntry(
        title=entry.title,
        answer=answer,
        source_excerpt=entry.source_excerpt,
        questions=entry.questions,
        synonyms=entry.synonyms,
        tags=entry.tags,
        canonical_question=entry.canonical_question,
    )
    embedding_text = limit_compiled_text(
        build_embedding_text(compatibility_entry),
        max_chars=KCD_STAGE_K_MERGED_EMBEDDING_TEXT_MAX_CHARS,
    )

    return KnowledgePreprocessingEntry(
        title=entry.title,
        answer=answer,
        source_excerpt=entry.source_excerpt,
        questions=entry.questions,
        synonyms=entry.synonyms,
        tags=entry.tags,
        embedding_text=embedding_text,
        canonical_question=entry.canonical_question,
        source_chunk_indexes=entry.source_chunk_indexes,
    )


def _answer_resolution_decision_is_publishable(
    decision: KnowledgeAnswerResolutionDecision,
    *,
    entries: Sequence[KnowledgePreprocessingEntry],
) -> bool:
    if not decision.is_merge:
        return True
    if not decision.canonical_answer:
        return False

    candidate_entries: list[KnowledgePreprocessingEntry] = []
    for candidate_id in decision.candidate_ids:
        index = build_answer_resolution_candidate_index(candidate_id)
        if index is None or index < 0 or index >= len(entries):
            continue
        candidate_entries.append(entries[index])

    if len(candidate_entries) < 2:
        return False

    expected_language = _answer_resolution_component_language_hint(*candidate_entries)
    if expected_language == "unknown":
        return False

    actual_language = _answer_resolution_text_language_hint(decision.canonical_answer)
    return actual_language == expected_language


def _answer_resolution_text_language_hint(value: str) -> str:
    return detect_language_hint(_clean_optional_text(value))


def _answer_resolution_component_language_hint(
    *entries: KnowledgePreprocessingEntry,
) -> str:
    samples: list[str] = []
    for entry in entries:
        combined = " ".join(
            part
            for part in (
                _clean_optional_text(entry.answer),
                _clean_optional_text(entry.source_excerpt),
            )
            if part
        )
        if combined:
            samples.append(combined)
    return dominant_language(samples)


def _apply_answer_resolution_decisions(
    *,
    entries: Sequence[KnowledgePreprocessingEntry],
    decisions: Sequence[KnowledgeAnswerResolutionDecision],
    source_excerpts_by_entry: Sequence[tuple[str, ...]] | None = None,
) -> tuple[tuple[KnowledgePreprocessingEntry, ...], tuple[tuple[str, ...], ...]]:
    if not entries:
        return (), ()

    updated_entries: list[KnowledgePreprocessingEntry] = list(entries)
    updated_source_excerpts: list[tuple[str, ...]] = (
        list(source_excerpts_by_entry)
        if source_excerpts_by_entry is not None
        else [source_excerpts_from_preprocessing_entry(entry) for entry in entries]
    )

    if len(updated_source_excerpts) != len(updated_entries):
        updated_source_excerpts = [
            source_excerpts_from_preprocessing_entry(entry) for entry in entries
        ]

    if not decisions:
        return tuple(updated_entries), tuple(updated_source_excerpts)

    removed_indexes: set[int] = set()

    for decision in decisions:
        if not decision.is_merge and _answer_resolution_decision_is_publishable(
            decision, entries=entries
        ):
            continue
        if decision.is_merge and not _answer_resolution_decision_is_publishable(
            decision, entries=entries
        ):
            continue

        candidate_indexes: list[int] = []
        for candidate_id in decision.candidate_ids:
            index = build_answer_resolution_candidate_index(candidate_id)
            if index is None or index < 0 or index >= len(entries):
                continue
            if index in candidate_indexes or index in removed_indexes:
                continue
            candidate_indexes.append(index)

        if len(candidate_indexes) < 2:
            continue

        ordered_indexes = tuple(sorted(candidate_indexes))
        survivor_index = build_answer_resolution_survivor_index(
            decision=decision,
            candidate_indexes=ordered_indexes,
            entries=entries,
        )

        merged_entry = updated_entries[survivor_index]
        for index in ordered_indexes:
            if index == survivor_index:
                continue
            merged_entry = merge_entry_fields_deterministically(
                existing_entry=merged_entry,
                incoming_entry=updated_entries[index],
                merged_answer="",
            )

        merged_source_excerpts = _merge_text_tuple_values(
            *(updated_source_excerpts[index] for index in ordered_indexes)
        )
        updated_entries[survivor_index] = apply_answer_resolution_decision_to_entry(
            entry=merged_entry,
            decision=decision,
        )
        updated_source_excerpts[survivor_index] = merged_source_excerpts
        removed_indexes.update(
            index for index in ordered_indexes if index != survivor_index
        )

    return (
        tuple(
            entry
            for index, entry in enumerate(updated_entries)
            if index not in removed_indexes
        ),
        tuple(
            source_excerpts
            for index, source_excerpts in enumerate(updated_source_excerpts)
            if index not in removed_indexes
        ),
    )


def _answer_resolution_candidate_trace_payload(
    candidate: KnowledgeAnswerResolutionCandidate,
) -> JsonObject:
    return {
        "candidate_id": candidate.candidate_id,
        "answer_preview": candidate.answer[:280],
        "source_excerpt_preview": candidate.source_excerpt[:280],
    }


def _answer_resolution_trace_row(
    *,
    answer_case: KnowledgeAnswerResolutionCase,
    decision: KnowledgeAnswerResolutionDecision,
) -> JsonObject:
    return {
        "case_id": answer_case.case_id,
        "action": decision.action,
        "candidate_ids": list(decision.candidate_ids),
        "candidate_count": len(answer_case.candidates),
        "question_intent": answer_case.question_intent,
        "candidates": [
            _answer_resolution_candidate_trace_payload(candidate)
            for candidate in answer_case.candidates
        ],
        "canonical_answer_preview": decision.canonical_answer[:360],
        "reason": decision.reason,
        "confidence": decision.confidence,
    }


def attach_case_candidate_ids_to_answer_resolution_decisions(
    *,
    answer_case: KnowledgeAnswerResolutionCase,
    decisions: Sequence[KnowledgeAnswerResolutionDecision],
) -> tuple[KnowledgeAnswerResolutionDecision, ...]:
    case_candidate_ids = tuple(
        candidate.candidate_id for candidate in answer_case.candidates
    )
    updated: list[KnowledgeAnswerResolutionDecision] = []
    for decision in decisions:
        if decision.case_id != answer_case.case_id or decision.candidate_ids:
            updated.append(decision)
            continue
        updated.append(replace(decision, candidate_ids=case_candidate_ids))
    return tuple(updated)


async def _resolve_compiled_answer_cases(
    *,
    preprocessor: KnowledgePreprocessorPort,
    mode: KnowledgePreprocessingMode,
    file_name: str,
    entries: Sequence[KnowledgePreprocessingEntry],
    source_excerpts_by_entry: Sequence[tuple[str, ...]],
    existing_project_titles: Sequence[str],
    on_progress: Callable[[JsonObject], Awaitable[None]] | None = None,
) -> tuple[
    tuple[KnowledgePreprocessingEntry, ...],
    tuple[tuple[str, ...], ...],
    JsonObject,
]:
    groups = build_answer_resolution_cases_from_entries(entries)
    source_excerpts = tuple(source_excerpts_by_entry)
    if len(source_excerpts) != len(entries):
        source_excerpts = tuple(
            source_excerpts_from_preprocessing_entry(entry) for entry in entries
        )

    metrics: JsonObject = {
        "status": "processing" if groups else "completed",
        "candidate_count": len(entries),
        "raw_draft_count": len(entries),
        "suspect_case_count": len(groups),
        "candidate_case_count": len(groups),
        "processed_case_count": 0,
        "entry_count_before": len(entries),
        "existing_project_title_count": len(existing_project_titles),
        "strategy": "deterministic_first_answer_only_llm_resolver",
        "fallback_published": False,
        "llm_call_count": 0,
        "decision_count": 0,
        "resolved_answer_count": 0,
        "kept_separate_count": 0,
        "rejected_decision_count": 0,
        "invalid_resolution_output_count": 0,
        "decision_trace": [],
    }

    async def publish_progress() -> None:
        if on_progress is not None:
            await on_progress(dict(metrics))

    await publish_progress()

    if not groups:
        metrics["entry_count_after"] = len(entries)
        return tuple(entries), source_excerpts, metrics

    decisions: tuple[KnowledgeAnswerResolutionDecision, ...] = ()
    try:
        for group in groups:
            execution = await preprocessor.resolve_answer_cases(
                mode=mode,
                file_name=file_name,
                cases=(group,),
                existing_project_titles=existing_project_titles,
            )
            metrics["llm_call_count"] = json_metric_int(metrics, "llm_call_count") + 1
            case_decisions = attach_case_candidate_ids_to_answer_resolution_decisions(
                answer_case=group,
                decisions=execution.result.decisions,
            )
            decisions = (*decisions, *case_decisions)
            existing_trace = metrics.get("decision_trace")
            decision_trace = (
                list(existing_trace) if isinstance(existing_trace, list) else []
            )
            decision_trace.extend(
                _answer_resolution_trace_row(answer_case=group, decision=decision)
                for decision in case_decisions
            )
            metrics["decision_trace"] = decision_trace[-200:]
            metrics["processed_case_count"] = (
                json_metric_int(metrics, "processed_case_count") + 1
            )
            metrics["decision_count"] = len(decisions)
            metrics["resolved_answer_count"] = sum(
                1 for decision in decisions if decision.is_merge
            )
            metrics["kept_separate_count"] = sum(
                1 for decision in decisions if not decision.is_merge
            )
            metrics["rejected_decision_count"] = sum(
                1
                for decision in decisions
                if not _answer_resolution_decision_is_publishable(
                    decision, entries=entries
                )
            )
            await publish_progress()
    except Exception as exc:
        metrics["status"] = "failed"
        metrics["fallback_published"] = True
        metrics["error_type"] = type(exc).__name__
        metrics["error_message"] = str(exc)[:240]
        metrics["entry_count_after"] = len(entries)
        metrics["invalid_resolution_output_count"] = 1
        await publish_progress()
        return tuple(entries), source_excerpts, metrics

    tightened_entries, tightened_source_excerpts = _apply_answer_resolution_decisions(
        entries=entries,
        decisions=decisions,
        source_excerpts_by_entry=source_excerpts,
    )

    metrics["status"] = "completed"
    metrics["fallback_published"] = False
    metrics["decision_count"] = len(decisions)
    metrics["resolved_answer_count"] = sum(
        1 for decision in decisions if decision.is_merge
    )
    metrics["kept_separate_count"] = sum(
        1 for decision in decisions if not decision.is_merge
    )
    metrics["rejected_decision_count"] = sum(
        1
        for decision in decisions
        if not _answer_resolution_decision_is_publishable(decision, entries=entries)
    )
    metrics["invalid_resolution_output_count"] = 0
    metrics["entry_count_after"] = len(tightened_entries)
    metrics["final_entry_count"] = len(tightened_entries)
    metrics["published_entry_count"] = len(tightened_entries)
    metrics["collapsed_entry_count"] = len(entries) - len(tightened_entries)
    await publish_progress()

    return tightened_entries, tightened_source_excerpts, metrics


@dataclass(frozen=True, slots=True)
class AnswerResolutionResult:
    entries: tuple[KnowledgePreprocessingEntry, ...]
    source_excerpts_by_entry: tuple[tuple[str, ...], ...]
    metrics: JsonObject


class KnowledgeAnswerResolutionService:
    async def resolve_compiled_answer_cases(
        self,
        *,
        preprocessor: KnowledgePreprocessorPort,
        mode: KnowledgePreprocessingMode,
        file_name: str,
        entries: Sequence[KnowledgePreprocessingEntry],
        source_excerpts_by_entry: Sequence[tuple[str, ...]],
        existing_project_titles: Sequence[str],
        on_progress: Callable[[JsonObject], Awaitable[None]] | None = None,
    ) -> AnswerResolutionResult:
        (
            resolved_entries,
            resolved_source_excerpts,
            metrics,
        ) = await _resolve_compiled_answer_cases(
            preprocessor=preprocessor,
            mode=mode,
            file_name=file_name,
            entries=entries,
            source_excerpts_by_entry=source_excerpts_by_entry,
            existing_project_titles=existing_project_titles,
            on_progress=on_progress,
        )
        return AnswerResolutionResult(
            entries=resolved_entries,
            source_excerpts_by_entry=resolved_source_excerpts,
            metrics=metrics,
        )
