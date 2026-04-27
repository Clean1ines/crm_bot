"""
Embedding generation service using fastembed.

fastembed is intentionally imported lazily inside _create_model().
Plain application imports, webhook imports, and FastAPI app assembly must not
load ONNX / fastembed runtime dependencies until embeddings are actually needed.
"""

import asyncio
from collections.abc import Iterable
from typing import Protocol, cast

from src.infrastructure.logging.logger import get_logger

logger = get_logger(__name__)

EMBEDDING_MODEL_NAME = "BAAI/bge-small-en-v1.5"


class EmbeddingVector(Protocol):
    def tolist(self) -> list[float]: ...


class EmbeddingModel(Protocol):
    def embed(self, documents: list[str]) -> Iterable[EmbeddingVector]: ...


_model: EmbeddingModel | None = None


def _create_model() -> EmbeddingModel:
    """
    Create the concrete fastembed model only when embeddings are requested.

    Importing TextEmbedding here keeps `import src.interfaces.http.app` free from
    fastembed and its heavy transitive dependencies.
    """
    from fastembed import TextEmbedding

    return cast(EmbeddingModel, TextEmbedding(EMBEDDING_MODEL_NAME))


def _get_model() -> EmbeddingModel:
    global _model

    if _model is None:
        logger.info("Loading embedding model '%s'", EMBEDDING_MODEL_NAME)
        _model = _create_model()

    return _model


def _embed_one_sync(model: EmbeddingModel, text: str) -> list[float]:
    vectors = list(model.embed([text]))
    if not vectors:
        return []

    return vectors[0].tolist()


def _embed_batch_sync(model: EmbeddingModel, texts: list[str]) -> list[list[float]]:
    return [vector.tolist() for vector in model.embed(texts)]


async def embed_text(text: str) -> list[float]:
    logger.debug("Generating embedding for text of length %s", len(text))

    loop = asyncio.get_running_loop()
    model = _get_model()

    return await loop.run_in_executor(None, _embed_one_sync, model, text)


async def embed_batch(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []

    logger.debug("Generating embeddings for batch of %s texts", len(texts))

    loop = asyncio.get_running_loop()
    model = _get_model()

    return await loop.run_in_executor(None, _embed_batch_sync, model, texts)
