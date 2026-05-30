from __future__ import annotations

import asyncio
import hashlib
import json
import re
import uuid
from collections.abc import Awaitable, Callable, Mapping, Sequence
from pathlib import Path
from dataclasses import dataclass, field
from typing import TypedDict, cast

from groq import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    AsyncGroq,
    RateLimitError,
)

from src.application.ports.knowledge_port import KnowledgeSurfaceCompilerPort
from src.domain.project_plane.json_types import JsonObject, json_value_from_unknown
from src.domain.project_plane.knowledge_preprocessing import (
    MODE_FAQ,
    KnowledgePreprocessingMode,
    KnowledgePreprocessingValidationError,
)
from src.domain.project_plane.retrieval_surface_compilation import (
    RetrievalSurfaceCompilationResult,
    RetrievalSurfaceDraft,
    RetrievalSurfaceGraph,
    RetrievalSurfaceMergeDecision,
    RetrievalSurfaceRelation,
    RetrievalSurfaceSourceUnit,
    SurfaceKind,
    SurfaceMergeDecisionType,
    SurfacePublicationStatus,
    SurfaceQuestionKind,
    SurfaceQuestionOwnership,
    SurfaceQuestionReassignment,
    SurfaceRelationType,
    SurfaceStatus,
)
from src.infrastructure.config.settings import settings
from src.infrastructure.llm.groq_keyring import RotatingAsyncGroq
from src.infrastructure.logging.logger import get_logger

logger = get_logger(__name__)

FAQ_RETRIEVAL_SURFACE_COMPILATION_PROMPT_VERSION = (
    "faq_retrieval_surface_compilation_v1"
)
PROMPTS_DIR = Path(__file__).resolve().parents[2] / "agent" / "prompts"
FAQ_SECTION_FINDINGS_PROMPT_FILE = "faq_surface_section_findings.ru.txt"
FAQ_REGISTRY_MERGE_PROMPT_FILE = "faq_surface_registry_merge.ru.txt"
FAQ_FINAL_RECONCILIATION_PROMPT_FILE = "faq_surface_final_reconciliation.ru.txt"
STRICT_JSON_SYSTEM_MESSAGE = (
    "You are a strict JSON API. Return exactly one valid JSON object. "
    "Do not include markdown, code fences, explanations, comments, apologies, "
    "prefixes, suffixes, or multiple JSON objects. The first non-whitespace "
    "character must be { and the last non-whitespace character must be }."
)
GROQ_INSTANT_MODEL_ID = "llama-3.1-8b-instant"
GROQ_LARGE_REQUEST_FALLBACK_MODEL_ID = "meta-llama/llama-4-scout-17b-16e-instruct"
SURFACE_KIND_VALUES: frozenset[str] = frozenset(
    {
        "umbrella",
        "child",
        "specific",
        "standalone",
        "definition",
        "procedural",
        "safety",
        "handoff",
        "integration",
        "channel",
        "document_upload",
        "curation",
        "retrieval_quality",
        "service_limits",
        "other",
    }
)
RELATION_TYPE_VALUES: frozenset[str] = frozenset(
    {
        "umbrella_contains",
        "specializes",
        "sibling",
        "duplicates",
        "overlaps",
        "contradicts",
        "unrelated",
    }
)
QUESTION_KIND_VALUES: frozenset[str] = frozenset(
    {
        "faq_question",
        "test_question",
        "generated_variant",
        "user_like_question",
        "negative_test_question",
        "expected_topic_hint",
    }
)
STATUS_VALUES: frozenset[str] = frozenset(
    {"draft", "needs_review", "published", "rejected", "merged", "superseded"}
)
PUBLICATION_STATUS_VALUES: frozenset[str] = frozenset(
    {"unpublished", "publishing", "published", "publish_failed"}
)
MERGE_DECISION_VALUES: frozenset[str] = frozenset({"merge", "keep_separate"})
SHORT_ANSWER_LABEL_FINGERPRINTS: frozenset[str] = frozenset(
    {
        "короткий ответ клиенту",
        "short answer for customer",
        "client short answer",
    }
)


def _compact_text(value: object) -> str:
    if value is None or isinstance(value, bool):
        return ""
    return " ".join(str(value).strip().split())


def _limited_text(value: object, *, max_chars: int) -> str:
    text = _compact_text(value)
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rsplit(" ", 1)[0].strip() or text[:max_chars].strip()


def _fingerprint(value: str) -> str:
    return " ".join(
        re.sub(r"[^0-9a-zа-яё]+", " ", value.lower().replace("ё", "е")).split()
    )


def _is_short_answer_label(value: str) -> bool:
    return _fingerprint(value) in SHORT_ANSWER_LABEL_FINGERPRINTS


def _loads_json_object(text: str) -> Mapping[str, object]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE)
        stripped = re.sub(r"\s*```$", "", stripped).strip()
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise KnowledgePreprocessingValidationError(
            f"Invalid FAQ surface compiler JSON: {exc}"
        ) from exc
    if not isinstance(payload, Mapping):
        raise KnowledgePreprocessingValidationError(
            "FAQ surface compiler JSON root must be an object"
        )
    return cast(Mapping[str, object], payload)


def _json_object(value: object) -> JsonObject:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): json_value_from_unknown(item) for key, item in value.items()}


def _mapping_items(
    value: object, *, field_name: str
) -> tuple[Mapping[str, object], ...]:
    if not isinstance(value, list):
        raise KnowledgePreprocessingValidationError(
            f"FAQ surface compiler payload must contain {field_name}[]"
        )
    result: list[Mapping[str, object]] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise KnowledgePreprocessingValidationError(
                f"FAQ surface compiler {field_name}[{index}] must be an object"
            )
        result.append(cast(Mapping[str, object], item))
    return tuple(result)


def _text_tuple(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        candidates: tuple[object, ...] = (value,)
    elif isinstance(value, list | tuple):
        candidates = tuple(value)
    else:
        return ()
    result: list[str] = []
    for item in candidates:
        text = _compact_text(item)
        if text and text not in result:
            result.append(text)
    return tuple(result)


def _int_tuple(value: object) -> tuple[int, ...]:
    if not isinstance(value, list | tuple):
        return ()
    result: list[int] = []
    for item in value:
        parsed: int | None = None
        if isinstance(item, int) and not isinstance(item, bool):
            parsed = item
        elif isinstance(item, float) and item.is_integer():
            parsed = int(item)
        elif isinstance(item, str) and item.strip().isdigit():
            parsed = int(item.strip())
        if parsed is not None and parsed >= 0 and parsed not in result:
            result.append(parsed)
    return tuple(result)


def _confidence(value: object, *, default: float = 0.0) -> float:
    parsed = default
    if isinstance(value, int | float) and not isinstance(value, bool):
        parsed = float(value)
    elif isinstance(value, str):
        try:
            parsed = float(value.strip())
        except ValueError:
            parsed = default
    return max(0.0, min(1.0, parsed))


def _enum_text(value: object, *, allowed: frozenset[str], default: str) -> str:
    text = _compact_text(value)
    return text if text in allowed else default


def _source_unit_by_key(
    source_units: Sequence[RetrievalSurfaceSourceUnit],
) -> dict[str, RetrievalSurfaceSourceUnit]:
    by_key: dict[str, RetrievalSurfaceSourceUnit] = {}
    for unit in source_units:
        by_key[unit.source_unit_key] = unit
        by_key[unit.id] = unit
    return by_key


def _surface_source_chunk_indexes(
    payload: Mapping[str, object],
    source_units_by_key: Mapping[str, RetrievalSurfaceSourceUnit],
) -> tuple[int, ...]:
    explicit = _int_tuple(payload.get("source_chunk_indexes"))
    if explicit:
        return explicit
    unit_key = _compact_text(payload.get("source_unit_key"))
    unit = source_units_by_key.get(unit_key)
    return unit.source_chunk_indexes if unit is not None else ()


def _surface_source_refs(
    payload: Mapping[str, object],
    source_units_by_key: Mapping[str, RetrievalSurfaceSourceUnit],
    source_chunk_indexes: tuple[int, ...],
) -> tuple[str, ...]:
    explicit = _text_tuple(payload.get("source_refs"))
    if explicit:
        return explicit
    unit_key = _compact_text(payload.get("source_unit_key"))
    unit = source_units_by_key.get(unit_key)
    if unit is not None and unit.source_refs:
        return unit.source_refs
    return tuple(f"chunk:{index}" for index in source_chunk_indexes)


def _stable_uuid(*parts: object) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, ":".join(str(part) for part in parts)))


def _local_surface_key(payload: Mapping[str, object], *, index: int) -> str:
    explicit = _compact_text(
        payload.get("local_surface_key")
        or payload.get("surface_key")
        or payload.get("key")
    )
    if explicit:
        return explicit
    title = _compact_text(payload.get("title"))
    digest = hashlib.sha256(f"{index}:{title}".encode("utf-8")).hexdigest()[:12]
    return f"surface:{index}:{digest}"


def _parse_surfaces(
    payloads: Sequence[Mapping[str, object]],
    *,
    run_id: str,
    document_id: str,
    source_units: Sequence[RetrievalSurfaceSourceUnit],
) -> tuple[RetrievalSurfaceDraft, ...]:
    source_units_by_key = _source_unit_by_key(source_units)
    surfaces: list[RetrievalSurfaceDraft] = []
    seen_keys: set[str] = set()
    skipped_short_answer_labels = 0

    for index, item in enumerate(payloads):
        title = _compact_text(item.get("title"))
        if _is_short_answer_label(title):
            skipped_short_answer_labels += 1
            continue
        local_key = _local_surface_key(item, index=index)
        if local_key in seen_keys:
            raise KnowledgePreprocessingValidationError(
                f"Duplicate FAQ surface key: {local_key}"
            )
        seen_keys.add(local_key)

        source_chunk_indexes = _surface_source_chunk_indexes(item, source_units_by_key)
        source_refs = _surface_source_refs(
            item, source_units_by_key, source_chunk_indexes
        )
        answer = _compact_text(item.get("answer"))
        if not answer:
            raise KnowledgePreprocessingValidationError(
                f"FAQ surface {local_key} missing answer"
            )
        canonical_question = _compact_text(item.get("canonical_question")) or title
        if not title:
            title = canonical_question or f"FAQ surface {index + 1}"

        surfaces.append(
            RetrievalSurfaceDraft(
                id=_stable_uuid(run_id, "surface", local_key),
                run_id=run_id,
                document_id=document_id,
                local_surface_key=local_key,
                title=title,
                canonical_question=canonical_question or title,
                surface_kind=cast(
                    SurfaceKind,
                    _enum_text(
                        item.get("surface_kind"),
                        allowed=SURFACE_KIND_VALUES,
                        default="other",
                    ),
                ),
                answer_scope=_limited_text(item.get("answer_scope"), max_chars=1000),
                question_scope=_limited_text(
                    item.get("question_scope"), max_chars=1000
                ),
                exclusion_scope=_limited_text(
                    item.get("exclusion_scope"), max_chars=1000
                ),
                answer=_limited_text(answer, max_chars=3200),
                short_answer=_limited_text(
                    item.get("short_answer") or answer,
                    max_chars=360,
                ),
                status=cast(
                    SurfaceStatus,
                    _enum_text(
                        item.get("status"), allowed=STATUS_VALUES, default="draft"
                    ),
                ),
                publication_status=cast(
                    SurfacePublicationStatus,
                    _enum_text(
                        item.get("publication_status"),
                        allowed=PUBLICATION_STATUS_VALUES,
                        default="unpublished",
                    ),
                ),
                source_refs=source_refs,
                source_excerpt=_limited_text(
                    item.get("source_excerpt") or answer,
                    max_chars=1200,
                ),
                confidence=_confidence(item.get("confidence"), default=0.75),
                warnings=_text_tuple(item.get("warnings")),
                metadata={
                    **_json_object(item.get("metadata")),
                    "compiler": FAQ_RETRIEVAL_SURFACE_COMPILATION_PROMPT_VERSION,
                    "short_answer_service_labels_absorbed": skipped_short_answer_labels,
                },
                source_chunk_indexes=source_chunk_indexes,
            )
        )

    if not surfaces:
        raise KnowledgePreprocessingValidationError(
            "FAQ surface compiler produced no publishable surfaces"
        )
    if len(surfaces) > 1 and all(
        surface.surface_kind == "standalone" for surface in surfaces
    ):
        raise KnowledgePreprocessingValidationError(
            "FAQ surface compiler produced all-standalone surfaces; bootstrap-like output is forbidden"
        )
    return tuple(surfaces)


def _parse_relations(
    payloads: Sequence[Mapping[str, object]],
    *,
    run_id: str,
    document_id: str,
    surface_keys: frozenset[str],
) -> tuple[RetrievalSurfaceRelation, ...]:
    relations: list[RetrievalSurfaceRelation] = []
    for index, item in enumerate(payloads):
        parent_key = _compact_text(
            item.get("parent_surface_key") or item.get("from_surface_key")
        )
        child_key = _compact_text(
            item.get("child_surface_key") or item.get("to_surface_key")
        )
        if not parent_key or not child_key:
            continue
        if parent_key not in surface_keys or child_key not in surface_keys:
            raise KnowledgePreprocessingValidationError(
                f"FAQ relation {index} references unknown surface"
            )
        relation_type = _enum_text(
            item.get("relation_type"),
            allowed=RELATION_TYPE_VALUES,
            default="unrelated",
        )
        if relation_type == "duplicates" and parent_key == child_key:
            continue
        relations.append(
            RetrievalSurfaceRelation(
                id=_stable_uuid(run_id, "relation", index, parent_key, child_key),
                run_id=run_id,
                document_id=document_id,
                parent_surface_key=parent_key,
                child_surface_key=child_key,
                relation_type=cast(SurfaceRelationType, relation_type),
                reason=_limited_text(item.get("reason"), max_chars=1000),
                confidence=_confidence(item.get("confidence"), default=0.7),
                source_refs=_text_tuple(item.get("source_refs")),
            )
        )
    return tuple(relations)


def _parse_ownership(
    payloads: Sequence[Mapping[str, object]],
    *,
    run_id: str,
    document_id: str,
    surface_keys: frozenset[str],
) -> tuple[SurfaceQuestionOwnership, ...]:
    ownership: list[SurfaceQuestionOwnership] = []
    seen: set[tuple[str, str]] = set()
    for index, item in enumerate(payloads):
        question = _compact_text(item.get("question"))
        owner_key = _compact_text(
            item.get("owner_surface_key") or item.get("surface_key")
        )
        if not question or not owner_key:
            continue
        if owner_key not in surface_keys:
            raise KnowledgePreprocessingValidationError(
                f"FAQ ownership {index} references unknown owner surface"
            )
        key = (_fingerprint(question), owner_key)
        if key in seen:
            continue
        seen.add(key)
        rejected = tuple(
            surface_key
            for surface_key in _text_tuple(item.get("rejected_from_surface_keys"))
            if surface_key in surface_keys and surface_key != owner_key
        )
        ownership.append(
            SurfaceQuestionOwnership(
                id=_stable_uuid(run_id, "ownership", index, owner_key, question),
                run_id=run_id,
                document_id=document_id,
                question=question,
                owner_surface_key=owner_key,
                question_kind=cast(
                    SurfaceQuestionKind,
                    _enum_text(
                        item.get("question_kind"),
                        allowed=QUESTION_KIND_VALUES,
                        default="faq_question",
                    ),
                ),
                confidence=_confidence(item.get("confidence"), default=0.75),
                reason=_limited_text(item.get("reason"), max_chars=1000),
                rejected_from_surface_keys=rejected,
            )
        )
    return tuple(ownership)


def _parse_reassignments(
    payloads: Sequence[Mapping[str, object]],
    *,
    run_id: str,
    document_id: str,
    surface_keys: frozenset[str],
) -> tuple[SurfaceQuestionReassignment, ...]:
    reassignments: list[SurfaceQuestionReassignment] = []
    seen: set[tuple[str, str, str]] = set()
    for index, item in enumerate(payloads):
        question = _compact_text(item.get("question"))
        from_key = _compact_text(
            item.get("from_surface_key")
            or item.get("previous_owner_surface_key")
            or item.get("source_surface_key")
        )
        to_key = _compact_text(
            item.get("to_surface_key")
            or item.get("owner_surface_key")
            or item.get("target_surface_key")
        )
        if not question or not from_key or not to_key or from_key == to_key:
            continue
        if from_key not in surface_keys or to_key not in surface_keys:
            raise KnowledgePreprocessingValidationError(
                f"FAQ question reassignment {index} references unknown surface"
            )
        key = (_fingerprint(question), from_key, to_key)
        if key in seen:
            continue
        seen.add(key)
        reassignments.append(
            SurfaceQuestionReassignment(
                id=_stable_uuid(
                    run_id,
                    "question_reassignment",
                    index,
                    from_key,
                    to_key,
                    question,
                ),
                run_id=run_id,
                document_id=document_id,
                question=question,
                from_surface_key=from_key,
                to_surface_key=to_key,
                reason=_limited_text(item.get("reason"), max_chars=1000),
                confidence=_confidence(item.get("confidence"), default=0.75),
            )
        )
    return tuple(reassignments)


def _parse_merge_decisions(
    payloads: Sequence[Mapping[str, object]],
    *,
    run_id: str,
    document_id: str,
    surface_keys: frozenset[str],
) -> tuple[RetrievalSurfaceMergeDecision, ...]:
    decisions: list[RetrievalSurfaceMergeDecision] = []
    for index, item in enumerate(payloads):
        survivor = _compact_text(item.get("survivor_surface_key"))
        if not survivor:
            survivor = next(
                (key for key in _text_tuple(item.get("keep_separate_surface_keys"))),
                "",
            )
        if survivor and survivor not in surface_keys:
            raise KnowledgePreprocessingValidationError(
                f"FAQ merge decision {index} references unknown survivor surface"
            )
        merged = tuple(
            key
            for key in _text_tuple(item.get("merged_surface_keys"))
            if key in surface_keys
        )
        keep_separate = tuple(
            key
            for key in _text_tuple(item.get("keep_separate_surface_keys"))
            if key in surface_keys
        )
        decision_type = _enum_text(
            item.get("decision_type"),
            allowed=MERGE_DECISION_VALUES,
            default="keep_separate",
        )
        if not survivor and keep_separate:
            survivor = keep_separate[0]
        if not survivor:
            continue
        decisions.append(
            RetrievalSurfaceMergeDecision(
                id=_stable_uuid(run_id, "merge", index, survivor),
                run_id=run_id,
                document_id=document_id,
                survivor_surface_key=survivor,
                merged_surface_keys=merged,
                keep_separate_surface_keys=keep_separate,
                decision_type=cast(SurfaceMergeDecisionType, decision_type),
                reason=_limited_text(item.get("reason"), max_chars=1000),
                confidence=_confidence(item.get("confidence"), default=0.7),
            )
        )
    return tuple(decisions)


def parse_surface_compilation_payload(
    payload: object,
    *,
    mode: KnowledgePreprocessingMode,
    model: str,
    run_id: str,
    document_id: str,
    source_units: Sequence[RetrievalSurfaceSourceUnit],
) -> RetrievalSurfaceCompilationResult:
    if mode != MODE_FAQ:
        raise KnowledgePreprocessingValidationError(
            "Retrieval surface compiler is only available for mode=faq"
        )
    parsed = _loads_json_object(payload) if isinstance(payload, str) else payload
    if not isinstance(parsed, Mapping):
        raise KnowledgePreprocessingValidationError(
            "FAQ surface compiler payload must be a JSON object"
        )
    if "fragments" in parsed:
        raise KnowledgePreprocessingValidationError(
            "FAQ surface compiler must return surfaces[], not legacy fragments[]"
        )

    surfaces = _parse_surfaces(
        _mapping_items(parsed.get("surfaces"), field_name="surfaces"),
        run_id=run_id,
        document_id=document_id,
        source_units=source_units,
    )
    surface_keys = frozenset(surface.local_surface_key for surface in surfaces)
    relations = _parse_relations(
        _mapping_items(parsed.get("relations", []), field_name="relations"),
        run_id=run_id,
        document_id=document_id,
        surface_keys=surface_keys,
    )
    ownership = _parse_ownership(
        _mapping_items(
            parsed.get("question_ownership", []),
            field_name="question_ownership",
        ),
        run_id=run_id,
        document_id=document_id,
        surface_keys=surface_keys,
    )
    reassignments = _parse_reassignments(
        _mapping_items(
            parsed.get("question_reassignments", []),
            field_name="question_reassignments",
        ),
        run_id=run_id,
        document_id=document_id,
        surface_keys=surface_keys,
    )
    merge_decisions = _parse_merge_decisions(
        _mapping_items(parsed.get("merge_decisions", []), field_name="merge_decisions"),
        run_id=run_id,
        document_id=document_id,
        surface_keys=surface_keys,
    )

    metrics = _json_object(parsed.get("metrics"))
    metrics.update(
        {
            "surface_count": len(surfaces),
            "relation_count": len(relations),
            "ownership_count": len(ownership),
            "reassignment_count": len(reassignments),
            "merge_decision_count": len(merge_decisions),
            "source_unit_count": len(source_units),
            "bootstrap_forbidden": True,
            "json_contract": "surfaces_relations_question_ownership_merge_decisions",
        }
    )
    graph = RetrievalSurfaceGraph(
        run_id=run_id,
        document_id=document_id,
        source_units=tuple(source_units),
        surfaces=surfaces,
        relations=relations,
        ownership=ownership,
        reassignments=reassignments,
        merge_decisions=merge_decisions,
        metrics=metrics,
    )
    return RetrievalSurfaceCompilationResult(
        mode=mode,
        prompt_version=FAQ_RETRIEVAL_SURFACE_COMPILATION_PROMPT_VERSION,
        model=model,
        graph=graph,
        metrics=metrics,
    )


def _source_unit_payload(unit: RetrievalSurfaceSourceUnit) -> JsonObject:
    return {
        "id": unit.id,
        "source_unit_key": unit.source_unit_key,
        "source_chunk_indexes": list(unit.source_chunk_indexes),
        "title": unit.title,
        "body": unit.body,
        "raw_text": unit.raw_text,
        "section_path": list(unit.section_path),
        "source_refs": list(unit.source_refs),
        "children": [
            {
                "title": child.title,
                "body": child.body,
                "raw_text": child.raw_text,
                "label_kind": child.label_kind,
                "metadata": child.metadata,
            }
            for child in unit.children
        ],
        "metadata": unit.metadata,
    }


def _load_prompt(file_name: str) -> str:
    safe_name = Path(file_name).name
    if safe_name != file_name:
        raise KnowledgePreprocessingValidationError(
            f"Unsafe FAQ surface prompt file name: {file_name}"
        )
    path = PROMPTS_DIR / safe_name
    try:
        return path.read_text(encoding="utf-8").strip()
    except FileNotFoundError as exc:
        raise KnowledgePreprocessingValidationError(
            f"FAQ surface compiler prompt file not found: {safe_name}"
        ) from exc


ROLE_LABEL_SURFACE_FINGERPRINTS: frozenset[str] = frozenset(
    {
        "factual answer core",
        "factual_answer_core",
        "short answer",
        "short_answer",
        "customer intent",
        "customer_intent",
        "expected topic",
        "expected_topic",
        "test question",
        "test_question",
        "короткий ответ клиенту",
    }
)


def _is_role_label_surface(value: str) -> bool:
    fingerprint = _fingerprint(value)
    return fingerprint in ROLE_LABEL_SURFACE_FINGERPRINTS or _is_short_answer_label(
        value
    )


ProgressCallback = Callable[[Mapping[str, object]], Awaitable[None] | None]
CancelCheck = Callable[[], Awaitable[None]]


class _LangGraphCompilerState(TypedDict, total=False):
    mode: KnowledgePreprocessingMode
    source_units: Sequence[RetrievalSurfaceSourceUnit]
    file_name: str
    run_id: str
    result: RetrievalSurfaceCompilationResult


@dataclass(slots=True)
class _SectionFinding:
    local_surface_key: str
    target_surface_key: str
    action: str
    title: str
    canonical_question: str
    surface_kind: SurfaceKind
    answer: str
    short_answer: str
    answer_scope: str
    question_scope: str
    exclusion_scope: str
    variants: tuple[str, ...]
    parent_surface_key: str
    child_surface_keys: tuple[str, ...]
    source_refs: tuple[str, ...]
    source_chunk_indexes: tuple[int, ...]
    confidence: float
    reason: str
    warnings: tuple[str, ...]
    evidence_quotes: tuple[str, ...] = ()
    role_label_kind: str = ""
    role_label_metadata: JsonObject = field(default_factory=dict)


@dataclass(slots=True)
class _RegistryEntry:
    registry_entry_key: str
    canonical_question: str
    question_variants: list[str]
    surface_kind: SurfaceKind
    answer: str
    short_answer: str
    answer_scope: str
    question_scope: str
    exclusion_scope: str
    evidence_quotes: list[str]
    source_refs: list[str]
    source_chunk_indexes: list[int]
    parent_keys: list[str]
    child_keys: list[str]
    duplicate_keys: list[str]
    source_unit_keys: list[str]
    role_label_metadata: JsonObject
    title: str
    confidence: float = 0.75
    warnings: list[str] = field(default_factory=list)

    @property
    def local_surface_key(self) -> str:
        return self.registry_entry_key

    @property
    def variants(self) -> list[str]:
        return self.question_variants

    @property
    def evidence_refs(self) -> list[str]:
        return self.evidence_quotes

    @property
    def parent_surface_key(self) -> str:
        return self.parent_keys[0] if self.parent_keys else ""

    @parent_surface_key.setter
    def parent_surface_key(self, value: str) -> None:
        text = _compact_text(value)
        if text and text not in self.parent_keys:
            self.parent_keys.append(text)

    @property
    def child_surface_keys(self) -> list[str]:
        return self.child_keys


@dataclass(slots=True)
class _CompilerState:
    source_units: tuple[RetrievalSurfaceSourceUnit, ...]
    current_index: int
    processed_source_unit_keys: set[str]
    pending_source_unit_keys: list[str]
    question_registry: dict[str, _RegistryEntry]
    section_findings: list[_SectionFinding]
    answer_drafts: list[_SectionFinding]
    relations: list[RetrievalSurfaceRelation]
    ownership: list[SurfaceQuestionOwnership]
    merge_decisions: list[RetrievalSurfaceMergeDecision]
    warnings: list[str]
    metrics: dict[str, object]
    run_id: str
    file_name: str
    model: str


SECTION_FINDING_CHECKPOINT_VERSION = 1
SECTION_REGISTRY_CHECKPOINT_VERSION = 2
SECTION_REGISTRY_CHECKPOINT_KIND = "section_registry_state"


def _role_label_kind(value: object) -> str:
    fingerprint = _fingerprint(_compact_text(value))
    if fingerprint in {"factual answer core", "factual_answer_core", "answer core"}:
        return "factual_answer_core"
    if fingerprint in {
        "short answer",
        "short_answer",
        "short answer for customer",
        "client short answer",
        "короткий ответ клиенту",
    }:
        return "short_answer"
    if fingerprint in {"customer intent", "customer_intent", "intent"}:
        return "customer_intent"
    if fingerprint in {
        "expected topic",
        "expected_topic",
        "expected topic hint",
        "topic hint",
    }:
        return "expected_topic"
    if fingerprint in {"test question", "test_question", "negative test question"}:
        return "test_question"
    return ""


def _finding_role_label_kind(finding: _SectionFinding) -> str:
    return (
        _role_label_kind(finding.role_label_kind)
        or _role_label_kind(finding.local_surface_key)
        or _role_label_kind(finding.title)
        or _role_label_kind(finding.canonical_question)
        or _role_label_kind(finding.action)
        or _role_label_kind(finding.role_label_metadata.get("role_label_kind"))
    )


def _append_unique(target: list[str], values: Sequence[str]) -> None:
    for value in values:
        text = _compact_text(value)
        if text and text not in target:
            target.append(text)


def _append_unique_int(target: list[int], values: Sequence[int]) -> None:
    for value in values:
        if value not in target:
            target.append(value)


def _metadata_list(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list | tuple):
        return [str(item) for item in value]
    return []


def _put_role_label_metadata(
    entry: _RegistryEntry,
    key: str,
    values: Sequence[str],
) -> None:
    current = _metadata_list(entry.role_label_metadata.get(key))
    _append_unique(current, values)
    entry.role_label_metadata[key] = json_value_from_unknown(current)


def _finding_to_json(finding: _SectionFinding) -> JsonObject:
    return {
        "local_surface_key": finding.local_surface_key,
        "target_surface_key": finding.target_surface_key,
        "action": finding.action,
        "title": finding.title,
        "canonical_question": finding.canonical_question,
        "surface_kind": finding.surface_kind,
        "answer": finding.answer,
        "short_answer": finding.short_answer,
        "answer_scope": finding.answer_scope,
        "question_scope": finding.question_scope,
        "exclusion_scope": finding.exclusion_scope,
        "variants": json_value_from_unknown(list(finding.variants)),
        "parent_surface_key": finding.parent_surface_key,
        "child_surface_keys": json_value_from_unknown(list(finding.child_surface_keys)),
        "source_refs": json_value_from_unknown(list(finding.source_refs)),
        "source_chunk_indexes": json_value_from_unknown(
            list(finding.source_chunk_indexes)
        ),
        "confidence": finding.confidence,
        "reason": finding.reason,
        "warnings": json_value_from_unknown(list(finding.warnings)),
        "evidence_quotes": json_value_from_unknown(list(finding.evidence_quotes)),
        "role_label_kind": finding.role_label_kind,
        "role_label_metadata": finding.role_label_metadata,
    }


def _finding_from_json(value: object) -> _SectionFinding | None:
    if not isinstance(value, Mapping):
        return None
    question = _compact_text(value.get("canonical_question"))
    title = _compact_text(value.get("title"))
    answer = _compact_text(value.get("answer"))
    role_label_kind = (
        _role_label_kind(value.get("role_label_kind"))
        or _role_label_kind(value.get("local_surface_key"))
        or _role_label_kind(title)
        or _role_label_kind(question)
        or _role_label_kind(value.get("action"))
    )
    if not role_label_kind and not question and not answer:
        return None
    return _SectionFinding(
        local_surface_key=_compact_text(value.get("local_surface_key")),
        target_surface_key=_compact_text(value.get("target_surface_key")),
        action=_compact_text(value.get("action")) or "new",
        title=title or question or role_label_kind,
        canonical_question=question or title,
        surface_kind=cast(
            SurfaceKind,
            _enum_text(
                value.get("surface_kind"),
                allowed=SURFACE_KIND_VALUES,
                default="specific",
            ),
        ),
        answer=answer,
        short_answer=_compact_text(value.get("short_answer")) or answer,
        answer_scope=_limited_text(value.get("answer_scope"), max_chars=1000),
        question_scope=_limited_text(value.get("question_scope"), max_chars=1000),
        exclusion_scope=_limited_text(value.get("exclusion_scope"), max_chars=1000),
        variants=_text_tuple(value.get("variants")),
        parent_surface_key=_compact_text(value.get("parent_surface_key")),
        child_surface_keys=_text_tuple(value.get("child_surface_keys")),
        source_refs=_text_tuple(value.get("source_refs")),
        source_chunk_indexes=_int_tuple(value.get("source_chunk_indexes")),
        confidence=_confidence(value.get("confidence"), default=0.75),
        reason=_limited_text(value.get("reason"), max_chars=1000),
        warnings=_text_tuple(value.get("warnings")),
        evidence_quotes=_text_tuple(value.get("evidence_quotes")),
        role_label_kind=role_label_kind,
        role_label_metadata=_json_object(value.get("role_label_metadata")),
    )


def _section_findings_to_checkpoint(
    *,
    source_unit_key: str,
    findings: Sequence[_SectionFinding],
) -> JsonObject:
    return {
        "version": SECTION_FINDING_CHECKPOINT_VERSION,
        "source_unit_key": source_unit_key,
        "findings": json_value_from_unknown(
            [_finding_to_json(item) for item in findings]
        ),
    }


def _section_findings_from_checkpoint(value: object) -> tuple[_SectionFinding, ...]:
    if not isinstance(value, Mapping):
        return ()
    version = value.get("version")
    if version != SECTION_FINDING_CHECKPOINT_VERSION:
        return ()
    findings: list[_SectionFinding] = []
    raw_findings = value.get("findings")
    if not isinstance(raw_findings, list):
        return ()
    for item in raw_findings:
        finding = _finding_from_json(item)
        if finding is not None:
            findings.append(finding)
    return tuple(findings)


class GroqKnowledgeSurfaceCompiler(KnowledgeSurfaceCompilerPort):
    """Groq-backed section-scoped FAQ Retrieval Surface Compiler.

    This is intentionally the same production adapter class and the same
    compile_surfaces entrypoint, but the implementation is now a bounded
    section state-machine instead of a one-shot all-document compiler.
    """

    _seed_section_count = 3
    _parallel_section_concurrency = 3

    def __init__(
        self,
        *,
        client: AsyncGroq | None = None,
        model: str | None = None,
        max_source_units: int = 24,
        max_unit_chars: int = 12000,
    ) -> None:
        self._client = client or RotatingAsyncGroq()
        self._model = model or settings.GROQ_KNOWLEDGE_PREPROCESSING_MODEL
        self._max_source_units = max(1, max_source_units)
        self._max_unit_chars = max(2000, max_unit_chars)
        self._progress_callback: ProgressCallback | None = None
        self._cancel_check: CancelCheck | None = None
        self._source_unit_result_checkpoints: dict[str, object] = {}
        self._source_unit_state_checkpoints: dict[str, Mapping[str, object]] = {}
        self._checkpoint_restore_warnings: list[str] = []

    @property
    def model_name(self) -> str:
        return self._model

    def set_progress_callback(self, callback: ProgressCallback | None) -> None:
        self._progress_callback = callback

    def set_cancel_check(self, cancel_check: CancelCheck | None) -> None:
        self._cancel_check = cancel_check

    def set_source_unit_result_checkpoints(
        self,
        checkpoints: Mapping[str, object],
    ) -> None:
        restored_findings: dict[str, object] = {}
        restored_state: dict[str, Mapping[str, object]] = {}
        restore_warnings: list[str] = []

        for source_unit_key, payload in checkpoints.items():
            if isinstance(payload, Mapping) and (
                payload.get("checkpoint_kind") == SECTION_REGISTRY_CHECKPOINT_KIND
            ):
                version = payload.get("version")
                if version == SECTION_REGISTRY_CHECKPOINT_VERSION:
                    restored_state[str(source_unit_key)] = payload
                else:
                    restore_warnings.append(
                        f"incompatible_section_registry_checkpoint:"
                        f"{source_unit_key}:version={version}"
                    )
                continue

            findings = _section_findings_from_checkpoint(payload)
            if findings:
                restored_findings[str(source_unit_key)] = findings
            elif isinstance(payload, Mapping):
                restore_warnings.append(
                    f"ignored_unknown_source_unit_checkpoint:{source_unit_key}"
                )

        self._source_unit_result_checkpoints = restored_findings
        self._source_unit_state_checkpoints = restored_state
        self._checkpoint_restore_warnings = restore_warnings

    def _checkpoint_processed_count(self, checkpoint: Mapping[str, object]) -> int:
        processed = checkpoint.get("processed_source_unit_keys")
        if isinstance(processed, list | tuple):
            return len(tuple(str(item) for item in processed))
        metrics = checkpoint.get("metrics")
        if isinstance(metrics, Mapping):
            value = metrics.get("processed_source_unit_count")
            if isinstance(value, int) and not isinstance(value, bool):
                return value
            if isinstance(value, float) and value.is_integer():
                return int(value)
            if isinstance(value, str) and value.isdigit():
                return int(value)
        return 0

    def _latest_state_checkpoint(self) -> Mapping[str, object] | None:
        checkpoints = tuple(self._source_unit_state_checkpoints.values())
        if not checkpoints:
            return None
        return max(
            checkpoints,
            key=lambda item: (
                self._checkpoint_processed_count(item),
                _compact_text(item.get("source_unit_key")),
            ),
        )

    def _registry_entry_to_checkpoint(self, entry: _RegistryEntry) -> JsonObject:
        return {
            "registry_entry_key": entry.registry_entry_key,
            "canonical_question": entry.canonical_question,
            "question_variants": json_value_from_unknown(entry.question_variants),
            "surface_kind": entry.surface_kind,
            "answer": entry.answer,
            "short_answer": entry.short_answer,
            "answer_scope": entry.answer_scope,
            "question_scope": entry.question_scope,
            "exclusion_scope": entry.exclusion_scope,
            "evidence_quotes": json_value_from_unknown(entry.evidence_quotes),
            "source_refs": json_value_from_unknown(entry.source_refs),
            "source_chunk_indexes": json_value_from_unknown(entry.source_chunk_indexes),
            "parent_keys": json_value_from_unknown(entry.parent_keys),
            "child_keys": json_value_from_unknown(entry.child_keys),
            "duplicate_keys": json_value_from_unknown(entry.duplicate_keys),
            "source_unit_keys": json_value_from_unknown(entry.source_unit_keys),
            "role_label_metadata": entry.role_label_metadata,
            "title": entry.title,
            "confidence": entry.confidence,
            "warnings": json_value_from_unknown(entry.warnings),
        }

    def _registry_entry_from_checkpoint(
        self,
        value: object,
    ) -> _RegistryEntry | None:
        if not isinstance(value, Mapping):
            return None
        key = _compact_text(value.get("registry_entry_key"))
        question = _compact_text(value.get("canonical_question"))
        if not key or not question:
            return None
        return _RegistryEntry(
            registry_entry_key=key,
            canonical_question=question,
            question_variants=list(_text_tuple(value.get("question_variants"))),
            surface_kind=cast(
                SurfaceKind,
                _enum_text(
                    value.get("surface_kind"),
                    allowed=SURFACE_KIND_VALUES,
                    default="specific",
                ),
            ),
            answer=_compact_text(value.get("answer")),
            short_answer=_compact_text(value.get("short_answer")),
            answer_scope=_limited_text(value.get("answer_scope"), max_chars=1000),
            question_scope=_limited_text(value.get("question_scope"), max_chars=1000),
            exclusion_scope=_limited_text(
                value.get("exclusion_scope"),
                max_chars=1000,
            ),
            evidence_quotes=list(_text_tuple(value.get("evidence_quotes"))),
            source_refs=list(_text_tuple(value.get("source_refs"))),
            source_chunk_indexes=list(_int_tuple(value.get("source_chunk_indexes"))),
            parent_keys=list(_text_tuple(value.get("parent_keys"))),
            child_keys=list(_text_tuple(value.get("child_keys"))),
            duplicate_keys=list(_text_tuple(value.get("duplicate_keys"))),
            source_unit_keys=list(_text_tuple(value.get("source_unit_keys"))),
            role_label_metadata=_json_object(value.get("role_label_metadata")),
            title=_compact_text(value.get("title")) or question,
            confidence=_confidence(value.get("confidence"), default=0.75),
            warnings=list(_text_tuple(value.get("warnings"))),
        )

    def _registry_snapshot_for_checkpoint(self, state: _CompilerState) -> JsonObject:
        return {
            "entries": json_value_from_unknown(
                [
                    self._registry_entry_to_checkpoint(entry)
                    for entry in state.question_registry.values()
                ]
            )
        }

    def _restore_registry_snapshot(
        self,
        *,
        state: _CompilerState,
        snapshot: object,
    ) -> None:
        if not isinstance(snapshot, Mapping):
            raise KnowledgePreprocessingValidationError(
                "section registry checkpoint missing registry_snapshot_after_section"
            )
        raw_entries = snapshot.get("entries")
        if not isinstance(raw_entries, list):
            raise KnowledgePreprocessingValidationError(
                "section registry checkpoint registry snapshot must contain entries[]"
            )
        restored: dict[str, _RegistryEntry] = {}
        for raw_entry in raw_entries:
            entry = self._registry_entry_from_checkpoint(raw_entry)
            if entry is not None:
                restored[entry.registry_entry_key] = entry
        state.question_registry = restored

    def _restore_checkpointed_state(self, state: _CompilerState) -> _CompilerState:
        if self._checkpoint_restore_warnings:
            state.warnings.extend(self._checkpoint_restore_warnings)
            state.metrics["checkpoint_restore_warnings"] = json_value_from_unknown(
                list(self._checkpoint_restore_warnings)
            )

        latest = self._latest_state_checkpoint()
        if latest is not None:
            self._restore_registry_snapshot(
                state=state,
                snapshot=latest.get("registry_snapshot_after_section"),
            )
            processed = _text_tuple(latest.get("processed_source_unit_keys"))
            state.processed_source_unit_keys = set(processed)
            state.pending_source_unit_keys = [
                unit.source_unit_key
                for unit in state.source_units
                if unit.source_unit_key not in state.processed_source_unit_keys
            ]
            state.warnings.extend(_text_tuple(latest.get("warnings")))
            state.metrics.update(_json_object(latest.get("metrics")))
            state.metrics["checkpoint_restore_mode"] = "section_registry_state"
            state.metrics["checkpoint_restored_source_unit_key"] = _compact_text(
                latest.get("source_unit_key")
            )
            state.metrics["checkpoint_restored_processed_source_unit_keys"] = (
                json_value_from_unknown(list(state.processed_source_unit_keys))
            )
            state.metrics["checkpoint_restored_processed_source_unit_count"] = len(
                state.processed_source_unit_keys
            )
            return state

        if self._source_unit_result_checkpoints:
            state.metrics["checkpoint_restore_mode"] = "legacy_section_findings_rebuild"
            for unit in state.source_units:
                raw_findings = self._source_unit_result_checkpoints.get(
                    unit.source_unit_key
                )
                if not isinstance(raw_findings, tuple) or not all(
                    isinstance(item, _SectionFinding) for item in raw_findings
                ):
                    continue
                findings = cast(tuple[_SectionFinding, ...], raw_findings)
                self._merge_section_findings_into_registry(
                    state=state,
                    unit=unit,
                    findings=findings,
                    merge_context={"registry_updates": []},
                )
            state.metrics["checkpoint_restored_processed_source_unit_count"] = len(
                state.processed_source_unit_keys
            )
            return state

        state.metrics["checkpoint_restore_mode"] = "none"
        return state

    def _build_source_unit_checkpoint(
        self,
        *,
        state: _CompilerState,
        unit: RetrievalSurfaceSourceUnit,
        findings: Sequence[_SectionFinding],
        merge_context: Mapping[str, object],
    ) -> JsonObject:
        processed = [
            source_unit.source_unit_key
            for source_unit in state.source_units
            if source_unit.source_unit_key in state.processed_source_unit_keys
        ]
        registry_updates = self._registry_updates_from_context(merge_context)
        relation_count = sum(
            len(entry.parent_keys) + len(entry.child_keys)
            for entry in state.question_registry.values()
        )
        metrics: JsonObject = {
            "processed_source_unit_count": len(processed),
            "registry_size": len(state.question_registry),
            "finding_count": len(findings),
            "surface_count_so_far": len(state.question_registry),
            "relation_count_so_far": relation_count,
            "checkpoint_version": SECTION_REGISTRY_CHECKPOINT_VERSION,
        }
        return {
            "version": SECTION_REGISTRY_CHECKPOINT_VERSION,
            "checkpoint_kind": SECTION_REGISTRY_CHECKPOINT_KIND,
            "run_id": state.run_id,
            "source_unit_key": unit.source_unit_key,
            "processed_source_unit_keys": json_value_from_unknown(processed),
            "registry_snapshot_after_section": self._registry_snapshot_for_checkpoint(
                state
            ),
            "section_findings": json_value_from_unknown(
                [_finding_to_json(item) for item in findings]
            ),
            "registry_updates_applied": json_value_from_unknown(
                [dict(item) for item in registry_updates]
            ),
            "relations_snapshot": json_value_from_unknown([]),
            "ownership_snapshot": json_value_from_unknown([]),
            "merge_decisions_snapshot": json_value_from_unknown([]),
            "warnings": json_value_from_unknown(list(state.warnings)),
            "metrics": metrics,
        }

    def _model_for_request(self, *, prompt: str, max_tokens: int) -> str:
        # Provider response is the source of truth. Keep current model routing.
        return self._model

    async def _ensure_not_cancelled(self) -> None:
        if self._cancel_check is not None:
            await self._cancel_check()

    async def _emit_progress(
        self,
        *,
        stage_kind: str,
        status: str,
        input_summary: str = "",
        output_summary: str = "",
        metrics: Mapping[str, object] | None = None,
        source_unit_checkpoint: JsonObject | None = None,
    ) -> None:
        callback = self._progress_callback
        if callback is None:
            return

        event_metrics: dict[str, object] = dict(metrics or {})
        event: dict[str, object] = {
            "stage_kind": stage_kind,
            "status": status,
            "input_summary": input_summary,
            "output_summary": output_summary,
            "metrics": event_metrics,
        }
        if source_unit_checkpoint is not None:
            event["source_unit_checkpoint"] = source_unit_checkpoint
            event["source_unit_checkpoint_version"] = source_unit_checkpoint.get(
                "version",
                SECTION_REGISTRY_CHECKPOINT_VERSION,
            )
            for key in (
                "source_unit_key",
                "processed_source_unit_keys",
                "registry_snapshot_after_section",
            ):
                if key in source_unit_checkpoint:
                    event[key] = source_unit_checkpoint[key]
            checkpoint_metrics = source_unit_checkpoint.get("metrics")
            if isinstance(checkpoint_metrics, Mapping):
                event_metrics.update(
                    {str(key): value for key, value in checkpoint_metrics.items()}
                )
                for key in (
                    "registry_size",
                    "finding_count",
                    "surface_count_so_far",
                    "relation_count_so_far",
                ):
                    if key in checkpoint_metrics:
                        event[key] = checkpoint_metrics[key]
        result = callback(event)
        if result is not None:
            await result

    async def _request_json(self, *, prompt: str, max_tokens: int) -> tuple[str, str]:
        request_model = self._model_for_request(prompt=prompt, max_tokens=max_tokens)
        response = await self._client.chat.completions.create(
            model=request_model,
            messages=[
                {"role": "system", "content": STRICT_JSON_SYSTEM_MESSAGE},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or ""
        return request_model, content

    def _initialize_registry(
        self,
        *,
        source_units: Sequence[RetrievalSurfaceSourceUnit],
        file_name: str,
        run_id: str,
    ) -> _CompilerState:
        units = tuple(source_units)
        return _CompilerState(
            source_units=units,
            current_index=0,
            processed_source_unit_keys=set(),
            pending_source_unit_keys=[unit.source_unit_key for unit in units],
            question_registry={},
            section_findings=[],
            answer_drafts=[],
            relations=[],
            ownership=[],
            merge_decisions=[],
            warnings=[],
            metrics={
                "compiler_kind": "sectional_registry_state_machine",
                "graph_execution": "langgraph_stategraph",
                "section_scoped_prompts": True,
                "one_shot_all_source_units_prompt": False,
                "seed_section_count": self._seed_section_count,
                "parallel_section_concurrency": self._parallel_section_concurrency,
            },
            run_id=run_id,
            file_name=file_name,
            model=self.model_name,
        )

    def _section_source_unit_payload(
        self,
        unit: RetrievalSurfaceSourceUnit,
    ) -> JsonObject:
        return {
            "id": unit.id,
            "source_unit_key": unit.source_unit_key,
            "source_chunk_indexes": json_value_from_unknown(
                list(unit.source_chunk_indexes)
            ),
            "title": unit.title,
            "body": _limited_text(unit.body, max_chars=self._max_unit_chars),
            "raw_text": _limited_text(unit.raw_text, max_chars=self._max_unit_chars),
            "section_path": json_value_from_unknown(list(unit.section_path)),
            "source_refs": json_value_from_unknown(list(unit.source_refs)),
            "children": json_value_from_unknown(
                [
                    {
                        "title": child.title,
                        "body": _limited_text(child.body, max_chars=2000),
                        "raw_text": _limited_text(child.raw_text, max_chars=2000),
                        "label_kind": child.label_kind,
                        "metadata": child.metadata,
                    }
                    for child in unit.children
                ]
            ),
            "metadata": unit.metadata,
        }

    def _registry_snapshot(self, state: _CompilerState) -> JsonObject:
        known_questions: list[JsonObject] = []
        for entry in state.question_registry.values():
            known_questions.append(
                {
                    "surface_key": entry.local_surface_key,
                    "canonical_question": entry.canonical_question,
                    "variants": json_value_from_unknown(entry.variants[:8]),
                    "surface_kind": entry.surface_kind,
                    "parent_surface_key": entry.parent_surface_key,
                    "child_surface_keys": json_value_from_unknown(
                        entry.child_surface_keys[:12]
                    ),
                    "short_answer": _limited_text(
                        entry.short_answer,
                        max_chars=360,
                    ),
                    "evidence_refs": json_value_from_unknown(
                        entry.evidence_refs[:12] or entry.source_refs[:12]
                    ),
                }
            )
        return {
            "registry_size": len(state.question_registry),
            "known_canonical_questions": json_value_from_unknown(known_questions[:80]),
        }

    def _build_section_prompt(
        self,
        *,
        stage_kind: str,
        prompt_file: str,
        state: _CompilerState,
        unit: RetrievalSurfaceSourceUnit,
        match_context: Mapping[str, object] | None = None,
        section_findings: Sequence[_SectionFinding] = (),
        final_reconciliation: bool = False,
    ) -> str:
        payload: JsonObject = {
            "task": "faq_sectional_registry_compilation",
            "stage": stage_kind,
            "file_name": state.file_name,
            "run_id": state.run_id,
            "prompt_version": FAQ_RETRIEVAL_SURFACE_COMPILATION_PROMPT_VERSION,
            "rules": json_value_from_unknown(
                [
                    "You receive exactly one markdown source section.",
                    "Never infer from the full document.",
                    "surface means a customer-answerable intent.",
                    "Role labels are evidence fields, not standalone surfaces.",
                    "Forbidden standalone role labels: factual_answer_core, short_answer, customer_intent, expected_topic, test_question.",
                    "Use compact JSON only.",
                ]
            ),
            "json_contract": {
                "match_stage": {
                    "root_fields": ["matches", "warnings", "metrics"],
                    "matches_item_fields": [
                        "registry_surface_key",
                        "relation",
                        "confidence",
                        "reason",
                    ],
                },
                "discover_stage": {
                    "root_fields": ["findings", "warnings", "metrics"],
                    "findings_item_fields": [
                        "action",
                        "target_surface_key",
                        "local_surface_key",
                        "title",
                        "canonical_question",
                        "surface_kind",
                        "answer",
                        "short_answer",
                        "answer_scope",
                        "question_scope",
                        "exclusion_scope",
                        "variants",
                        "parent_surface_key",
                        "child_surface_keys",
                        "source_refs",
                        "confidence",
                        "reason",
                        "warnings",
                    ],
                },
            },
            "registry_snapshot": self._registry_snapshot(state),
            "source_unit": self._section_source_unit_payload(unit),
        }
        if match_context is not None:
            payload["match_context"] = json_value_from_unknown(match_context)
        if section_findings:
            payload["section_findings"] = json_value_from_unknown(
                [_finding_to_json(item) for item in section_findings]
            )
        if final_reconciliation:
            payload["final_reconciliation"] = True
        node_instruction = _load_prompt(prompt_file)
        return (
            f"{node_instruction}\n\n"
            "FAQ SECTION REGISTRY COMPILER NODE.\n"
            "Return exactly one JSON object for this node contract.\n\n"
            "SECTION_COMPILATION_INPUT_JSON:\n"
            f"{json.dumps(payload, ensure_ascii=False)}"
        )

    async def _match_section_against_registry(
        self,
        *,
        state: _CompilerState,
        unit: RetrievalSurfaceSourceUnit,
    ) -> Mapping[str, object]:
        await self._ensure_not_cancelled()
        unit_text = _fingerprint(" ".join((unit.title, unit.body, unit.raw_text)))
        matches: list[JsonObject] = []
        for key, entry in state.question_registry.items():
            question_fp = _fingerprint(entry.canonical_question)
            answer_fp = _fingerprint(entry.answer)
            if question_fp and question_fp in unit_text:
                relation = "extends_existing_question"
                confidence = 0.72
            elif answer_fp and answer_fp in unit_text:
                relation = "adds_evidence"
                confidence = 0.68
            else:
                continue
            matches.append(
                {
                    "registry_surface_key": key,
                    "relation": relation,
                    "confidence": confidence,
                    "reason": "deterministic_registry_snapshot_match",
                }
            )
        return {
            "matches": json_value_from_unknown(matches[:12]),
            "warnings": [],
            "metrics": {
                "deterministic_match": True,
                "registry_size": len(state.question_registry),
            },
        }

    async def _discover_section_findings(
        self,
        *,
        state: _CompilerState,
        unit: RetrievalSurfaceSourceUnit,
        match_context: Mapping[str, object],
    ) -> tuple[_SectionFinding, ...]:
        cached = self._source_unit_result_checkpoints.get(unit.source_unit_key)
        if isinstance(cached, tuple) and all(
            isinstance(item, _SectionFinding) for item in cached
        ):
            findings = cast(tuple[_SectionFinding, ...], cached)
            await self._emit_progress(
                stage_kind="source_unit_checkpoint_reused",
                status="completed",
                input_summary=f"section={unit.source_unit_key}",
                output_summary=f"findings={len(findings)} source=checkpoint",
                metrics={
                    "source_unit_key": unit.source_unit_key,
                    "checkpoint_reused": True,
                    "finding_count": len(findings),
                },
            )
            return findings

        await self._ensure_not_cancelled()
        prompt = self._build_section_prompt(
            stage_kind="discover_section_findings",
            prompt_file=FAQ_SECTION_FINDINGS_PROMPT_FILE,
            state=state,
            unit=unit,
            match_context=match_context,
        )
        _, content = await self._request_json(prompt=prompt, max_tokens=2200)
        payload = _loads_json_object(content)
        findings = self._parse_section_findings(payload, unit=unit)
        return findings

    def _parse_section_findings(
        self,
        payload: Mapping[str, object],
        *,
        unit: RetrievalSurfaceSourceUnit,
    ) -> tuple[_SectionFinding, ...]:
        raw_findings = payload.get("findings")
        if not isinstance(raw_findings, list):
            return ()

        findings: list[_SectionFinding] = []
        for item in raw_findings:
            finding = _finding_from_json(item)
            if finding is None:
                continue
            source_refs = finding.source_refs or unit.source_refs
            source_chunk_indexes = (
                finding.source_chunk_indexes or unit.source_chunk_indexes
            )
            findings.append(
                _SectionFinding(
                    local_surface_key=finding.local_surface_key,
                    target_surface_key=finding.target_surface_key,
                    action=finding.action,
                    title=finding.title,
                    canonical_question=finding.canonical_question,
                    surface_kind=finding.surface_kind,
                    answer=finding.answer,
                    short_answer=finding.short_answer,
                    answer_scope=finding.answer_scope,
                    question_scope=finding.question_scope,
                    exclusion_scope=finding.exclusion_scope,
                    variants=finding.variants,
                    parent_surface_key=finding.parent_surface_key,
                    child_surface_keys=finding.child_surface_keys,
                    source_refs=source_refs,
                    source_chunk_indexes=source_chunk_indexes,
                    confidence=finding.confidence,
                    reason=finding.reason,
                    warnings=finding.warnings,
                )
            )
        return tuple(findings)

    def _registry_updates_from_context(
        self,
        merge_context: Mapping[str, object],
    ) -> tuple[Mapping[str, object], ...]:
        raw_updates = merge_context.get("registry_updates")
        if isinstance(raw_updates, list):
            return tuple(item for item in raw_updates if isinstance(item, Mapping))

        raw_decisions = merge_context.get("merge_decisions")
        if not isinstance(raw_decisions, list):
            return ()

        updates: list[Mapping[str, object]] = []
        for item in raw_decisions:
            if not isinstance(item, Mapping):
                continue
            source_key = _compact_text(
                item.get("source_local_surface_key")
                or item.get("local_surface_key")
                or item.get("source_surface_key")
            )
            target_key = _compact_text(
                item.get("target_surface_key") or item.get("survivor_surface_key")
            )
            if not source_key and not target_key:
                continue
            updates.append(
                {
                    "operation": "extend" if target_key else "create",
                    "target_surface_key": target_key,
                    "source_local_surface_key": source_key,
                    "append_variants": list(_text_tuple(item.get("append_variants"))),
                    "append_source_refs": list(
                        _text_tuple(item.get("append_source_refs"))
                    ),
                    "append_source_chunk_indexes": list(
                        _int_tuple(item.get("append_source_chunk_indexes"))
                    ),
                    "append_evidence_quotes": list(
                        _text_tuple(item.get("append_evidence_quotes"))
                    ),
                    "compatibility_source": "merge_decisions",
                }
            )
        return tuple(updates)

    async def _plan_registry_merge(
        self,
        *,
        state: _CompilerState,
        unit: RetrievalSurfaceSourceUnit,
        findings: Sequence[_SectionFinding],
        match_context: Mapping[str, object],
    ) -> Mapping[str, object]:
        if not findings:
            return {
                "registry_updates": [],
                "warnings": [],
                "metrics": {"empty": True, "advisory": True},
            }
        await self._ensure_not_cancelled()
        prompt = self._build_section_prompt(
            stage_kind="merge_section_findings_into_registry",
            prompt_file=FAQ_REGISTRY_MERGE_PROMPT_FILE,
            state=state,
            unit=unit,
            match_context=match_context,
            section_findings=findings,
        )
        try:
            _, content = await self._request_json(prompt=prompt, max_tokens=1600)
            return _loads_json_object(content)
        except Exception as exc:
            return {
                "registry_updates": [],
                "warnings": [f"registry_merge_advisory_ignored:{type(exc).__name__}"],
                "metrics": {"advisory_parse_failed": True},
            }

    def _can_deterministically_merge(
        self,
        *,
        existing: _RegistryEntry,
        finding: _SectionFinding,
    ) -> bool:
        if existing.surface_kind in {"umbrella", "child"} or finding.surface_kind in {
            "umbrella",
            "child",
        }:
            return existing.surface_kind == finding.surface_kind
        return True

    def _deterministic_registry_target(
        self,
        *,
        state: _CompilerState,
        unit: RetrievalSurfaceSourceUnit,
        finding: _SectionFinding,
    ) -> str:
        explicit = _compact_text(finding.target_surface_key)
        if explicit in state.question_registry:
            return explicit

        canonical_fp = _fingerprint(finding.canonical_question)
        if canonical_fp:
            for key, entry in state.question_registry.items():
                if self._can_deterministically_merge(existing=entry, finding=finding):
                    if _fingerprint(entry.canonical_question) == canonical_fp:
                        return key

        short_fp = _fingerprint(finding.short_answer)
        if short_fp:
            for key, entry in state.question_registry.items():
                if self._can_deterministically_merge(existing=entry, finding=finding):
                    if _fingerprint(entry.short_answer) == short_fp:
                        return key

        answer_fp = _fingerprint(finding.answer)
        if answer_fp:
            for key, entry in state.question_registry.items():
                if self._can_deterministically_merge(existing=entry, finding=finding):
                    if _fingerprint(entry.answer) == answer_fp:
                        return key
                    if unit.source_unit_key in entry.source_unit_keys:
                        if _fingerprint(entry.answer) == answer_fp:
                            return key

        return ""

    def _new_registry_key(
        self,
        state: _CompilerState,
        finding: _SectionFinding,
    ) -> str:
        explicit = _compact_text(finding.local_surface_key)
        if explicit and not _is_role_label_surface(explicit):
            candidate = explicit
        else:
            digest = hashlib.sha256(
                (finding.canonical_question or finding.answer).encode("utf-8")
            ).hexdigest()[:12]
            candidate = f"surface:{digest}"

        if candidate not in state.question_registry:
            return candidate

        suffix = 2
        while f"{candidate}:{suffix}" in state.question_registry:
            suffix += 1
        return f"{candidate}:{suffix}"

    def _create_registry_entry(
        self,
        *,
        state: _CompilerState,
        unit: RetrievalSurfaceSourceUnit,
        finding: _SectionFinding,
    ) -> _RegistryEntry:
        key = self._new_registry_key(state, finding)
        entry = _RegistryEntry(
            registry_entry_key=key,
            canonical_question=finding.canonical_question or finding.title,
            question_variants=list(finding.variants),
            surface_kind=finding.surface_kind,
            answer=finding.answer,
            short_answer=_limited_text(finding.short_answer, max_chars=360),
            answer_scope=finding.answer_scope,
            question_scope=finding.question_scope,
            exclusion_scope=finding.exclusion_scope,
            evidence_quotes=list(finding.evidence_quotes),
            source_refs=list(finding.source_refs),
            source_chunk_indexes=list(finding.source_chunk_indexes),
            parent_keys=(
                [finding.parent_surface_key] if finding.parent_surface_key else []
            ),
            child_keys=list(finding.child_surface_keys),
            duplicate_keys=[],
            source_unit_keys=[unit.source_unit_key],
            role_label_metadata=dict(finding.role_label_metadata),
            title=finding.title or finding.canonical_question,
            confidence=finding.confidence,
            warnings=list(finding.warnings),
        )
        state.question_registry[key] = entry
        return entry

    def _merge_finding_into_entry(
        self,
        *,
        entry: _RegistryEntry,
        finding: _SectionFinding,
        unit: RetrievalSurfaceSourceUnit,
    ) -> None:
        if finding.answer and len(finding.answer) > len(entry.answer):
            entry.answer = finding.answer
        if finding.short_answer and len(finding.short_answer) <= 360:
            entry.short_answer = finding.short_answer
        _append_unique(entry.question_variants, finding.variants)
        _append_unique(entry.source_refs, finding.source_refs)
        _append_unique(entry.evidence_quotes, finding.evidence_quotes)
        _append_unique_int(entry.source_chunk_indexes, finding.source_chunk_indexes)
        _append_unique(entry.source_unit_keys, (unit.source_unit_key,))
        _append_unique(entry.parent_keys, (finding.parent_surface_key,))
        _append_unique(entry.child_keys, finding.child_surface_keys)
        _append_unique(entry.warnings, finding.warnings)
        entry.confidence = max(entry.confidence, finding.confidence)

    def _role_label_group_surface_finding(
        self,
        *,
        unit: RetrievalSurfaceSourceUnit,
        role_label_findings: Sequence[_SectionFinding],
    ) -> _SectionFinding | None:
        by_kind: dict[str, list[_SectionFinding]] = {}
        for finding in role_label_findings:
            kind = _finding_role_label_kind(finding)
            if kind:
                by_kind.setdefault(kind, []).append(finding)

        intents = by_kind.get("customer_intent", [])
        answer_cores = by_kind.get("factual_answer_core", [])
        short_answers = by_kind.get("short_answer", [])

        if not intents or not (answer_cores or short_answers):
            return None

        intent = intents[0]
        answer_core = answer_cores[0] if answer_cores else short_answers[0]
        short_answer = short_answers[0] if short_answers else answer_core

        variants: list[str] = []
        evidence_quotes: list[str] = []
        source_refs: list[str] = []
        source_chunk_indexes: list[int] = []
        role_metadata: JsonObject = {}

        for finding in role_label_findings:
            kind = _finding_role_label_kind(finding)
            values = tuple(
                item
                for item in (
                    finding.canonical_question,
                    finding.title,
                    finding.answer,
                    finding.short_answer,
                )
                if item
            )
            if kind:
                role_metadata[kind] = json_value_from_unknown(list(values))
            if kind in {"customer_intent", "expected_topic", "test_question"}:
                _append_unique(variants, values)
            if kind == "factual_answer_core":
                _append_unique(evidence_quotes, values)
            _append_unique(source_refs, finding.source_refs)
            _append_unique_int(source_chunk_indexes, finding.source_chunk_indexes)

        digest = hashlib.sha256(unit.source_unit_key.encode("utf-8")).hexdigest()[:12]
        canonical_question = intent.answer or intent.canonical_question or intent.title
        answer = answer_core.answer or answer_core.short_answer or answer_core.title
        return _SectionFinding(
            local_surface_key=f"role_group:{digest}",
            target_surface_key="",
            action="create",
            title=canonical_question,
            canonical_question=canonical_question,
            surface_kind="specific",
            answer=answer,
            short_answer=short_answer.short_answer or short_answer.answer or answer,
            answer_scope=answer_core.answer_scope,
            question_scope=intent.question_scope,
            exclusion_scope="",
            variants=tuple(variants),
            parent_surface_key="",
            child_surface_keys=(),
            source_refs=tuple(source_refs or unit.source_refs),
            source_chunk_indexes=tuple(
                source_chunk_indexes or unit.source_chunk_indexes
            ),
            confidence=max(
                (item.confidence for item in role_label_findings),
                default=0.75,
            ),
            reason="deterministic_role_label_group_absorption",
            warnings=(),
            evidence_quotes=tuple(evidence_quotes),
            role_label_metadata={
                **role_metadata,
                "absorbed_role_label_group": True,
            },
        )

    def _absorb_role_label_into_entry(
        self,
        *,
        entry: _RegistryEntry,
        finding: _SectionFinding,
        unit: RetrievalSurfaceSourceUnit,
    ) -> None:
        kind = _finding_role_label_kind(finding)
        values = tuple(
            item
            for item in (
                finding.canonical_question,
                finding.title,
                finding.answer,
                finding.short_answer,
            )
            if item
        )
        if kind == "factual_answer_core":
            if finding.answer and len(finding.answer) > len(entry.answer):
                entry.answer = finding.answer
            _append_unique(entry.evidence_quotes, values)
            _put_role_label_metadata(entry, "factual_answer_core", values)
        elif kind == "short_answer":
            entry.short_answer = _limited_text(
                finding.short_answer or finding.answer or finding.title,
                max_chars=360,
            )
            _put_role_label_metadata(entry, "short_answer", values)
        elif kind == "customer_intent":
            question = finding.answer or finding.canonical_question or finding.title
            if question:
                if not entry.canonical_question:
                    entry.canonical_question = question
                elif _fingerprint(entry.canonical_question) != _fingerprint(question):
                    _append_unique(entry.question_variants, (question,))
            _put_role_label_metadata(entry, "customer_intent", values)
        elif kind == "expected_topic":
            _append_unique(entry.question_variants, values)
            _put_role_label_metadata(entry, "expected_topic", values)
        elif kind == "test_question":
            _append_unique(entry.question_variants, values)
            _put_role_label_metadata(entry, "test_question", values)

        _append_unique(entry.source_refs, finding.source_refs or unit.source_refs)
        _append_unique_int(
            entry.source_chunk_indexes,
            finding.source_chunk_indexes or unit.source_chunk_indexes,
        )
        _append_unique(entry.source_unit_keys, (unit.source_unit_key,))

    def _apply_registry_update(
        self,
        *,
        state: _CompilerState,
        update: Mapping[str, object],
        source_key_to_entry_key: Mapping[str, str],
    ) -> None:
        operation = _compact_text(update.get("operation"))
        if operation not in {
            "create",
            "add_evidence",
            "extend",
            "refine",
            "add_child",
            "add_parent",
            "mark_duplicate",
            "mark_overlap",
            "skip_role_label",
        }:
            return

        if operation == "skip_role_label":
            return

        source_key = _compact_text(update.get("source_local_surface_key"))
        target_key = _compact_text(
            update.get("target_surface_key")
        ) or source_key_to_entry_key.get(source_key, "")

        if operation == "create":
            if source_key in source_key_to_entry_key:
                return
            finding = _finding_from_json(update.get("new_surface"))
            if finding is None or _finding_role_label_kind(finding):
                return
            if self._deterministic_registry_target(
                state=state,
                unit=state.source_units[0],
                finding=finding,
            ):
                return
            self._create_registry_entry(
                state=state,
                unit=state.source_units[0],
                finding=finding,
            )
            return

        if target_key not in state.question_registry:
            return

        entry = state.question_registry[target_key]
        _append_unique(
            entry.question_variants, _text_tuple(update.get("append_variants"))
        )
        _append_unique(entry.source_refs, _text_tuple(update.get("append_source_refs")))
        _append_unique_int(
            entry.source_chunk_indexes,
            _int_tuple(update.get("append_source_chunk_indexes")),
        )
        _append_unique(
            entry.evidence_quotes,
            _text_tuple(update.get("append_evidence_quotes")),
        )

        answer_delta = _limited_text(update.get("append_answer_delta"), max_chars=1200)
        if answer_delta and _fingerprint(answer_delta) not in _fingerprint(
            entry.answer
        ):
            entry.answer = f"{entry.answer}\\n\\n{answer_delta}".strip()

        if operation == "add_child":
            child_key = source_key_to_entry_key.get(source_key, source_key)
            if child_key in state.question_registry and child_key != target_key:
                _append_unique(entry.child_keys, (child_key,))
                _append_unique(
                    state.question_registry[child_key].parent_keys, (target_key,)
                )
        elif operation == "add_parent":
            parent_key = source_key_to_entry_key.get(source_key, source_key)
            if parent_key in state.question_registry and parent_key != target_key:
                _append_unique(entry.parent_keys, (parent_key,))
                _append_unique(
                    state.question_registry[parent_key].child_keys, (target_key,)
                )
        elif operation == "mark_duplicate":
            duplicate_key = source_key_to_entry_key.get(source_key, source_key)
            if duplicate_key and duplicate_key != target_key:
                _append_unique(entry.duplicate_keys, (duplicate_key,))

    def _apply_registry_advisory_updates(
        self,
        *,
        state: _CompilerState,
        merge_context: Mapping[str, object],
        source_key_to_entry_key: Mapping[str, str],
    ) -> None:
        for update in self._registry_updates_from_context(merge_context):
            self._apply_registry_update(
                state=state,
                update=update,
                source_key_to_entry_key=source_key_to_entry_key,
            )

    def _merge_section_findings_into_registry(
        self,
        *,
        state: _CompilerState,
        unit: RetrievalSurfaceSourceUnit,
        findings: Sequence[_SectionFinding],
        merge_context: Mapping[str, object],
    ) -> None:
        if not findings:
            state.processed_source_unit_keys.add(unit.source_unit_key)
            if unit.source_unit_key in state.pending_source_unit_keys:
                state.pending_source_unit_keys.remove(unit.source_unit_key)
            return

        role_label_findings = [
            finding for finding in findings if _finding_role_label_kind(finding)
        ]
        surface_findings = [
            finding for finding in findings if not _finding_role_label_kind(finding)
        ]

        if not surface_findings:
            grouped = self._role_label_group_surface_finding(
                unit=unit,
                role_label_findings=role_label_findings,
            )
            if grouped is not None:
                surface_findings.append(grouped)

        source_key_to_entry_key: dict[str, str] = {}

        for finding in surface_findings:
            if _is_role_label_surface(finding.title) or _is_role_label_surface(
                finding.canonical_question
            ):
                role_label_findings.append(finding)
                continue

            target_key = self._deterministic_registry_target(
                state=state,
                unit=unit,
                finding=finding,
            )

            if target_key:
                entry = state.question_registry[target_key]
                self._merge_finding_into_entry(
                    entry=entry,
                    finding=finding,
                    unit=unit,
                )
            else:
                entry = self._create_registry_entry(
                    state=state,
                    unit=unit,
                    finding=finding,
                )
                target_key = entry.registry_entry_key

            source_key_to_entry_key[finding.local_surface_key] = target_key

            if finding.parent_surface_key in state.question_registry:
                _append_unique(entry.parent_keys, (finding.parent_surface_key,))
                parent = state.question_registry[finding.parent_surface_key]
                _append_unique(parent.child_keys, (target_key,))

            for child_key in finding.child_surface_keys:
                if child_key in state.question_registry:
                    _append_unique(entry.child_keys, (child_key,))
                    _append_unique(
                        state.question_registry[child_key].parent_keys,
                        (target_key,),
                    )

            state.section_findings.append(finding)
            state.answer_drafts.append(finding)

        if role_label_findings:
            target_entry: _RegistryEntry | None = None
            if source_key_to_entry_key:
                target_entry = state.question_registry[
                    next(iter(source_key_to_entry_key.values()))
                ]
            else:
                for entry in reversed(tuple(state.question_registry.values())):
                    if unit.source_unit_key in entry.source_unit_keys:
                        target_entry = entry
                        break

            if target_entry is not None:
                for finding in role_label_findings:
                    self._absorb_role_label_into_entry(
                        entry=target_entry,
                        finding=finding,
                        unit=unit,
                    )
                    state.section_findings.append(finding)

        self._apply_registry_advisory_updates(
            state=state,
            merge_context=merge_context,
            source_key_to_entry_key=source_key_to_entry_key,
        )

        state.processed_source_unit_keys.add(unit.source_unit_key)
        if unit.source_unit_key in state.pending_source_unit_keys:
            state.pending_source_unit_keys.remove(unit.source_unit_key)

    async def _process_seed_section(
        self,
        *,
        state: _CompilerState,
        unit_index: int,
        unit: RetrievalSurfaceSourceUnit,
    ) -> _CompilerState:
        state.current_index = unit_index
        match_context = await self._match_section_against_registry(
            state=state,
            unit=unit,
        )
        findings = await self._discover_section_findings(
            state=state,
            unit=unit,
            match_context=match_context,
        )
        merge_context = await self._plan_registry_merge(
            state=state,
            unit=unit,
            findings=findings,
            match_context=match_context,
        )
        self._merge_section_findings_into_registry(
            state=state,
            unit=unit,
            findings=findings,
            merge_context=merge_context,
        )
        await self._emit_progress(
            stage_kind="process_seed_section",
            status="completed",
            input_summary=f"section={unit_index + 1}/{len(state.source_units)}",
            output_summary=f"findings={len(findings)} registry={len(state.question_registry)}",
            metrics={
                "section_index": unit_index,
                "total_sections": len(state.source_units),
                "source_unit_key": unit.source_unit_key,
                "finding_count": len(findings),
                "registry_size": len(state.question_registry),
                "seed_phase": True,
            },
            source_unit_checkpoint=self._build_source_unit_checkpoint(
                state=state,
                unit=unit,
                findings=findings,
                merge_context=merge_context,
            ),
        )
        return state

    async def _process_parallel_section_batch(
        self,
        *,
        state: _CompilerState,
        batch: Sequence[tuple[int, RetrievalSurfaceSourceUnit]],
    ) -> tuple[
        tuple[int, RetrievalSurfaceSourceUnit, tuple[_SectionFinding, ...]], ...
    ]:
        semaphore = asyncio.Semaphore(self._parallel_section_concurrency)

        async def run_one(
            item: tuple[int, RetrievalSurfaceSourceUnit],
        ) -> tuple[int, RetrievalSurfaceSourceUnit, tuple[_SectionFinding, ...]]:
            unit_index, unit = item
            async with semaphore:
                match_context = await self._match_section_against_registry(
                    state=state,
                    unit=unit,
                )
                findings = await self._discover_section_findings(
                    state=state,
                    unit=unit,
                    match_context=match_context,
                )
                return unit_index, unit, findings

        return tuple(await asyncio.gather(*(run_one(item) for item in batch)))

    async def _reconcile_parallel_batch_results(
        self,
        *,
        state: _CompilerState,
        batch_results: Sequence[
            tuple[int, RetrievalSurfaceSourceUnit, tuple[_SectionFinding, ...]]
        ],
    ) -> _CompilerState:
        for unit_index, unit, findings in sorted(
            batch_results, key=lambda item: item[0]
        ):
            match_context = await self._match_section_against_registry(
                state=state,
                unit=unit,
            )
            merge_context = await self._plan_registry_merge(
                state=state,
                unit=unit,
                findings=findings,
                match_context=match_context,
            )
            self._merge_section_findings_into_registry(
                state=state,
                unit=unit,
                findings=findings,
                merge_context=merge_context,
            )
            await self._emit_progress(
                stage_kind="reconcile_parallel_batch_results",
                status="completed",
                input_summary=f"section={unit_index + 1}/{len(state.source_units)}",
                output_summary=(
                    f"findings={len(findings)} registry={len(state.question_registry)}"
                ),
                metrics={
                    "section_index": unit_index,
                    "total_sections": len(state.source_units),
                    "source_unit_key": unit.source_unit_key,
                    "finding_count": len(findings),
                    "registry_size": len(state.question_registry),
                    "parallel_phase": True,
                    "max_concurrency": self._parallel_section_concurrency,
                },
                source_unit_checkpoint=self._build_source_unit_checkpoint(
                    state=state,
                    unit=unit,
                    findings=findings,
                    merge_context=merge_context,
                ),
            )
        return state

    async def _run_final_reconciliation(
        self,
        *,
        state: _CompilerState,
    ) -> None:
        await self._ensure_not_cancelled()
        restored_processed_keys = set(
            _text_tuple(
                state.metrics.get("checkpoint_restored_processed_source_unit_keys")
            )
        )
        representative_unit = next(
            (
                unit
                for unit in reversed(state.source_units)
                if unit.source_unit_key not in restored_processed_keys
            ),
            state.source_units[-1],
        )
        prompt = self._build_section_prompt(
            stage_kind="finalize_retrieval_surface_graph",
            prompt_file=FAQ_FINAL_RECONCILIATION_PROMPT_FILE,
            state=state,
            unit=representative_unit,
            final_reconciliation=True,
        )
        _, content = await self._request_json(prompt=prompt, max_tokens=1200)
        payload = _loads_json_object(content)
        raw_warnings = payload.get("warnings")
        if isinstance(raw_warnings, list):
            for warning in _text_tuple(raw_warnings):
                if warning not in state.warnings:
                    state.warnings.append(warning)
        state.metrics["final_reconciliation_prompt_used"] = True
        state.metrics["final_reconciliation_payload_metrics"] = json_value_from_unknown(
            _json_object(payload.get("metrics"))
        )

    def _finalize_retrieval_surface_graph(
        self,
        *,
        mode: KnowledgePreprocessingMode,
        state: _CompilerState,
    ) -> RetrievalSurfaceCompilationResult:
        if not state.question_registry:
            raise KnowledgePreprocessingValidationError(
                "FAQ sectional registry compiler produced no publishable surfaces"
            )

        surfaces: list[RetrievalSurfaceDraft] = []
        ownership: list[SurfaceQuestionOwnership] = []
        relation_pairs: set[tuple[str, str, str]] = set()
        relations: list[RetrievalSurfaceRelation] = []

        for index, entry in enumerate(state.question_registry.values()):
            if _is_role_label_surface(entry.title) or _is_role_label_surface(
                entry.canonical_question
            ):
                continue

            source_chunk_indexes = tuple(sorted(entry.source_chunk_indexes))
            source_refs = tuple(entry.source_refs) or tuple(
                f"chunk:{item}" for item in source_chunk_indexes
            )
            surfaces.append(
                RetrievalSurfaceDraft(
                    id=_stable_uuid(state.run_id, "surface", entry.registry_entry_key),
                    run_id=state.run_id,
                    document_id=state.source_units[0].document_id,
                    local_surface_key=entry.registry_entry_key,
                    title=entry.title,
                    canonical_question=entry.canonical_question,
                    surface_kind=entry.surface_kind,
                    answer_scope=_limited_text(entry.answer_scope, max_chars=1000),
                    question_scope=_limited_text(entry.question_scope, max_chars=1000),
                    exclusion_scope=_limited_text(
                        entry.exclusion_scope,
                        max_chars=1000,
                    ),
                    answer=_limited_text(entry.answer, max_chars=3200),
                    short_answer=_limited_text(entry.short_answer, max_chars=360),
                    status="draft",
                    publication_status="unpublished",
                    source_refs=source_refs,
                    source_excerpt=_limited_text(entry.answer, max_chars=1200),
                    confidence=entry.confidence,
                    warnings=tuple(entry.warnings),
                    metadata={
                        "compiler": FAQ_RETRIEVAL_SURFACE_COMPILATION_PROMPT_VERSION,
                        "sectional_registry": True,
                        "registry_entry_key": entry.registry_entry_key,
                        "question_variants": json_value_from_unknown(
                            entry.question_variants
                        ),
                        "evidence_quotes": json_value_from_unknown(
                            entry.evidence_quotes
                        ),
                        "source_unit_keys": json_value_from_unknown(
                            entry.source_unit_keys
                        ),
                        "role_label_metadata": entry.role_label_metadata,
                        "duplicate_keys": json_value_from_unknown(entry.duplicate_keys),
                    },
                    source_chunk_indexes=source_chunk_indexes,
                )
            )
            ownership.append(
                SurfaceQuestionOwnership(
                    id=_stable_uuid(
                        state.run_id,
                        "ownership",
                        entry.registry_entry_key,
                        entry.canonical_question,
                    ),
                    run_id=state.run_id,
                    document_id=state.source_units[0].document_id,
                    question=entry.canonical_question,
                    owner_surface_key=entry.registry_entry_key,
                    question_kind="faq_question",
                    confidence=entry.confidence,
                    reason="sectional_registry_owner",
                    rejected_from_surface_keys=(),
                )
            )
            for variant in entry.question_variants:
                if _is_role_label_surface(variant):
                    continue
                ownership.append(
                    SurfaceQuestionOwnership(
                        id=_stable_uuid(
                            state.run_id,
                            "ownership",
                            entry.registry_entry_key,
                            variant,
                        ),
                        run_id=state.run_id,
                        document_id=state.source_units[0].document_id,
                        question=variant,
                        owner_surface_key=entry.registry_entry_key,
                        question_kind="generated_variant",
                        confidence=entry.confidence,
                        reason="sectional_registry_variant",
                        rejected_from_surface_keys=(),
                    )
                )

            for parent_key in entry.parent_keys:
                relation_pairs.add(
                    (parent_key, entry.registry_entry_key, "umbrella_contains")
                )
            for child_key in entry.child_keys:
                relation_pairs.add(
                    (entry.registry_entry_key, child_key, "umbrella_contains")
                )

        surface_keys = {surface.local_surface_key for surface in surfaces}
        for index, (parent_key, child_key, relation_type) in enumerate(
            sorted(relation_pairs)
        ):
            if parent_key not in surface_keys or child_key not in surface_keys:
                continue
            relations.append(
                RetrievalSurfaceRelation(
                    id=_stable_uuid(
                        state.run_id, "relation", index, parent_key, child_key
                    ),
                    run_id=state.run_id,
                    document_id=state.source_units[0].document_id,
                    parent_surface_key=parent_key,
                    child_surface_key=child_key,
                    relation_type=cast(SurfaceRelationType, relation_type),
                    reason="sectional_registry_relation",
                    confidence=0.75,
                    source_refs=(),
                )
            )

        metrics: JsonObject = {
            **{
                key: json_value_from_unknown(value)
                for key, value in state.metrics.items()
            },
            "source_unit_count": len(state.source_units),
            "processed_source_unit_count": len(state.processed_source_unit_keys),
            "pending_source_unit_count": len(state.pending_source_unit_keys),
            "surface_count": len(surfaces),
            "relation_count": len(relations),
            "ownership_count": len(ownership),
            "merge_decision_count": len(state.merge_decisions),
            "warning_count": len(state.warnings),
            "role_label_surfaces_forbidden": True,
            "deterministic_registry_merge": True,
            "llm_registry_merge_advisory_only": True,
            "json_contract": "registry_updates_advisory",
            "graph_nodes": json_value_from_unknown(
                [
                    "initialize_registry",
                    "process_seed_section",
                    "match_section_against_registry",
                    "discover_section_findings",
                    "merge_section_findings_into_registry",
                    "process_parallel_section_batch",
                    "reconcile_parallel_batch_results",
                    "finalize_retrieval_surface_graph",
                ]
            ),
        }

        graph = RetrievalSurfaceGraph(
            run_id=state.run_id,
            document_id=state.source_units[0].document_id,
            source_units=state.source_units,
            surfaces=tuple(surfaces),
            relations=tuple(relations),
            ownership=tuple(ownership),
            reassignments=(),
            merge_decisions=tuple(state.merge_decisions),
            metrics=metrics,
        )
        return RetrievalSurfaceCompilationResult(
            mode=mode,
            prompt_version=FAQ_RETRIEVAL_SURFACE_COMPILATION_PROMPT_VERSION,
            model=state.model,
            graph=graph,
            metrics=metrics,
        )

    async def _execute_sectional_registry_stategraph(
        self,
        *,
        mode: KnowledgePreprocessingMode,
        source_units: Sequence[RetrievalSurfaceSourceUnit],
        file_name: str,
        run_id: str,
    ) -> RetrievalSurfaceCompilationResult:
        units = tuple(source_units)
        state = self._initialize_registry(
            source_units=units,
            file_name=file_name,
            run_id=run_id,
        )
        state = self._restore_checkpointed_state(state)

        await self._ensure_not_cancelled()
        await self._emit_progress(
            stage_kind="initialize_registry",
            status="completed",
            input_summary=f"sections={len(units)}",
            metrics={
                "total_sections": len(units),
                "seed_section_count": min(self._seed_section_count, len(units)),
                "parallel_section_concurrency": self._parallel_section_concurrency,
                "processed_source_unit_count": len(state.processed_source_unit_keys),
                "pending_source_unit_count": len(state.pending_source_unit_keys),
                "registry_size": len(state.question_registry),
                "checkpoint_restore_mode": state.metrics.get(
                    "checkpoint_restore_mode", "none"
                ),
                "langgraph_stategraph": True,
            },
        )

        seed_units = units[: self._seed_section_count]
        for unit_index, unit in enumerate(seed_units):
            if unit.source_unit_key in state.processed_source_unit_keys:
                continue
            await self._ensure_not_cancelled()
            state = await self._process_seed_section(
                state=state,
                unit_index=unit_index,
                unit=unit,
            )

        remaining = tuple(
            (unit_index, unit)
            for unit_index, unit in enumerate(
                units[self._seed_section_count :],
                start=self._seed_section_count,
            )
            if unit.source_unit_key not in state.processed_source_unit_keys
        )
        for batch_start in range(0, len(remaining), self._parallel_section_concurrency):
            await self._ensure_not_cancelled()
            batch = remaining[
                batch_start : batch_start + self._parallel_section_concurrency
            ]
            batch_results = await self._process_parallel_section_batch(
                state=state,
                batch=batch,
            )
            state = await self._reconcile_parallel_batch_results(
                state=state,
                batch_results=batch_results,
            )

        await self._run_final_reconciliation(state=state)
        await self._ensure_not_cancelled()
        result = self._finalize_retrieval_surface_graph(mode=mode, state=state)
        await self._emit_progress(
            stage_kind="finalize_retrieval_surface_graph",
            status="completed",
            output_summary=f"surfaces={len(result.graph.surfaces)}",
            metrics=result.metrics,
        )
        return result

    async def compile_surfaces(
        self,
        *,
        mode: KnowledgePreprocessingMode,
        source_units: Sequence[RetrievalSurfaceSourceUnit],
        file_name: str,
        run_id: str,
    ) -> RetrievalSurfaceCompilationResult:
        if mode != MODE_FAQ:
            raise KnowledgePreprocessingValidationError(
                "GroqKnowledgeSurfaceCompiler is only available for mode=faq"
            )
        if not source_units:
            raise KnowledgePreprocessingValidationError(
                "FAQ surface compiler requires at least one source unit"
            )

        async def initialize_registry(
            graph_state: _LangGraphCompilerState,
        ) -> _LangGraphCompilerState:
            result = await self._execute_sectional_registry_stategraph(
                mode=graph_state["mode"],
                source_units=graph_state["source_units"],
                file_name=str(graph_state["file_name"]),
                run_id=str(graph_state["run_id"]),
            )
            return {"result": result}

        from langchain_core.runnables import RunnableLambda
        from langgraph.graph import END, StateGraph

        graph = StateGraph(_LangGraphCompilerState)
        graph.add_node("initialize_registry", RunnableLambda(initialize_registry))
        graph.set_entry_point("initialize_registry")
        graph.add_edge("initialize_registry", END)
        compiled_graph = graph.compile()

        try:
            final_state = await compiled_graph.ainvoke(
                {
                    "mode": mode,
                    "source_units": tuple(source_units),
                    "file_name": file_name,
                    "run_id": run_id,
                }
            )
            result = final_state.get("result")
            if not isinstance(result, RetrievalSurfaceCompilationResult):
                raise KnowledgePreprocessingValidationError(
                    "FAQ StateGraph did not return RetrievalSurfaceCompilationResult"
                )
            return result
        except (
            APIConnectionError,
            APIError,
            APITimeoutError,
            RateLimitError,
            AttributeError,
            IndexError,
            TypeError,
            ValueError,
            KnowledgePreprocessingValidationError,
        ) as exc:
            logger.warning(
                "FAQ retrieval surface compilation failed",
                extra={
                    "mode": mode,
                    "model": self._model,
                    "prompt_version": FAQ_RETRIEVAL_SURFACE_COMPILATION_PROMPT_VERSION,
                    "source_unit_count": len(source_units),
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:300],
                },
            )
            raise
