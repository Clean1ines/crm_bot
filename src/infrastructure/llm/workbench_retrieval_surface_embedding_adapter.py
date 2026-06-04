from __future__ import annotations

from src.application.services.faq_workbench_retrieval_surface_publication_service import (
    WorkbenchRetrievalSurfaceEmbeddingResult,
)
from src.infrastructure.llm.embedding_service import embed_batch


class WorkbenchRetrievalSurfaceEmbeddingAdapter:
    async def embed_passages(
        self,
        texts: list[str],
    ) -> WorkbenchRetrievalSurfaceEmbeddingResult:
        result = await embed_batch(texts)
        return WorkbenchRetrievalSurfaceEmbeddingResult(
            embeddings=[list(vector) for vector in result.embeddings],
        )


__all__ = ["WorkbenchRetrievalSurfaceEmbeddingAdapter"]
