from __future__ import annotations

import pytest

from src.contexts.llm_runtime.application.ports.llm_provider_input import (
    LlmProviderInput,
    LlmProviderMessage,
    LlmProviderMessageRole,
)


def test_provider_input_requires_non_empty_messages() -> None:
    message = LlmProviderMessage(
        role=LlmProviderMessageRole.USER,
        content="Hello",
    )

    provider_input = LlmProviderInput(messages=(message,))

    assert provider_input.messages == (message,)

    with pytest.raises(ValueError):
        LlmProviderInput(messages=())


def test_provider_message_requires_non_empty_content() -> None:
    with pytest.raises(ValueError):
        LlmProviderMessage(
            role=LlmProviderMessageRole.USER,
            content="",
        )
