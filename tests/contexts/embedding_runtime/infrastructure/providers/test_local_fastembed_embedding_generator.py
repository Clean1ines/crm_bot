from __future__ import annotations

import asyncio
from collections.abc import Iterable
from pathlib import Path

import pytest

from src.application.errors import PermanentEmbeddingProviderError
from src.contexts.embedding_runtime.application.ports.embedding_generation_port import (
    EmbeddingGenerationRequest,
)
from src.contexts.embedding_runtime.infrastructure.providers.local_fastembed_embedding_generator import (
    FastEmbedEmbeddingModel,
    LocalFastEmbedEmbeddingGenerator,
)


ROOT = Path(__file__).resolve().parents[5]
PROVIDER_FILE = (
    ROOT
    / "src"
    / "contexts"
    / "embedding_runtime"
    / "infrastructure"
    / "providers"
    / "local_fastembed_embedding_generator.py"
)


class _FakeVector:
    def __init__(self, values: tuple[float, ...]) -> None:
        self._values = values

    def tolist(self) -> list[float]:
        return list(self._values)


class _FakeModel:
    def __init__(self, vectors: tuple[tuple[float, ...], ...]) -> None:
        self._vectors = vectors
        self.documents: list[str] = []

    def embed(self, documents: list[str]) -> Iterable[_FakeVector]:
        self.documents.extend(documents)
        return [_FakeVector(vector) for vector in self._vectors[: len(documents)]]


class _FakeModelFactory:
    def __init__(self, model: _FakeModel) -> None:
        self._model = model
        self.calls: list[tuple[str, int]] = []

    def __call__(self, model_id: str, threads: int) -> FastEmbedEmbeddingModel:
        self.calls.append((model_id, threads))
        return self._model


def _request(*texts: str) -> EmbeddingGenerationRequest:
    return EmbeddingGenerationRequest(
        texts=tuple(texts),
        model_id="fake-model",
        expected_dimensions=3,
        task="retrieval.passage",
    )


def test_local_provider_returns_vectors_with_expected_dimensions() -> None:
    model = _FakeModel(((1.0, 2.0, 3.0), (4.0, 5.0, 6.0)))
    factory = _FakeModelFactory(model)
    generator = LocalFastEmbedEmbeddingGenerator(
        model_id="fake-model",
        dimensions=3,
        threads=2,
        executor_max_workers=1,
        model_factory=factory,
    )

    async def run() -> None:
        result = await generator.embed(_request("first", "second"))

        assert result.embeddings == ((1.0, 2.0, 3.0), (4.0, 5.0, 6.0))
        assert result.model_id == "fake-model"
        assert result.dimensions == 3

    try:
        asyncio.run(run())
    finally:
        generator.close()

    assert factory.calls == [("fake-model", 2)]
    assert model.documents == ["first", "second"]


def test_local_provider_preserves_embedding_order() -> None:
    model = _FakeModel(((10.0, 0.0, 0.0), (20.0, 0.0, 0.0), (30.0, 0.0, 0.0)))
    generator = LocalFastEmbedEmbeddingGenerator(
        model_id="fake-model",
        dimensions=3,
        model_factory=_FakeModelFactory(model),
    )

    async def run() -> None:
        result = await generator.embed(_request("a", "b", "c"))

        assert tuple(vector[0] for vector in result.embeddings) == (
            10.0,
            20.0,
            30.0,
        )

    try:
        asyncio.run(run())
    finally:
        generator.close()


def test_local_provider_handles_empty_texts_without_loading_model() -> None:
    model = _FakeModel(())
    factory = _FakeModelFactory(model)
    generator = LocalFastEmbedEmbeddingGenerator(
        model_id="fake-model",
        dimensions=3,
        model_factory=factory,
    )

    async def run() -> None:
        result = await generator.embed(_request())

        assert result.embeddings == ()

    asyncio.run(run())

    assert factory.calls == []
    assert model.documents == []


def test_local_provider_rejects_dimension_mismatch() -> None:
    model = _FakeModel(((1.0, 2.0),))
    generator = LocalFastEmbedEmbeddingGenerator(
        model_id="fake-model",
        dimensions=3,
        model_factory=_FakeModelFactory(model),
    )

    async def run() -> None:
        with pytest.raises(
            PermanentEmbeddingProviderError,
            match="unexpected vector dimensions",
        ):
            await generator.embed(_request("bad-dimensions"))

    try:
        asyncio.run(run())
    finally:
        generator.close()


def test_local_provider_rejects_request_model_mismatch() -> None:
    generator = LocalFastEmbedEmbeddingGenerator(
        model_id="fake-model",
        dimensions=3,
        model_factory=_FakeModelFactory(_FakeModel(())),
    )
    request = EmbeddingGenerationRequest(
        texts=("text",),
        model_id="other-model",
        expected_dimensions=3,
    )

    async def run() -> None:
        with pytest.raises(PermanentEmbeddingProviderError, match="model"):
            await generator.embed(request)

    asyncio.run(run())


def test_fastembed_import_is_lazy_inside_provider_function() -> None:
    source = PROVIDER_FILE.read_text(encoding="utf-8")
    lines = source.splitlines()

    import_lines = [
        line for line in lines if "fastembed" in line or "TextEmbedding" in line
    ]

    assert import_lines == [
        "    from fastembed import TextEmbedding",
        "        TextEmbedding(model_name=model_id, threads=threads),",
    ]
