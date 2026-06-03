from __future__ import annotations

from typing import Protocol

from src.domain.project_plane.llm_routing import (
    LlmJsonInvocationRequest,
    LlmJsonInvocationResult,
)


class LlmJsonInvocationPort(Protocol):
    async def invoke_json(
        self,
        request: LlmJsonInvocationRequest,
    ) -> LlmJsonInvocationResult: ...
