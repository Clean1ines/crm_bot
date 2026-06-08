from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from src.contexts.knowledge_workbench.extraction.application.policies.draft_claim_embedding_input_builder import (
    DraftClaimEmbeddingInputBuilder,
)
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


ROOT = Path(__file__).resolve().parents[6]
BUILDER_FILE = (
    ROOT
    / "src"
    / "contexts"
    / "knowledge_workbench"
    / "extraction"
    / "application"
    / "policies"
    / "draft_claim_embedding_input_builder.py"
)


def _now() -> datetime:
    return datetime(2026, 6, 8, 12, 0, tzinfo=timezone.utc)


def _observation(
    observation_ref: str,
    *,
    source_unit_ref: str = "document-1.unit.0",
    claim: str = "Продукт превращает документы в знания.",
    possible_questions: tuple[PossibleQuestion, ...] = (
        PossibleQuestion("Что делает продукт?"),
    ),
    exclusion_scope: ExclusionScope = ExclusionScope("Цены не описаны."),
    evidence_block: EvidenceBlock = EvidenceBlock("превращает документы в знания"),
) -> DraftClaimObservation:
    return DraftClaimObservation(
        observation_ref=DraftClaimObservationRef(observation_ref),
        source_unit_ref=SourceUnitRef(source_unit_ref),
        claim=DraftClaimText(claim),
        granularity=DraftClaimGranularity.ATOMIC,
        possible_questions=possible_questions,
        exclusion_scope=exclusion_scope,
        evidence_block=evidence_block,
        created_at=_now(),
    )


def _build(
    observations: tuple[DraftClaimObservation, ...],
):
    return DraftClaimEmbeddingInputBuilder().build(observations)


def test_builds_one_embedding_input() -> None:
    observation = _observation("draft-claim-1")

    result = _build((observation,))

    assert len(result) == 1
    assert result[0].observation_ref == observation.observation_ref
    assert result[0].source_unit_ref == observation.source_unit_ref
    assert result[0].text.startswith("claim: Продукт превращает документы в знания.")


def test_includes_possible_questions() -> None:
    observation = _observation(
        "draft-claim-1",
        possible_questions=(
            PossibleQuestion("Что делает продукт?"),
            PossibleQuestion("Как продукт работает с документами?"),
        ),
    )

    result = _build((observation,))

    assert result[0].text == (
        "claim: Продукт превращает документы в знания.\n"
        "possible_questions:\n"
        "- Что делает продукт?\n"
        "- Как продукт работает с документами?\n"
        "exclusion_scope: Цены не описаны.\n"
        "evidence_block: превращает документы в знания"
    )


def test_omits_empty_possible_questions_section() -> None:
    observation = _observation(
        "draft-claim-1",
        possible_questions=(),
    )

    result = _build((observation,))

    assert "possible_questions:" not in result[0].text
    assert "- " not in result[0].text
    assert result[0].text == (
        "claim: Продукт превращает документы в знания.\n"
        "exclusion_scope: Цены не описаны.\n"
        "evidence_block: превращает документы в знания"
    )


def test_omits_empty_exclusion_scope() -> None:
    observation = _observation(
        "draft-claim-1",
        exclusion_scope=ExclusionScope(""),
    )

    result = _build((observation,))

    assert "exclusion_scope:" not in result[0].text
    assert result[0].text == (
        "claim: Продукт превращает документы в знания.\n"
        "possible_questions:\n"
        "- Что делает продукт?\n"
        "evidence_block: превращает документы в знания"
    )


def test_preserves_evidence_block() -> None:
    observation = _observation(
        "draft-claim-1",
        evidence_block=EvidenceBlock("Exact source fragment stays unchanged."),
    )

    result = _build((observation,))

    assert result[0].text.endswith(
        "evidence_block: Exact source fragment stays unchanged."
    )


def test_order_preserved() -> None:
    first = _observation("draft-claim-1", claim="First claim.")
    second = _observation("draft-claim-2", claim="Second claim.")
    third = _observation("draft-claim-3", claim="Third claim.")

    result = _build((first, second, third))

    assert tuple(
        embedding_input.observation_ref.value for embedding_input in result
    ) == (
        "draft-claim-1",
        "draft-claim-2",
        "draft-claim-3",
    )
    assert tuple(
        embedding_input.text.splitlines()[0] for embedding_input in result
    ) == (
        "claim: First claim.",
        "claim: Second claim.",
        "claim: Third claim.",
    )


def test_empty_observations_returns_empty_tuple() -> None:
    assert _build(()) == ()


def test_builder_file_does_not_import_runtime_or_later_stage_terms() -> None:
    text = BUILDER_FILE.read_text(encoding="utf-8")

    forbidden_markers = (
        "embedding_runtime",
        "llm_runtime",
        "artifact_runtime",
        "PipelineArtifact",
        "Postgres",
        "postgres",
        "Groq",
        "groq",
        "Qwen",
        "qwen",
        "ClaimType",
        "ClaimTriple",
        "ClaimRelation",
        "CanonicalIntent",
        "Surface",
        "surface",
    )

    offenders = [marker for marker in forbidden_markers if marker in text]

    assert not offenders
