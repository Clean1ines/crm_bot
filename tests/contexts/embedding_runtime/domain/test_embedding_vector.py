from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.contexts.embedding_runtime.domain.entities.embedding_vector import (
    EmbeddingVector,
)
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


def _now() -> datetime:
    return datetime(2026, 6, 8, 12, 0, tzinfo=timezone.utc)


def _vector(
    *,
    dimensions: EmbeddingDimensions = EmbeddingDimensions(3),
    values: tuple[float, ...] = (0.1, 0.2, 0.3),
    created_at: datetime | None = None,
) -> EmbeddingVector:
    return EmbeddingVector(
        vector_ref=EmbeddingVectorRef("embedding-vector-1"),
        input_ref=EmbeddingInputRef("embedding-input-1"),
        model_id=EmbeddingModelId("text-embedding-model"),
        dimensions=dimensions,
        values=values,
        created_at=created_at or _now(),
    )


def test_embedding_vector_is_valid_when_values_match_dimensions() -> None:
    vector = _vector()

    assert vector.vector_ref.value == "embedding-vector-1"
    assert vector.input_ref.value == "embedding-input-1"
    assert vector.model_id.value == "text-embedding-model"
    assert vector.dimensions.value == 3
    assert vector.values == (0.1, 0.2, 0.3)


def test_embedding_dimensions_must_be_positive() -> None:
    with pytest.raises(ValueError):
        EmbeddingDimensions(0)

    with pytest.raises(ValueError):
        EmbeddingDimensions(-1)


def test_embedding_vector_rejects_values_length_mismatch() -> None:
    with pytest.raises(ValueError):
        _vector(
            dimensions=EmbeddingDimensions(3),
            values=(0.1, 0.2),
        )


def test_embedding_vector_requires_timezone_aware_created_at() -> None:
    with pytest.raises(ValueError):
        _vector(created_at=datetime(2026, 6, 8, 12, 0))


def test_embedding_refs_and_model_id_must_be_non_empty() -> None:
    with pytest.raises(ValueError):
        EmbeddingVectorRef(" ")

    with pytest.raises(ValueError):
        EmbeddingInputRef(" ")

    with pytest.raises(ValueError):
        EmbeddingModelId(" ")


def test_embedding_vector_values_are_tuple() -> None:
    vector = _vector(values=(1.0, 2.0, 3.0))

    assert isinstance(vector.values, tuple)
