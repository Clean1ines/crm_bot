from __future__ import annotations

from typing import Protocol


class TextCompletionPort(Protocol):
    async def complete(
        self,
        prompt: str,
        *,
        target_language: str = "ru",
        max_tokens: int = 700,
        temperature: float = 0.2,
    ) -> str: ...
