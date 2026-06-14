from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone

from src.application.ai_playground.contracts import AiPlaygroundRunRequest
from src.application.ai_playground.run_ai_playground import (
    AiPlaygroundLlmResult,
    RunAiPlaygroundService,
)
from src.contexts.llm_runtime.application.ports.llm_provider_port import (
    LlmProviderFailure,
    LlmProviderSuccess,
)
from src.contexts.llm_runtime.domain.entities.model_profile import ModelProfile
from src.contexts.llm_runtime.domain.entities.provider_account import ProviderAccount
from src.contexts.llm_runtime.domain.value_objects.llm_route import LlmRoute
from src.contexts.llm_runtime.domain.value_objects.model_id import ModelId
from src.contexts.llm_runtime.domain.value_objects.reasoning_effort import (
    ReasoningEffort,
)
from src.contexts.llm_runtime.infrastructure.config.llm_runtime_provider_composition import (
    LlmRuntimeProviderCompositionFactory,
)
from src.contexts.llm_runtime.infrastructure.config.llm_runtime_settings import (
    LlmRuntimeSettings,
)
from src.contexts.llm_runtime.infrastructure.providers.groq.groq_chat_request_builder import (
    GroqChatMessage,
    GroqChatMessageRole,
    GroqChatRequestBuilder,
    GroqChatRequestOptions,
    GroqResponseFormatKind,
)
from src.contexts.llm_runtime.infrastructure.providers.groq.groq_provider_adapter import (
    GroqProviderAdapter,
)
from src.contexts.llm_runtime.infrastructure.providers.groq.groq_provider_response_mapper import (
    GroqProviderHttpResponse,
    GroqProviderResponseMapper,
)


@dataclass(slots=True)
class GroqAiPlaygroundAdapter:
    provider: GroqProviderAdapter
    model_profiles: tuple[ModelProfile, ...]
    provider_accounts: tuple[ProviderAccount, ...]
    request_builder: GroqChatRequestBuilder = field(
        default_factory=GroqChatRequestBuilder
    )
    response_mapper: GroqProviderResponseMapper = field(
        default_factory=GroqProviderResponseMapper
    )

    @classmethod
    def create_default(cls) -> "GroqAiPlaygroundAdapter":
        settings = LlmRuntimeSettings.from_env_mapping(os.environ)
        components = LlmRuntimeProviderCompositionFactory(settings=settings).build()
        return cls(
            provider=components.groq.provider,
            model_profiles=components.groq.model_profiles,
            provider_accounts=components.groq.provider_accounts,
        )

    async def run(
        self,
        request: AiPlaygroundRunRequest,
    ) -> AiPlaygroundLlmResult:
        model_profile = self._model_profile(request.model)
        account = self._primary_account(model_profile)
        route = LlmRoute(
            provider_id=model_profile.provider_id,
            model_id=model_profile.model_id,
            account_ref=account.account_ref,
        )
        chat_request = self.request_builder.build(
            route=route,
            model_profile=model_profile,
            messages=(
                GroqChatMessage(
                    role=GroqChatMessageRole.SYSTEM,
                    content=request.system_prompt,
                ),
                GroqChatMessage(
                    role=GroqChatMessageRole.USER,
                    content=request.user_input,
                ),
            ),
            options=self._request_options(request),
        )
        payload = dict(chat_request.payload)
        if request.reasoning_format is not None:
            payload["reasoning_format"] = request.reasoning_format

        transport_response = await asyncio.to_thread(
            self.provider.transport.post_chat_completions,
            payload=payload,
        )
        mapped = self.response_mapper.map_response(
            response=GroqProviderHttpResponse(
                status_code=transport_response.status_code,
                headers=transport_response.headers,
                body=transport_response.body,
            ),
            observed_at=datetime.now(timezone.utc),
        )
        provider_result = mapped.provider_result

        if isinstance(provider_result, LlmProviderFailure):
            return AiPlaygroundLlmResult(
                raw_text="",
                model=request.model,
                provider="groq",
                status=f"failed:{provider_result.error_kind.value}",
            )

        if not isinstance(provider_result, LlmProviderSuccess):
            raise RuntimeError("Unsupported LLM provider result")

        usage = provider_result.usage
        return AiPlaygroundLlmResult(
            raw_text=provider_result.raw_text,
            model=request.model,
            provider="groq",
            status="completed",
            prompt_tokens=usage.input_tokens if usage is not None else None,
            completion_tokens=usage.output_tokens if usage is not None else None,
            total_tokens=usage.total_tokens if usage is not None else None,
        )

    def _model_profile(self, model_id: str) -> ModelProfile:
        requested_model_id = ModelId(model_id)
        for profile in self.model_profiles:
            if profile.model_id == requested_model_id:
                return profile
        raise ValueError(f"AI Playground model is not available: {model_id}")

    def _primary_account(self, model_profile: ModelProfile) -> ProviderAccount:
        for account in self.provider_accounts:
            if account.provider_id == model_profile.provider_id and account.enabled:
                return account
        raise ValueError("No enabled Groq provider account is configured")

    def _request_options(
        self,
        request: AiPlaygroundRunRequest,
    ) -> GroqChatRequestOptions:
        response_format = (
            GroqResponseFormatKind.JSON_OBJECT
            if request.response_format == "json"
            else GroqResponseFormatKind.TEXT
        )
        reasoning_effort = (
            ReasoningEffort(request.reasoning_effort)
            if request.reasoning_effort is not None
            else None
        )
        return GroqChatRequestOptions(
            response_format=response_format,
            reasoning_effort=reasoning_effort,
        )


def make_run_ai_playground_service() -> RunAiPlaygroundService:
    return RunAiPlaygroundService(
        llm=GroqAiPlaygroundAdapter.create_default(),
    )
