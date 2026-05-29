from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import asdict
from typing import cast

from groq import APIError, RateLimitError

from src.application.services.knowledge_surface_prompt_versions import (
    FAQ_RETRIEVAL_SURFACE_GRAPH_PROMPT_VERSION,
)
from src.domain.project_plane.knowledge_preprocessing import (
    KnowledgePreprocessingValidationError,
)
from src.domain.project_plane.retrieval_surface_compilation import (
    LocalRelationPlanningResult,
    LocalSurfaceRelation,
    RetrievalSurfaceCandidate,
    RetrievalSurfaceSourceUnit,
    SurfaceAnswerDraft,
    SurfaceDiscoveryResult,
    SurfaceKind,
    SurfaceQuestionKind,
    SurfaceQuestionOwnershipDecision,
    SurfaceQuestionOwnershipResult,
    SurfaceRejectedQuestion,
    SurfaceRelationType,
)
from src.infrastructure.llm.knowledge_surface_compiler import (
    GROQ_LARGE_REQUEST_FALLBACK_MODEL_ID,
    GroqKnowledgeSurfaceCompiler,
    PROMPTS_DIR,
    _compact_text,
    _confidence,
    _enum_text,
    _json_object,
    _loads_json_object,
    _source_unit_payload,
    _stable_uuid,
    _text_tuple,
)

GRAPH_PROMPT_VERSION = FAQ_RETRIEVAL_SURFACE_GRAPH_PROMPT_VERSION
PROMPTS = {
    "discover": "faq_surface_local_discovery.ru.txt",
    "relations": "faq_surface_local_relations.ru.txt",
    "answer": "faq_surface_answer_synthesis_v2.ru.txt",
    "questions": "faq_surface_question_ownership_v2.ru.txt",
}
SURFACE_KINDS = frozenset(
    {
        "umbrella",
        "child",
        "specific",
        "standalone",
        "procedural",
        "safety",
        "pricing",
        "integration",
        "handoff",
        "definition",
        "curation",
        "retrieval_quality",
        "service_limits",
        "other",
    }
)
RELATION_TYPES = frozenset(
    {
        "umbrella_contains",
        "specializes",
        "sibling",
        "overlaps",
        "duplicates",
        "near_duplicate",
        "contradicts",
        "unrelated",
        "split_needed",
    }
)
SurfaceGraphProgressCallback = Callable[[Mapping[str, object]], Awaitable[None]]


QUESTION_KINDS = frozenset(
    {
        "faq_question",
        "test_question",
        "generated_variant",
        "user_like_question",
        "expected_topic_hint",
    }
)


def _is_large_request_error(exc: BaseException) -> bool:
    text = str(exc).lower()
    return (
        "413" in text
        or "request too large" in text
        or "tokens per minute" in text
        or "tpm" in text
    )


class GroqKnowledgeSurfaceGraphCompilerV2(GroqKnowledgeSurfaceCompiler):
    async def discover_surfaces_for_source_unit(
        self,
        *,
        source_unit: RetrievalSurfaceSourceUnit,
        file_name: str,
        run_id: str,
        compilation_context: Mapping[str, object] | None = None,
    ) -> SurfaceDiscoveryResult:
        payload: dict[str, object] = {
            "file_name": file_name,
            "run_id": run_id,
            "source_unit": _source_unit_payload(source_unit),
        }
        if compilation_context is not None:
            payload["compilation_context"] = dict(compilation_context)
        data = await self._stage(
            "discover",
            payload,
        )
        candidates = tuple(
            self._candidate(item, source_unit=source_unit, run_id=run_id, index=index)
            for index, item in enumerate(
                _objects(data.get("surface_candidates"), "surface_candidates")
            )
        )
        return SurfaceDiscoveryResult(
            surface_candidates=candidates,
            warnings=_text_tuple(data.get("warnings")),
            metrics=_json_object(data.get("metrics")),
        )

    async def plan_local_relations(
        self,
        *,
        source_unit: RetrievalSurfaceSourceUnit,
        candidates: Sequence[RetrievalSurfaceCandidate],
        file_name: str,
        run_id: str,
        compilation_context: Mapping[str, object] | None = None,
    ) -> LocalRelationPlanningResult:
        keys = frozenset(candidate.local_surface_key for candidate in candidates)
        payload: dict[str, object] = {
            "file_name": file_name,
            "run_id": run_id,
            "source_unit": _source_unit_payload(source_unit),
            "surface_candidates": [asdict(candidate) for candidate in candidates],
        }
        if compilation_context is not None:
            payload["compilation_context"] = dict(compilation_context)
        data = await self._stage(
            "relations",
            payload,
        )
        relations = tuple(
            self._relation(
                item, source_unit=source_unit, run_id=run_id, keys=keys, index=index
            )
            for index, item in enumerate(_objects(data.get("relations"), "relations"))
        )
        return LocalRelationPlanningResult(
            relations=relations,
            warnings=_text_tuple(data.get("warnings")),
            metrics=_json_object(data.get("metrics")),
        )

    async def synthesize_surface_answer(
        self,
        *,
        source_unit: RetrievalSurfaceSourceUnit,
        candidate: RetrievalSurfaceCandidate,
        local_relations: Sequence[LocalSurfaceRelation],
        related_candidates: Sequence[RetrievalSurfaceCandidate],
        file_name: str,
        run_id: str,
        compilation_context: Mapping[str, object] | None = None,
    ) -> SurfaceAnswerDraft:
        payload: dict[str, object] = {
            "file_name": file_name,
            "run_id": run_id,
            "source_unit": _source_unit_payload(source_unit),
            "current_surface_candidate": asdict(candidate),
            "local_relations": [asdict(relation) for relation in local_relations],
            "related_candidates": [asdict(item) for item in related_candidates],
        }
        if compilation_context is not None:
            payload["compilation_context"] = dict(compilation_context)
        data = await self._stage(
            "answer",
            payload,
        )
        answer_payload = data.get("surface_answer")
        if not isinstance(answer_payload, Mapping):
            raise KnowledgePreprocessingValidationError(
                "surface_answer must be an object"
            )
        return SurfaceAnswerDraft(
            id=_stable_uuid(run_id, "answer", candidate.local_surface_key),
            run_id=run_id,
            document_id=source_unit.document_id,
            candidate_key=candidate.local_surface_key,
            title=_compact_text(answer_payload.get("title"))
            or candidate.provisional_title,
            canonical_question=_compact_text(answer_payload.get("canonical_question"))
            or candidate.provisional_title,
            short_answer=_compact_text(answer_payload.get("short_answer")),
            answer=_compact_text(answer_payload.get("answer")),
            answer_scope=_compact_text(answer_payload.get("answer_scope"))
            or candidate.answer_scope,
            question_scope=_compact_text(answer_payload.get("question_scope"))
            or candidate.question_scope,
            exclusion_scope=_compact_text(answer_payload.get("exclusion_scope"))
            or candidate.exclusion_scope,
            source_refs=_text_tuple(answer_payload.get("source_refs"))
            or candidate.source_refs,
            warnings=_text_tuple(answer_payload.get("warnings")),
            metadata=_json_object(answer_payload.get("metadata")),
        )

    async def assign_surface_questions(
        self,
        *,
        source_unit: RetrievalSurfaceSourceUnit,
        answer_draft: SurfaceAnswerDraft,
        candidate: RetrievalSurfaceCandidate,
        local_relations: Sequence[LocalSurfaceRelation],
        related_candidates: Sequence[RetrievalSurfaceCandidate],
        file_name: str,
        run_id: str,
        compilation_context: Mapping[str, object] | None = None,
    ) -> SurfaceQuestionOwnershipResult:
        payload: dict[str, object] = {
            "file_name": file_name,
            "run_id": run_id,
            "source_unit": _source_unit_payload(source_unit),
            "current_surface_candidate": asdict(candidate),
            "current_surface_answer": asdict(answer_draft),
            "local_relations": [asdict(relation) for relation in local_relations],
            "related_candidates": [asdict(item) for item in related_candidates],
        }
        if compilation_context is not None:
            payload["compilation_context"] = dict(compilation_context)
        data = await self._stage(
            "questions",
            payload,
        )
        owned = tuple(
            SurfaceQuestionOwnershipDecision(
                id=_stable_uuid(run_id, "owned", candidate.local_surface_key, index),
                run_id=run_id,
                document_id=source_unit.document_id,
                surface_key=candidate.local_surface_key,
                question=_compact_text(item.get("question")),
                question_kind=cast(
                    SurfaceQuestionKind,
                    _enum_text(
                        item.get("question_kind"),
                        allowed=QUESTION_KINDS,
                        default="generated_variant",
                    ),
                ),
                ownership_confidence=_confidence(item.get("confidence"), default=0.75),
                source=_compact_text(item.get("source")) or "generated",
                status="owned",
            )
            for index, item in enumerate(
                _objects(data.get("owned_questions"), "owned_questions")
            )
        )
        rejected = tuple(
            SurfaceRejectedQuestion(
                question=_compact_text(item.get("question")),
                belongs_to_surface_key=_compact_text(
                    item.get("belongs_to_surface_key")
                ),
                reason=_compact_text(item.get("reason")),
                confidence=_confidence(item.get("confidence"), default=0.75),
            )
            for item in _objects(data.get("rejected_questions"), "rejected_questions")
        )
        return SurfaceQuestionOwnershipResult(
            owned_questions=owned,
            rejected_questions=rejected,
            warnings=_text_tuple(data.get("warnings")),
            metrics=_json_object(data.get("metrics")),
        )

    async def _stage(
        self, stage: str, payload: Mapping[str, object]
    ) -> Mapping[str, object]:
        prompt = (PROMPTS_DIR / PROMPTS[stage]).read_text(encoding="utf-8")
        full_prompt = (
            f"{prompt}\n\nINPUT_JSON:\n{json.dumps(payload, ensure_ascii=False)}"
        )
        _, content = await self._request_json_with_large_request_fallback(
            prompt=full_prompt,
            max_tokens=3000,
        )
        parsed = _loads_json_object(content)
        if not isinstance(parsed, Mapping):
            raise KnowledgePreprocessingValidationError(
                "stage response must be a JSON object"
            )
        return parsed

    async def _request_json_with_large_request_fallback(
        self,
        *,
        prompt: str,
        max_tokens: int,
    ) -> tuple[str, str]:
        try:
            return await self._request_json(prompt=prompt, max_tokens=max_tokens)
        except (APIError, RateLimitError) as exc:
            if not _is_large_request_error(exc):
                raise
            return await self._request_json_using_fallback_model(
                prompt=prompt,
                max_tokens=max_tokens,
            )

    async def _request_json_using_fallback_model(
        self,
        *,
        prompt: str,
        max_tokens: int,
    ) -> tuple[str, str]:
        previous_model = self._model
        try:
            self._model = GROQ_LARGE_REQUEST_FALLBACK_MODEL_ID
            return await self._request_json(prompt=prompt, max_tokens=max_tokens)
        finally:
            self._model = previous_model

    def set_progress_callback(
        self,
        callback: SurfaceGraphProgressCallback | None,
    ) -> None:
        self._progress_callback = callback

    async def _emit_progress(
        self,
        *,
        stage_kind: str,
        status: str,
        input_summary: str = "",
        output_summary: str = "",
        metrics: Mapping[str, object] | None = None,
        error_type: str | None = None,
        error_message: str | None = None,
    ) -> None:
        callback = getattr(self, "_progress_callback", None)
        if callback is None:
            return
        await callback(
            {
                "stage_kind": stage_kind,
                "status": status,
                "input_summary": input_summary,
                "output_summary": output_summary,
                "metrics": dict(metrics or {}),
                "error_type": error_type or "",
                "error_message": error_message or "",
            }
        )

    def _candidate(
        self,
        payload: Mapping[str, object],
        *,
        source_unit: RetrievalSurfaceSourceUnit,
        run_id: str,
        index: int,
    ) -> RetrievalSurfaceCandidate:
        key = _compact_text(payload.get("local_surface_key")) or f"surface_{index + 1}"
        return RetrievalSurfaceCandidate(
            id=_stable_uuid(run_id, "candidate", source_unit.id, key),
            run_id=run_id,
            document_id=source_unit.document_id,
            source_unit_id=source_unit.id,
            local_surface_key=key,
            provisional_title=_compact_text(payload.get("provisional_title")) or key,
            surface_kind=cast(
                SurfaceKind,
                _enum_text(
                    payload.get("surface_kind"), allowed=SURFACE_KINDS, default="other"
                ),
            ),
            answer_scope=_compact_text(payload.get("answer_scope")),
            question_scope=_compact_text(payload.get("question_scope")),
            exclusion_scope=_compact_text(payload.get("exclusion_scope")),
            parent_candidate_keys=_text_tuple(payload.get("parent_candidate_keys")),
            child_candidate_keys=_text_tuple(payload.get("child_candidate_keys")),
            sibling_candidate_keys=_text_tuple(payload.get("sibling_candidate_keys")),
            source_refs=_text_tuple(payload.get("source_refs"))
            or source_unit.source_refs,
            confidence=_confidence(payload.get("confidence"), default=0.75),
            metadata=_json_object(payload.get("metadata")),
        )

    def _relation(
        self,
        payload: Mapping[str, object],
        *,
        source_unit: RetrievalSurfaceSourceUnit,
        run_id: str,
        keys: frozenset[str],
        index: int,
    ) -> LocalSurfaceRelation:
        source_key = _compact_text(payload.get("source_surface_key"))
        target_key = _compact_text(payload.get("target_surface_key"))
        if source_key not in keys or target_key not in keys:
            raise KnowledgePreprocessingValidationError(
                "local relation references unknown surface"
            )
        return LocalSurfaceRelation(
            id=_stable_uuid(run_id, "relation", source_unit.id, index),
            run_id=run_id,
            document_id=source_unit.document_id,
            source_unit_id=source_unit.id,
            source_surface_key=source_key,
            target_surface_key=target_key,
            relation_type=cast(
                SurfaceRelationType,
                _enum_text(
                    payload.get("relation_type"),
                    allowed=RELATION_TYPES,
                    default="unrelated",
                ),
            ),
            confidence=_confidence(payload.get("confidence"), default=0.7),
            reason=_compact_text(payload.get("reason")),
            source_refs=_text_tuple(payload.get("source_refs")),
        )


def _objects(value: object, name: str) -> tuple[Mapping[str, object], ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise KnowledgePreprocessingValidationError(f"{name} must be an array")
    result: list[Mapping[str, object]] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise KnowledgePreprocessingValidationError(
                f"{name}[{index}] must be an object"
            )
        result.append(cast(Mapping[str, object], item))
    return tuple(result)
