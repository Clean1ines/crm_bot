"""
Embedding generation service using fastembed.
Provides a function to generate vector embeddings for text.
"""

import asyncio
from typing import List
from fastembed import TextEmbedding

from src.core.logging import get_logger

logger = get_logger(__name__)

_model = None

def _get_model():
    """Lazy-load the embedding model."""
    global _model
    if _model is None:
        logger.info("Loading embedding model 'BAAI/bge-small-en-v1.5'")
        _model = TextEmbedding("BAAI/bge-small-en-v1.5")
    return _model

async def embed_text(text: str) -> List[float]:
    """
    Generate an embedding vector for the given text.

    Args:
        text: Input text string.

    Returns:
        List of floats representing the embedding.
    """
    logger.debug(f"Generating embedding for text of length {len(text)}")
    loop = asyncio.get_event_loop()
    model = _get_model()
    # model.embed returns a generator, take the first element
    embedding = await loop.run_in_executor(
        None, 
        lambda: list(model.embed([text]))[0]
    )
    return embedding.tolist()
