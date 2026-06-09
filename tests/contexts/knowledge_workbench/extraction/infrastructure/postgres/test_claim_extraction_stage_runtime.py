from __future__ import annotations

import inspect
from pathlib import Path

from src.contexts.knowledge_workbench.extraction.application.process_managers.apply_draft_claim_observation_artifact import (
    ApplyDraftClaimObservationArtifactAsync,
)
from src.contexts.knowledge_workbench.extraction.application.read_models.claim_extraction_stage_progress_async import (
    AsyncClaimExtractionStageProgressReadModel,
)
from src.contexts.knowledge_workbench.extraction.application.use_cases.run_claim_extraction_stage_async import (
    RunClaimExtractionStageAsync,
)
from src.contexts.knowledge_workbench.extraction.infrastructure.postgres.claim_extraction_stage_runtime import (
    ClaimExtractionStagePostgresRuntime,
    make_claim_extraction_stage_postgres_runtime,
)


RUNTIME_FILE = (
    Path(__file__).resolve().parents[6]
    / "src/contexts/knowledge_workbench/extraction/infrastructure/postgres/claim_extraction_stage_runtime.py"
)


class FakeConnection:
    def transaction(self) -> object:
        return object()

    async def execute(self, query: str, *args: object) -> object:
        return "OK"

    async def fetch(self, query: str, *args: object) -> list[object]:
        return []

    async def fetchval(self, query: str, *args: object) -> object:
        return 0


def test_postgres_runtime_composition_builds_runner_progress_reader_and_apply_use_case() -> None:
    runtime = make_claim_extraction_stage_postgres_runtime(FakeConnection())

    assert isinstance(runtime, ClaimExtractionStagePostgresRuntime)
    assert isinstance(runtime.runner, RunClaimExtractionStageAsync)
    assert isinstance(
        runtime.progress_reader, AsyncClaimExtractionStageProgressReadModel
    )
    assert isinstance(
        runtime.apply_draft_claim_observation_artifact,
        ApplyDraftClaimObservationArtifactAsync,
    )
    assert inspect.iscoroutinefunction(runtime.progress_reader.execute)
    assert inspect.iscoroutinefunction(
        runtime.apply_draft_claim_observation_artifact.execute
    )


def test_postgres_runtime_wires_apply_without_later_stage_or_runtime_leaks() -> None:
    text = RUNTIME_FILE.read_text(encoding="utf-8")

    required_markers = (
        "ClaimExtractionStagePostgresRuntime",
        "runner: RunClaimExtractionStageAsync",
        "progress_reader: AsyncClaimExtractionStageProgressReadModel",
        "apply_draft_claim_observation_artifact: ApplyDraftClaimObservationArtifactAsync",
        "DraftClaimObservationApplicationConnectionLike",
        "make_postgres_apply_draft_claim_observation_artifact",
    )
    forbidden_markers = (
        "src.contexts.execution_runtime.infrastructure",
        "src.contexts.llm_runtime.infrastructure",
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
        "consolidation",
        "publication",
    )

    missing = [marker for marker in required_markers if marker not in text]
    offenders = [marker for marker in forbidden_markers if marker in text]

    assert not missing, "\n".join(missing)
    assert not offenders, "\n".join(offenders)
