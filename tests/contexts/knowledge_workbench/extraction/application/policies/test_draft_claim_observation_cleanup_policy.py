from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from src.contexts.knowledge_workbench.extraction.application.policies.draft_claim_observation_cleanup_policy import (
    DraftClaimObservationCleanupInput,
    DraftClaimObservationCleanupPolicy,
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
POLICY_FILE = (
    ROOT
    / "src"
    / "contexts"
    / "knowledge_workbench"
    / "extraction"
    / "application"
    / "policies"
    / "draft_claim_observation_cleanup_policy.py"
)


def _now() -> datetime:
    return datetime(2026, 6, 8, 12, 0, tzinfo=timezone.utc)


def _observation(
    observation_ref: str,
    *,
    claim: str = "Product turns documents into knowledge.",
    possible_questions: tuple[PossibleQuestion, ...] = (
        PossibleQuestion("What does the product do?"),
    ),
    exclusion_scope: ExclusionScope = ExclusionScope("Pricing is not covered."),
) -> DraftClaimObservation:
    return DraftClaimObservation(
        observation_ref=DraftClaimObservationRef(observation_ref),
        source_unit_ref=SourceUnitRef("document-1.unit.0"),
        claim=DraftClaimText(claim),
        granularity=DraftClaimGranularity.ATOMIC,
        possible_questions=possible_questions,
        exclusion_scope=exclusion_scope,
        evidence_block=EvidenceBlock("turns documents into knowledge"),
        created_at=_now(),
    )


def _clean(
    observations: tuple[DraftClaimObservation, ...],
):
    return DraftClaimObservationCleanupPolicy().clean(
        DraftClaimObservationCleanupInput(observations=observations)
    )


def test_duplicate_possible_questions_removed_inside_one_observation() -> None:
    observation = _observation(
        "draft-claim-1",
        possible_questions=(
            PossibleQuestion("What does it do?"),
            PossibleQuestion("What does it do?"),
            PossibleQuestion("How does it work?"),
        ),
    )

    result = _clean((observation,))

    assert tuple(
        question.value for question in result.observations[0].possible_questions
    ) == (
        "What does it do?",
        "How does it work?",
    )
    assert result.removed_possible_question_count == 1


def test_possible_question_order_preserved() -> None:
    observation = _observation(
        "draft-claim-1",
        possible_questions=(
            PossibleQuestion("First?"),
            PossibleQuestion("Second?"),
            PossibleQuestion("First?"),
            PossibleQuestion("Third?"),
            PossibleQuestion("Second?"),
        ),
    )

    result = _clean((observation,))

    assert tuple(
        question.value for question in result.observations[0].possible_questions
    ) == (
        "First?",
        "Second?",
        "Third?",
    )


def test_duplicate_exclusion_scope_parts_removed() -> None:
    observation = _observation(
        "draft-claim-1",
        exclusion_scope=ExclusionScope(
            "Pricing is not covered; Setup is not covered; Pricing is not covered"
        ),
    )

    result = _clean((observation,))

    assert result.observations[0].exclusion_scope.value == (
        "Pricing is not covered; Setup is not covered"
    )
    assert result.normalized_exclusion_scope_count == 1


def test_exclusion_scope_parts_are_trimmed_and_first_order_is_preserved() -> None:
    observation = _observation(
        "draft-claim-1",
        exclusion_scope=ExclusionScope("  A  ; B ; A ;  C  ; B "),
    )

    result = _clean((observation,))

    assert result.observations[0].exclusion_scope.value == "A; B; C"
    assert result.normalized_exclusion_scope_count == 1


def test_empty_exclusion_scope_remains_empty() -> None:
    observation = _observation(
        "draft-claim-1",
        exclusion_scope=ExclusionScope(""),
    )

    result = _clean((observation,))

    assert result.observations[0].exclusion_scope.value == ""
    assert result.normalized_exclusion_scope_count == 0


def test_observations_are_not_merged_even_if_claim_text_is_same() -> None:
    first = _observation(
        "draft-claim-1",
        claim="Same claim.",
        possible_questions=(PossibleQuestion("First?"),),
    )
    second = _observation(
        "draft-claim-2",
        claim="Same claim.",
        possible_questions=(PossibleQuestion("Second?"),),
    )

    result = _clean((first, second))

    assert len(result.observations) == 2
    assert tuple(
        observation.observation_ref.value for observation in result.observations
    ) == (
        "draft-claim-1",
        "draft-claim-2",
    )
    assert tuple(observation.claim.value for observation in result.observations) == (
        "Same claim.",
        "Same claim.",
    )


def test_counts_are_correct_across_observations() -> None:
    first = _observation(
        "draft-claim-1",
        possible_questions=(
            PossibleQuestion("A?"),
            PossibleQuestion("A?"),
            PossibleQuestion("B?"),
            PossibleQuestion("B?"),
        ),
        exclusion_scope=ExclusionScope("A; A; B"),
    )
    second = _observation(
        "draft-claim-2",
        possible_questions=(
            PossibleQuestion("C?"),
            PossibleQuestion("C?"),
        ),
        exclusion_scope=ExclusionScope("C"),
    )

    result = _clean((first, second))

    assert result.removed_possible_question_count == 3
    assert result.normalized_exclusion_scope_count == 1


def test_input_empty_tuple_returns_empty_result() -> None:
    result = _clean(())

    assert result.observations == ()
    assert result.removed_possible_question_count == 0
    assert result.normalized_exclusion_scope_count == 0


def test_policy_file_does_not_import_runtime_db_or_later_stage_terms() -> None:
    text = POLICY_FILE.read_text(encoding="utf-8")

    forbidden_markers = (
        "llm_runtime",
        "embedding",
        "artifact_runtime",
        "PipelineArtifact",
        "Postgres",
        "postgres",
        "Groq",
        "groq",
        "Qwen",
        "qwen",
        "Ontology",
        "ClaimType",
        "ClaimTriple",
        "ClaimRelation",
        "CanonicalIntent",
        "Surface",
        "surface",
        ".commit(",
        ".rollback(",
    )

    offenders = [marker for marker in forbidden_markers if marker in text]

    assert not offenders
