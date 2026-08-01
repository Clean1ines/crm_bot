from __future__ import annotations

from typing import Protocol


class PromptTemplateNotFoundError(RuntimeError):
    pass


class PromptTemplateLoaderPort(Protocol):
    def load(self, stem: str, *, language: str | None = None) -> str: ...

    def load_filename(self, filename: str) -> str: ...
