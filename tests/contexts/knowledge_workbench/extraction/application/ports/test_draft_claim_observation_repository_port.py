from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from src.contexts.knowledge_workbench.extraction.application.ports.draft_claim_observation_repository_port import (
    DraftClaimObservationRepositoryPort,
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
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_document_ref import (
    SourceDocumentRef,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_ref import (
    SourceUnitRef,
)


ROOT = Path(__file__).resolve().parents[6]
PORT_FILE = (
    ROOT
    / "src"
    / "contexts"
    / "knowledge_workbench"
    / "extraction"
    / "application"
    / "ports"
    / "draft_claim_observation_repository_port.py"
)


class FakeDraftClaimObservationRepository:
    def __init__(
        self,
        *,
        source_unit_documents: dict[SourceUnitRef, SourceDocumentRef] | None = None,
    ) -> None:
        self._observations: tuple[DraftClaimObservation, ...] = ()
        self._source_unit_documents = source_unit_documents or {}

    def save_many(
        self,
        observations: tuple[DraftClaimObservation, ...],
    ) -> None:
        self._observations = self._observations + observations

    def list_by_source_unit(
        self,
        source_unit_ref: SourceUnitRef,
    ) -> tuple[DraftClaimObservation, ...]:
        return tuple(
            observation
            for observation in self._observations
            if observation.source_unit_ref == source_unit_ref
        )

    def list_by_document(
        self,
        document_ref: SourceDocumentRef,
    ) -> tuple[DraftClaimObservation, ...]:
        return tuple(
            observation
            for observation in self._observations
            if self._source_unit_documents.get(observation.source_unit_ref)
            == document_ref
        )


def _accept_repository(
    repository: DraftClaimObservationRepositoryPort,
) -> DraftClaimObservationRepositoryPort:
    return repository


def _now() -> datetime:
    return datetime(2026, 6, 8, 12, 0, tzinfo=timezone.utc)


def _observation(
    observation_ref: str,
    source_unit_ref: str,
    *,
    claim: str = "Product turns documents into knowledge.",
) -> DraftClaimObservation:
    return DraftClaimObservation(
        observation_ref=DraftClaimObservationRef(observation_ref),
        source_unit_ref=SourceUnitRef(source_unit_ref),
        claim=DraftClaimText(claim),
        granularity=DraftClaimGranularity.ATOMIC,
        possible_questions=(PossibleQuestion("What does the product do?"),),
        exclusion_scope=ExclusionScope(""),
        evidence_block=EvidenceBlock("turns documents into knowledge"),
        created_at=_now(),
    )


def test_fake_repository_implements_port_contract() -> None:
    repository = FakeDraftClaimObservationRepository()

    accepted = _accept_repository(repository)

    assert accepted.list_by_source_unit(SourceUnitRef("missing")) == ()


def test_save_many_stores_observations() -> None:
    repository = FakeDraftClaimObservationRepository()
    first = _observation("draft-claim-1", "document-1.unit.0")
    second = _observation("draft-claim-2", "document-1.unit.1")

    repository.save_many((first, second))

    assert repository.list_by_source_unit(SourceUnitRef("document-1.unit.0")) == (
        first,
    )
    assert repository.list_by_source_unit(SourceUnitRef("document-1.unit.1")) == (
        second,
    )


def test_save_many_empty_tuple_is_valid_no_op() -> None:
    repository = FakeDraftClaimObservationRepository()

    repository.save_many(())

    assert repository.list_by_source_unit(SourceUnitRef("document-1.unit.0")) == ()


def test_list_by_source_unit_filters_observations() -> None:
    repository = FakeDraftClaimObservationRepository()
    matching = _observation("draft-claim-1", "document-1.unit.0")
    other = _observation("draft-claim-2", "document-1.unit.1")

    repository.save_many((matching, other))

    assert repository.list_by_source_unit(SourceUnitRef("document-1.unit.0")) == (
        matching,
    )


def test_list_by_document_filters_through_source_unit_document_mapping() -> None:
    document_ref = SourceDocumentRef("document-1")
    other_document_ref = SourceDocumentRef("document-2")
    repository = FakeDraftClaimObservationRepository(
        source_unit_documents={
            SourceUnitRef("document-1.unit.0"): document_ref,
            SourceUnitRef("document-1.unit.1"): document_ref,
            SourceUnitRef("document-2.unit.0"): other_document_ref,
        }
    )
    first = _observation("draft-claim-1", "document-1.unit.0")
    second = _observation("draft-claim-2", "document-1.unit.1")
    other = _observation("draft-claim-3", "document-2.unit.0")

    repository.save_many((first, second, other))

    assert repository.list_by_document(document_ref) == (first, second)
    assert repository.list_by_document(other_document_ref) == (other,)


def test_repository_does_not_mutate_observations() -> None:
    repository = FakeDraftClaimObservationRepository()
    observation = _observation("draft-claim-1", "document-1.unit.0")
    original_claim = observation.claim
    original_questions = observation.possible_questions

    repository.save_many((observation,))
    stored = repository.list_by_source_unit(SourceUnitRef("document-1.unit.0"))[0]

    assert stored is observation
    assert observation.claim == original_claim
    assert observation.possible_questions == original_questions


def test_repository_stores_draft_observations_only() -> None:
    repository = FakeDraftClaimObservationRepository()
    observation = _observation("draft-claim-1", "document-1.unit.0")

    repository.save_many((observation,))

    stored = repository.list_by_source_unit(SourceUnitRef("document-1.unit.0"))[0]
    assert isinstance(stored, DraftClaimObservation)
    assert stored.claim.value == "Product turns documents into knowledge."


def test_port_file_does_not_import_forbidden_runtime_or_later_stage_concepts() -> None:
    text = PORT_FILE.read_text(encoding="utf-8")

    forbidden_markers = (
        "ArtifactPayload",
        "PipelineArtifact",
        "llm_runtime",
        "execution_runtime",
        "Groq",
        "groq",
        "Qwen",
        "qwen",
        "registry",
        "surface",
        "Surface",
        "Ontology",
        "ClaimType",
        "ClaimTriple",
        "ClaimRelation",
        "CanonicalIntent",
    )

    offenders = [marker for marker in forbidden_markers if marker in text]

    assert not offenders
