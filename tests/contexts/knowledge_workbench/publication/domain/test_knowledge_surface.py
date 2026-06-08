from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.contexts.knowledge_workbench.consolidation.domain.surfaces.value_objects.consolidated_surface_ref import (
    ConsolidatedSurfaceRef,
)
from src.contexts.knowledge_workbench.publication.domain.entities.knowledge_surface import (
    KnowledgeSurface,
)
from src.contexts.knowledge_workbench.publication.domain.value_objects.knowledge_surface_ref import (
    KnowledgeSurfaceRef,
)


ROOT = Path(__file__).resolve().parents[5]
PUBLICATION_DOMAIN = (
    ROOT / "src" / "contexts" / "knowledge_workbench" / "publication" / "domain"
)


def _now() -> datetime:
    return datetime(2026, 6, 8, 12, 0, tzinfo=timezone.utc)


def _surface(
    *,
    canonical_intent: str = "What does the product do?",
    answer: str = "The product turns documents into knowledge.",
    published_at: datetime | None = None,
) -> KnowledgeSurface:
    return KnowledgeSurface(
        surface_ref=KnowledgeSurfaceRef("knowledge-surface-1"),
        source_consolidated_surface_ref=ConsolidatedSurfaceRef("surface-1"),
        canonical_intent=canonical_intent,
        answer=answer,
        published_at=published_at or _now(),
    )


def test_valid_knowledge_surface() -> None:
    surface = _surface()

    assert surface.surface_ref.value == "knowledge-surface-1"
    assert surface.source_consolidated_surface_ref.value == "surface-1"
    assert surface.canonical_intent == "What does the product do?"
    assert surface.answer == "The product turns documents into knowledge."
    assert surface.published_at == _now()


def test_knowledge_surface_refs_must_be_non_empty() -> None:
    with pytest.raises(ValueError):
        KnowledgeSurfaceRef(" ")

    with pytest.raises(ValueError):
        ConsolidatedSurfaceRef(" ")


def test_canonical_intent_must_be_non_empty() -> None:
    with pytest.raises(ValueError):
        _surface(canonical_intent=" ")


def test_answer_must_be_non_empty() -> None:
    with pytest.raises(ValueError):
        _surface(answer=" ")


def test_published_at_must_be_timezone_aware() -> None:
    with pytest.raises(ValueError):
        _surface(published_at=datetime(2026, 6, 8, 12, 0))


def test_publication_domain_has_no_intermediate_runtime_semantics() -> None:
    forbidden_markers = (
        "DraftClaimObservation",
        "DraftClaimCluster",
        "EmbeddingVector",
        "PipelineArtifact",
        "Groq",
        "groq",
        "Qwen",
        "qwen",
        "Postgres",
        "postgres",
        ".commit(",
        ".rollback(",
    )

    offenders: list[str] = []
    for path in PUBLICATION_DOMAIN.rglob("*.py"):
        if path.name == "__init__.py":
            continue
        text = path.read_text(encoding="utf-8")
        for marker in forbidden_markers:
            if marker in text:
                offenders.append(f"{path.relative_to(ROOT)} contains {marker!r}")

    assert not offenders
