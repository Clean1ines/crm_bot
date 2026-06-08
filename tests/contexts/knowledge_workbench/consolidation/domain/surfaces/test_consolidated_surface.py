from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.contexts.knowledge_workbench.consolidation.domain.surfaces.entities.consolidated_surface import (
    ConsolidatedSurface,
)
from src.contexts.knowledge_workbench.consolidation.domain.surfaces.value_objects.canonical_intent import (
    CanonicalIntent,
)
from src.contexts.knowledge_workbench.consolidation.domain.surfaces.value_objects.consolidated_surface_ref import (
    ConsolidatedSurfaceRef,
)
from src.contexts.knowledge_workbench.consolidation.domain.surfaces.value_objects.ontology_tag import (
    OntologyTag,
)
from src.contexts.knowledge_workbench.consolidation.domain.surfaces.value_objects.surface_evidence_ref import (
    SurfaceEvidenceRef,
)
from src.contexts.knowledge_workbench.consolidation.domain.surfaces.value_objects.surface_kind import (
    SurfaceKind,
)
from src.contexts.knowledge_workbench.consolidation.domain.surfaces.value_objects.surface_relation import (
    SurfaceRelation,
)
from src.contexts.knowledge_workbench.extraction.domain.value_objects.draft_claim_observation_ref import (
    DraftClaimObservationRef,
)


ROOT = Path(__file__).resolve().parents[6]
CLUSTERING_DOMAIN = (
    ROOT
    / "src"
    / "contexts"
    / "knowledge_workbench"
    / "consolidation"
    / "domain"
    / "clustering"
)


def _now() -> datetime:
    return datetime(2026, 6, 8, 12, 0, tzinfo=timezone.utc)


def _surface(
    *,
    canonical_intent: CanonicalIntent = CanonicalIntent("What does the product do?"),
    answer: str = "The product turns documents into knowledge.",
    surface_kind: SurfaceKind = SurfaceKind.CAPABILITY,
    source_observation_refs: tuple[DraftClaimObservationRef, ...] = (
        DraftClaimObservationRef("draft-claim-1"),
    ),
    evidence_refs: tuple[SurfaceEvidenceRef, ...] = (
        SurfaceEvidenceRef("draft-claim-1:evidence"),
    ),
    ontology_tags: tuple[OntologyTag, ...] = (),
    relations: tuple[SurfaceRelation, ...] = (),
    created_at: datetime | None = None,
) -> ConsolidatedSurface:
    return ConsolidatedSurface(
        surface_ref=ConsolidatedSurfaceRef("surface-1"),
        canonical_intent=canonical_intent,
        answer=answer,
        surface_kind=surface_kind,
        source_observation_refs=source_observation_refs,
        evidence_refs=evidence_refs,
        ontology_tags=ontology_tags,
        relations=relations,
        created_at=created_at or _now(),
    )


def test_valid_surface() -> None:
    surface = _surface()

    assert surface.surface_ref.value == "surface-1"
    assert surface.canonical_intent.value == "What does the product do?"
    assert surface.answer == "The product turns documents into knowledge."
    assert surface.surface_kind is SurfaceKind.CAPABILITY
    assert tuple(ref.value for ref in surface.source_observation_refs) == (
        "draft-claim-1",
    )
    assert tuple(ref.value for ref in surface.evidence_refs) == (
        "draft-claim-1:evidence",
    )


def test_canonical_intent_must_be_non_empty() -> None:
    with pytest.raises(ValueError):
        CanonicalIntent(" ")


def test_answer_must_be_non_empty() -> None:
    with pytest.raises(ValueError):
        _surface(answer=" ")


def test_source_observation_refs_must_be_non_empty() -> None:
    with pytest.raises(ValueError):
        _surface(source_observation_refs=())


def test_duplicate_source_refs_rejected() -> None:
    source_ref = DraftClaimObservationRef("draft-claim-1")

    with pytest.raises(ValueError):
        _surface(source_observation_refs=(source_ref, source_ref))


def test_created_at_must_be_timezone_aware() -> None:
    with pytest.raises(ValueError):
        _surface(created_at=datetime(2026, 6, 8, 12, 0))


def test_surface_kind_exact_values() -> None:
    assert tuple(kind.value for kind in SurfaceKind) == (
        "overview",
        "definition",
        "property",
        "capability",
        "limitation",
        "rule",
        "condition",
        "process",
        "list",
        "comparison",
        "criterion",
        "example_set",
        "value",
        "exception",
    )


def test_ontology_tags_allowed() -> None:
    surface = _surface(
        ontology_tags=(
            OntologyTag("product"),
            OntologyTag("knowledge_management"),
        )
    )

    assert tuple(tag.value for tag in surface.ontology_tags) == (
        "product",
        "knowledge_management",
    )


def test_relations_allowed() -> None:
    surface = _surface(
        relations=(
            SurfaceRelation(
                relation_kind="supports",
                target_surface_ref=ConsolidatedSurfaceRef("surface-2"),
            ),
        )
    )

    assert len(surface.relations) == 1
    assert surface.relations[0].relation_kind == "supports"
    assert surface.relations[0].target_surface_ref.value == "surface-2"


def test_refs_and_relation_kind_must_be_non_empty() -> None:
    with pytest.raises(ValueError):
        ConsolidatedSurfaceRef(" ")

    with pytest.raises(ValueError):
        SurfaceEvidenceRef(" ")

    with pytest.raises(ValueError):
        OntologyTag(" ")

    with pytest.raises(ValueError):
        SurfaceRelation(
            relation_kind=" ",
            target_surface_ref=ConsolidatedSurfaceRef("surface-2"),
        )


def test_clustering_guard_is_narrowed_to_clustering_subpackage() -> None:
    forbidden_markers = (
        "Surface",
        "surface",
        "Ontology",
        "ontology",
        "CanonicalIntent",
        "ConsolidatedSurface",
        "KnowledgeSurface",
        "Publication",
        "Prompt C output parser",
    )

    offenders: list[str] = []
    for path in CLUSTERING_DOMAIN.rglob("*.py"):
        if path.name == "__init__.py":
            continue
        text = path.read_text(encoding="utf-8")
        for marker in forbidden_markers:
            if marker in text:
                offenders.append(f"{path.relative_to(ROOT)} contains {marker!r}")

    assert not offenders
