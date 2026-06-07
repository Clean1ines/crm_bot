from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol, cast

from src.application.ports.llm_json_invocation import LlmJsonInvocationPort
from src.domain.project_plane.llm_routing import (
    JsonValue,
    LlmInvocationFailure,
    LlmInvocationStatus,
    LlmJsonInvocationRequest,
    LlmJsonInvocationResult,
    LlmRouteAttempt,
    LlmRouteAttemptStatus,
    LlmTokenUsage,
)
from src.infrastructure.llm.groq_keyring import RotatingAsyncGroq
from src.infrastructure.llm.groq_router import (
    GroqFallbackExhaustedError,
    GroqLimitKind,
    GroqRouteFailureType,
    classify_groq_exception,
    retry_after_seconds_from_exception,
)


STRICT_JSON_SYSTEM_MESSAGE = (
    "You are a strict JSON API. Return exactly one valid JSON object. "
    "Do not include markdown, code fences, explanations, comments, apologies, "
    "prefixes, suffixes, or multiple JSON objects. The first non-whitespace "
    "character must be { and the last non-whitespace character must be }."
)

DEFAULT_GROQ_JSON_MODEL = "llama-3.1-8b-instant"
GROQ_PROVIDER_ID = "groq"


class GroqUsageLike(Protocol):
    prompt_tokens: int | str | None
    completion_tokens: int | str | None
    total_tokens: int | str | None


class GroqMessageLike(Protocol):
    content: str | None


class GroqChoiceLike(Protocol):
    message: GroqMessageLike


class GroqChatCompletionLike(Protocol):
    choices: Sequence[GroqChoiceLike]
    usage: GroqUsageLike | None
    model: str | None


class GroqChatCompletionsLike(Protocol):
    async def create(self, **kwargs: object) -> GroqChatCompletionLike: ...


class GroqChatLike(Protocol):
    completions: GroqChatCompletionsLike


class GroqJsonClientLike(Protocol):
    chat: GroqChatLike

    def route_observability_snapshot(self) -> dict[str, object]: ...


@dataclass(frozen=True, slots=True)
class GroqLlmJsonInvocationConfig:
    default_model: str = DEFAULT_GROQ_JSON_MODEL
    temperature: float = 0.0
    max_completion_tokens: int | None = None
    reasoning_effort: str | None = None
    reasoning_format: str | None = None


@dataclass(slots=True)
class GroqLlmJsonInvocationAdapter(LlmJsonInvocationPort):
    client: GroqJsonClientLike
    config: GroqLlmJsonInvocationConfig = field(
        default_factory=GroqLlmJsonInvocationConfig
    )

    @classmethod
    def create_default(
        cls,
        *,
        config: GroqLlmJsonInvocationConfig | None = None,
    ) -> GroqLlmJsonInvocationAdapter:
        return cls(
            client=cast(GroqJsonClientLike, RotatingAsyncGroq()),
            config=config or GroqLlmJsonInvocationConfig(),
        )

    async def invoke_json(
        self,
        request: LlmJsonInvocationRequest,
    ) -> LlmJsonInvocationResult:
        started_at = datetime.now(timezone.utc)

        try:
            response = await self.client.chat.completions.create(
                model=self.config.default_model,
                messages=[
                    {"role": "system", "content": STRICT_JSON_SYSTEM_MESSAGE},
                    {"role": "user", "content": request.prompt},
                ],
                temperature=self.config.temperature,
                response_format={"type": "json_object"},
                **self._completion_kwargs(),
            )

            raw_text = self._response_text(response)
            parsed_json = self._loads_json_value(raw_text)
            token_usage = self._token_usage(response.usage)
            attempts = self._route_attempts(
                status=LlmRouteAttemptStatus.SUCCESS,
                fallback_model=response.model or self.config.default_model,
            )

            return LlmJsonInvocationResult(
                status=LlmInvocationStatus.SUCCESS,
                parsed_json=parsed_json,
                raw_text=raw_text,
                token_usage=token_usage,
                attempts=attempts,
                started_at=started_at,
                completed_at=datetime.now(timezone.utc),
            )
        except GroqFallbackExhaustedError as exc:
            return self._failed_result(
                request=request,
                started_at=started_at,
                status=self._status_from_groq_failure_type(exc.failure_type),
                error_kind=exc.failure_type.value,
                internal_message=str(exc),
                exc=exc.last_error or exc,
            )
        except json.JSONDecodeError as exc:
            return self._failed_result(
                request=request,
                started_at=started_at,
                status=LlmInvocationStatus.INVALID_JSON,
                error_kind="invalid_json",
                internal_message=str(exc),
                exc=exc,
            )
        except Exception as exc:
            limit_kind = classify_groq_exception(exc)
            return self._failed_result(
                request=request,
                started_at=started_at,
                status=self._status_from_limit_kind(limit_kind),
                error_kind=limit_kind.value,
                internal_message=str(exc),
                exc=exc,
            )

    def _completion_kwargs(self) -> dict[str, object]:
        kwargs = self._max_completion_kwargs()
        kwargs.update(self._reasoning_kwargs())
        return kwargs

    def _max_completion_kwargs(self) -> dict[str, object]:
        if self.config.max_completion_tokens is None:
            return {}
        return {"max_completion_tokens": self.config.max_completion_tokens}

    def _reasoning_kwargs(self) -> dict[str, object]:
        kwargs: dict[str, object] = {}
        if self.config.reasoning_effort is not None:
            kwargs["reasoning_effort"] = self.config.reasoning_effort
        if self.config.reasoning_format is not None:
            kwargs["reasoning_format"] = self.config.reasoning_format
        return kwargs

    def _response_text(self, response: GroqChatCompletionLike) -> str:
        if not response.choices:
            raise json.JSONDecodeError("empty Groq choices", "", 0)

        content = response.choices[0].message.content
        if content is None or not content.strip():
            raise json.JSONDecodeError("empty Groq response content", "", 0)

        return content.strip()

    def _loads_json_value(self, raw_text: str) -> JsonValue:
        payload = json.loads(raw_text)
        return self._json_value_from_object(payload)

    def _json_value_from_object(self, value: object) -> JsonValue:
        if value is None or isinstance(value, str | int | float | bool):
            return value
        if isinstance(value, list):
            return [self._json_value_from_object(item) for item in value]
        if isinstance(value, dict):
            return {
                str(key): self._json_value_from_object(item)
                for key, item in value.items()
            }
        return str(value)

    def _token_usage(self, usage: GroqUsageLike | None) -> LlmTokenUsage:
        if usage is None:
            return LlmTokenUsage(prompt_tokens=0, completion_tokens=0)

        return LlmTokenUsage(
            prompt_tokens=self._int_value(usage.prompt_tokens),
            completion_tokens=self._int_value(usage.completion_tokens),
        )

    def _int_value(self, value: int | str | None) -> int:
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        if isinstance(value, str) and value.strip().isdigit():
            return int(value.strip())
        return 0

    def _route_attempts(
        self,
        *,
        status: LlmRouteAttemptStatus,
        fallback_model: str,
    ) -> tuple[LlmRouteAttempt, ...]:
        events = self._route_events()
        attempts: list[LlmRouteAttempt] = []

        for index, event in enumerate(events):
            event_status = self._event_text(event, "status")
            model = self._event_text(event, "routed_model") or fallback_model
            key_slot = self._event_text(event, "key_slot_label") or self._event_text(
                event,
                "key_slot",
            )
            limit_kind = self._event_text(event, "limit_kind")

            attempts.append(
                LlmRouteAttempt(
                    provider_id=GROQ_PROVIDER_ID,
                    model=model,
                    api_key_slot=key_slot or "unknown",
                    attempt_index=index,
                    status=(
                        LlmRouteAttemptStatus.SUCCESS
                        if event_status == "success"
                        else status
                    ),
                    error_kind=limit_kind or None,
                    cooldown_seconds=self._event_cooldown_seconds(event),
                )
            )

        if attempts:
            return tuple(attempts)

        return (
            LlmRouteAttempt(
                provider_id=GROQ_PROVIDER_ID,
                model=fallback_model,
                api_key_slot="unknown",
                attempt_index=0,
                status=status,
            ),
        )

    def _route_events(self) -> tuple[Mapping[str, object], ...]:
        snapshot = self.client.route_observability_snapshot()
        events = snapshot.get("groq_route_events")
        if not isinstance(events, list):
            return ()

        result: list[Mapping[str, object]] = []
        for event in events:
            if isinstance(event, Mapping):
                result.append(event)
        return tuple(result)

    def _event_text(self, event: Mapping[str, object], key: str) -> str:
        value = event.get(key)
        if value is None:
            return ""
        return str(value).strip()

    def _event_cooldown_seconds(self, event: Mapping[str, object]) -> int | None:
        value = event.get("retry_after_seconds")
        if isinstance(value, int | float) and value > 0:
            return int(value)
        return None

    def _failed_result(
        self,
        *,
        request: LlmJsonInvocationRequest,
        started_at: datetime,
        status: LlmInvocationStatus,
        error_kind: str,
        internal_message: str,
        exc: BaseException,
    ) -> LlmJsonInvocationResult:
        retry_after = retry_after_seconds_from_exception(exc)
        cooldown_seconds = int(retry_after) if retry_after is not None else None

        return LlmJsonInvocationResult(
            status=status,
            parsed_json=None,
            raw_text="",
            token_usage=LlmTokenUsage(prompt_tokens=0, completion_tokens=0),
            attempts=self._route_attempts(
                status=LlmRouteAttemptStatus.FAILED,
                fallback_model=self.config.default_model,
            ),
            failure=LlmInvocationFailure(
                status=status,
                error_kind=error_kind,
                user_message=self._user_message(status),
                internal_message=internal_message or request.operation_name,
                cooldown_seconds=cooldown_seconds,
            ),
            started_at=started_at,
            completed_at=datetime.now(timezone.utc),
        )

    def _status_from_groq_failure_type(
        self,
        failure_type: GroqRouteFailureType,
    ) -> LlmInvocationStatus:
        if failure_type is GroqRouteFailureType.INPUT_TOO_LARGE:
            return LlmInvocationStatus.REQUEST_TOO_LARGE
        if failure_type is GroqRouteFailureType.OUTPUT_TOO_LARGE:
            return LlmInvocationStatus.OUTPUT_TOO_LARGE
        if failure_type is GroqRouteFailureType.QUOTA_EXHAUSTED:
            return LlmInvocationStatus.DAILY_LIMITED
        return LlmInvocationStatus.PROVIDER_ERROR

    def _status_from_limit_kind(self, limit_kind: GroqLimitKind) -> LlmInvocationStatus:
        if limit_kind in {GroqLimitKind.REQUEST_TOO_LARGE, GroqLimitKind.CONTEXT_LIMIT}:
            return LlmInvocationStatus.REQUEST_TOO_LARGE
        if limit_kind is GroqLimitKind.OUTPUT_TOO_LARGE:
            return LlmInvocationStatus.OUTPUT_TOO_LARGE
        if limit_kind in {
            GroqLimitKind.TPM,
            GroqLimitKind.RPM,
            GroqLimitKind.RATE_LIMIT,
        }:
            return LlmInvocationStatus.RATE_LIMITED
        if limit_kind in {GroqLimitKind.TPD, GroqLimitKind.RPD}:
            return LlmInvocationStatus.DAILY_LIMITED
        if limit_kind is GroqLimitKind.TEMPORARY_PROVIDER_ERROR:
            return LlmInvocationStatus.PROVIDER_ERROR
        return LlmInvocationStatus.PROVIDER_ERROR

    def _user_message(self, status: LlmInvocationStatus) -> str:
        if status is LlmInvocationStatus.REQUEST_TOO_LARGE:
            return "LLM request is too large for the available model routes."
        if status is LlmInvocationStatus.OUTPUT_TOO_LARGE:
            return "LLM output is too large for the available model routes."
        if status is LlmInvocationStatus.RATE_LIMITED:
            return "LLM provider is temporarily rate limited."
        if status is LlmInvocationStatus.DAILY_LIMITED:
            return "LLM provider daily quota is exhausted."
        if status is LlmInvocationStatus.INVALID_JSON:
            return "LLM returned invalid JSON."
        return "LLM provider request failed."
