from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TypeAlias

from src.contexts.llm_runtime.domain.capacity.llm_model_route_catalog import (
    LlmModelExecutionSettings,
)
from src.contexts.llm_runtime.domain.entities.model_profile import ModelProfile
from src.contexts.llm_runtime.domain.value_objects.llm_route import LlmRoute
from src.contexts.llm_runtime.domain.value_objects.reasoning_effort import (
    ReasoningEffort,
)


JsonScalar: TypeAlias = None | bool | int | float | str
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]


class GroqChatMessageRole(StrEnum):
    SYSTEM = "system"
    DEVELOPER = "developer"
    USER = "user"
    ASSISTANT = "assistant"


class GroqResponseFormatKind(StrEnum):
    TEXT = "text"
    JSON_OBJECT = "json_object"


@dataclass(frozen=True, slots=True)
class GroqChatMessage:
    role: GroqChatMessageRole
    content: str

    def __post_init__(self) -> None:
        if not self.content or not self.content.strip():
            raise ValueError("GroqChatMessage.content must be non-empty")


@dataclass(frozen=True, slots=True)
class GroqChatRequestOptions:
    response_format: GroqResponseFormatKind = GroqResponseFormatKind.JSON_OBJECT
    max_completion_tokens: int | None = None
    temperature: float | None = 0.0
    reasoning_effort: ReasoningEffort | None = None
    execution_settings: LlmModelExecutionSettings | None = None

    def __post_init__(self) -> None:
        if self.max_completion_tokens is not None and self.max_completion_tokens <= 0:
            raise ValueError("max_completion_tokens must be > 0 when provided")
        if self.temperature is not None and not 0 <= self.temperature <= 2:
            raise ValueError("temperature must be between 0 and 2 when provided")
        if self.execution_settings is not None and not isinstance(
            self.execution_settings,
            LlmModelExecutionSettings,
        ):
            raise TypeError("execution_settings must be LlmModelExecutionSettings")


@dataclass(frozen=True, slots=True)
class GroqChatRequest:
    payload: dict[str, JsonValue]


class GroqChatRequestBuilder:
    """Build Groq Chat Completions request payloads.

    This builder is infrastructure-specific. It does not execute HTTP requests,
    choose routes, or decide retry/fallback behavior.
    """

    def build(
        self,
        *,
        route: LlmRoute,
        model_profile: ModelProfile,
        messages: tuple[GroqChatMessage, ...],
        options: GroqChatRequestOptions | None = None,
    ) -> GroqChatRequest:
        if route.provider_id != model_profile.provider_id:
            raise ValueError("route.provider_id must match model_profile.provider_id")
        if route.model_id != model_profile.model_id:
            raise ValueError("route.model_id must match model_profile.model_id")
        if not messages:
            raise ValueError("messages must not be empty")

        options = options or GroqChatRequestOptions()
        if (
            options.max_completion_tokens is not None
            and options.max_completion_tokens > model_profile.max_output_tokens
        ):
            raise ValueError(
                "max_completion_tokens must not exceed model max_output_tokens"
            )

        payload: dict[str, JsonValue] = {
            "model": route.model_id.value,
            "messages": [
                {
                    "role": message.role.value,
                    "content": message.content,
                }
                for message in messages
            ],
        }
        if options.max_completion_tokens is not None:
            payload["max_completion_tokens"] = options.max_completion_tokens

        if options.temperature is not None:
            payload["temperature"] = options.temperature

        if options.response_format is GroqResponseFormatKind.JSON_OBJECT:
            if not model_profile.supports_json_object:
                raise ValueError("Model does not support JSON object response format")
            payload["response_format"] = {"type": "json_object"}

        reasoning_effort: ReasoningEffort | None = None
        if options.execution_settings is not None:
            if options.execution_settings.reasoning_enabled:
                reasoning_effort = options.reasoning_effort
                if (
                    reasoning_effort is None
                    and options.execution_settings.reasoning_effort is not None
                ):
                    reasoning_effort = ReasoningEffort(
                        options.execution_settings.reasoning_effort,
                    )
                if reasoning_effort is None:
                    reasoning_effort = model_profile.reasoning_profile.default_effort
        else:
            reasoning_effort = options.reasoning_effort
            if reasoning_effort is None:
                reasoning_effort = model_profile.reasoning_profile.default_effort

        if reasoning_effort is not None:
            if (
                reasoning_effort
                not in model_profile.reasoning_profile.supported_efforts
            ):
                raise ValueError("Requested reasoning effort is not supported by model")
            payload["reasoning_effort"] = reasoning_effort.value

        return GroqChatRequest(payload=payload)
