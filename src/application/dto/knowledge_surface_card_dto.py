from __future__ import annotations

from dataclasses import dataclass

from src.domain.project_plane.retrieval_surface_compilation import (
    RetrievalSurfaceDraft,
    RetrievalSurfaceRelation,
    SurfaceQuestionOwnership,
    SurfaceQuestionReassignment,
)


@dataclass(frozen=True, slots=True)
class SurfaceRelationSummaryDto:
    surface_key: str
    relation_type: str
    reason: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "surface_key": self.surface_key,
            "relation_type": self.relation_type,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class SurfaceOwnedQuestionDto:
    question: str
    question_kind: str
    confidence: float
    source: str = "compiled"

    def to_dict(self) -> dict[str, object]:
        return {
            "question": self.question,
            "question_kind": self.question_kind,
            "confidence": self.confidence,
            "source": self.source,
        }


@dataclass(frozen=True, slots=True)
class SurfaceRejectedQuestionDto:
    question: str
    belongs_to_surface_key: str
    reason: str
    confidence: float

    def to_dict(self) -> dict[str, object]:
        return {
            "question": self.question,
            "belongs_to_surface_key": self.belongs_to_surface_key,
            "reason": self.reason,
            "confidence": self.confidence,
        }


@dataclass(frozen=True, slots=True)
class SurfaceCardDto:
    surface_id: str
    local_surface_key: str
    title: str
    surface_kind: str
    answer: str
    short_answer: str
    canonical_question: str
    answer_scope: str
    question_scope: str
    exclusion_scope: str
    owned_questions: tuple[SurfaceOwnedQuestionDto, ...]
    rejected_questions: tuple[SurfaceRejectedQuestionDto, ...]
    parent_surfaces: tuple[SurfaceRelationSummaryDto, ...]
    child_surfaces: tuple[SurfaceRelationSummaryDto, ...]
    sibling_surfaces: tuple[SurfaceRelationSummaryDto, ...]
    duplicate_candidates: tuple[SurfaceRelationSummaryDto, ...]
    overlap_warnings: tuple[str, ...]
    source_refs: tuple[str, ...]
    status: str
    publication_status: str
    quality_warnings: tuple[str, ...]

    @classmethod
    def from_surface_graph(
        cls,
        *,
        surface: RetrievalSurfaceDraft,
        relations: tuple[RetrievalSurfaceRelation, ...],
        ownership: tuple[SurfaceQuestionOwnership, ...],
        reassignments: tuple[SurfaceQuestionReassignment, ...] = (),
    ) -> "SurfaceCardDto":
        key = surface.local_surface_key
        parent_surfaces: list[SurfaceRelationSummaryDto] = []
        child_surfaces: list[SurfaceRelationSummaryDto] = []
        sibling_surfaces: list[SurfaceRelationSummaryDto] = []
        duplicate_candidates: list[SurfaceRelationSummaryDto] = []
        overlap_warnings: list[str] = []

        for relation in relations:
            if _is_parent_relation(relation=relation, surface_key=key):
                parent_surfaces.append(
                    SurfaceRelationSummaryDto(
                        surface_key=relation.parent_surface_key,
                        relation_type=relation.relation_type,
                        reason=relation.reason,
                    )
                )
            if _is_child_relation(relation=relation, surface_key=key):
                child_surfaces.append(
                    SurfaceRelationSummaryDto(
                        surface_key=relation.child_surface_key,
                        relation_type=relation.relation_type,
                        reason=relation.reason,
                    )
                )
            if key not in {relation.parent_surface_key, relation.child_surface_key}:
                continue
            other_key = _other_surface_key(relation=relation, surface_key=key)
            if relation.relation_type == "sibling":
                sibling_surfaces.append(
                    SurfaceRelationSummaryDto(
                        other_key,
                        relation.relation_type,
                        relation.reason,
                    )
                )
            if relation.relation_type in {"duplicates", "near_duplicate"}:
                duplicate_candidates.append(
                    SurfaceRelationSummaryDto(
                        other_key,
                        relation.relation_type,
                        relation.reason,
                    )
                )
            if relation.relation_type == "overlaps":
                overlap_warnings.append(relation.reason or f"overlaps:{other_key}")

        owned_questions = tuple(
            SurfaceOwnedQuestionDto(
                question=item.question,
                question_kind=item.question_kind,
                confidence=item.confidence,
            )
            for item in ownership
            if item.owner_surface_key == key
        )
        rejected_questions = tuple(
            SurfaceRejectedQuestionDto(
                question=item.question,
                belongs_to_surface_key=item.to_surface_key,
                reason=item.reason,
                confidence=item.confidence,
            )
            for item in reassignments
            if item.from_surface_key == key
        )
        quality_warnings = tuple(surface.warnings) + _umbrella_quality_warnings(
            surface_kind=surface.surface_kind,
            child_surfaces=tuple(child_surfaces),
        )
        return cls(
            surface_id=surface.id,
            local_surface_key=key,
            title=surface.title,
            surface_kind=surface.surface_kind,
            answer=surface.answer,
            short_answer=surface.short_answer,
            canonical_question=surface.canonical_question,
            answer_scope=surface.answer_scope,
            question_scope=surface.question_scope,
            exclusion_scope=surface.exclusion_scope,
            owned_questions=owned_questions,
            rejected_questions=rejected_questions,
            parent_surfaces=tuple(parent_surfaces),
            child_surfaces=tuple(child_surfaces),
            sibling_surfaces=tuple(sibling_surfaces),
            duplicate_candidates=tuple(duplicate_candidates),
            overlap_warnings=tuple(overlap_warnings),
            source_refs=surface.source_refs,
            status=surface.status,
            publication_status=surface.publication_status,
            quality_warnings=quality_warnings,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "surface_id": self.surface_id,
            "local_surface_key": self.local_surface_key,
            "title": self.title,
            "surface_kind": self.surface_kind,
            "answer": self.answer,
            "short_answer": self.short_answer,
            "canonical_question": self.canonical_question,
            "answer_scope": self.answer_scope,
            "question_scope": self.question_scope,
            "exclusion_scope": self.exclusion_scope,
            "owned_questions": [item.to_dict() for item in self.owned_questions],
            "rejected_questions": [item.to_dict() for item in self.rejected_questions],
            "parent_surfaces": [item.to_dict() for item in self.parent_surfaces],
            "child_surfaces": [item.to_dict() for item in self.child_surfaces],
            "sibling_surfaces": [item.to_dict() for item in self.sibling_surfaces],
            "duplicate_candidates": [
                item.to_dict() for item in self.duplicate_candidates
            ],
            "overlap_warnings": list(self.overlap_warnings),
            "source_refs": list(self.source_refs),
            "status": self.status,
            "publication_status": self.publication_status,
            "quality_warnings": list(self.quality_warnings),
        }


def _is_parent_relation(
    *, relation: RetrievalSurfaceRelation, surface_key: str
) -> bool:
    return (
        relation.child_surface_key == surface_key
        and relation.relation_type == "umbrella_contains"
    )


def _is_child_relation(
    *, relation: RetrievalSurfaceRelation, surface_key: str
) -> bool:
    return (
        relation.parent_surface_key == surface_key
        and relation.relation_type == "umbrella_contains"
    )


def _other_surface_key(
    *, relation: RetrievalSurfaceRelation, surface_key: str
) -> str:
    if relation.parent_surface_key == surface_key:
        return relation.child_surface_key
    return relation.parent_surface_key


def _umbrella_quality_warnings(
    *,
    surface_kind: str,
    child_surfaces: tuple[SurfaceRelationSummaryDto, ...],
) -> tuple[str, ...]:
    if surface_kind != "umbrella" or not child_surfaces:
        return ()
    return (
        "Эта карточка является зонтичной. Она не должна владеть вопросами, "
        "которые точнее отвечаются дочерними карточками.",
    )
