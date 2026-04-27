"""Query expansion adapters for RAG.

The default expander is deterministic and never calls external services.
Groq expansion is optional and injected explicitly.
"""

from __future__ import annotations

import json
import re

from groq import APIConnectionError, APIError, APITimeoutError, AsyncGroq, RateLimitError

from src.infrastructure.config.settings import settings
from src.infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


class NoOpQueryExpander:
    """Safe default query expander used when no LLM adapter is injected."""

    async def expand(self, query: str, *, max_expansions: int) -> list[str]:
        return []


class GroqQueryExpander:
    """Groq-backed query expansion adapter.

    This adapter is isolated from RAGService so tests never need real Groq.
    """

    def __init__(
        self,
        *,
        client: object | None = None,
        model: str = "llama-3.3-70b-versatile",
    ) -> None:
        self._client = client or AsyncGroq(api_key=settings.GROQ_API_KEY)
        self._model = model

    async def expand(self, query: str, *, max_expansions: int) -> list[str]:
        prompt = f"""
Перефразируй запрос {max_expansions} разными способами.

Запрос: "{query}"

Верни ТОЛЬКО JSON массив строк:
["...", "...", "..."]
"""

        try:
            resp = await self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=160,
            )
            content = resp.choices[0].message.content or ""
            return self._extract_string_array(content)[:max_expansions]

        except (
            APIConnectionError,
            APIError,
            APITimeoutError,
            RateLimitError,
            json.JSONDecodeError,
            AttributeError,
            IndexError,
            TypeError,
            ValueError,
        ) as exc:
            logger.warning(
                "RAG query expansion failed; falling back to original query",
                extra={"error": str(exc)[:200]},
            )
            return []

    @staticmethod
    def _extract_string_array(text: str) -> list[str]:
        if not text:
            return []

        match = re.search(r"\[.*\]", text, re.DOTALL)
        if not match:
            return []

        data = json.loads(match.group(0))
        if not isinstance(data, list):
            return []

        return [item.strip() for item in data if isinstance(item, str) and item.strip()]
