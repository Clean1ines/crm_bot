from __future__ import annotations

from dataclasses import dataclass

from src.application.errors import (
    EmbeddingProviderDisabledError,
    PermanentEmbeddingProviderError,
)
from src.contexts.embedding_runtime.application.ports.embedding_generation_port import (
    EmbeddingGenerationPort,
    EmbeddingGenerationRequest,
    EmbeddingGenerationResult,
)
from src.contexts.embedding_runtime.infrastructure.config.embedding_runtime_settings import (
    EmbeddingRuntimeSettings,
    load_embedding_runtime_settings,
)
from src.contexts.embedding_runtime.infrastructure.providers.local_fastembed_embedding_generator import (
    LocalFastEmbedEmbeddingGenerator,
)


@dataclass(frozen=True, slots=True)
class DisabledEmbeddingGenerationPort:
    provider: str = "disabled"

    async def embed(
        self,
        request: EmbeddingGenerationRequest,
    ) -> EmbeddingGenerationResult:
        raise EmbeddingProviderDisabledError(
            "Embedding provider is disabled",
            provider=self.provider,
            task=request.task,
            model=request.model_id,
        )


def make_embedding_generation_port(
    runtime_settings: EmbeddingRuntimeSettings | None = None,
) -> EmbeddingGenerationPort:
    resolved_settings = runtime_settings or load_embedding_runtime_settings()

    if resolved_settings.provider == "local":
        return LocalFastEmbedEmbeddingGenerator(
            model_id=resolved_settings.local_model,
            dimensions=resolved_settings.vector_dimensions,
            threads=resolved_settings.local_threads,
            executor_max_workers=resolved_settings.executor_max_workers,
        )

    if resolved_settings.provider == "disabled":
        return DisabledEmbeddingGenerationPort()

    raise PermanentEmbeddingProviderError(
        "Embedding runtime provider is not supported",
        provider=resolved_settings.provider,
        task="config",
        model=resolved_settings.local_model,
    )


__all__ = [
    "DisabledEmbeddingGenerationPort",
    "make_embedding_generation_port",
]
