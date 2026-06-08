from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.contexts.knowledge_workbench.extraction.domain.entities.draft_claim_observation import (
    DraftClaimObservation,
)
from src.contexts.knowledge_workbench.extraction.domain.value_objects.draft_claim_granularity import (
    DraftClaimGranularity,
)
from src.contexts.knowledge_workbench.extraction.domain.value_objects.draft_claim_observation_ref import (
    DraftClaimObservationRef,
)
from src.contexts.knowledge_workbench.extraction.domain.value_objects.draft_claim_text import (
    DraftClaimText,
)
from src.contexts.knowledge_workbench.extraction.domain.value_objects.evidence_block import (
    EvidenceBlock,
)
from src.contexts.knowledge_workbench.extraction.domain.value_objects.exclusion_scope import (
    ExclusionScope,
)
from src.contexts.knowledge_workbench.extraction.domain.value_objects.possible_question import (
    PossibleQuestion,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_ref import (
    SourceUnitRef,
)


ROOT = Path(__file__).resolve().parents[5]
DRAFT_CLAIM_DOMAIN_FILES = (
    ROOT
    / "src"
    / "contexts"
    / "knowledge_workbench"
    / "extraction"
    / "domain"
    / "entities"
    / "draft_claim_observation.py",
    ROOT
    / "src"
    / "contexts"
    / "knowledge_workbench"
    / "extraction"
    / "domain"
    / "value_objects"
    / "draft_claim_observation_ref.py",
    ROOT
    / "src"
    / "contexts"
    / "knowledge_workbench"
    / "extraction"
    / "domain"
    / "value_objects"
    / "draft_claim_text.py",
    ROOT
    / "src"
    / "contexts"
    / "knowledge_workbench"
    / "extraction"
    / "domain"
    / "value_objects"
    / "draft_claim_granularity.py",
    ROOT
    / "src"
    / "contexts"
    / "knowledge_workbench"
    / "extraction"
    / "domain"
    / "value_objects"
    / "possible_question.py",
    ROOT
    / "src"
    / "contexts"
    / "knowledge_workbench"
    / "extraction"
    / "domain"
    / "value_objects"
    / "exclusion_scope.py",
    ROOT
    / "src"
    / "contexts"
    / "knowledge_workbench"
    / "extraction"
    / "domain"
    / "value_objects"
    / "evidence_block.py",
)


def _now() -> datetime:
    return datetime(2026, 6, 8, 12, 0, tzinfo=timezone.utc)


def _observation(
    *,
    granularity: DraftClaimGranularity = DraftClaimGranularity.ATOMIC,
    possible_questions: tuple[PossibleQuestion, ...] = (
        PossibleQuestion("What does the product do?"),
    ),
    exclusion_scope: ExclusionScope = ExclusionScope("Pricing is not covered."),
    created_at: datetime | None = None,
) -> DraftClaimObservation:
    return DraftClaimObservation(
        observation_ref=DraftClaimObservationRef("artifact-1:claim:claim-1"),
        source_unit_ref=SourceUnitRef("document-1.unit.0"),
        claim=DraftClaimText("The product turns documents into knowledge."),
        granularity=granularity,
        possible_questions=possible_questions,
        exclusion_scope=exclusion_scope,
        evidence_block=EvidenceBlock("turns documents into knowledge"),
        created_at=created_at or _now(),
    )


def test_valid_atomic_observation() -> None:
    observation = _observation()

    assert observation.observation_ref.value == "artifact-1:claim:claim-1"
    assert observation.source_unit_ref.value == "document-1.unit.0"
    assert observation.claim.value == "The product turns documents into knowledge."
    assert observation.granularity is DraftClaimGranularity.ATOMIC
    assert tuple(question.value for question in observation.possible_questions) == (
        "What does the product do?",
    )
    assert observation.exclusion_scope.value == "Pricing is not covered."
    assert observation.evidence_block.value == "turns documents into knowledge"


def test_valid_composite_observation() -> None:
    observation = _observation(
        granularity=DraftClaimGranularity.COMPOSITE,
        possible_questions=(
            PossibleQuestion("What steps does onboarding include?"),
            PossibleQuestion("How does onboarding work?"),
        ),
    )

    assert observation.granularity is DraftClaimGranularity.COMPOSITE
    assert len(observation.possible_questions) == 2


def test_possible_questions_may_be_empty() -> None:
    observation = _observation(possible_questions=())

    assert observation.possible_questions == ()


def test_duplicate_possible_questions_rejected() -> None:
    with pytest.raises(ValueError):
        _observation(
            possible_questions=(
                PossibleQuestion("What does it do?"),
                PossibleQuestion("What does it do?"),
            )
        )


def test_empty_claim_rejected() -> None:
    with pytest.raises(ValueError):
        DraftClaimText(" ")


def test_empty_evidence_block_rejected() -> None:
    with pytest.raises(ValueError):
        EvidenceBlock(" ")


def test_empty_exclusion_scope_allowed() -> None:
    observation = _observation(exclusion_scope=ExclusionScope(""))

    assert observation.exclusion_scope.value == ""


def test_invalid_granularity_rejected_by_enum() -> None:
    with pytest.raises(ValueError):
        DraftClaimGranularity("final_surface")


def test_naive_created_at_rejected() -> None:
    with pytest.raises(ValueError):
        _observation(created_at=datetime(2026, 6, 8, 12, 0))


def _assign_claim(
    observation: DraftClaimObservation,
    claim: DraftClaimText,
) -> None:
    setattr(observation, "claim", claim)


def test_domain_objects_are_immutable() -> None:
    observation = _observation()

    with pytest.raises(FrozenInstanceError):
        _assign_claim(observation, DraftClaimText("Changed"))


def test_draft_claim_domain_does_not_import_or_name_later_stage_concepts() -> None:
    forbidden_markers = (
        "llm_runtime",
        "artifact_runtime",
        "execution_runtime",
        "Groq",
        "groq",
        "Qwen",
        "qwen",
        "consolidation",
        "ClaimType",
        "ClaimRelation",
        "ClaimTriple",
        "SurfaceKind",
        "CanonicalIntent",
        "Ontology",
        "Subject",
        "Predicate",
        "Object",
        "confidence",
    )

    offenders: list[str] = []
    for path in DRAFT_CLAIM_DOMAIN_FILES:
        text = path.read_text(encoding="utf-8")
        for marker in forbidden_markers:
            if marker in text:
                offenders.append(f"{path.relative_to(ROOT)} contains {marker!r}")

    assert not offenders
