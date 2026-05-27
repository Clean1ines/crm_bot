from __future__ import annotations

import json
import uuid
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

from src.domain.project_plane.json_types import JsonObject, json_value_from_unknown
from src.domain.project_plane.knowledge_preprocessing import KnowledgePreprocessingValidationError
from src.domain.project_plane.retrieval_surface_compilation import (
    LocalRelationPlanningResult,
    LocalSurfaceRelation,
    NewParentSurfaceCandidate,
    RetrievalSurfaceCandidate,
    RetrievalSurfaceSourceUnit,
    SurfaceAnswerDraft,
    SurfaceDiscoveryResult,
    SurfaceGraphReconciliationResult,
    SurfaceGraphReconciliationRun,
    SurfaceKind,
    SurfaceQuestionOwnership,
    SurfaceQuestionOwnershipDecision,
    SurfaceQuestionOwnershipResult,
    SurfaceQuestionReassignment,
    SurfaceRelationClusterContext,
    SurfaceRelationJudgement,
    SurfaceRelationJudgeAction,
    SurfaceRelationJudgeResult,
    SurfaceRelationType,
)
from src.infrastructure.llm.knowledge_surface_compiler import (
    FAQ_RETRIEVAL_SURFACE_COMPILATION_PROMPT_VERSION,
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

FAQ_RETRIEVAL_SURFACE_GRAPH_PROMPT_VERSION = "faq_retrieval_surface_graph_v1"
STAGED_PROMPT_FILES: dict[str, str] = {
    "local_discovery": "faq_surface_local_discovery.ru.txt",
    "local_relations": "faq_surface_local_relations.ru.txt",
    "answer_synthesis": "faq_surface_answer_synthesis_v2.ru.txt",
    "question_ownership": "faq_surface_question_ownership_v2.ru.txt",
    "global_relation_judge": "faq_surface_global_relation_judge.ru.txt",
    "question_reassignment": "faq_surface_question_reassignment.ru.txt",
}
SURFACE_KIND_VALUES: frozenset[str] = frozenset(
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
        "channel",
        "document_upload",
        "other",
    }
)
RELATION_TYPE_VALUES: frozenset[str] = frozenset(
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
        "needs_new_parent",
        "reparent_needed",
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
JUDGE_ACTION_VALUES: frozenset[str] = frozenset(
    {"keep", "merge_same_surface", "create_parent", "reparent", "split", "review"}
)


def _read_stage_prompt(stage_key: str) -> str:
    file_name = STAGED_PROMPT_FILES[stage_key]
    return (PROMPTS_DIR / file_name).read_text(encoding="utf-8")


def _payload_json(payload: Mapping[str, object]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _candidate_payload(candidate: RetrievalSurfaceCandidate) -> JsonObject:
    return {
        "id": candidate.id,
        "local_surface_key": candidate.local_surface_key,
        "provisional_title": candidate.provisional_title,
        "surface_kind": candidate.surface_kind,
        "answer_scope": candidate.answer_scope,
        "question_scope": candidate.question_scope,
        "exclusion_scope": candidate.exclusion_scope,
        "parent_candidate_keys": list(candidate.parent_candidate_keys),
        "child_candidate_keys": list(candidate.child_candidate_keys),
        "sibling_candidate_keys": list(candidate.sibling_candidate_keys),
        "source_refs": list(candidate.source_refs),
        "confidence": candidate.confidence,
        "metadata": candidate.metadata,
    }


def _local_relation_payload(relation: LocalSurfaceRelation) -> JsonObject:
    return {
        "source_surface_key": relation.source_surface_key,
        "target_surface_key": relation.target_surface_key,
        "relation_type": relation.relation_type,
        "confidence": relation.confidence,
        "reason": relation.reason,
        "source_refs": list(relation.source_refs),
    }


def _answer_payload(answer: SurfaceAnswerDraft) -> JsonObject:
    return {
        "candidate_key": answer.candidate_key,
        "title": answer.title,
        "canonical_question": answer.canonical_question,
        "short_answer": answer.short_answer,
        "answer": answer.answer,
        "answer_scope": answer.answer_scope,
        "question_scope": answer.question_scope,
        "exclusion_scope": answer.exclusion_scope,
        "source_refs": list(answer.source_refs),
        "warnings": list(answer.warnings),
        "metadata": answer.metadata,
    }


def _ownership_payload(ownership: SurfaceQuestionOwnership) -> JsonObject:
    return {
        "question": ownership.question,
        "owner_surface_key": ownership.owner_surface_key,
        "question_kind": ownership.question_kind,
        "confidence": ownership.confidence,
        "reason": ownership.reason,
        "rejected_from_surface_keys": list(ownership.rejected_from_surface_keys),
    }


def _mapping_items(value: object, *, field_name: str) -> tuple[Mapping[str, object], ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise KnowledgePreprocessingValidationError(f"{field_name} must be an array")
    items: list[Mapping[str, object]] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise KnowledgePreprocessingValidationError(f"{field_name}[{index}] must be an object")
        items.append(cast(Mapping[str, object], item))
    return tuple(items)


def _stage_json_object(value: object) -> Mapping[str, object]:
    parsed = _loads_json_object(value) if isinstance(value, str) else value
    if not isinstance(parsed, Mapping):
        raise KnowledgePreprocessingValidationError("Stage compiler response must be a JSON object")
    return cast(Mapping[str, object], parsed)


class GroqKnowledgeSurfaceGraphCompiler(GroqKnowledgeSurfaceCompiler):
    """Staged Groq adapter for Retrieval Surface Graph v1.

    The legacy compile_surfaces method inherited from GroqKnowledgeSurfaceCompiler is kept
    only for backwards compatibility. The FAQ primary path should call these staged methods
    instead of sending all source units to one mega-prompt.
    """

    async def discover_surfaces_for_source_unit(
        self,
        *,
        source_unit: RetrievalSurfaceSourceUnit,
        file_name: str,
        run_id: str,
    ) -> SurfaceDiscoveryResult:
        payload = {
            "file_name": file_name,
            "run_id": run_id,
            "prompt_version": FAQ_RETRIEVAL_SURFACE_GRAPH_PROMPT_VERSION,
            "source_unit": _source_unit_payload(source_unit),
        }
        content = await self._request_stage_json(
            stage_key="local_discovery",
            payload_label="LOCAL_DISCOVERY_INPUT_JSON",
            payload=payload,
            max_tokens=2500,
        )
        parsed = _stage_json_object(content)
        candidates = tuple(
            self._candidate_from_payload(
                item,
                run_id=run_id,
                document_id=source_unit.document_id,
                source_unit_id=source_unit.id,
                source_unit_refs=source_unit.source_refs,
                index=index,
            )
            for index, item in enumerate(
                _mapping_items(parsed.get("surface_candidates"), field_name="surface_candidates")
            )
        )
        return SurfaceDiscoveryResult(
            surface_candidates=candidates,
            warnings=_text_tuple(parsed.get("warnings")),
            metrics=_json_object(parsed.get("metrics")),
        )

    async def plan_local_relations(
        self,
        *,
        source_unit: RetrievalSurfaceSourceUnit,
        candidates: Sequence[RetrievalSurfaceCandidate],
        file_name: str,
        run_id: str,
    ) -> LocalRelationPlanningResult:
        payload = {
            "file_name": file_name,
            "run_id": run_id,
            "prompt_version": FAQ_RETRIEVAL_SURFACE_GRAPH_PROMPT_VERSION,
            "source_unit": _source_unit_payload(source_unit),
            "surface_candidates": [_candidate_payload(candidate) for candidate in candidates],
        }
        content = await self._request_stage_json(
            stage_key="local_relations",
            payload_label="LOCAL_RELATION_PLANNING_INPUT_JSON",
            payload=payload,
            max_tokens=2500,
        )
        parsed = _stage_json_object(content)
        candidate_keys = frozenset(candidate.local_surface_key for candidate in candidates)
        relations = tuple(
            self._local_relation_from_payload(
                item,
                run_id=run_id,
                document_id=source_unit.document_id,
                source_unit_id=source_unit.id,
                candidate_keys=candidate_keys,
                index=index,
            )
            for index, item in enumerate(
                _mapping_items(parsed.get("relations"), field_name="relations")
            )
        )
        return LocalRelationPlanningResult(
            relations=relations,
            warnings=_text_tuple(parsed.get("warnings")),
            metrics=_json_object(parsed.get("metrics")),
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
    ) -> SurfaceAnswerDraft:
        payload = {
            "file_name": file_name,
            "run_id": run_id,
            "prompt_version": FAQ_RETRIEVAL_SURFACE_GRAPH_PROMPT_VERSION,
            "source_unit": _source_unit_payload(source_unit),
            "current_surface_candidate": _candidate_payload(candidate),
            "related_candidates": [_candidate_payload(item) for item in related_candidates],
            "local_relations": [_local_relation_payload(item) for item in local_relations],
        }
        content = await self._request_stage_json(
            stage_key="answer_synthesis",
            payload_label="SURFACE_ANSWER_SYNTHESIS_INPUT_JSON",
            payload=payload,
            max_tokens=2500,
        )
        parsed = _stage_json_object(content)
        answer_payload = parsed.get("surface_answer")
        if not isinstance(answer_payload, Mapping):
            raise KnowledgePreprocessingValidationError("surface_answer must be an object")
        return self._answer_from_payload(
            cast(Mapping[str, object], answer_payload),
            run_id=run_id,
            document_id=source_unit.document_id,
            candidate=candidate,
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
    ) -> SurfaceQuestionOwnershipResult:
        payload = {
            "file_name": file_name,
            "run_id": run_id,
            "prompt_version": FAQ_RETRIEVAL_SURFACE_GRAPH_PROMPT_VERSION,
            "source_unit": _source_unit_payload(source_unit),
            "current_surface_candidate": _candidate_payload(candidate),
            "current_surface_answer": _answer_payload(answer_draft),
            "related_candidates": [_candidate_payload(item) for item in related_candidates],
            "local_relations": [_local_relation_payload(item) for item in local_relations],
        }
        content = await self._request_stage_json(
            stage_key="question_ownership",
            payload_label="QUESTION_OWNERSHIP_INPUT_JSON",
            payload=payload,
            max_tokens=2200,
        )
        parsed = _stage_json_object(content)
        owned = tuple(
            self._ownership_decision_from_payload(
                item,
                run_id=run_id,
                document_id=source_unit.document_id,
                surface_key=candidate.local_surface_key,
                index=index,
            )
            for index, item in enumerate(
                _mapping_items(parsed.get("owned_questions"), field_name="owned_questions")
            )
        )
        rejected = tuple(
            self._rejected_question_from_payload(item)
            for item in _mapping_items(
                parsed.get("rejected_questions"), field_name="rejected_questions"
            )
        )
        return SurfaceQuestionOwnershipResult(
            owned_questions=owned,
            rejected_questions=rejected,
            warnings=_text_tuple(parsed.get("warnings")),
            metrics=_json_object(parsed.get("metrics")),
        )

    async def judge_relation_cluster(
        self,
        *,
        candidates: Sequence[SurfaceAnswerDraft],
        existing_relations: Sequence[LocalSurfaceRelation],
        cluster_context: SurfaceRelationClusterContext,
        run_id: str,
    ) -> SurfaceRelationJudgeResult:
        payload = {
            "run_id": run_id,
            "prompt_version": FAQ_RETRIEVAL_SURFACE_GRAPH_PROMPT_VERSION,
            "cluster_context": {
                "cluster_key": cluster_context.cluster_key,
                "reason": cluster_context.reason,
                "candidate_similarity_reasons": list(cluster_context.candidate_similarity_reasons),
                "metadata": cluster_context.metadata,
            },
            "surfaces": [_answer_payload(item) for item in candidates],
            "existing_relations": [_local_relation_payload(item) for item in existing_relations],
        }
        content = await self._request_stage_json(
            stage_key="global_relation_judge",
            payload_label="GLOBAL_RELATION_JUDGE_INPUT_JSON",
            payload=payload,
            max_tokens=2500,
        )
        parsed = _stage_json_object(content)
        return SurfaceRelationJudgeResult(
            judgements=tuple(
                self._judgement_from_payload(item)
                for item in _mapping_items(parsed.get("judgements"), field_name="judgements")
            ),
            new_parent_candidates=tuple(
                self._new_parent_from_payload(item)
                for item in _mapping_items(
                    parsed.get("new_parent_candidates"), field_name="new_parent_candidates"
                )
            ),
            warnings=_text_tuple(parsed.get("warnings")),
            metrics=_json_object(parsed.get("metrics")),
        )

    async def reconcile_global_graph(
        self,
        *,
        candidates: Sequence[SurfaceAnswerDraft],
        local_relations: Sequence[LocalSurfaceRelation],
        question_ownership: Sequence[SurfaceQuestionOwnership],
        relation_judgements: Sequence[SurfaceRelationJudgeResult],
        run_id: str,
    ) -> SurfaceGraphReconciliationResult:
        payload = {
            "run_id": run_id,
            "prompt_version": FAQ_RETRIEVAL_SURFACE_GRAPH_PROMPT_VERSION,
            "surfaces": [_answer_payload(item) for item in candidates],
            "local_relations": [_local_relation_payload(item) for item in local_relations],
            "question_ownership": [_ownership_payload(item) for item in question_ownership],
            "relation_judgements": [
                {
                    "judgements": [judgement.__dict__ for judgement in result.judgements],
                    "new_parent_candidates": [candidate.__dict__ for candidate in result.new_parent_candidates],
                    "warnings": list(result.warnings),
                    "metrics": result.metrics,
                }
                for result in relation_judgements
            ],
        }
        content = await self._request_stage_json(
            stage_key="question_reassignment",
            payload_label="GLOBAL_GRAPH_RECONCILIATION_INPUT_JSON",
            payload=payload,
            max_tokens=2500,
        )
        parsed = _stage_json_object(content)
        reassignments = tuple(
            self._reassignment_from_payload(
                item,
                run_id=run_id,
                document_id=candidates[0].document_id if candidates else "",
                index=index,
            )
            for index, item in enumerate(
                _mapping_items(parsed.get("reassignments"), field_name="reassignments")
            )
        )
        warnings = _text_tuple(parsed.get("warnings"))
        reconciliation_run = SurfaceGraphReconciliationRun(
            id=_stable_uuid(run_id, "global_graph_reconciliation"),
            project_id="",
            document_id=candidates[0].document_id if candidates else "",
            run_id=run_id,
            input_candidate_count=len(candidates),
            input_relation_count=len(local_relations),
            created_parent_count=sum(
                len(result.new_parent_candidates) for result in relation_judgements
            ),
            reparented_surface_count=sum(
                1
                for result in relation_judgements
                for judgement in result.judgements
                if judgement.recommended_action == "reparent"
            ),
            moved_question_count=len(reassignments),
            merged_candidate_count=sum(
                1
                for result in relation_judgements
                for judgement in result.judgements
                if judgement.recommended_action == "merge_same_surface"
            ),
            warning_count=len(warnings),
            status="pending",
            metrics=_json_object(parsed.get("metrics")),
        )
        return SurfaceGraphReconciliationResult(
            final_surfaces=tuple(candidates),
            global_relations=tuple(local_relations),
            question_ownership=(),
            question_reassignments=reassignments,
            merge_decisions=(),
            warnings=warnings,
            reconciliation_run=reconciliation_run,
            metrics=_json_object(parsed.get("metrics")),
        )

    async def _request_stage_json(
        self,
        *,
        stage_key: str,
        payload_label: str,
        payload: Mapping[str, object],
        max_tokens: int,
    ) -> str:
        prompt = f"{_read_stage_prompt(stage_key)}\n\n{payload_label}:\n{_payload_json(payload)}"
        _, content = await self._request_json(prompt=prompt, max_tokens=max_tokens)
        return content

    def _candidate_from_payload(
        self,
        payload: Mapping[str, object],
        *,
        run_id: str,
        document_id: str,
        source_unit_id: str,
        source_unit_refs: tuple[str, ...],
        index: int,
    ) -> RetrievalSurfaceCandidate:
        key = _compact_text(payload.get("local_surface_key")) or f"surface_{index + 1}"
        return RetrievalSurfaceCandidate(
            id=_stable_uuid(run_id, "candidate", source_unit_id, key),
            run_id=run_id,
            document_id=document_id,
            source_unit_id=source_unit_id,
            local_surface_key=key,
            provisional_title=_compact_text(payload.get("provisional_title")) or key,
            surface_kind=cast(
                SurfaceKind,
                _enum_text(
                    payload.get("surface_kind"), allowed=SURFACE_KIND_VALUES, default="other"
                ),
            ),
            answer_scope=_compact_text(payload.get("answer_scope")),
            question_scope=_compact_text(payload.get("question_scope")),
            exclusion_scope=_compact_text(payload.get("exclusion_scope")),
            parent_candidate_keys=_text_tuple(payload.get("parent_candidate_keys")),
            child_candidate_keys=_text_tuple(payload.get("child_candidate_keys")),
            sibling_candidate_keys=_text_tuple(payload.get("sibling_candidate_keys")),
            source_refs=_text_tuple(payload.get("source_refs")) or source_unit_refs,
            confidence=_confidence(payload.get("confidence"), default=0.75),
            metadata={
                **_json_object(payload.get("metadata")),
                "reason": json_value_from_unknown(payload.get("reason")),
            },
        )

    def _local_relation_from_payload(
        self,
        payload: Mapping[str, object],
        *,
        run_id: str,
        document_id: str,
        source_unit_id: str,
        candidate_keys: frozenset[str],
        index: int,
    ) -> LocalSurfaceRelation:
        source_key = _compact_text(payload.get("source_surface_key"))
        target_key = _compact_text(payload.get("target_surface_key"))
        if source_key not in candidate_keys or target_key not in candidate_keys:
            raise KnowledgePreprocessingValidationError("local relation references unknown surface")
        return LocalSurfaceRelation(
            id=_stable_uuid(run_id, "local_relation", source_unit_id, index),
            run_id=run_id,
            document_id=document_id,
            source_unit_id=source_unit_id,
            source_surface_key=source_key,
            target_surface_key=target_key,
            relation_type=cast(
                SurfaceRelationType,
                _enum_text(
                    payload.get("relation_type"),
                    allowed=RELATION_TYPE_VALUES,
                    default="unrelated",
                ),
            ),
            confidence=_confidence(payload.get("confidence"), default=0.7),
            reason=_compact_text(payload.get("reason")),
            source_refs=_text_tuple(payload.get("source_refs")),
        )

    def _answer_from_payload(
        self,
        payload: Mapping[str, object],
        *,
        run_id: str,
        document_id: str,
        candidate: RetrievalSurfaceCandidate,
    ) -> SurfaceAnswerDraft:
        return SurfaceAnswerDraft(
            id=_stable_uuid(run_id, "answer", candidate.local_surface_key),
            run_id=run_id,
            document_id=document_id,
            candidate_key=candidate.local_surface_key,
            title=_compact_text(payload.get("title")) or candidate.provisional_title,
            canonical_question=_compact_text(payload.get("canonical_question"))
            or candidate.provisional_title,
            short_answer=_compact_text(payload.get("short_answer")),
            answer=_compact_text(payload.get("answer")),
            answer_scope=_compact_text(payload.get("answer_scope")) or candidate.answer_scope,
            question_scope=_compact_text(payload.get("question_scope")) or candidate.question_scope,
            exclusion_scope=_compact_text(payload.get("exclusion_scope"))
            or candidate.exclusion_scope,
            source_refs=_text_tuple(payload.get("source_refs")) or candidate.source_refs,
            warnings=_text_tuple(payload.get("warnings")),
            metadata=_json_object(payload.get("metadata")),
        )

    def _ownership_decision_from_payload(
        self,
        payload: Mapping[str, object],
        *,
        run_id: str,
        document_id: str,
        surface_key: str,
        index: int,
    ) -> SurfaceQuestionOwnershipDecision:
        question = _compact_text(payload.get("question"))
        return SurfaceQuestionOwnershipDecision(
            id=_stable_uuid(run_id, "ownership_decision", surface_key, index, question),
            run_id=run_id,
            document_id=document_id,
            surface_key=surface_key,
            question=question,
            question_kind=cast(
                str,
                _enum_text(
                    payload.get("question_kind"),
                    allowed=QUESTION_KIND_VALUES,
                    default="generated_variant",
                ),
            ),
            ownership_confidence=_confidence(payload.get("confidence"), default=0.75),
            source=_compact_text(payload.get("source")) or "generated",
            status="owned",
        )

    def _rejected_question_from_payload(
        self, payload: Mapping[str, object]
    ) -> object:
        from src.domain.project_plane.retrieval_surface_compilation import SurfaceRejectedQuestion

        return SurfaceRejectedQuestion(
            question=_compact_text(payload.get("question")),
            belongs_to_surface_key=_compact_text(payload.get("belongs_to_surface_key")),
            reason=_compact_text(payload.get("reason")),
            confidence=_confidence(payload.get("confidence"), default=0.75),
        )

    def _judgement_from_payload(
        self, payload: Mapping[str, object]
    ) -> SurfaceRelationJudgement:
        return SurfaceRelationJudgement(
            surface_a_key=_compact_text(payload.get("surface_a_key")),
            surface_b_key=_compact_text(payload.get("surface_b_key")),
            relation_type=cast(
                SurfaceRelationType,
                _enum_text(
                    payload.get("relation_type"),
                    allowed=RELATION_TYPE_VALUES,
                    default="unrelated",
                ),
            ),
            parent_key=_compact_text(payload.get("parent_key")) or None,
            child_key=_compact_text(payload.get("child_key")) or None,
            confidence=_confidence(payload.get("confidence"), default=0.7),
            reason=_compact_text(payload.get("reason")),
            recommended_action=cast(
                SurfaceRelationJudgeAction,
                _enum_text(
                    payload.get("recommended_action"),
                    allowed=JUDGE_ACTION_VALUES,
                    default="review",
                ),
            ),
        )

    def _new_parent_from_payload(
        self, payload: Mapping[str, object]
    ) -> NewParentSurfaceCandidate:
        return NewParentSurfaceCandidate(
            local_surface_key=_compact_text(payload.get("local_surface_key"))
            or str(uuid.uuid4()),
            title=_compact_text(payload.get("title")),
            answer_scope=_compact_text(payload.get("answer_scope")),
            question_scope=_compact_text(payload.get("question_scope")),
            exclusion_scope=_compact_text(payload.get("exclusion_scope")),
            children=_text_tuple(payload.get("children")),
        )

    def _reassignment_from_payload(
        self,
        payload: Mapping[str, object],
        *,
        run_id: str,
        document_id: str,
        index: int,
    ) -> SurfaceQuestionReassignment:
        return SurfaceQuestionReassignment(
            id=_stable_uuid(run_id, "question_reassignment", index),
            run_id=run_id,
            document_id=document_id,
            question=_compact_text(payload.get("question")),
            from_surface_key=_compact_text(payload.get("from_surface_key")),
            to_surface_key=_compact_text(payload.get("to_surface_key")),
            reason=_compact_text(payload.get("reason")),
            confidence=_confidence(payload.get("confidence"), default=0.75),
        )
