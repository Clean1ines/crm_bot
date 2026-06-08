from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.contexts.embedding_runtime.domain.value_objects.embedding_dimensions import (
    EmbeddingDimensions,
)
from src.contexts.embedding_runtime.domain.value_objects.embedding_input_ref import (
    EmbeddingInputRef,
)
from src.contexts.embedding_runtime.domain.value_objects.embedding_model_id import (
    EmbeddingModelId,
)
from src.contexts.embedding_runtime.domain.value_objects.embedding_vector_ref import (
    EmbeddingVectorRef,
)


@dataclass(frozen=True, slots=True)
class EmbeddingVector:
    vector_ref: EmbeddingVectorRef
    input_ref: EmbeddingInputRef
    model_id: EmbeddingModelId
    dimensions: EmbeddingDimensions
    values: tuple[float, ...]
    created_at: datetime

    def __post_init__(self) -> None:
        if len(self.values) != self.dimensions.value:
            raise ValueError("EmbeddingVector.values length must equal dimensions")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("EmbeddingVector.created_at must be timezone-aware")
