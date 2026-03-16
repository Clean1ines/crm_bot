import asyncio
from typing import List
from fastembed import TextEmbedding

_model = None

def _get_model():
    global _model
    if _model is None:
        # Используем мультиязычную модель (поддерживает русский)
        _model = TextEmbedding("BAAI/bge-small-en-v1.5")
    return _model

async def embed_text(text: str) -> List[float]:
    """
    Генерирует эмбеддинг для текста.
    """
    loop = asyncio.get_event_loop()
    model = _get_model()
    # model.embed возвращает генератор, берём первый элемент
    embedding = await loop.run_in_executor(
        None, 
        lambda: list(model.embed([text]))[0]
    )
    return embedding.tolist()
