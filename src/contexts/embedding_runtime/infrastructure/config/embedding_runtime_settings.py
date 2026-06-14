from __future__ import annotations

from dataclasses import dataclass

from src.infrastructure.config.settings import settings


SUPPORTED_EMBEDDING_RUNTIME_PROVIDERS = ("local", "disabled")


@dataclass(frozen=True, slots=True)
class EmbeddingRuntimeSettings:
    provider: str
    local_model: str
    vector_dimensions: int
    local_threads: int
    executor_max_workers: int

    def __post_init__(self) -> None:
        if not self.provider.strip():
            raise ValueError("EmbeddingRuntimeSettings.provider must be non-empty")
        if not self.local_model.strip():
            raise ValueError("EmbeddingRuntimeSettings.local_model must be non-empty")
        if self.vector_dimensions < 1:
            raise ValueError(
                "EmbeddingRuntimeSettings.vector_dimensions must be positive"
            )
        if self.local_threads < 1:
            raise ValueError("EmbeddingRuntimeSettings.local_threads must be positive")
        if self.executor_max_workers < 1:
            raise ValueError(
                "EmbeddingRuntimeSettings.executor_max_workers must be positive"
            )


def load_embedding_runtime_settings() -> EmbeddingRuntimeSettings:
    return EmbeddingRuntimeSettings(
        provider=str(settings.EMBEDDING_PROVIDER).strip().lower(),
        local_model=(
            settings.EMBEDDING_LOCAL_MODEL.strip()
            or "sentence-transformers/all-MiniLM-L6-v2"
        ),
        vector_dimensions=int(settings.EMBEDDING_VECTOR_DIMENSIONS),
        local_threads=int(settings.EMBEDDING_LOCAL_THREADS),
        executor_max_workers=int(settings.EMBEDDING_EXECUTOR_MAX_WORKERS),
    )


__all__ = [
    "EmbeddingRuntimeSettings",
    "SUPPORTED_EMBEDDING_RUNTIME_PROVIDERS",
    "load_embedding_runtime_settings",
]
