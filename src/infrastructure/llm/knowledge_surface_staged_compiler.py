from __future__ import annotations

import re
import uuid
from collections.abc import Sequence
from dataclasses import replace

from src.application.services.knowledge_surface_graph_quality import (
    validate_faq_surface_graph_quality,
)
from src.domain.project_plane.json_types import JsonObject, json_value_from_unknown
from src.domain.project_plane.knowledge_preprocessing import (
    KnowledgePreprocessingMode,
    KnowledgePreprocessingValidationError,
)
from src.domain.project_plane.retrieval_surface_compilation import (
    LocalSurfaceRelation,
    RetrievalSurfaceCandidate,
    RetrievalSurfaceCompilationResult,
    RetrievalSurfaceDraft,
    RetrievalSurfaceGraph,
    RetrievalSurfaceMergeDecision,
    RetrievalSurfaceRelation,
    RetrievalSurfaceSourceUnit,
    SurfaceAnswerDraft,
    SurfaceQuestionOwnership,
    SurfaceQuestionOwnershipDecision,
    SurfaceQuestionReassignment,
)
from src.infrastructure.llm.knowledge_surface_graph_compiler_v2 import (
    GRAPH_PROMPT_VERSION,
    GroqKnowledgeSurfaceGraphCompilerV2,
)

SURFACE_KEY_PATTERN = re.compile(r"[^0-9A-Za-z_]+")


class GroqStagedKnowledgeSurfaceCompiler(GroqKnowledgeSurfaceGraphCompilerV2):
    async def compile_surfaces(
        self,
        *,
        mode: KnowledgePreprocessingMode,
        source_units: Sequence[RetrievalSurfaceSourceUnit],
        file_name: str,
        run_id: str,
    ) -> RetrievalSurfaceCompilationResult:
        units = tuple(source_units)
        if not units:
            raise KnowledgePreprocessingValidationError(
                "FAQ surface graph compiler requires source units"
            )

        candidates: list[RetrievalSurfaceCandidate] = []
        local_relations: list[LocalSurfaceRelation] = []
        answer_drafts: list[SurfaceAnswerDraft] = []
        owned_decisions: list[SurfaceQuestionOwnershipDecision] = []
        reassignments: list[SurfaceQuestionReassignment] = []
        warnings: list[str] = []

        for unit in units:
            discovery = await self.discover_surfaces_for_source_unit(
                source_unit=unit,
                file_name=file_name,
                run_id=run_id,
            )
            unit_candidates = discovery.surface_candidates
            candidates.extend(unit_candidates)
            warnings.extend(discovery.warnings)

            relation_plan = await self.plan_local_relations(
                source_unit=unit,
                candidates=unit_candidates,
                file_name=file_name,
                run_id=run_id,
            )
            unit_relations = relation_plan.relations
            local_relations.extend(unit_relations)
            warnings.extend(relation_plan.warnings)

            for candidate in unit_candidates:
                related_candidates = _related_candidates(
                    candidate=candidate,
                    candidates=unit_candidates,
                    relations=unit_relations,
                )
                related_relations = _related_relations(
                    candidate_key=candidate.local_surface_key,
                    relations=unit_relations,
                )
                answer = await self.synthesize_surface_answer(
                    source_unit=unit,
                    candidate=candidate,
                    local_relations=related_relations,
                    related_candidates=related_candidates,
                    file_name=file_name,
                    run_id=run_id,
                )
                answer_drafts.append(answer)
                warnings.extend(answer.warnings)

                ownership = await self.assign_surface_questions(
                    source_unit=unit,
                    answer_draft=answer,
                    candidate=candidate,
                    local_relations=related_relations,
                    related_candidates=related_candidates,
                    file_name=file_name,
                    run_id=run_id,
                )
                owned_decisions.extend(ownership.owned_questions)
                warnings.extend(ownership.warnings)
                for index, rejected in enumerate(ownership.rejected_questions):
                    reassignments.append(
                        SurfaceQuestionReassignment(
                            id=_stable_id(run_id, "rejected", candidate.local_surface_key, index),
                            run_id=run_id,
                            document_id=unit.document_id,
                            question=rejected.question,
                            from_surface_key=candidate.local_surface_key,
                            to_surface_key=rejected.belongs_to_surface_key,
                            reason=rejected.reason,
                            confidence=rejected.confidence,
                        )
                    )

        relations = _global_relations(
            run_id=run_id,
            document_id=units[0].document_id,
            local_relations=tuple(local_relations),
            answer_drafts=tuple(answer_drafts),
        )
        surfaces = _final_surfaces(
            run_id=run_id,
            document_id=units[0].document_id,
            candidates=tuple(candidates),
            answer_drafts=tuple(answer_drafts),
            warnings=tuple(warnings),
        )
        ownership = _final_ownership(
            run_id=run_id,
            document_id=units[0].document_id,
            decisions=tuple(owned_decisions),
            reassignments=tuple(reassignments),
        )
        graph = RetrievalSurfaceGraph(
            run_id=run_id,
            document_id=units[0].document_id,
            source_units=units,
            surfaces=surfaces,
            relations=relations,
            ownership=ownership,
            reassignments=tuple(reassignments),
            merge_decisions=_merge_decisions(
                run_id=run_id,
                document_id=units[0].document_id,
                relations=relations,
            ),
            metrics=_json_object(
                {
                    "compiler_kind": "staged_surface_graph_v1",
                    "source_unit_count": len(units),
                    "candidate_count": len(candidates),
                    "surface_count": len(surfaces),
                    "relation_count": len(relations),
                    "ownership_count": len(ownership),
                    "reassignment_count": len(reassignments),
                    "warning_count": len(warnings),
                }
            ),
        )
        quality = validate_faq_surface_graph_quality(graph)
        if not quality.passed:
            raise KnowledgePreprocessingValidationError(
                "FAQ surface graph quality failed: " + ", ".join(quality.issues)
            )
        metrics = _json_object({**graph.metrics, **quality.metrics})
        if quality.warnings:
            metrics["quality_warnings"] = [
                json_value_from_unknown(warning) for warning in quality.warnings
            ]
        return RetrievalSurfaceCompilationResult(
            mode=mode,
            prompt_version=GRAPH_PROMPT_VERSION,
            model=self.model_name,
            graph=replace(graph, metrics=metrics),
            metrics=metrics,
        )


def _related_candidates(
    *,
    candidate: RetrievalSurfaceCandidate,
    candidates: Sequence[RetrievalSurfaceCandidate],
    relations: Sequence[LocalSurfaceRelation],
) -> tuple[RetrievalSurfaceCandidate, ...]:
    keys = {candidate.local_surface_key}
    for relation in relations:
        if relation.source_surface_key == candidate.local_surface_key:
            keys.add(relation.target_surface_key)
        if relation.target_surface_key == candidate.local_surface_key:
            keys.add(relation.source_surface_key)
    return tuple(item for item in candidates if item.local_surface_key in keys)


def _related_relations(
    *, candidate_key: str, relations: Sequence[LocalSurfaceRelation]
) -> tuple[LocalSurfaceRelation, ...]:
    return tuple(
        relation
        for relation in relations
        if candidate_key in {relation.source_surface_key, relation.target_surface_key}
    )


def _final_surfaces(
    *,
    run_id: str,
    document_id: str,
    candidates: tuple[RetrievalSurfaceCandidate, ...],
    answer_drafts: tuple[SurfaceAnswerDraft, ...],
    warnings: tuple[str, ...],
) -> tuple[RetrievalSurfaceDraft, ...]:
    candidate_by_key = {candidate.local_surface_key: candidate for candidate in candidates}
    surfaces: list[RetrievalSurfaceDraft] = []
    for draft in answer_drafts:
        candidate = candidate_by_key[draft.candidate_key]
        source_indexes = _source_indexes(candidate.source_refs)
        surfaces.append(
            RetrievalSurfaceDraft(
                id=_stable_id(run_id, "surface", draft.candidate_key),
                run_id=run_id,
                document_id=document_id,
                local_surface_key=draft.candidate_key,
                title=draft.title,
                canonical_question=draft.canonical_question,
                surface_kind=candidate.surface_kind,
                answer_scope=draft.answer_scope,
                question_scope=draft.question_scope,
                exclusion_scope=draft.exclusion_scope,
                answer=draft.answer,
                short_answer=draft.short_answer,
                status="draft",
                publication_status="unpublished",
                source_refs=draft.source_refs,
                source_excerpt=draft.answer[:500],
                confidence=candidate.confidence,
                warnings=tuple(sorted(set(draft.warnings + warnings))),
                metadata={
                    **draft.metadata,
                    "candidate_id": candidate.id,
                    "source_unit_id": candidate.source_unit_id,
                    "graph_context_compiled": True,
                },
                source_chunk_indexes=source_indexes,
            )
        )
    return tuple(surfaces)


def _global_relations(
    *,
    run_id: str,
    document_id: str,
    local_relations: tuple[LocalSurfaceRelation, ...],
    answer_drafts: tuple[SurfaceAnswerDraft, ...],
) -> tuple[RetrievalSurfaceRelation, ...]:
    relations: list[RetrievalSurfaceRelation] = []
    for index, relation in enumerate(local_relations):
        parent, child = _relation_endpoints(relation)
        if parent == child:
            continue
        relations.append(
            RetrievalSurfaceRelation(
                id=_stable_id(run_id, "relation", index, parent, child),
                run_id=run_id,
                document_id=document_id,
                parent_surface_key=parent,
                child_surface_key=child,
                relation_type=relation.relation_type,
                reason=relation.reason,
                confidence=relation.confidence,
                source_refs=relation.source_refs,
            )
        )
    relations.extend(_cross_surface_relations(run_id, document_id, answer_drafts))
    if not relations and len(answer_drafts) > 1:
        relations.extend(_fallback_siblings(run_id, document_id, answer_drafts))
    return tuple(_dedupe_relations(relations))


def _relation_endpoints(relation: LocalSurfaceRelation) -> tuple[str, str]:
    if relation.relation_type == "specializes":
        return relation.target_surface_key, relation.source_surface_key
    return relation.source_surface_key, relation.target_surface_key


def _cross_surface_relations(
    run_id: str,
    document_id: str,
    drafts: tuple[SurfaceAnswerDraft, ...],
) -> list[RetrievalSurfaceRelation]:
    result: list[RetrievalSurfaceRelation] = []
    for left_index, left in enumerate(drafts):
        for right in drafts[left_index + 1 :]:
            left_title = _norm(left.title)
            right_title = _norm(right.title)
            if not left_title or not right_title:
                continue
            if left_title == right_title:
                result.append(
                    _relation(run_id, document_id, left.candidate_key, right.candidate_key, "duplicates")
                )
            elif left_title in right_title or right_title in left_title:
                parent = left if len(left_title) < len(right_title) else right
                child = right if parent is left else left
                result.append(
                    _relation(run_id, document_id, parent.candidate_key, child.candidate_key, "umbrella_contains")
                )
    return result


def _relation(
    run_id: str,
    document_id: str,
    parent: str,
    child: str,
    relation_type: str,
) -> RetrievalSurfaceRelation:
    return RetrievalSurfaceRelation(
        id=_stable_id(run_id, relation_type, parent, child),
        run_id=run_id,
        document_id=document_id,
        parent_surface_key=parent,
        child_surface_key=child,
        relation_type=relation_type,  # type: ignore[arg-type]
        reason="Deterministic global graph reconciliation.",
        confidence=0.6,
    )


def _fallback_siblings(
    run_id: str,
    document_id: str,
    drafts: tuple[SurfaceAnswerDraft, ...],
) -> list[RetrievalSurfaceRelation]:
    return [
        _relation(run_id, document_id, left.candidate_key, right.candidate_key, "sibling")
        for left, right in zip(drafts, drafts[1:])
    ]


def _dedupe_relations(
    relations: list[RetrievalSurfaceRelation],
) -> list[RetrievalSurfaceRelation]:
    seen: set[tuple[str, str, str]] = set()
    result: list[RetrievalSurfaceRelation] = []
    for relation in relations:
        key = (
            relation.parent_surface_key,
            relation.child_surface_key,
            relation.relation_type,
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(relation)
    return result


def _final_ownership(
    *,
    run_id: str,
    document_id: str,
    decisions: tuple[SurfaceQuestionOwnershipDecision, ...],
    reassignments: tuple[SurfaceQuestionReassignment, ...],
) -> tuple[SurfaceQuestionOwnership, ...]:
    reassigned = {item.question for item in reassignments}
    ownership: list[SurfaceQuestionOwnership] = []
    for index, item in enumerate(decisions):
        if item.question in reassigned and item.surface_key in {
            reassignment.from_surface_key for reassignment in reassignments
        }:
            continue
        rejected_from = tuple(
            reassignment.from_surface_key
            for reassignment in reassignments
            if reassignment.question == item.question
            and reassignment.to_surface_key == item.surface_key
        )
        ownership.append(
            SurfaceQuestionOwnership(
                id=_stable_id(run_id, "ownership", index, item.surface_key, item.question),
                run_id=run_id,
                document_id=document_id,
                question=item.question,
                owner_surface_key=item.surface_key,
                question_kind=item.question_kind,
                confidence=item.ownership_confidence,
                reason="Assigned by staged question ownership.",
                rejected_from_surface_keys=rejected_from,
            )
        )
    return tuple(ownership)


def _merge_decisions(
    *,
    run_id: str,
    document_id: str,
    relations: tuple[RetrievalSurfaceRelation, ...],
) -> tuple[RetrievalSurfaceMergeDecision, ...]:
    decisions: list[RetrievalSurfaceMergeDecision] = []
    for index, relation in enumerate(relations):
        if relation.relation_type not in {"duplicates", "near_duplicate"}:
            continue
        decisions.append(
            RetrievalSurfaceMergeDecision(
                id=_stable_id(run_id, "merge", index),
                run_id=run_id,
                document_id=document_id,
                survivor_surface_key=relation.parent_surface_key,
                merged_surface_keys=(relation.child_surface_key,),
                keep_separate_surface_keys=(),
                decision_type="merge",
                reason=relation.reason,
                confidence=relation.confidence,
            )
        )
    return tuple(decisions)


def _source_indexes(source_refs: tuple[str, ...]) -> tuple[int, ...]:
    indexes: list[int] = []
    for ref in source_refs:
        match = re.search(r"(\d+)", ref)
        if match:
            indexes.append(int(match.group(1)))
    return tuple(sorted(set(indexes)))


def _norm(value: str) -> str:
    return " ".join(value.casefold().split())


def _stable_id(*parts: object) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, ":".join(str(part) for part in parts)))


def _json_object(payload: dict[str, object]) -> JsonObject:
    return {str(key): json_value_from_unknown(value) for key, value in payload.items()}
