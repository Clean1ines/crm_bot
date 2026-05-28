from __future__ import annotations

from typing import cast

from groq import AsyncGroq

from src.infrastructure.llm.groq_model_router import (
    GroqAllFallbacksExhaustedError,
    GroqClient,
    GroqModelRouter,
    GroqRouteResult,
    GroqRouterError,
    route_error_metrics,
)
from src.infrastructure.llm.knowledge_surface_compiler import STRICT_JSON_SYSTEM_MESSAGE
from src.infrastructure.llm.knowledge_surface_quality_gated_compiler import (
    GroqQualityGatedKnowledgeSurfaceCompiler,
)


class GroqRoutedKnowledgeSurfaceCompiler(GroqQualityGatedKnowledgeSurfaceCompiler):
    """FAQ surface compiler adapter backed by GroqModelRouter."""

    def __init__(
        self,
        *,
        client: AsyncGroq | None = None,
        model: str | None = None,
        max_source_units: int = 24,
        max_unit_chars: int = 12000,
        model_router: GroqModelRouter | None = None,
    ) -> None:
        super().__init__(
            client=client,
            model=model,
            max_source_units=max_source_units,
            max_unit_chars=max_unit_chars,
        )
        router_client = cast(GroqClient, client) if client is not None else None
        self._model_router = model_router or GroqModelRouter(client=router_client)
        self._last_route_metrics = {}

    async def _request_json_with_large_request_fallback(
        self,
        *,
        prompt: str,
        max_tokens: int,
    ) -> tuple[str, str]:
        current_calls = int(getattr(self, "_llm_call_count", 0))
        call_limit = self._model_router.policy.max_total_llm_calls_per_document
        if current_calls >= call_limit:
            raise GroqAllFallbacksExhaustedError(
                "FAQ surface compiler exceeded document LLM call budget",
                error_type="all_fallbacks_exhausted",
            )
        try:
            result = await self._model_router.request_json(
                system_message=STRICT_JSON_SYSTEM_MESSAGE,
                prompt=prompt,
                max_tokens=max_tokens,
                chain_name="primary",
            )
        except GroqRouterError as exc:
            self._llm_error_count = int(getattr(self, "_llm_error_count", 0)) + max(
                1,
                len(exc.attempts),
            )
            self._last_route_metrics = route_error_metrics(exc)
            raise
        self._record_route_result(result)
        return result.model, result.content

    def _record_route_result(self, result: GroqRouteResult) -> None:
        self._llm_error_count = int(getattr(self, "_llm_error_count", 0)) + max(
            0,
            result.attempt_count - 1,
        )
        self._record_usage(
            model=result.model,
            tokens_input=result.tokens_input,
            tokens_output=result.tokens_output,
            tokens_total=result.tokens_total,
            fallback=result.chain_name != "primary" or result.attempt_count > 1,
        )
        self._last_route_metrics = result.to_metrics()
