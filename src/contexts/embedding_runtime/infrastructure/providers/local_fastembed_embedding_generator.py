from __future__ import annotations

import asyncio
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Protocol, cast

from src.application.errors import PermanentEmbeddingProviderError
from src.contexts.embedding_runtime.application.ports.embedding_generation_port import (
    EmbeddingGenerationRequest,
    EmbeddingGenerationResult,
)


class FastEmbedVector(Protocol):
    def tolist(self) -> list[float]: ...


class FastEmbedEmbeddingModel(Protocol):
    def embed(self, documents: list[str]) -> Iterable[FastEmbedVector]: ...


class FastEmbedModelFactory(Protocol):
    def __call__(
        self,
        model_id: str,
        threads: int,
    ) -> FastEmbedEmbeddingModel: ...


def _default_model_factory(
    model_id: str,
    threads: int,
) -> FastEmbedEmbeddingModel:
    from fastembed import TextEmbedding

    return cast(
        FastEmbedEmbeddingModel,
        TextEmbedding(model_name=model_id, threads=threads),
    )


@dataclass(slots=True)
class LocalFastEmbedEmbeddingGenerator:
    model_id: str
    dimensions: int
    threads: int = 1
    executor_max_workers: int = 1
    model_factory: FastEmbedModelFactory = field(
        default=_default_model_factory,
        repr=False,
    )
    _model: FastEmbedEmbeddingModel | None = field(
        default=None,
        init=False,
        repr=False,
    )
    _model_init_lock: asyncio.Lock | None = field(
        default=None,
        init=False,
        repr=False,
    )
    _executor: ThreadPoolExecutor | None = field(
        default=None,
        init=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        if not self.model_id.strip():
            raise ValueError("LocalFastEmbedEmbeddingGenerator.model_id is required")
        if self.dimensions < 1:
            raise ValueError(
                "LocalFastEmbedEmbeddingGenerator.dimensions must be positive"
            )
        if self.threads < 1:
            raise ValueError(
                "LocalFastEmbedEmbeddingGenerator.threads must be positive"
            )
        if self.executor_max_workers < 1:
            raise ValueError(
                "LocalFastEmbedEmbeddingGenerator.executor_max_workers must be positive"
            )

    async def embed(
        self,
        request: EmbeddingGenerationRequest,
    ) -> EmbeddingGenerationResult:
        self._validate_request_matches_provider(request)

        if not request.texts:
            return EmbeddingGenerationResult(
                embeddings=(),
                model_id=self.model_id,
                dimensions=self.dimensions,
            )

        loop = asyncio.get_running_loop()
        model = await self._get_model()
        vectors = await loop.run_in_executor(
            self._get_executor(),
            self._embed_batch_sync,
            model,
            list(request.texts),
            request.task,
            request.expected_dimensions,
        )

        if len(vectors) != len(request.texts):
            raise PermanentEmbeddingProviderError(
                "Embedding provider returned incomplete response payload",
                provider="local",
                task=request.task,
                model=self.model_id,
            )

        return EmbeddingGenerationResult(
            embeddings=vectors,
            model_id=self.model_id,
            dimensions=self.dimensions,
        )

    def close(self) -> None:
        if self._executor is not None:
            self._executor.shutdown(wait=True)
            self._executor = None

    def _validate_request_matches_provider(
        self,
        request: EmbeddingGenerationRequest,
    ) -> None:
        if request.model_id != self.model_id:
            raise PermanentEmbeddingProviderError(
                "Embedding request model does not match local provider configuration",
                provider="local",
                task=request.task,
                model=request.model_id,
            )

        if request.expected_dimensions != self.dimensions:
            raise PermanentEmbeddingProviderError(
                "Embedding request dimensions do not match local provider configuration",
                provider="local",
                task=request.task,
                model=self.model_id,
            )

    def _get_executor(self) -> ThreadPoolExecutor:
        if self._executor is None:
            self._executor = ThreadPoolExecutor(
                max_workers=self.executor_max_workers,
                thread_name_prefix="embedding-runtime",
            )
        return self._executor

    def _get_model_init_lock(self) -> asyncio.Lock:
        if self._model_init_lock is None:
            self._model_init_lock = asyncio.Lock()
        return self._model_init_lock

    async def _get_model(self) -> FastEmbedEmbeddingModel:
        if self._model is not None:
            return self._model

        async with self._get_model_init_lock():
            if self._model is None:
                loop = asyncio.get_running_loop()
                self._model = await loop.run_in_executor(
                    self._get_executor(),
                    self.model_factory,
                    self.model_id,
                    self.threads,
                )

        if self._model is None:
            raise RuntimeError("Embedding model initialization returned no model")
        return self._model

    def _embed_batch_sync(
        self,
        model: FastEmbedEmbeddingModel,
        texts: list[str],
        task: str,
        expected_dimensions: int,
    ) -> tuple[tuple[float, ...], ...]:
        return tuple(
            self._ensure_numeric_vector(
                vector.tolist(),
                task=task,
                expected_dimensions=expected_dimensions,
            )
            for vector in model.embed(texts)
        )

    def _ensure_numeric_vector(
        self,
        values: object,
        *,
        task: str,
        expected_dimensions: int,
    ) -> tuple[float, ...]:
        if not isinstance(values, list):
            raise PermanentEmbeddingProviderError(
                "Embedding provider returned invalid vector payload",
                provider="local",
                task=task,
                model=self.model_id,
            )

        vector: list[float] = []
        for value in values:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise PermanentEmbeddingProviderError(
                    "Embedding provider returned invalid vector payload",
                    provider="local",
                    task=task,
                    model=self.model_id,
                )
            vector.append(float(value))

        if len(vector) != expected_dimensions:
            raise PermanentEmbeddingProviderError(
                "Embedding provider returned unexpected vector dimensions",
                provider="local",
                task=task,
                model=self.model_id,
            )

        return tuple(vector)


__all__ = [
    "FastEmbedEmbeddingModel",
    "FastEmbedModelFactory",
    "FastEmbedVector",
    "LocalFastEmbedEmbeddingGenerator",
]
