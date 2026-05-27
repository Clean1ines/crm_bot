from __future__ import annotations

from dataclasses import dataclass, field

from src.domain.project_plane.retrieval_surface_compilation import (
    RetrievalSurfaceGraph,
    SurfaceQuestionOwnership,
)


@dataclass(frozen=True, slots=True)
class SurfaceGraphQualityResult:
    passed: bool
    issues: tuple[str, ...]
    warnings: tuple[str, ...]
    metrics: dict[str, int | str] = field(default_factory=dict)


def validate_faq_surface_graph_quality(graph: RetrievalSurfaceGraph) -> SurfaceGraphQualityResult:
    """Validate production-critical FAQ Retrieval Surface Graph invariants.

    This is intentionally deterministic application logic. It must not call DB,
    HTTP, LLMs, embeddings, or prompt adapters. The ingestion orchestrator can use
    it before marking a document as processed.
    """

    source_unit_count = len(graph.source_units)
    final_surface_count = len(graph.surfaces)
    final_relation_count = len(graph.relations)
    surface_answer_count = sum(1 for surface in graph.surfaces if surface.answer.strip())
    rejected_question_count = sum(
        len(ownership.rejected_from_surface_keys) for ownership in graph.ownership
    )
    parent_child_relation_count = sum(
        1 for relation in graph.relations if relation.relation_type == "umbrella_contains"
    )

    issues: list[str] = []
    warnings: list[str] = []

    if source_unit_count >= 20 and final_surface_count < 8:
        issues.append("large_document_collapsed_to_too_few_surfaces")

    if surface_answer_count == 0:
        issues.append("no_surface_answers")

    if final_surface_count <= 2 and source_unit_count >= 20:
        issues.append("large_document_final_surface_count_too_low")

    if final_relation_count == 0 and final_surface_count > 1:
        issues.append("missing_relations_for_multi_surface_graph")

    if _umbrella_owns_child_specific_questions(graph):
        issues.append("umbrella_owns_child_specific_questions")

    if rejected_question_count == 0 and parent_child_relation_count > 0:
        warnings.append("ownership_not_discriminative")

    return SurfaceGraphQualityResult(
        passed=not issues,
        issues=tuple(issues),
        warnings=tuple(warnings),
        metrics={
            "quality_status": "passed" if not issues else "failed",
            "source_unit_count": source_unit_count,
            "final_surface_count": final_surface_count,
            "final_relation_count": final_relation_count,
            "surface_answer_count": surface_answer_count,
            "rejected_question_count": rejected_question_count,
            "parent_child_relation_count": parent_child_relation_count,
        },
    )


def _umbrella_owns_child_specific_questions(graph: RetrievalSurfaceGraph) -> bool:
    surface_kind_by_key = {
        surface.local_surface_key: surface.surface_kind for surface in graph.surfaces
    }
    child_keys_by_parent = {
        relation.parent_surface_key: relation.child_surface_key
        for relation in graph.relations
        if relation.relation_type == "umbrella_contains"
    }
    ownership_by_owner = _ownership_by_surface(graph.ownership)

    for parent_key, child_key in child_keys_by_parent.items():
        if surface_kind_by_key.get(parent_key) != "umbrella":
            continue
        parent_questions = {_question_fingerprint(item.question) for item in ownership_by_owner.get(parent_key, ())}
        child_questions = {_question_fingerprint(item.question) for item in ownership_by_owner.get(child_key, ())}
        if parent_questions.intersection(child_questions):
            return True
    return False


def _ownership_by_surface(
    ownership: tuple[SurfaceQuestionOwnership, ...],
) -> dict[str, tuple[SurfaceQuestionOwnership, ...]]:
    grouped: dict[str, list[SurfaceQuestionOwnership]] = {}
    for item in ownership:
        grouped.setdefault(item.owner_surface_key, []).append(item)
    return {key: tuple(value) for key, value in grouped.items()}


def _question_fingerprint(question: str) -> str:
    return " ".join(question.lower().replace("ё", "е").split())
