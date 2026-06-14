from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class EmbeddingGenerationRequest:
    texts: tuple[str, ...]
    model_id: str
    expected_dimensions: int
    task: str = "retrieval.passage"

    def __post_init__(self) -> None:
        if not self.model_id.strip():
            raise ValueError("EmbeddingGenerationRequest.model_id must be non-empty")
        if self.expected_dimensions < 1:
            raise ValueError(
                "EmbeddingGenerationRequest.expected_dimensions must be positive"
            )
        if not self.task.strip():
            raise ValueError("EmbeddingGenerationRequest.task must be non-empty")

        for index, text in enumerate(self.texts):
            if not text or not text.strip():
                raise ValueError(
                    f"EmbeddingGenerationRequest.texts[{index}] must be non-empty"
                )


@dataclass(frozen=True, slots=True)
class EmbeddingGenerationResult:
    embeddings: tuple[tuple[float, ...], ...]
    model_id: str
    dimensions: int

    def __post_init__(self) -> None:
        if not self.model_id.strip():
            raise ValueError("EmbeddingGenerationResult.model_id must be non-empty")
        if self.dimensions < 1:
            raise ValueError("EmbeddingGenerationResult.dimensions must be positive")

        for vector_index, vector in enumerate(self.embeddings):
            if len(vector) != self.dimensions:
                raise ValueError(
                    "EmbeddingGenerationResult.embeddings"
                    f"[{vector_index}] has unexpected dimensions"
                )
            for item_index, value in enumerate(vector):
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise ValueError(
                        "EmbeddingGenerationResult.embeddings"
                        f"[{vector_index}][{item_index}] must be numeric"
                    )


class EmbeddingGenerationPort(Protocol):
    async def embed(
        self,
        request: EmbeddingGenerationRequest,
    ) -> EmbeddingGenerationResult: ...
