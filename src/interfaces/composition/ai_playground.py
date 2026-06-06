from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence, cast

from src.application.ai_playground.contracts import AiPlaygroundRunRequest
from src.application.ai_playground.run_ai_playground import (
    AiPlaygroundLlmResult,
    RunAiPlaygroundService,
)
from src.infrastructure.llm.groq_keyring import GroqClientRotator


class _UsageLike(Protocol):
    prompt_tokens: int | str | None
    completion_tokens: int | str | None
    total_tokens: int | str | None


class _MessageLike(Protocol):
    content: str | None


class _ChoiceLike(Protocol):
    message: _MessageLike


class _CompletionLike(Protocol):
    choices: Sequence[_ChoiceLike]
    usage: _UsageLike | None
    model: str | None


class _ChatCompletionsLike(Protocol):
    async def create(self, **kwargs: object) -> _CompletionLike: ...


class _ChatLike(Protocol):
    completions: _ChatCompletionsLike


@dataclass(slots=True)
class GroqAiPlaygroundAdapter:
    client: GroqClientRotator

    @classmethod
    def create_default(cls) -> "GroqAiPlaygroundAdapter":
        return cls(client=GroqClientRotator())

    async def run(
        self,
        request: AiPlaygroundRunRequest,
    ) -> AiPlaygroundLlmResult:
        kwargs: dict[str, object] = {
            "model": request.model,
            "messages": [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.user_input},
            ],
        }

        if request.response_format == "json":
            kwargs["response_format"] = {"type": "json_object"}

        async def create_completion(client: object) -> _CompletionLike:
            chat = getattr(client, "chat")
            completions = getattr(chat, "completions")
            create = getattr(completions, "create")
            response = await create(**kwargs)
            return cast(_CompletionLike, response)

        completion = await self.client.run(
            create_completion,
            operation_name="ai_playground.run",
        )

        raw_text = self._response_text(completion)
        usage = getattr(completion, "usage", None)

        return AiPlaygroundLlmResult(
            raw_text=raw_text,
            model=getattr(completion, "model", None) or request.model,
            provider="groq",
            status="completed",
            prompt_tokens=self._int_value(getattr(usage, "prompt_tokens", None)),
            completion_tokens=self._int_value(
                getattr(usage, "completion_tokens", None)
            ),
            total_tokens=self._int_value(getattr(usage, "total_tokens", None)),
        )

    def _response_text(self, response: _CompletionLike) -> str:
        choices = getattr(response, "choices", None) or []
        if not choices:
            return ""
        message = getattr(choices[0], "message", None)
        content = getattr(message, "content", None)
        return str(content or "").strip()

    def _int_value(self, value: object) -> int | None:
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        if isinstance(value, str) and value.strip().isdigit():
            return int(value.strip())
        return None


def make_run_ai_playground_service() -> RunAiPlaygroundService:
    return RunAiPlaygroundService(
        llm=GroqAiPlaygroundAdapter.create_default(),
    )
