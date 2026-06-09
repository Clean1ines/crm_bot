from __future__ import annotations

from src.contexts.knowledge_workbench.extraction.application.read_models.claim_extraction_stage_progress import (
    ClaimExtractionStageProgressReadModel,
)
from src.contexts.knowledge_workbench.extraction.application.use_cases.run_claim_extraction_stage_async import (
    RunClaimExtractionStageAsync,
)
from src.contexts.knowledge_workbench.extraction.infrastructure.postgres.claim_extraction_stage_runtime import (
    ClaimExtractionStagePostgresRuntime,
    make_claim_extraction_stage_postgres_runtime,
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


def test_postgres_runtime_composition_builds_runner_and_progress_reader() -> None:
    runtime = make_claim_extraction_stage_postgres_runtime(FakeConnection())

    assert isinstance(runtime, ClaimExtractionStagePostgresRuntime)
    assert isinstance(runtime.runner, RunClaimExtractionStageAsync)
    assert isinstance(runtime.progress_reader, ClaimExtractionStageProgressReadModel)
