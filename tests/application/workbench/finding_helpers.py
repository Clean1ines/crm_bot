from __future__ import annotations

from src.application.services.faq_workbench_claim_observations_service import (
    ParsedSectionFinding,
)
from src.domain.project_plane.knowledge_workbench import (
    SectionFindingAction,
    SurfaceKind,
)


def _section_action(*candidates: str) -> SectionFindingAction:
    normalized = {candidate.strip().lower() for candidate in candidates}
    for member in SectionFindingAction:
        if member.value.strip().lower() in normalized:
            return member
        if member.name.strip().lower() in normalized:
            return member

    available = ", ".join(
        f"{member.name}={member.value}" for member in SectionFindingAction
    )
    raise AssertionError(
        f"Unsupported SectionFindingAction candidates; available: {available}"
    )


def _surface_kind(*candidates: str) -> SurfaceKind:
    normalized = {candidate.strip().lower() for candidate in candidates}
    for member in SurfaceKind:
        if member.value.strip().lower() in normalized:
            return member
        if member.name.strip().lower() in normalized:
            return member

    available = ", ".join(f"{member.name}={member.value}" for member in SurfaceKind)
    raise AssertionError(f"Unsupported SurfaceKind candidates; available: {available}")


def product_finding() -> ParsedSectionFinding:
    return ParsedSectionFinding(
        action=_section_action("new"),
        local_surface_key="product_definition",
        title="Product",
        canonical_question="Что такое продукт?",
        surface_kind=_surface_kind("definition"),
        answer="Product turns documents into reviewed knowledge surfaces.",
        short_answer="Product turns documents into reviewed knowledge surfaces.",
        answer_delta="",
        answer_scope="Product definition.",
        question_scope="Questions about what the product does.",
        exclusion_scope="Questions outside product definition.",
        variants=("что делает продукт",),
        evidence_quotes=("Product text.",),
        source_refs=("document-1#section-0001-product",),
        source_chunk_indexes=(0,),
        confidence=0.9,
        reason="Test product finding.",
    )


def extension_finding() -> ParsedSectionFinding:
    return ParsedSectionFinding(
        action=_section_action("extends_existing"),
        local_surface_key="product_definition",
        title="Product",
        canonical_question="Что такое продукт?",
        surface_kind=_surface_kind("curation", "definition"),
        answer="Продукт помогает курировать знания.",
        short_answer="Продукт помогает курировать знания.",
        answer_delta="Продукт помогает курировать знания.",
        answer_scope="Product curation behavior.",
        question_scope="Questions about product curation workflow.",
        exclusion_scope="Questions outside product curation workflow.",
        variants=("как курировать знания",),
        evidence_quotes=("Curation text.",),
        source_refs=("document-1#section-0002-curation",),
        source_chunk_indexes=(1,),
        confidence=0.9,
        reason="Test extension finding.",
        target_surface_key="product_definition",
    )


def override_finding() -> ParsedSectionFinding:
    return ParsedSectionFinding(
        action=_section_action("new"),
        local_surface_key="override_definition",
        title="Override",
        canonical_question="Что такое override?",
        surface_kind=_surface_kind("definition"),
        answer="Override answer.",
        short_answer="Override answer.",
        answer_delta="",
        answer_scope="Override behavior.",
        question_scope="Questions about override behavior.",
        exclusion_scope="Questions outside override behavior.",
        variants=("override",),
        evidence_quotes=("Product text.",),
        source_refs=("document-1#section-0001-product",),
        source_chunk_indexes=(0,),
        confidence=0.9,
        reason="Test override finding.",
    )
