from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from src.contexts.llm_runtime.application.ports.llm_provider_input import (
    LlmProviderInput,
    LlmProviderMessageRole,
)
from src.contexts.llm_runtime.application.ports.llm_provider_port import (
    LlmProviderPort,
    LlmProviderResult,
)
from src.contexts.llm_runtime.domain.entities.llm_task import LlmTask
from src.contexts.llm_runtime.domain.entities.model_profile import ModelProfile
from src.contexts.llm_runtime.domain.value_objects.llm_route import LlmRoute
from src.contexts.llm_runtime.infrastructure.providers.groq.groq_chat_request_builder import (
    GroqChatMessage,
    GroqChatMessageRole,
    GroqChatRequestBuilder,
)
from src.contexts.llm_runtime.infrastructure.providers.groq.groq_provider_response_mapper import (
    GroqProviderHttpResponse,
    GroqProviderResponseMapper,
)
from src.contexts.llm_runtime.infrastructure.providers.groq.groq_transport_port import (
    GroqTransportPort,
)


@dataclass(frozen=True, slots=True)
class GroqProviderAdapter(LlmProviderPort):
    """Thin Groq provider adapter.

    It translates generic LLM Runtime input into Groq Chat Completions payload,
    delegates HTTP to a transport port, and maps the response back to generic
    provider result. It does not own retry/fallback/quota policy.
    """

    transport: GroqTransportPort
    model_profiles: tuple[ModelProfile, ...]
    request_builder: GroqChatRequestBuilder = GroqChatRequestBuilder()
    response_mapper: GroqProviderResponseMapper = GroqProviderResponseMapper()

    def invoke(
        self,
        *,
        task: LlmTask,
        route: LlmRoute,
        provider_input: LlmProviderInput,
    ) -> LlmProviderResult:
        model_profile = self._find_model_profile(route=route)
        request = self.request_builder.build(
            route=route,
            model_profile=model_profile,
            messages=tuple(
                GroqChatMessage(
                    role=self._map_role(message.role),
                    content=message.content,
                )
                for message in provider_input.messages
            ),
        )

        transport_response = self.transport.post_chat_completions(
            payload=dict(request.payload),
        )

        mapped = self.response_mapper.map_response(
            response=GroqProviderHttpResponse(
                status_code=transport_response.status_code,
                headers=transport_response.headers,
                body=transport_response.body,
            ),
            observed_at=datetime.now(timezone.utc),
        )

        return mapped.provider_result

    def _find_model_profile(self, *, route: LlmRoute) -> ModelProfile:
        for profile in self.model_profiles:
            if (
                profile.provider_id == route.provider_id
                and profile.model_id == route.model_id
            ):
                return profile

        raise ValueError("No ModelProfile found for route")

    def _map_role(self, role: LlmProviderMessageRole) -> GroqChatMessageRole:
        if role is LlmProviderMessageRole.SYSTEM:
            return GroqChatMessageRole.SYSTEM
        if role is LlmProviderMessageRole.DEVELOPER:
            return GroqChatMessageRole.DEVELOPER
        if role is LlmProviderMessageRole.USER:
            return GroqChatMessageRole.USER
        if role is LlmProviderMessageRole.ASSISTANT:
            return GroqChatMessageRole.ASSISTANT

        raise ValueError(f"Unsupported provider message role: {role!r}")


@dataclass(frozen=True, slots=True)
class GroqProviderAdapterFactory:
    """Factory for explicit construction without hidden global configuration."""

    transport: GroqTransportPort
    model_profiles: tuple[ModelProfile, ...]

    def build(self) -> GroqProviderAdapter:
        return GroqProviderAdapter(
            transport=self.transport,
            model_profiles=self.model_profiles,
        )
