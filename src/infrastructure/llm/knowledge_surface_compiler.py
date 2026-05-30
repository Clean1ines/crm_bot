from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

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
FAQ_SURFACE_PROMPT_FILES: tuple[str, ...] = (
    "faq_surface_discovery.ru.txt",
    "faq_surface_relation_planning.ru.txt",
    "faq_surface_answer_synthesis.ru.txt",
    "faq_surface_question_ownership.ru.txt",
    "faq_surface_merge_decisions.ru.txt",
)
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


def _load_instruction() -> str:
    sections = [
        (PROMPTS_DIR / file_name).read_text(encoding="utf-8")
        for file_name in FAQ_SURFACE_PROMPT_FILES
    ]
    return "\n\n".join(sections)


class GroqKnowledgeSurfaceCompiler(KnowledgeSurfaceCompilerPort):
    """Groq-backed FAQ Retrieval Surface Compilation adapter."""

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

    @property
    def model_name(self) -> str:
        return self._model

    def _model_for_request(self, *, prompt: str, max_tokens: int) -> str:
        # Provider response is the source of truth. Keep instant-first routing;
        # GroqModelRouter reacts to provider failures.
        return self._model

    def _build_prompt(
        self,
        *,
        mode: KnowledgePreprocessingMode,
        source_units: Sequence[RetrievalSurfaceSourceUnit],
        file_name: str,
        run_id: str,
    ) -> str:
        payload = {
            "file_name": file_name,
            "mode": mode,
            "run_id": run_id,
            "prompt_version": FAQ_RETRIEVAL_SURFACE_COMPILATION_PROMPT_VERSION,
            "json_contract": {
                "required_root_fields": [
                    "surfaces",
                    "relations",
                    "question_ownership",
                    "merge_decisions",
                ],
                "forbidden_root_fields": ["fragments"],
            },
            "source_units": [
                _source_unit_payload(unit)
                for unit in source_units[: self._max_source_units]
            ],
        }
        return f"{_load_instruction()}\n\nSOURCE_PAYLOAD_JSON:\n{json.dumps(payload, ensure_ascii=False)}"

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

        prompt = self._build_prompt(
            mode=mode,
            source_units=source_units,
            file_name=file_name,
            run_id=run_id,
        )
        max_tokens = 6000
        try:
            request_model, content = await self._request_json(
                prompt=prompt,
                max_tokens=max_tokens,
            )
            try:
                return parse_surface_compilation_payload(
                    content,
                    mode=mode,
                    model=request_model,
                    run_id=run_id,
                    document_id=source_units[0].document_id,
                    source_units=source_units,
                )
            except KnowledgePreprocessingValidationError as first_error:
                repair_prompt = (
                    f"{_load_instruction()}\n\n"
                    "Repair the invalid JSON below. Return the same required contract only: "
                    "surfaces[], relations[], question_ownership[], merge_decisions[]. "
                    "Do not return fragments[]. Do not create bootstrap all-standalone surfaces.\n\n"
                    f"VALIDATION_ERROR: {first_error}\n\nINVALID_JSON:\n{content}"
                )
                repair_model, repaired_content = await self._request_json(
                    prompt=repair_prompt,
                    max_tokens=max_tokens,
                )
                repaired = parse_surface_compilation_payload(
                    repaired_content,
                    mode=mode,
                    model=repair_model,
                    run_id=run_id,
                    document_id=source_units[0].document_id,
                    source_units=source_units,
                )
                metrics = dict(repaired.metrics)
                metrics["json_repair_retry_count"] = 1
                return RetrievalSurfaceCompilationResult(
                    mode=repaired.mode,
                    prompt_version=repaired.prompt_version,
                    model=repaired.model,
                    graph=repaired.graph,
                    metrics=metrics,
                )
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
