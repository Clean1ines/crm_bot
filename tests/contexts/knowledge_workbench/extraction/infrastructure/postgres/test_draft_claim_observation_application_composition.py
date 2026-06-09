from __future__ import annotations

from pathlib import Path

from src.contexts.knowledge_workbench.extraction.application.policies.draft_claim_observation_artifact_parser import (
    DraftClaimObservationArtifactParser,
)
from src.contexts.knowledge_workbench.extraction.application.policies.draft_claim_observation_provenance_candidate_builder import (
    DraftClaimObservationProvenanceCandidateBuilder,
)
from src.contexts.knowledge_workbench.extraction.application.process_managers.apply_draft_claim_observation_artifact import (
    ApplyDraftClaimObservationArtifactAsync,
)
from src.contexts.knowledge_workbench.extraction.infrastructure.postgres.draft_claim_observation_application_composition import (
    make_postgres_apply_draft_claim_observation_artifact,
)
from src.contexts.knowledge_workbench.extraction.infrastructure.postgres.postgres_draft_claim_observation_application_unit_of_work import (
    PostgresDraftClaimObservationApplicationUnitOfWork,
)


COMPOSITION_FILE = (
    Path(__file__).resolve().parents[6]
    / "src/contexts/knowledge_workbench/extraction/infrastructure/postgres/draft_claim_observation_application_composition.py"
)


class FakeTransaction:
    async def start(self) -> None:
        pass

    async def commit(self) -> None:
        pass

    async def rollback(self) -> None:
        pass


class FakeConnection:
    def transaction(self) -> FakeTransaction:
        return FakeTransaction()

    async def execute(self, query: str, *args: object) -> object:
        return "OK"


def test_make_postgres_apply_draft_claim_observation_artifact_wires_async_use_case() -> None:
    use_case = make_postgres_apply_draft_claim_observation_artifact(FakeConnection())

    assert isinstance(use_case, ApplyDraftClaimObservationArtifactAsync)
    assert isinstance(use_case._parser, DraftClaimObservationArtifactParser)
    assert isinstance(
        use_case._provenance_candidate_builder,
        DraftClaimObservationProvenanceCandidateBuilder,
    )
    assert isinstance(
        use_case._unit_of_work,
        PostgresDraftClaimObservationApplicationUnitOfWork,
    )


def test_draft_claim_observation_application_composition_has_no_runtime_or_legacy_dependencies() -> None:
    text = COMPOSITION_FILE.read_text(encoding="utf-8")

    required_markers = (
        "make_postgres_apply_draft_claim_observation_artifact",
        "class DraftClaimObservationApplicationConnectionLike",
        "ApplyDraftClaimObservationArtifactAsync",
        "PostgresDraftClaimObservationApplicationUnitOfWork",
        "DraftClaimObservationArtifactParser",
        "DraftClaimObservationProvenanceCandidateBuilder",
    )
    forbidden_markers = (
        "src.contexts.execution_runtime",
        "src.contexts.llm_runtime",
        "src.contexts.artifact_runtime.infrastructure",
        "src.infrastructure",
        "SectionBatchQueueItem",
        "CLAIM_OBSERVATIONS_PERSISTED",
        "REGISTRY_APPLICATION",
        "claim_extraction_stage_blockers",
        "asyncpg",
        "Groq",
        "Qwen",
        "frontend",
    )

    missing = [marker for marker in required_markers if marker not in text]
    offenders = [marker for marker in forbidden_markers if marker in text]

    assert not missing, "\n".join(missing)
    assert not offenders, "\n".join(offenders)
