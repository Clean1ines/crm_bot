from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass
from typing import Protocol

from .contracts import (
    AI_PLAYGROUND_DEFAULT_MODEL,
    AI_PLAYGROUND_MODEL_LIMITS,
    AiPlaygroundRunRequest,
    AiPlaygroundRunResponse,
    AiPlaygroundUsage,
)


class AiPlaygroundValidationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class AiPlaygroundLlmResult:
    raw_text: str
    model: str
    provider: str = "groq"
    status: str = "completed"
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


class AiPlaygroundLlmPort(Protocol):
    async def run(
        self,
        request: AiPlaygroundRunRequest,
    ) -> AiPlaygroundLlmResult: ...


@dataclass(frozen=True, slots=True)
class RunAiPlaygroundService:
    llm: AiPlaygroundLlmPort

    async def run(self, request: AiPlaygroundRunRequest) -> AiPlaygroundRunResponse:
        normalized = self._validate(request)
        started = time.perf_counter()

        result = await self.llm.run(normalized)

        parsed_json: object | None = None
        json_parse_error: str | None = None
        if normalized.response_format == "json":
            try:
                parsed_json = json.loads(result.raw_text)
            except json.JSONDecodeError as exc:
                json_parse_error = f"{exc.msg} at line {exc.lineno} column {exc.colno}"

        duration_ms = int((time.perf_counter() - started) * 1000)
        usage = self._usage_from_result(result)

        return AiPlaygroundRunResponse(
            ok=True,
            model=result.model or normalized.model,
            provider=result.provider or "unknown",
            status=result.status or "completed",
            raw_text=result.raw_text,
            parsed_json=parsed_json,
            json_parse_error=json_parse_error,
            usage=usage,
            duration_ms=duration_ms,
        )

    def _validate(self, request: AiPlaygroundRunRequest) -> AiPlaygroundRunRequest:
        system_prompt = request.system_prompt.strip()
        user_input = request.user_input.strip()
        model = (request.model or AI_PLAYGROUND_DEFAULT_MODEL).strip()

        if not system_prompt:
            raise AiPlaygroundValidationError("system_prompt must not be empty")
        if not user_input:
            raise AiPlaygroundValidationError("user_input must not be empty")
        if len(system_prompt) > 20000:
            raise AiPlaygroundValidationError("system_prompt must be <= 20000 chars")
        if len(user_input) > 20000:
            raise AiPlaygroundValidationError("user_input must be <= 20000 chars")
        if model not in AI_PLAYGROUND_MODEL_LIMITS:
            raise AiPlaygroundValidationError(f"model is not allowed: {model}")

        estimated_tokens = self.estimate_input_tokens(system_prompt, user_input)
        tpm_limit = AI_PLAYGROUND_MODEL_LIMITS[model]["tpm"]
        if estimated_tokens > tpm_limit:
            raise AiPlaygroundValidationError(
                f"Твоё сообщение: {estimated_tokens} токенов. "
                f"Лимит для {model}: {tpm_limit} TPM."
            )

        return AiPlaygroundRunRequest(
            system_prompt=system_prompt,
            user_input=user_input,
            model=model,
            response_format=request.response_format,
            reasoning_effort=request.reasoning_effort,
            reasoning_format=request.reasoning_format,
            max_completion_tokens=request.max_completion_tokens,
        )

    @staticmethod
    def estimate_input_tokens(system_prompt: str, user_input: str) -> int:
        # Conservative, dependency-free preflight estimate. It is intentionally
        # approximate: the goal is to block obviously impossible requests before
        # provider call, while real usage still comes from Groq response headers/body.
        text = f"{system_prompt}\n\n{user_input}"
        return max(1, math.ceil(len(text) / 4))

    @staticmethod
    def _usage_from_result(
        result: AiPlaygroundLlmResult,
    ) -> AiPlaygroundUsage | None:
        if result.prompt_tokens is None and result.completion_tokens is None:
            return None

        prompt_tokens = max(0, int(result.prompt_tokens or 0))
        completion_tokens = max(0, int(result.completion_tokens or 0))
        total_tokens = (
            max(0, int(result.total_tokens))
            if result.total_tokens is not None
            else prompt_tokens + completion_tokens
        )

        return AiPlaygroundUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        )
