from __future__ import annotations

from typing import Protocol, cast

from src.application.ports.text_completion_port import TextCompletionPort
from src.infrastructure.config.settings import settings


class ChatMessageResponse(Protocol):
    content: str | None


class ChatGroqClient(Protocol):
    async def ainvoke(self, messages: list[tuple[str, str]]) -> ChatMessageResponse: ...


class ChatGroqFactory(Protocol):
    def __call__(
        self,
        *,
        model: str,
        temperature: float,
        max_tokens: int,
        api_key: object,
        model_kwargs: dict[str, object] | None = None,
        reasoning_effort: str | None = None,
    ) -> ChatGroqClient: ...


ChatGroq: ChatGroqFactory | None = None


class GroqTextCompletionClient(TextCompletionPort):
    async def complete(
        self,
        prompt: str,
        *,
        target_language: str = "ru",
        max_tokens: int = 700,
        temperature: float = 0.2,
        model_name: str | None = None,
        llm: ChatGroqClient | None = None,
        response_format: dict[str, object] | None = None,
        reasoning_effort: str | None = None,
    ) -> str:
        del target_language
        model = model_name or settings.GROQ_MODEL
        if llm is not None:
            response = await llm.ainvoke([("human", prompt)])
            return (response.content or "").strip()

        chat_groq_factory = _chat_groq_class()
        if response_format is None and reasoning_effort is None:
            client = chat_groq_factory(
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                api_key=_primary_groq_api_key(),
            )
        elif reasoning_effort is None:
            client = chat_groq_factory(
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                api_key=_primary_groq_api_key(),
                model_kwargs={"response_format": response_format},
            )
        else:
            client = chat_groq_factory(
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                api_key=_primary_groq_api_key(),
                model_kwargs={"response_format": response_format},
                reasoning_effort=reasoning_effort,
            )
        response = await client.ainvoke([("human", prompt)])
        return (response.content or "").strip()


def _primary_groq_api_key() -> str:
    value = str(settings.GROQ_API_KEY).strip()
    if not value:
        raise RuntimeError("GROQ_API_KEY is not configured")
    return value


def _chat_groq_class() -> ChatGroqFactory:
    if ChatGroq is not None:
        return ChatGroq

    from langchain_groq import ChatGroq as ImportedChatGroq

    return cast(ChatGroqFactory, ImportedChatGroq)
