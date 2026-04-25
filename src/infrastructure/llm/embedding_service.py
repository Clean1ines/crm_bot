"""
Embedding generation service using fastembed.
"""

import asyncio
from typing import List
from fastembed import TextEmbedding

from src.infrastructure.logging.logger import get_logger

logger = get_logger(__name__)

_model = None

def _get_model():
    global _model
    if _model is None:
        logger.info("Loading embedding model 'BAAI/bge-small-en-v1.5'")
        _model = TextEmbedding("BAAI/bge-small-en-v1.5")
    return _model

async def embed_text(text: str) -> List[float]:
    logger.debug(f"Generating embedding for text of length {len(text)}")
    loop = asyncio.get_event_loop()
    model = _get_model()
    embedding = await loop.run_in_executor(
        None, 
        lambda: list(model.embed([text]))[0]
    )
    return embedding.tolist()

async def embed_batch(texts: List[str]) -> List[List[float]]:
    if not texts:
        return []
    logger.debug(f"Generating embeddings for batch of {len(texts)} texts")
    loop = asyncio.get_event_loop()
    model = _get_model()
    embeddings = await loop.run_in_executor(
        None,
        lambda: list(model.embed(texts))
    )
    return [emb.tolist() for emb in embeddings]
