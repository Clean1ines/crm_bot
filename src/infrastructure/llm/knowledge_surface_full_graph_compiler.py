from __future__ import annotations

import json
import re
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import asdict, replace
from typing import cast

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
    SurfaceRelationClusterContext,
    SurfaceRelationType,
)
from src.infrastructure.llm.knowledge_surface_compiler import (
    PROMPTS_DIR,
    _loads_json_object,
)
from src.infrastructure.llm.knowledge_surface_graph_compiler_v2 import (
    GRAPH_PROMPT_VERSION,
    GroqKnowledgeSurfaceGraphCompilerV2,
)

SURFACE_KEY_PATTERN = re.compile(r"[^0-9A-Za-z_]+")
GLOBAL_JUDGE_PROMPT = "faq_surface_global_relation_judge.ru.txt"
QUESTION_REASSIGNMENT_PROMPT = "faq_surface_question_reassignment.ru.txt"
GLOBAL_RELATION_CLUSTER_SIZE = 8
GLOBAL_RELATION_MAX_CLUSTERS = 64
ANSWER_SLOT_CLUSTER_MIN_SCORE = 0.24


class GroqFullKnowledgeSurfaceGraphCompiler(GroqKnowledgeSurfaceGraphCompilerV2):
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
                "FAQ graph compiler requires source units"
            )

        candidates: list[RetrievalSurfaceCandidate] = []
        local_relations: list[LocalSurfaceRelation] = []
        drafts: list[SurfaceAnswerDraft] = []
        ownership_decisions: list[SurfaceQuestionOwnershipDecision] = []
        reassignments: list[SurfaceQuestionReassignment] = []
        warnings: list[str] = []

        for unit_index, unit in enumerate(units, start=1):
            discovered = await self.discover_surfaces_for_source_unit(
                source_unit=unit,
                file_name=file_name,
                run_id=run_id,
            )
            unit_candidates = discovered.surface_candidates
            candidates.extend(unit_candidates)
            warnings.extend(discovered.warnings)
            await self._emit_progress(
                stage_kind="surface_discovery",
                status="completed",
                input_summary=f"source_unit={unit_index}/{len(units)} {unit.title}",
                output_summary=f"candidates={len(unit_candidates)}",
                metrics={
                    "source_unit_index": unit_index,
                    "source_unit_count": len(units),
                    "candidate_count": len(unit_candidates),
                    "source_unit_key": unit.source_unit_key,
                },
            )

            planned = await self.plan_local_relations(
                source_unit=unit,
                candidates=unit_candidates,
                file_name=file_name,
                run_id=run_id,
            )
            unit_relations = planned.relations
            local_relations.extend(unit_relations)
            warnings.extend(planned.warnings)
            await self._emit_progress(
                stage_kind="relation_planning",
                status="completed",
                input_summary=f"source_unit={unit_index}/{len(units)} {unit.title}",
                output_summary=f"relations={len(unit_relations)}",
                metrics={
                    "source_unit_index": unit_index,
                    "source_unit_count": len(units),
                    "relation_count": len(unit_relations),
                    "candidate_count": len(unit_candidates),
                    "source_unit_key": unit.source_unit_key,
                },
            )

            for candidate_index, candidate in enumerate(unit_candidates, start=1):
                related_candidates = _related_candidates(
                    candidate, unit_candidates, unit_relations
                )
                related_relations = _related_relations(
                    candidate.local_surface_key, unit_relations
                )
                draft = await self.synthesize_surface_answer(
                    source_unit=unit,
                    candidate=candidate,
                    local_relations=related_relations,
                    related_candidates=related_candidates,
                    file_name=file_name,
                    run_id=run_id,
                )
                drafts.append(draft)
                warnings.extend(draft.warnings)
                await self._emit_progress(
                    stage_kind="answer_synthesis",
                    status="completed",
                    input_summary=(
                        f"source_unit={unit_index}/{len(units)} "
                        f"candidate={candidate_index}/{len(unit_candidates)}"
                    ),
                    output_summary=f"surface={candidate.local_surface_key}",
                    metrics={
                        "source_unit_index": unit_index,
                        "source_unit_count": len(units),
                        "candidate_index": candidate_index,
                        "candidate_count": len(unit_candidates),
                        "surface_key": candidate.local_surface_key,
                    },
                )

                ownership_result = await self.assign_surface_questions(
                    source_unit=unit,
                    answer_draft=draft,
                    candidate=candidate,
                    local_relations=related_relations,
                    related_candidates=related_candidates,
                    file_name=file_name,
                    run_id=run_id,
                )
                ownership_decisions.extend(ownership_result.owned_questions)
                warnings.extend(ownership_result.warnings)
                await self._emit_progress(
                    stage_kind="question_ownership",
                    status="completed",
                    input_summary=(
                        f"source_unit={unit_index}/{len(units)} "
                        f"candidate={candidate_index}/{len(unit_candidates)}"
                    ),
                    output_summary=(
                        f"owned={len(ownership_result.owned_questions)} "
                        f"rejected={len(ownership_result.rejected_questions)}"
                    ),
                    metrics={
                        "source_unit_index": unit_index,
                        "source_unit_count": len(units),
                        "candidate_index": candidate_index,
                        "candidate_count": len(unit_candidates),
                        "surface_key": candidate.local_surface_key,
                        "owned_question_count": len(ownership_result.owned_questions),
                        "rejected_question_count": len(
                            ownership_result.rejected_questions
                        ),
                    },
                )
                reassignments.extend(
                    _reassign_rejected(
                        run_id=run_id,
                        document_id=unit.document_id,
                        from_surface_key=candidate.local_surface_key,
                        rejected_questions=ownership_result.rejected_questions,
                    )
                )

        (
            judge_relations,
            merge_decisions,
            judge_warnings,
        ) = await self._judge_global_relations(
            run_id=run_id,
            document_id=units[0].document_id,
            drafts=tuple(drafts),
            local_relations=tuple(local_relations),
        )
        warnings.extend(judge_warnings)
        await self._emit_progress(
            stage_kind="global_relation_judge",
            status="completed",
            output_summary=f"judge_relations={len(judge_relations)} merges={len(merge_decisions)}",
            metrics={
                "judge_relation_count": len(judge_relations),
                "merge_decision_count": len(merge_decisions),
            },
        )
        final_relations = _merge_relations(
            run_id=run_id,
            document_id=units[0].document_id,
            local_relations=tuple(local_relations),
            judge_relations=judge_relations,
            drafts=tuple(drafts),
        )
        final_reassignments, reassignment_warnings = await self._reassign_questions(
            run_id=run_id,
            document_id=units[0].document_id,
            drafts=tuple(drafts),
            relations=final_relations,
            ownership_decisions=tuple(ownership_decisions),
            existing_reassignments=tuple(reassignments),
        )
        warnings.extend(reassignment_warnings)
        reassignments = list(
            _dedupe_reassignments(tuple(reassignments) + final_reassignments)
        )
        final_ownership = _final_ownership(
            run_id=run_id,
            document_id=units[0].document_id,
            decisions=tuple(ownership_decisions),
            reassignments=tuple(reassignments),
        )
        surfaces = _final_surfaces(
            run_id=run_id,
            document_id=units[0].document_id,
            candidates=tuple(candidates),
            drafts=tuple(drafts),
            warnings=tuple(warnings),
        )
        graph = RetrievalSurfaceGraph(
            run_id=run_id,
            document_id=units[0].document_id,
            source_units=units,
            surfaces=surfaces,
            relations=final_relations,
            ownership=final_ownership,
            reassignments=tuple(reassignments),
            merge_decisions=merge_decisions,
            metrics=_json_object(
                {
                    "compiler_kind": "full_staged_surface_graph_v1",
                    "source_unit_count": len(units),
                    "candidate_count": len(candidates),
                    "surface_count": len(surfaces),
                    "relation_count": len(final_relations),
                    "ownership_count": len(final_ownership),
                    "reassignment_count": len(reassignments),
                    "merge_decision_count": len(merge_decisions),
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
                json_value_from_unknown(item) for item in quality.warnings
            ]
        return RetrievalSurfaceCompilationResult(
            mode=mode,
            prompt_version=GRAPH_PROMPT_VERSION,
            model=self.model_name,
            graph=replace(graph, metrics=metrics),
            metrics=metrics,
        )

    async def _judge_global_relations(
        self,
        *,
        run_id: str,
        document_id: str,
        drafts: tuple[SurfaceAnswerDraft, ...],
        local_relations: tuple[LocalSurfaceRelation, ...],
    ) -> tuple[
        tuple[RetrievalSurfaceRelation, ...],
        tuple[RetrievalSurfaceMergeDecision, ...],
        tuple[str, ...],
    ]:
        relations: list[RetrievalSurfaceRelation] = []
        merges: list[RetrievalSurfaceMergeDecision] = []
        warnings: list[str] = []
        clusters = _answer_slot_clusters(
            drafts,
            local_relations=local_relations,
            size=GLOBAL_RELATION_CLUSTER_SIZE,
        )
        for cluster_index, cluster in enumerate(clusters[:GLOBAL_RELATION_MAX_CLUSTERS]):
            payload = {
                "run_id": run_id,
                "cluster_context": asdict(
                    SurfaceRelationClusterContext(
                        cluster_key=f"answer_slot_cluster_{cluster_index}",
                        reason=(
                            "deterministic answer-slot candidate cluster: shared "
                            "question/title/source/summary evidence"
                        ),
                    )
                ),
                "surfaces": [asdict(item) for item in cluster],
                "existing_relations": [asdict(item) for item in local_relations],
            }
            data = await self._prompt_json(GLOBAL_JUDGE_PROMPT, payload)
            warnings.extend(_strings(data.get("warnings")))
            for index, item in enumerate(
                _objects(data.get("judgements"), "judgements")
            ):
                relation_type = _text(item.get("relation_type")) or "unrelated"
                parent = _text(item.get("parent_key"))
                child = _text(item.get("child_key"))
                if not parent or not child or parent == child:
                    continue
                relations.append(
                    RetrievalSurfaceRelation(
                        id=_stable_id(
                            run_id, "judge", cluster_index, index, parent, child
                        ),
                        run_id=run_id,
                        document_id=document_id,
                        parent_surface_key=parent,
                        child_surface_key=child,
                        relation_type=_relation_type(relation_type),
                        reason=_text(item.get("reason")) or "Global relation judge.",
                        confidence=_float(item.get("confidence"), 0.7),
                    )
                )
                if _text(item.get("recommended_action")) == "merge_same_surface":
                    merges.append(
                        RetrievalSurfaceMergeDecision(
                            id=_stable_id(run_id, "merge", cluster_index, index),
                            run_id=run_id,
                            document_id=document_id,
                            survivor_surface_key=parent,
                            merged_surface_keys=(child,),
                            keep_separate_surface_keys=(),
                            decision_type="merge",
                            reason=_text(item.get("reason"))
                            or "Global duplicate merge.",
                            confidence=_float(item.get("confidence"), 0.7),
                        )
                    )
        return tuple(relations), tuple(merges), tuple(warnings)

    async def _reassign_questions(
        self,
        *,
        run_id: str,
        document_id: str,
        drafts: tuple[SurfaceAnswerDraft, ...],
        relations: tuple[RetrievalSurfaceRelation, ...],
        ownership_decisions: tuple[SurfaceQuestionOwnershipDecision, ...],
        existing_reassignments: tuple[SurfaceQuestionReassignment, ...],
    ) -> tuple[tuple[SurfaceQuestionReassignment, ...], tuple[str, ...]]:
        payload = {
            "run_id": run_id,
            "surfaces": [asdict(item) for item in drafts],
            "relations": [asdict(item) for item in relations],
            "question_ownership": [asdict(item) for item in ownership_decisions],
            "existing_reassignments": [asdict(item) for item in existing_reassignments],
        }
        data = await self._prompt_json(QUESTION_REASSIGNMENT_PROMPT, payload)
        reassignments = tuple(
            SurfaceQuestionReassignment(
                id=_stable_id(run_id, "global_reassign", index),
                run_id=run_id,
                document_id=document_id,
                question=_text(item.get("question")),
                from_surface_key=_text(item.get("from_surface_key")),
                to_surface_key=_text(item.get("to_surface_key")),
                reason=_text(item.get("reason")) or "Global question reassignment.",
                confidence=_float(item.get("confidence"), 0.7),
            )
            for index, item in enumerate(
                _objects(data.get("reassignments"), "reassignments")
            )
            if _text(item.get("from_surface_key")) and _text(item.get("to_surface_key"))
        )
        return reassignments, tuple(_strings(data.get("warnings")))

    async def _prompt_json(
        self, prompt_file: str, payload: Mapping[str, object]
    ) -> Mapping[str, object]:
        prompt = (PROMPTS_DIR / prompt_file).read_text(encoding="utf-8")
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


def _related_candidates(
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
    key: str, relations: Sequence[LocalSurfaceRelation]
) -> tuple[LocalSurfaceRelation, ...]:
    return tuple(
        relation
        for relation in relations
        if key in {relation.source_surface_key, relation.target_surface_key}
    )


def _reassign_rejected(
    *,
    run_id: str,
    document_id: str,
    from_surface_key: str,
    rejected_questions: Sequence[object],
) -> tuple[SurfaceQuestionReassignment, ...]:
    result: list[SurfaceQuestionReassignment] = []
    for index, rejected in enumerate(rejected_questions):
        question = getattr(rejected, "question", "")
        to_surface_key = getattr(rejected, "belongs_to_surface_key", "")
        if not question or not to_surface_key:
            continue
        result.append(
            SurfaceQuestionReassignment(
                id=_stable_id(run_id, "rejected", from_surface_key, index),
                run_id=run_id,
                document_id=document_id,
                question=str(question),
                from_surface_key=from_surface_key,
                to_surface_key=str(to_surface_key),
                reason=str(getattr(rejected, "reason", "Rejected by local ownership.")),
                confidence=float(getattr(rejected, "confidence", 0.7)),
            )
        )
    return tuple(result)


def _merge_relations(
    *,
    run_id: str,
    document_id: str,
    local_relations: tuple[LocalSurfaceRelation, ...],
    judge_relations: tuple[RetrievalSurfaceRelation, ...],
    drafts: tuple[SurfaceAnswerDraft, ...],
) -> tuple[RetrievalSurfaceRelation, ...]:
    relations = list(judge_relations)
    for index, relation in enumerate(local_relations):
        parent, child = _local_relation_endpoints(relation)
        if parent == child:
            continue
        relations.append(
            RetrievalSurfaceRelation(
                id=_stable_id(run_id, "local", index, parent, child),
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
    relations.extend(_deterministic_global_relations(run_id, document_id, drafts))
    if not relations and len(drafts) > 1:
        relations.extend(_fallback_siblings(run_id, document_id, drafts))
    return tuple(_dedupe_relations(relations))


def _local_relation_endpoints(relation: LocalSurfaceRelation) -> tuple[str, str]:
    if relation.relation_type == "specializes":
        return relation.target_surface_key, relation.source_surface_key
    return relation.source_surface_key, relation.target_surface_key


def _deterministic_global_relations(
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
                    _relation(
                        run_id,
                        document_id,
                        left.candidate_key,
                        right.candidate_key,
                        "duplicates",
                    )
                )
            elif left_title in right_title or right_title in left_title:
                parent = left if len(left_title) < len(right_title) else right
                child = right if parent is left else left
                result.append(
                    _relation(
                        run_id,
                        document_id,
                        parent.candidate_key,
                        child.candidate_key,
                        "umbrella_contains",
                    )
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
        relation_type=_relation_type(relation_type),
        reason="Deterministic global graph reconciliation.",
        confidence=0.6,
    )


def _fallback_siblings(
    run_id: str,
    document_id: str,
    drafts: tuple[SurfaceAnswerDraft, ...],
) -> list[RetrievalSurfaceRelation]:
    return [
        _relation(
            run_id, document_id, left.candidate_key, right.candidate_key, "sibling"
        )
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
        if key not in seen:
            seen.add(key)
            result.append(relation)
    return result


def _final_surfaces(
    *,
    run_id: str,
    document_id: str,
    candidates: tuple[RetrievalSurfaceCandidate, ...],
    drafts: tuple[SurfaceAnswerDraft, ...],
    warnings: tuple[str, ...],
) -> tuple[RetrievalSurfaceDraft, ...]:
    candidate_by_key = {
        candidate.local_surface_key: candidate for candidate in candidates
    }
    result: list[RetrievalSurfaceDraft] = []
    for draft in drafts:
        candidate = candidate_by_key[draft.candidate_key]
        result.append(
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
                    "graph_context_compiled": True,
                    "candidate_id": candidate.id,
                },
                source_chunk_indexes=_source_indexes(candidate.source_refs),
            )
        )
    return tuple(result)


def _final_ownership(
    *,
    run_id: str,
    document_id: str,
    decisions: tuple[SurfaceQuestionOwnershipDecision, ...],
    reassignments: tuple[SurfaceQuestionReassignment, ...],
) -> tuple[SurfaceQuestionOwnership, ...]:
    ownership: list[SurfaceQuestionOwnership] = []
    for index, item in enumerate(decisions):
        rejected_from = tuple(
            reassignment.from_surface_key
            for reassignment in reassignments
            if reassignment.question == item.question
            and reassignment.to_surface_key == item.surface_key
        )
        if any(
            reassignment.question == item.question
            and reassignment.from_surface_key == item.surface_key
            for reassignment in reassignments
        ):
            continue
        ownership.append(
            SurfaceQuestionOwnership(
                id=_stable_id(
                    run_id, "ownership", index, item.surface_key, item.question
                ),
                run_id=run_id,
                document_id=document_id,
                question=item.question,
                owner_surface_key=item.surface_key,
                question_kind=item.question_kind,
                confidence=item.ownership_confidence,
                reason="Assigned by staged graph question ownership.",
                rejected_from_surface_keys=rejected_from,
            )
        )
    return tuple(ownership)


def _dedupe_reassignments(
    reassignments: tuple[SurfaceQuestionReassignment, ...],
) -> tuple[SurfaceQuestionReassignment, ...]:
    seen: set[tuple[str, str, str]] = set()
    result: list[SurfaceQuestionReassignment] = []
    for item in reassignments:
        key = (item.question, item.from_surface_key, item.to_surface_key)
        if key not in seen:
            seen.add(key)
            result.append(item)
    return tuple(result)


def _answer_slot_clusters(
    drafts: tuple[SurfaceAnswerDraft, ...],
    *,
    local_relations: tuple[LocalSurfaceRelation, ...],
    size: int,
) -> tuple[tuple[SurfaceAnswerDraft, ...], ...]:
    if len(drafts) <= size:
        return (drafts,) if drafts else ()

    by_key = {draft.candidate_key: draft for draft in drafts}
    scored_neighbors: dict[str, list[tuple[float, str]]] = {
        draft.candidate_key: [] for draft in drafts
    }

    for relation in local_relations:
        if relation.source_surface_key not in by_key or relation.target_surface_key not in by_key:
            continue
        score = _local_relation_cluster_score(relation.relation_type, relation.confidence)
        if score <= 0:
            continue
        scored_neighbors[relation.source_surface_key].append(
            (score, relation.target_surface_key)
        )
        scored_neighbors[relation.target_surface_key].append(
            (score, relation.source_surface_key)
        )

    for left_index, left in enumerate(drafts):
        for right in drafts[left_index + 1 :]:
            score = _answer_slot_similarity_score(left, right)
            if score < ANSWER_SLOT_CLUSTER_MIN_SCORE:
                continue
            scored_neighbors[left.candidate_key].append((score, right.candidate_key))
            scored_neighbors[right.candidate_key].append((score, left.candidate_key))

    clusters: list[tuple[SurfaceAnswerDraft, ...]] = []
    seen: set[tuple[str, ...]] = set()
    for draft in drafts:
        neighbors = sorted(
            scored_neighbors[draft.candidate_key], key=lambda item: item[0], reverse=True
        )
        keys = [draft.candidate_key]
        for _, key in neighbors:
            if key not in keys:
                keys.append(key)
            if len(keys) >= size:
                break
        if len(keys) < 2:
            continue
        cluster_key = tuple(sorted(keys))
        if cluster_key in seen:
            continue
        seen.add(cluster_key)
        clusters.append(tuple(by_key[key] for key in keys))

    if clusters:
        return tuple(clusters)
    return _clusters(drafts, size=size)


def _local_relation_cluster_score(relation_type: str, confidence: float) -> float:
    base_scores = {
        "duplicates": 1.0,
        "near_duplicate": 0.9,
        "umbrella_contains": 0.72,
        "specializes": 0.72,
        "overlaps": 0.55,
        "split_needed": 0.5,
        "sibling": 0.35,
        "contradicts": 0.5,
    }
    return base_scores.get(relation_type, 0.0) * max(0.0, min(confidence, 1.0))


def _answer_slot_similarity_score(
    left: SurfaceAnswerDraft, right: SurfaceAnswerDraft
) -> float:
    left_question_tokens = _slot_question_tokens(left)
    right_question_tokens = _slot_question_tokens(right)
    left_answer_tokens = _tokens(left.answer)
    right_answer_tokens = _tokens(right.answer)
    left_title_tokens = _tokens(f"{left.title} {left.canonical_question}")
    right_title_tokens = _tokens(f"{right.title} {right.canonical_question}")

    question_score = _jaccard(left_question_tokens, right_question_tokens)
    title_score = _jaccard(left_title_tokens, right_title_tokens)
    answer_score = _jaccard(left_answer_tokens, right_answer_tokens)
    summary_score = max(
        _coverage(left_answer_tokens, right_answer_tokens),
        _coverage(right_answer_tokens, left_answer_tokens),
    )
    source_score = 1.0 if set(left.source_refs) & set(right.source_refs) else 0.0

    return max(
        question_score * 0.9,
        title_score * 0.7,
        answer_score * 0.55,
        summary_score * 0.6,
        source_score * 0.45,
    )


def _slot_question_tokens(draft: SurfaceAnswerDraft) -> set[str]:
    return _tokens(
        " ".join(
            (
                draft.title,
                draft.canonical_question,
                draft.question_scope,
                draft.answer_scope,
            )
        )
    )


def _clusters(
    items: tuple[SurfaceAnswerDraft, ...], *, size: int
) -> tuple[tuple[SurfaceAnswerDraft, ...], ...]:
    return tuple(
        tuple(items[index : index + size]) for index in range(0, len(items), size)
    )


def _source_indexes(source_refs: tuple[str, ...]) -> tuple[int, ...]:
    indexes: list[int] = []
    for ref in source_refs:
        match = re.search(r"(\d+)", ref)
        if match:
            indexes.append(int(match.group(1)))
    return tuple(sorted(set(indexes)))


def _relation_type(value: str) -> SurfaceRelationType:
    allowed = {
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
    return cast(SurfaceRelationType, value if value in allowed else "unrelated")


def _objects(value: object, name: str) -> tuple[Mapping[str, object], ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise KnowledgePreprocessingValidationError(f"{name} must be an array")
    return tuple(
        cast(Mapping[str, object], item) for item in value if isinstance(item, Mapping)
    )


def _strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item) for item in value if str(item).strip())


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""


def _float(value: object, default: float) -> float:
    try:
        if isinstance(value, (str, int, float)):
            return float(value)
    except ValueError:
        return default
    return default


def _norm(value: str) -> str:
    return " ".join(value.casefold().split())


def _tokens(value: str) -> set[str]:
    return {
        token
        for token in re.sub(r"[^0-9a-zа-яё]+", " ", value.casefold()).split()
        if len(token) >= 3 and token not in _STOP_WORDS
    }


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _coverage(needle: set[str], haystack: set[str]) -> float:
    if not needle or not haystack:
        return 0.0
    return len(needle & haystack) / len(needle)


_STOP_WORDS: frozenset[str] = frozenset(
    {
        "это",
        "как",
        "что",
        "для",
        "или",
        "если",
        "при",
        "про",
        "над",
        "под",
        "the",
        "and",
        "for",
        "with",
        "from",
        "into",
    }
)


def _stable_id(*parts: object) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, ":".join(str(part) for part in parts)))


def _json_object(payload: dict[str, object]) -> JsonObject:
    return {str(key): json_value_from_unknown(value) for key, value in payload.items()}
