from __future__ import annotations

from src.application.services.faq_workbench_local_claim_retrieval_surface_indexing_service import (
    LocalClaimRetrievalSurfaceEmbeddingResult,
)
from src.infrastructure.llm.embedding_service import embed_batch


class WorkbenchLocalClaimEmbeddingAdapter:
    async def embed_passages(
        self,
        texts: list[str],
    ) -> LocalClaimRetrievalSurfaceEmbeddingResult:
        result = await embed_batch(texts)
        return LocalClaimRetrievalSurfaceEmbeddingResult(
            embeddings=[list(vector) for vector in result.embeddings],
        )


__all__ = ["WorkbenchLocalClaimEmbeddingAdapter"]
