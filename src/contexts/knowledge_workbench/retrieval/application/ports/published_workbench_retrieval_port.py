from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from src.contexts.knowledge_workbench.retrieval.application.models.published_workbench_retrieval import (
    PublishedWorkbenchRetrievalResult,
)


class PublishedWorkbenchRetrievalPort(Protocol):
    async def search(
        self,
        *,
        project_id: str,
        query_text: str,
        query_embedding: Sequence[float],
        embedding_model_id: str,
        dimensions: int,
        limit: int,
    ) -> tuple[PublishedWorkbenchRetrievalResult, ...]: ...
