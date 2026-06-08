from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from src.contexts.llm_runtime.application.ports.llm_provider_input import (
    LlmProviderInput,
)
from src.contexts.llm_runtime.domain.entities.llm_task import LlmTask
from src.contexts.llm_runtime.domain.value_objects.llm_error_kind import LlmErrorKind
from src.contexts.llm_runtime.domain.value_objects.llm_route import LlmRoute
from src.contexts.llm_runtime.domain.value_objects.token_usage import TokenUsage


@dataclass(frozen=True, slots=True)
class LlmProviderSuccess:
    raw_text: str
    usage: TokenUsage | None = None


@dataclass(frozen=True, slots=True)
class LlmProviderFailure:
    error_kind: LlmErrorKind
    wait_until: datetime | None = None

    def __post_init__(self) -> None:
        if self.wait_until is not None:
            if self.wait_until.tzinfo is None or self.wait_until.utcoffset() is None:
                raise ValueError("wait_until must be timezone-aware")


LlmProviderResult = LlmProviderSuccess | LlmProviderFailure


class LlmProviderPort(Protocol):
    def invoke(
        self,
        *,
        task: LlmTask,
        route: LlmRoute,
        provider_input: LlmProviderInput,
    ) -> LlmProviderResult:
        """Invoke a prepared task through a selected route."""
