from __future__ import annotations

import inspect

from src.contexts.knowledge_workbench.extraction.application.read_models.claim_extraction_stage_progress_async import (
    AsyncClaimExtractionStageProgressReadModel,
)
from src.contexts.knowledge_workbench.extraction.infrastructure.postgres.claim_extraction_stage_progress_composition import (
    make_postgres_claim_extraction_stage_progress_reader,
)
from src.contexts.knowledge_workbench.extraction.infrastructure.postgres.postgres_claim_extraction_stage_progress_query import (
    PostgresClaimExtractionStageProgressQuery,
)


class FakeConnection:
    async def fetch(self, query: str, *args: object) -> list[object]:
        return []

    async def fetchval(self, query: str, *args: object) -> object:
        return 0


def test_postgres_claim_extraction_stage_progress_composition_builds_async_read_model() -> None:
    reader = make_postgres_claim_extraction_stage_progress_reader(FakeConnection())

    assert isinstance(reader, AsyncClaimExtractionStageProgressReadModel)
    assert isinstance(reader._query_port, PostgresClaimExtractionStageProgressQuery)
    assert inspect.iscoroutinefunction(reader.execute)
