from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.agent.nodes.response_generator import create_response_generator_node


def _state(
    *,
    user_input: str,
    settings: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "decision": "LLM_GENERATE",
        "generation_mode": "KNOWLEDGE_ANSWER",
        "user_input": user_input,
        "knowledge_chunks": [
            {
                "id": "entry-1",
                "score": 0.9,
                "content": "Готовой универсальной интеграции с HubSpot сейчас нет.",
            }
        ],
        "knowledge_retrieval_status": "retrieved",
        "project_configuration": {"settings": settings or {}},
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "user_input",
    [
        "А HubSpot?",
        "Есть WhatsApp и Instagram?",
    ],
)
async def test_unset_project_language_never_switches_russian_dialog_to_english(
    user_input: str,
) -> None:
    llm = AsyncMock()
    llm.ainvoke = AsyncMock(return_value=SimpleNamespace(content="not json"))
    node = create_response_generator_node(llm=llm, model_name="base-model")

    result = await node(_state(user_input=user_input))

    assert result["response_text"] == (
        "Сейчас не получилось сформировать корректный ответ по доступной базе знаний."
    )
    assert result["fallback_reason"] == "invalid_json"
    assert llm.ainvoke.await_count == 2


@pytest.mark.asyncio
async def test_explicit_project_language_remains_authoritative() -> None:
    llm = AsyncMock()
    llm.ainvoke = AsyncMock(return_value=SimpleNamespace(content="not json"))
    node = create_response_generator_node(llm=llm, model_name="base-model")

    result = await node(
        _state(
            user_input="Есть HubSpot?",
            settings={"target_language": "en"},
        )
    )

    assert result["response_text"] == (
        "I could not form a correct answer from the available knowledge base right now."
    )
    assert result["fallback_reason"] == "invalid_json"
