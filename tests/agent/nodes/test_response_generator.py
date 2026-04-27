from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.agent.nodes.response_generator import (
    _resolve_response_model_name,
    create_response_generator_node,
)


def test_resolve_response_model_name_prefers_project_fallback():
    model = _resolve_response_model_name(
        {
            "project_configuration": {
                "limit_profile": {"fallback_model": "llama-3.1-8b-instant"},
            }
        },
        "llama-3.3-70b-versatile",
    )

    assert model == "llama-3.1-8b-instant"


@pytest.mark.asyncio
async def test_response_generator_uses_base_llm_when_no_project_override():
    fake_llm = AsyncMock()
    fake_llm.ainvoke = AsyncMock(return_value=SimpleNamespace(content="ok"))
    node = create_response_generator_node(
        llm=fake_llm, model_name="llama-3.3-70b-versatile"
    )

    async def passthrough(_name, impl, state, **_kwargs):
        return await impl(state)

    with patch(
        "src.agent.nodes.response_generator.log_node_execution",
        AsyncMock(side_effect=passthrough),
    ):
        result = await node(
            {
                "decision": "LLM_GENERATE",
                "user_input": "Привет",
                "project_configuration": {},
            }
        )

    assert result["response_text"] == "ok"
    fake_llm.ainvoke.assert_awaited_once()


@pytest.mark.asyncio
async def test_response_generator_builds_project_override_llm():
    created_models = []

    class FakeChatGroq:
        def __init__(self, *, model, temperature, max_tokens, api_key):
            created_models.append(model)

        async def ainvoke(self, _messages):
            return SimpleNamespace(content="override")

    base_llm = AsyncMock()
    base_llm.ainvoke = AsyncMock(return_value=SimpleNamespace(content="base"))

    with patch("src.agent.nodes.response_generator.ChatGroq", FakeChatGroq):
        node = create_response_generator_node(
            llm=base_llm, model_name="llama-3.3-70b-versatile"
        )

        async def passthrough(_name, impl, state, **_kwargs):
            return await impl(state)

        with patch(
            "src.agent.nodes.response_generator.log_node_execution",
            AsyncMock(side_effect=passthrough),
        ):
            result = await node(
                {
                    "decision": "LLM_GENERATE",
                    "user_input": "Привет",
                    "project_configuration": {
                        "limit_profile": {"fallback_model": "llama-3.1-8b-instant"},
                    },
                }
            )

    assert result["response_text"] == "override"
    assert created_models == ["llama-3.1-8b-instant"]
    base_llm.ainvoke.assert_not_called()


@pytest.mark.asyncio
async def test_response_generator_returns_typed_fallback_when_llm_fails():
    fake_llm = AsyncMock()
    fake_llm.ainvoke = AsyncMock(side_effect=RuntimeError("llm unavailable"))
    node = create_response_generator_node(
        llm=fake_llm, model_name="llama-3.3-70b-versatile"
    )

    async def passthrough(_name, impl, state, **_kwargs):
        return await impl(state)

    with (
        patch(
            "src.agent.nodes.response_generator.log_node_execution",
            AsyncMock(side_effect=passthrough),
        ),
        patch("src.agent.nodes.response_generator.logger") as logger,
    ):
        result = await node(
            {
                "decision": "LLM_GENERATE",
                "user_input": "Привет",
                "project_configuration": {},
            }
        )

    assert result["response_text"] == (
        "Sorry, something went wrong while generating the response. Please try again later."
    )
    logger.exception.assert_called_once()
    assert (
        logger.exception.call_args.kwargs["extra"]["policy"]
        == "fallback_user_visible_error"
    )
