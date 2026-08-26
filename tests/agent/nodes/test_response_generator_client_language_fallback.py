import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.agent.nodes.response_generator import create_response_generator_node


def _state(*, target_language: str = "en") -> dict[str, object]:
    return {
        "decision": "LLM_GENERATE",
        "generation_mode": "KNOWLEDGE_ANSWER",
        "user_input": "Есть ли HubSpot?",
        "knowledge_chunks": [
            {
                "id": "entry-1",
                "score": 0.9,
                "content": "Готовой универсальной интеграции с HubSpot сейчас нет.",
            }
        ],
        "knowledge_retrieval_status": "retrieved",
        "project_configuration": {"settings": {"target_language": target_language}},
    }


@pytest.mark.asyncio
async def test_invalid_generation_fallback_prefers_current_client_language() -> None:
    llm = AsyncMock()
    llm.ainvoke = AsyncMock(return_value=SimpleNamespace(content="not json"))
    node = create_response_generator_node(llm=llm, model_name="base-model")

    result = await node(_state(target_language="en"))

    assert result["response_text"] == (
        "Сейчас не получилось сформировать корректный ответ по доступной базе знаний."
    )
    assert result["fallback_reason"] == "invalid_json"
    assert llm.ainvoke.await_count == 2


@pytest.mark.asyncio
async def test_language_mismatch_fallback_prefers_current_client_language() -> None:
    llm = AsyncMock()
    llm.ainvoke = AsyncMock(
        return_value=SimpleNamespace(
            content=json.dumps(
                {
                    "answerability": "supported",
                    "answer": "HubSpot is not available as a built-in integration.",
                    "supporting_evidence_refs": ["E1"],
                    "unsupported_aspects": [],
                }
            )
        )
    )
    node = create_response_generator_node(llm=llm, model_name="base-model")

    result = await node(_state(target_language="en"))

    assert result["response_text"].startswith("Хочу ответить на вашем языке корректно")
    assert result["fallback_reason"] == "language_validation_failed"
    assert llm.ainvoke.await_count == 1
