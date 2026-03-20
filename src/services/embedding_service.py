"""
Embedding generation service using fastembed with multilingual model.
"""

import asyncio
from typing import List
from fastembed import TextEmbedding

from src.core.logging import get_logger

logger = get_logger(__name__)

_model = None

# Default model for multilingual embeddings (supports Russian)
DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


def _get_model():
    global _model
    if _model is None:
        logger.info(f"Loading embedding model '{DEFAULT_MODEL}'")
        _model = TextEmbedding(DEFAULT_MODEL)
    return _model


def _format_text(text: str, is_query: bool = False) -> str:
    """
    Format text according to E5 model requirements.
    For queries: prefix "query: "
    For passages/documents: prefix "passage: "
    
    This is NOT needed for sentence-transformers models, but we keep it for consistency.
    """
    # For sentence-transformers, no prefix is needed.
    # We'll keep the original text without modifications.
    return text


async def embed_text(text: str, is_query: bool = False) -> List[float]:
    """
    Generate embedding for a single text.
    
    Args:
        text: Text to embed.
        is_query: Whether this is a query (True) or document passage (False).
    
    Returns:
        List of floats (embedding vector).
    """
    formatted = _format_text(text, is_query)
    logger.debug(f"Generating embedding for text of length {len(formatted)}")
    loop = asyncio.get_event_loop()
    model = _get_model()
    embedding = await loop.run_in_executor(
        None,
        lambda: list(model.embed([formatted]))[0]
    )
    return embedding.tolist()


async def embed_batch(texts: List[str], is_query: bool = False) -> List[List[float]]:
    """
    Generate embeddings for a batch of texts.
    
    Args:
        texts: List of texts to embed.
        is_query: Whether these are queries (True) or passages (False).
    
    Returns:
        List of embedding vectors.
    """
    if not texts:
        return []
    formatted = [_format_text(t, is_query) for t in texts]
    logger.debug(f"Generating embeddings for batch of {len(formatted)} texts")
    loop = asyncio.get_event_loop()
    model = _get_model()
    embeddings = await loop.run_in_executor(
        None,
        lambda: list(model.embed(formatted))
    )
    return [emb.tolist() for emb in embeddings]
