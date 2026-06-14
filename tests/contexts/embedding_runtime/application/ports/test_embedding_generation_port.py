from __future__ import annotations

import pytest

from src.contexts.embedding_runtime.application.ports.embedding_generation_port import (
    EmbeddingGenerationRequest,
    EmbeddingGenerationResult,
)


def test_request_allows_empty_texts_for_explicit_empty_batch() -> None:
    request = EmbeddingGenerationRequest(
        texts=(),
        model_id="test-model",
        expected_dimensions=3,
    )

    assert request.texts == ()


def test_request_rejects_blank_text() -> None:
    with pytest.raises(ValueError, match=r"texts\[0\]"):
        EmbeddingGenerationRequest(
            texts=(" ",),
            model_id="test-model",
            expected_dimensions=3,
        )


def test_result_accepts_numeric_vectors_with_expected_dimensions() -> None:
    result = EmbeddingGenerationResult(
        embeddings=((1.0, 2, 3.5),),
        model_id="test-model",
        dimensions=3,
    )

    assert result.embeddings == ((1.0, 2, 3.5),)


def test_result_rejects_dimension_mismatch() -> None:
    with pytest.raises(ValueError, match="unexpected dimensions"):
        EmbeddingGenerationResult(
            embeddings=((1.0, 2.0),),
            model_id="test-model",
            dimensions=3,
        )


def test_result_rejects_non_numeric_vector_values() -> None:
    with pytest.raises(ValueError, match="must be numeric"):
        EmbeddingGenerationResult(
            embeddings=((1.0, True, 3.0),),
            model_id="test-model",
            dimensions=3,
        )
