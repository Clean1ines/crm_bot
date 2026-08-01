import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agent.nodes.response_generator import (
    _resolve_response_model_name,
    build_answer_preview_prompt,
    create_response_generator_node,
)
from src.agent.nodes.intent_extractor import create_intent_extractor_node


def _structured_content(
    answer: str | None,
    *,
    answerability: str = "supported",
    supporting_entry_ids: list[str] | None = None,
    supporting_evidence_refs: list[str] | None = None,
    unsupported_aspects: list[str] | None = None,
) -> str:
    refs = supporting_evidence_refs
    if refs is None:
        entry_ids = (
            ["entry-1"]
            if supporting_entry_ids is None
            and answerability in {"supported", "partially_supported"}
            else supporting_entry_ids or []
        )
        refs = [
            f"E{entry_id.removeprefix('entry-')}"
            if entry_id.startswith("entry-")
            else entry_id
            for entry_id in entry_ids
        ]
    return json.dumps(
        {
            "answerability": answerability,
            "answer": answer,
            "supporting_evidence_refs": refs,
            "unsupported_aspects": unsupported_aspects or [],
        },
        ensure_ascii=False,
    )


def _retrieved_state(
    content: str = "Факт подтверждён в базе знаний.",
) -> dict[str, object]:
    return {
        "knowledge_chunks": [{"id": "entry-1", "score": 0.9, "content": content}],
        "knowledge_retrieval_status": "retrieved",
        "generation_mode": "KNOWLEDGE_ANSWER",
    }


class _FixedIntentLlm:
    def __init__(self, *, relation: str) -> None:
        self.relation = relation

    async def ainvoke(self, _messages):
        return SimpleNamespace(
            content=json.dumps(
                {
                    "domain": "business",
                    "turn_relation": "continuation",
                    "intent": "sales",
                    "cta": "none",
                    "features": {},
                    "topic": "product",
                    "cta_hint": None,
                    "emotion": "neutral",
                    "is_repeat_like": self.relation
                    in {"repeat_answered", "repeat_unresolved"},
                    "should_search_kb": True,
                    "should_generate_answer": True,
                    "should_offer_manager": False,
                    "knowledge_query": "может ли клиент писать через веб-панель",
                    "current_subject": "веб-панель",
                    "repeat_relation": self.relation,
                    "dissatisfaction": False,
                    "memory_candidates": [],
                },
                ensure_ascii=False,
            )
        )


class _CapturingResponseLlm:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    async def ainvoke(self, messages):
        self.prompts.append(messages[-1][1])
        return SimpleNamespace(content=_structured_content("Ответ по базе."))


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
@pytest.mark.parametrize(
    "relation",
    ("clarification", "repeat_answered", "repeat_unresolved"),
)
async def test_sequential_intent_patch_overrides_persisted_relation_in_response_prompt(
    relation,
):
    intent_node = create_intent_extractor_node(llm=_FixedIntentLlm(relation=relation))
    response_llm = _CapturingResponseLlm()
    response_node = create_response_generator_node(
        llm=response_llm,
        model_name="base-model",
    )

    async def passthrough(_name, impl, state, **_kwargs):
        return await impl(state)

    state = {
        "decision": "LLM_GENERATE",
        "user_input": "А клиент может писать через неё?",
        "conversation_context": {
            "current_subject": "старая тема",
            "repeat_relation": "none",
        },
        "project_configuration": {"settings": {"target_language": "ru"}},
        **_retrieved_state(),
    }

    with (
        patch(
            "src.agent.nodes.intent_extractor.log_node_execution",
            AsyncMock(side_effect=passthrough),
        ),
        patch(
            "src.agent.nodes.response_generator.log_node_execution",
            AsyncMock(side_effect=passthrough),
        ),
    ):
        intent_patch = await intent_node(state)
        await response_node({**state, **intent_patch})

    prompt = response_llm.prompts[-1]
    assert '"current_subject":"веб-панель"' in prompt
    assert f'"repeat_relation":"{relation}"' in prompt
    assert '"repeat_relation":"none"' not in prompt


def test_answer_preview_prompt_includes_clean_fact_without_internal_metadata() -> None:
    prompt = build_answer_preview_prompt(
        user_input="Когда доставка?",
        knowledge_chunks=[
            {
                "id": "runtime-entry-1",
                "content": "Доставка занимает два дня после оплаты.",
                "score": 0.91,
                "method": "runtime_hybrid",
                "runtime_entry_id": "runtime-entry-1",
                "workflow_run_id": "workflow-run-1",
                "source_document_ref": "source-doc-1",
                "source_claim_refs": [{"claim": "claim-1"}],
                "raw_source_refs": [{"source_unit_ref": "unit-1"}],
                "trace": {"vector_score": 0.9},
                "embedding_text": "embedding-only text",
                "triples": [{"subject": "delivery"}],
            }
        ],
        project_configuration={"settings": {}},
        target_language="ru",
    )

    assert "Доставка занимает два дня после оплаты." in prompt
    assert "E1 | score=0.910 | method=runtime_hybrid" in prompt
    assert "runtime-entry-1" not in prompt
    assert "id=runtime-entry-1" not in prompt
    assert "workflow-run-1" not in prompt
    assert "source-doc-1" not in prompt
    assert "source_claim_refs" not in prompt
    assert "raw_source_refs" not in prompt
    assert "trace" not in prompt
    assert "embedding-only text" not in prompt
    assert "subject" not in prompt


@pytest.mark.asyncio
async def test_response_generator_uses_base_llm_when_no_project_override():
    fake_llm = AsyncMock()
    fake_llm.ainvoke = AsyncMock(
        return_value=SimpleNamespace(content=_structured_content("ok"))
    )
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
                **_retrieved_state(),
            }
        )

    assert result["response_text"] == "ok"
    fake_llm.ainvoke.assert_awaited_once()


@pytest.mark.asyncio
async def test_response_generator_sets_structured_continuation_cta_for_product_answer():
    fake_llm = AsyncMock()
    fake_llm.ainvoke = AsyncMock(
        return_value=SimpleNamespace(
            content=_structured_content(
                "Axole помогает автоматизировать ответы клиентам."
            )
        )
    )
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
                "decision": "RESPOND_KB",
                "user_input": "Что умеет сервис?",
                "topic": "product",
                "turn_relation": "new_topic",
                "cta": "none",
                "project_configuration": {},
                **_retrieved_state(),
            }
        )

    assert result["cta"] == "continue_explanation"
    assert result["topic"] == "product"
    assert "Хотите узнать больше о том, как это работает?" in result["response_text"]


@pytest.mark.asyncio
async def test_response_generator_does_not_add_continuation_when_answer_is_question():
    fake_llm = AsyncMock()
    fake_llm.ainvoke = AsyncMock(
        return_value=SimpleNamespace(
            content=_structured_content("Что именно хотите автоматизировать?")
        )
    )
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
                "decision": "RESPOND_KB",
                "user_input": "Что умеет сервис?",
                "topic": "product",
                "turn_relation": "new_topic",
                "cta": "none",
                "project_configuration": {},
                **_retrieved_state(),
            }
        )

    assert result["response_text"] == "Что именно хотите автоматизировать?"
    assert "cta" not in result


@pytest.mark.asyncio
async def test_response_generator_does_not_add_continuation_for_action_cta_state():
    fake_llm = AsyncMock()
    fake_llm.ainvoke = AsyncMock(
        return_value=SimpleNamespace(
            content=_structured_content("Могу передать вопрос менеджеру.")
        )
    )
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
                "decision": "RESPOND_KB",
                "user_input": "Позовите менеджера",
                "topic": "product",
                "turn_relation": "new_topic",
                "cta": "call_manager",
                "project_configuration": {},
                **_retrieved_state(),
            }
        )

    assert result["response_text"] == "Могу передать вопрос менеджеру."
    assert "cta" not in result


@pytest.mark.asyncio
async def test_response_generator_does_not_add_continuation_on_continuation_turn():
    fake_llm = AsyncMock()
    fake_llm.ainvoke = AsyncMock(
        return_value=SimpleNamespace(
            content=_structured_content("Сервис подключается к базе знаний.")
        )
    )
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
                "decision": "RESPOND_KB",
                "user_input": "Да",
                "topic": "product",
                "turn_relation": "continuation",
                "cta": "continue_explanation",
                "project_configuration": {},
                **_retrieved_state(),
            }
        )

    assert result["response_text"] == "Сервис подключается к базе знаний."
    assert "cta" not in result


@pytest.mark.asyncio
async def test_response_generator_does_not_add_continuation_after_language_fallback():
    fake_llm = AsyncMock()
    fake_llm.ainvoke = AsyncMock(
        return_value=SimpleNamespace(
            content=_structured_content("I can explain how the product works.")
        )
    )
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
                "decision": "RESPOND_KB",
                "user_input": "Что умеет сервис?",
                "topic": "product",
                "turn_relation": "new_topic",
                "cta": "none",
                "project_configuration": {},
                **_retrieved_state(),
            }
        )

    assert "Хочу ответить на вашем языке корректно" in result["response_text"]
    assert "Хотите узнать больше" not in result["response_text"]
    assert "cta" not in result


@pytest.mark.asyncio
async def test_response_generator_builds_project_override_llm():
    created_models = []

    class FakeChatGroq:
        def __init__(self, *, model, temperature, max_tokens, api_key):
            created_models.append(model)

        async def ainvoke(self, _messages):
            return SimpleNamespace(content=_structured_content("override"))

    base_llm = AsyncMock()
    base_llm.ainvoke = AsyncMock(
        return_value=SimpleNamespace(content=_structured_content("base"))
    )

    with patch("src.infrastructure.llm.completion_client.ChatGroq", FakeChatGroq):
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
                    **_retrieved_state(),
                }
            )

    assert "Хочу ответить на вашем языке корректно" in result["response_text"]
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
                **_retrieved_state(),
            }
        )

    assert result["response_text"] == (
        "Не получилось сгенерировать ответ из-за технической ошибки. "
        "Можете повторить запрос, а если вопрос срочный — я передам диалог менеджеру."
    )
    assert result["technical_failure_count"] == 1
    assert result["technical_failure_stage"] == "response_generator"
    assert result["technical_failure_error"] == "RuntimeError"
    assert result["requires_human"] is False
    logger.exception.assert_called_once()
    assert (
        logger.exception.call_args.kwargs["extra"]["policy"]
        == "technical_failure_user_choice"
    )


@pytest.mark.asyncio
async def test_response_generator_repeated_llm_failure_uses_incident_text():
    fake_llm = AsyncMock()
    fake_llm.ainvoke = AsyncMock(side_effect=RuntimeError("llm unavailable"))
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
                "user_input": "Привет ещё раз",
                "project_configuration": {},
                "technical_failure_count": 1,
                **_retrieved_state(),
            }
        )

    assert result["technical_failure_count"] == 2
    assert "технический инцидент" in result["response_text"].lower()
    assert result["requires_human"] is False


@pytest.mark.asyncio
async def test_response_generator_language_guard_ru_input_en_output_uses_fallback():
    fake_llm = AsyncMock()
    fake_llm.ainvoke = AsyncMock(
        return_value=SimpleNamespace(
            content=_structured_content("I can help you with pricing details.")
        )
    )
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
                "user_input": "Подскажи, сколько стоит тариф Pro?",
                "project_configuration": {},
                **_retrieved_state(),
            }
        )

    assert "Хочу ответить на вашем языке корректно" in result["response_text"]


@pytest.mark.asyncio
async def test_response_generator_language_guard_allows_en_input_en_output():
    fake_llm = AsyncMock()
    fake_llm.ainvoke = AsyncMock(
        return_value=SimpleNamespace(
            content=_structured_content("The Pro plan starts at 2490 RUB monthly.")
        )
    )
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
                "user_input": "How much does Pro plan cost?",
                "project_configuration": {},
                **_retrieved_state("The Pro plan starts at 2490 RUB monthly."),
            }
        )

    assert result["response_text"] == "The Pro plan starts at 2490 RUB monthly."


@pytest.mark.asyncio
async def test_response_generator_language_guard_uses_project_target_language_es():
    llm = AsyncMock()
    llm.ainvoke.return_value = MagicMock(
        content=_structured_content("Hello, this is in English")
    )
    node = create_response_generator_node(llm=llm, model_name="base-model")

    async def passthrough(_name, impl, state, **_kwargs):
        return await impl(state)

    with patch(
        "src.agent.nodes.response_generator.log_node_execution",
        side_effect=passthrough,
    ):
        result = await node(
            {
                "decision": "LLM_GENERATE",
                "user_input": "Necesito ayuda con mi pedido",
                "project_configuration": {"settings": {"target_language": "es"}},
                **_retrieved_state(),
            }
        )

    assert result["response_text"].startswith("Quiero responder correctamente")


@pytest.mark.asyncio
async def test_response_generator_language_guard_uses_project_target_language_de():
    llm = AsyncMock()
    llm.ainvoke.return_value = MagicMock(
        content=_structured_content("Привет, отвечаю по-русски")
    )
    node = create_response_generator_node(llm=llm, model_name="base-model")

    async def passthrough(_name, impl, state, **_kwargs):
        return await impl(state)

    with patch(
        "src.agent.nodes.response_generator.log_node_execution",
        side_effect=passthrough,
    ):
        result = await node(
            {
                "decision": "LLM_GENERATE",
                "user_input": "Bitte helfen Sie mir",
                "project_configuration": {"settings": {"target_language": "de"}},
                **_retrieved_state(),
            }
        )

    assert result["response_text"].startswith("Ich möchte korrekt")


@pytest.mark.asyncio
async def test_response_generator_abstains_for_unsupported_widget_claim():
    llm = AsyncMock()
    llm.ainvoke = AsyncMock(
        return_value=SimpleNamespace(
            content=_structured_content(
                None,
                answerability="unsupported",
                supporting_entry_ids=[],
                unsupported_aspects=["named capability"],
            )
        )
    )
    node = create_response_generator_node(
        llm=llm,
        model_name="llama-3.3-70b-versatile",
    )

    result = await node(
        {
            "user_input": "Можно ли встроить Axole как чат-виджет на сайт?",
            "decision": "LLM_GENERATE",
            "knowledge_chunks": [
                {
                    "id": "entry-1",
                    "score": 0.9,
                    "content": "Axole помогает обрабатывать обращения в Telegram.",
                }
            ],
            "knowledge_retrieval_status": "retrieved",
            "generation_mode": "KNOWLEDGE_ANSWER",
            "project_configuration": {"settings": {"target_language": "ru"}},
        }
    )

    assert result["response_text"] == (
        "В доступной базе знаний нет данных, позволяющих подтвердить это."
    )
    assert result["model_answerability"] == "unsupported"
    assert result["semantic_grounding_status"] == "not_applicable"
    llm.ainvoke.assert_awaited_once()


@pytest.mark.asyncio
async def test_response_generator_distinguishes_empty_retrieval_without_llm_call():
    llm = AsyncMock()
    llm.ainvoke = AsyncMock(
        return_value=SimpleNamespace(content=_structured_content("Не должно уйти."))
    )
    node = create_response_generator_node(
        llm=llm,
        model_name="llama-3.3-70b-versatile",
    )

    result = await node(
        {
            "user_input": "Axole интегрируется с Bitrix24?",
            "decision": "LLM_GENERATE",
            "knowledge_chunks": [],
            "knowledge_retrieval_status": "empty",
            "generation_mode": "KNOWLEDGE_ANSWER",
            "project_configuration": {"settings": {"target_language": "ru"}},
        }
    )

    assert result["response_text"] == (
        "В доступной базе знаний нет данных, позволяющих подтвердить это."
    )
    assert result["model_answerability"] is None
    assert result["semantic_grounding_status"] == "not_applicable"
    assert result["fallback_reason"] == "no_evidence"
    llm.ainvoke.assert_not_called()


@pytest.mark.asyncio
async def test_response_generator_distinguishes_retrieval_failure_without_llm_call():
    llm = AsyncMock()
    node = create_response_generator_node(
        llm=llm,
        model_name="llama-3.3-70b-versatile",
    )

    result = await node(
        {
            "user_input": "Можно встроить чат-виджет?",
            "decision": "LLM_GENERATE",
            "knowledge_chunks": [],
            "knowledge_retrieval_status": "failed",
            "generation_mode": "KNOWLEDGE_ANSWER",
            "knowledge_retrieval_error_type": "knowledge_search_failed",
            "project_configuration": {"settings": {"target_language": "ru"}},
        }
    )

    assert result["response_text"] == (
        "Сейчас не получается проверить базу знаний из-за технической ошибки."
    )
    assert result["model_answerability"] is None
    assert result["semantic_grounding_status"] == "not_applicable"
    assert result["fallback_reason"] == "retrieval_failed"
    llm.ainvoke.assert_not_called()


@pytest.mark.asyncio
async def test_response_generator_rejects_invalid_structured_output():
    llm = AsyncMock()
    llm.ainvoke = AsyncMock(return_value=SimpleNamespace(content="plain answer"))
    node = create_response_generator_node(
        llm=llm,
        model_name="llama-3.3-70b-versatile",
    )

    result = await node(
        {
            "user_input": "Можно загрузить Excel?",
            "decision": "LLM_GENERATE",
            "project_configuration": {"settings": {"target_language": "ru"}},
            **_retrieved_state("База описывает загрузку PDF документов."),
        }
    )

    assert result["response_text"] == (
        "Сейчас не получилось сформировать корректный ответ по доступной базе знаний."
    )
    assert result["generation_output_parse_status"] == "invalid_json"
    assert result["generation_schema_status"] == "invalid_payload"
    assert result["evidence_reference_status"] == "not_called"
    assert result["semantic_grounding_status"] == "not_applicable"
    assert result["fallback_reason"] == "invalid_json"


@pytest.mark.asyncio
async def test_response_generator_rejects_invalid_supporting_entry_id():
    llm = AsyncMock()
    llm.ainvoke = AsyncMock(
        return_value=SimpleNamespace(
            content=_structured_content(
                "Да, возможность подтверждена.",
                supporting_entry_ids=["missing-entry"],
            )
        )
    )
    node = create_response_generator_node(
        llm=llm,
        model_name="llama-3.3-70b-versatile",
    )

    result = await node(
        {
            "user_input": "Поддерживается Bitrix24?",
            "decision": "LLM_GENERATE",
            "project_configuration": {"settings": {"target_language": "ru"}},
            **_retrieved_state("Система используется в CRM-процессах."),
        }
    )

    assert result["response_text"] == (
        "Сейчас не получилось сформировать корректный ответ по доступной базе знаний."
    )
    assert result["generation_schema_status"] == "valid"
    assert result["evidence_reference_status"] == "unknown_refs"
    assert result["semantic_grounding_status"] == "not_applicable"
    assert result["fallback_reason"] == "invalid_supporting_evidence_refs"


@pytest.mark.asyncio
async def test_response_generator_existing_id_does_not_prove_semantic_support():
    llm = AsyncMock()
    llm.ainvoke = AsyncMock(
        return_value=SimpleNamespace(
            content=_structured_content(
                "Да, конкретная интеграция поддерживается.",
                supporting_entry_ids=["entry-1"],
            )
        )
    )
    node = create_response_generator_node(
        llm=llm,
        model_name="llama-3.3-70b-versatile",
    )

    result = await node(
        {
            "user_input": "Поддерживается конкретная интеграция?",
            "decision": "LLM_GENERATE",
            "project_configuration": {"settings": {"target_language": "ru"}},
            **_retrieved_state("Система применяется в общих CRM-процессах."),
        }
    )

    assert result["response_text"] == "Да, конкретная интеграция поддерживается."
    assert result["generation_output_parse_status"] == "valid"
    assert result["generation_schema_status"] == "valid"
    assert result["evidence_reference_status"] == "valid"
    assert result["semantic_grounding_status"] == "unchecked"
    assert result["metadata"]["generation_attempt_count"] == 1
    assert result["metadata"]["initial_validation_failure_reason"] is None
    assert result["metadata"]["repair_attempted"] is False
    assert result["metadata"]["repair_validation_failure_reason"] is None
    assert result["metadata"]["repair_succeeded"] is False


@pytest.mark.asyncio
async def test_response_generator_rejects_supported_without_ids():
    llm = AsyncMock()
    llm.ainvoke = AsyncMock(
        return_value=SimpleNamespace(
            content=_structured_content(
                "Да, поддерживается.",
                supporting_entry_ids=[],
            )
        )
    )
    node = create_response_generator_node(
        llm=llm,
        model_name="llama-3.3-70b-versatile",
    )

    result = await node(
        {
            "user_input": "Поддерживается возможность?",
            "decision": "LLM_GENERATE",
            "project_configuration": {"settings": {"target_language": "ru"}},
            **_retrieved_state(),
        }
    )

    assert result["evidence_reference_status"] == "missing_required_refs"
    assert result["fallback_reason"] == "missing_supporting_evidence_refs"
    assert "Да, поддерживается" not in result["response_text"]


@pytest.mark.asyncio
async def test_response_generator_rejects_partial_without_unsupported_aspects():
    llm = AsyncMock()
    llm.ainvoke = AsyncMock(
        return_value=SimpleNamespace(
            content=_structured_content(
                "Подтверждена только часть ответа.",
                answerability="partially_supported",
                supporting_entry_ids=["entry-1"],
                unsupported_aspects=[],
            )
        )
    )
    node = create_response_generator_node(
        llm=llm,
        model_name="llama-3.3-70b-versatile",
    )

    result = await node(
        {
            "user_input": "Расскажите всё о запуске и сроках.",
            "decision": "LLM_GENERATE",
            "project_configuration": {"settings": {"target_language": "ru"}},
            **_retrieved_state(),
        }
    )

    assert result["generation_schema_status"] == "invalid_answerability_contract"
    assert result["fallback_reason"] == "missing_unsupported_aspects"


@pytest.mark.asyncio
async def test_response_generator_rejects_unsupported_with_free_text_answer():
    llm = AsyncMock()
    llm.ainvoke = AsyncMock(
        return_value=SimpleNamespace(
            content=_structured_content(
                "В базе нет подтверждения.",
                answerability="unsupported",
                supporting_entry_ids=[],
                unsupported_aspects=["requested capability"],
            )
        )
    )
    node = create_response_generator_node(
        llm=llm,
        model_name="llama-3.3-70b-versatile",
    )

    result = await node(
        {
            "user_input": "Есть ли такая возможность?",
            "decision": "LLM_GENERATE",
            "project_configuration": {"settings": {"target_language": "ru"}},
            **_retrieved_state(),
        }
    )

    assert result["generation_schema_status"] == "invalid_answerability_contract"
    assert result["fallback_reason"] == "unsupported_answer_must_be_empty"
    assert result["response_text"] == (
        "Сейчас не получилось сформировать корректный ответ по доступной базе знаний."
    )


@pytest.mark.asyncio
async def test_response_generator_does_not_lexically_ground_negative_paraphrase():
    llm = AsyncMock()
    llm.ainvoke = AsyncMock(
        return_value=SimpleNamespace(
            content=_structured_content("Загрузка файлов этого типа доступна.")
        )
    )
    node = create_response_generator_node(
        llm=llm,
        model_name="llama-3.3-70b-versatile",
    )

    result = await node(
        {
            "user_input": "Можно загрузить Excel?",
            "decision": "LLM_GENERATE",
            "project_configuration": {"settings": {"target_language": "ru"}},
            **_retrieved_state("Импорт этого типа файлов отключён."),
        }
    )

    assert result["response_text"] == "Загрузка файлов этого типа доступна."
    assert result["generation_output_parse_status"] == "valid"
    assert result["generation_schema_status"] == "valid"
    assert result["evidence_reference_status"] == "valid"
    assert result["semantic_grounding_status"] == "unchecked"


@pytest.mark.asyncio
async def test_response_generator_rejects_conflict_without_two_valid_ids():
    llm = AsyncMock()
    llm.ainvoke = AsyncMock(
        return_value=SimpleNamespace(
            content=_structured_content(
                None,
                answerability="conflicting_evidence",
                supporting_entry_ids=["entry-1"],
                unsupported_aspects=[],
            )
        )
    )
    node = create_response_generator_node(
        llm=llm,
        model_name="llama-3.3-70b-versatile",
    )

    result = await node(
        {
            "user_input": "Поддерживается ли интеграция?",
            "decision": "LLM_GENERATE",
            "project_configuration": {"settings": {"target_language": "ru"}},
            **_retrieved_state(),
        }
    )

    assert result["evidence_reference_status"] == "invalid_for_answerability"
    assert (
        result["fallback_reason"] == "conflicting_evidence_requires_two_supporting_refs"
    )


@pytest.mark.asyncio
async def test_response_generator_handles_conflicting_evidence():
    llm = AsyncMock()
    llm.ainvoke = AsyncMock(
        return_value=SimpleNamespace(
            content=_structured_content(
                None,
                answerability="conflicting_evidence",
                supporting_entry_ids=["entry-1", "entry-2"],
                unsupported_aspects=["conflicting fragments"],
            )
        )
    )
    node = create_response_generator_node(
        llm=llm,
        model_name="llama-3.3-70b-versatile",
    )

    result = await node(
        {
            "user_input": "Поддерживается ли интеграция?",
            "decision": "LLM_GENERATE",
            "knowledge_chunks": [
                {
                    "id": "entry-1",
                    "score": 0.9,
                    "content": "Интеграция поддерживается.",
                },
                {
                    "id": "entry-2",
                    "score": 0.8,
                    "content": "Интеграция не поддерживается.",
                },
            ],
            "knowledge_retrieval_status": "retrieved",
            "generation_mode": "KNOWLEDGE_ANSWER",
            "project_configuration": {"settings": {"target_language": "ru"}},
        }
    )

    assert result["response_text"] == (
        "В доступной базе знаний есть противоречивые сведения, поэтому я не могу уверенно ответить."
    )
    assert result["model_answerability"] == "conflicting_evidence"
    assert result["evidence_reference_status"] == "valid"
    assert result["semantic_grounding_status"] == "not_applicable"


@pytest.mark.asyncio
async def test_response_generator_allows_partial_process_without_timeline_duration():
    llm = AsyncMock()
    llm.ainvoke = AsyncMock(
        return_value=SimpleNamespace(
            content=_structured_content(
                "Запуск описан этапами: настройка базы знаний и подключение бота. Срок в днях не подтверждён.",
                answerability="partially_supported",
                supporting_entry_ids=["entry-1"],
                unsupported_aspects=["duration in days"],
            )
        )
    )
    node = create_response_generator_node(
        llm=llm,
        model_name="llama-3.3-70b-versatile",
    )

    result = await node(
        {
            "user_input": "Сколько дней занимает запуск?",
            "decision": "LLM_GENERATE",
            "project_configuration": {"settings": {"target_language": "ru"}},
            **_retrieved_state(
                "Запуск включает настройку базы знаний и подключение бота."
            ),
        }
    )

    assert "Срок в днях не подтверждён" in result["response_text"]
    assert "answerability" not in result
    assert result["model_answerability"] == "partially_supported"
    assert result["unsupported_aspects"] == ["duration in days"]
    assert result["semantic_grounding_status"] == "unchecked"


@pytest.mark.asyncio
async def test_response_generator_tool_result_mode_works_without_kb_chunks():
    llm = AsyncMock()
    llm.ainvoke = AsyncMock(
        return_value=SimpleNamespace(
            content=_structured_content(
                "Действие выполнено: найдено 3 записи.",
                supporting_entry_ids=[],
            )
        )
    )
    node = create_response_generator_node(
        llm=llm,
        model_name="llama-3.3-70b-versatile",
    )

    result = await node(
        {
            "user_input": "Проверь записи",
            "decision": "CALL_TOOL",
            "generation_mode": "TOOL_RESULT_RESPONSE",
            "tool_result": {"ok": True, "text": "found 3 records"},
            "tool_execution_status": "succeeded",
            "knowledge_chunks": [],
            "knowledge_retrieval_status": "skipped",
            "project_configuration": {"settings": {"target_language": "ru"}},
        }
    )

    assert result["response_text"] == "Действие выполнено: найдено 3 записи."
    assert result["generation_mode"] == "TOOL_RESULT_RESPONSE"
    assert result["evidence_reference_status"] == "not_applicable"
    assert result["semantic_grounding_status"] == "unchecked"
    llm.ainvoke.assert_awaited_once()


@pytest.mark.asyncio
async def test_response_generator_tool_failure_is_not_kb_failure_or_unsupported():
    llm = AsyncMock()
    node = create_response_generator_node(
        llm=llm,
        model_name="llama-3.3-70b-versatile",
    )

    result = await node(
        {
            "user_input": "Выполни действие",
            "decision": "CALL_TOOL",
            "generation_mode": "TOOL_RESULT_RESPONSE",
            "tool_result": {"ok": False, "text": "tool failed"},
            "tool_execution_status": "failed",
            "knowledge_chunks": [],
            "knowledge_retrieval_status": "skipped",
            "project_configuration": {"settings": {"target_language": "ru"}},
        }
    )

    assert result["response_text"] == (
        "Не получилось выполнить запрошенное действие из-за технической ошибки."
    )
    assert result["fallback_reason"] == "tool_failed"
    assert result["model_answerability"] is None
    llm.ainvoke.assert_not_called()


@pytest.mark.asyncio
async def test_response_generator_conversational_mode_allows_no_kb_chunks():
    llm = AsyncMock()
    llm.ainvoke = AsyncMock(
        return_value=SimpleNamespace(
            content=_structured_content(
                "Понял, продолжим без передачи менеджеру.",
                supporting_entry_ids=[],
            )
        )
    )
    node = create_response_generator_node(
        llm=llm,
        model_name="llama-3.3-70b-versatile",
    )

    result = await node(
        {
            "user_input": "Понятно, спасибо",
            "decision": "LLM_GENERATE",
            "generation_mode": "CONVERSATIONAL_RESPONSE",
            "knowledge_chunks": [],
            "knowledge_retrieval_status": "skipped",
            "project_configuration": {"settings": {"target_language": "ru"}},
        }
    )

    assert result["response_text"] == "Понял, продолжим без передачи менеджеру."
    assert result["generation_mode"] == "CONVERSATIONAL_RESPONSE"
    assert result["evidence_reference_status"] == "not_applicable"
    llm.ainvoke.assert_awaited_once()


@pytest.mark.asyncio
async def test_response_generator_strips_orphan_action_offer_question():
    llm = AsyncMock()
    llm.ainvoke = AsyncMock(
        return_value=SimpleNamespace(
            content=_structured_content(
                "Axole помогает отвечать клиентам. Могу передать вопрос менеджеру?"
            )
        )
    )
    node = create_response_generator_node(
        llm=llm,
        model_name="llama-3.3-70b-versatile",
    )

    result = await node(
        {
            "user_input": "Что такое Axole?",
            "decision": "LLM_GENERATE",
            "topic": "product",
            "project_configuration": {"settings": {"target_language": "ru"}},
            **_retrieved_state(),
        }
    )

    assert "менеджеру?" not in result["response_text"].lower()
    assert result.get("cta") == "continue_explanation"
    assert result["metadata"]["generated_action_cta_detected"] is True


@pytest.mark.asyncio
async def test_response_generator_sets_continuation_cta_for_benign_generated_question():
    llm = AsyncMock()
    llm.ainvoke = AsyncMock(
        return_value=SimpleNamespace(
            content=_structured_content("В проекте есть роли клиента и менеджера.")
        )
    )
    node = create_response_generator_node(
        llm=llm,
        model_name="llama-3.3-70b-versatile",
    )

    result = await node(
        {
            "user_input": "Какие роли есть в проекте?",
            "decision": "LLM_GENERATE",
            "topic": "product",
            "turn_relation": "new_topic",
            "dialog_state": {"repeat_count": 1},
            "project_configuration": {"settings": {"target_language": "ru"}},
            **_retrieved_state("В проекте есть роли клиента и менеджера."),
        }
    )

    assert result["cta"] == "continue_explanation"
    assert result["topic"] == "product"


@pytest.mark.asyncio
async def test_response_generator_rejects_cjk_contaminated_russian_response():
    llm = AsyncMock()
    llm.ainvoke = AsyncMock(
        return_value=SimpleNamespace(
            content=_structured_content("Для более详ной консультации напишите.")
        )
    )
    node = create_response_generator_node(
        llm=llm,
        model_name="llama-3.3-70b-versatile",
    )

    result = await node(
        {
            "user_input": "Расскажите подробнее",
            "decision": "LLM_GENERATE",
            "project_configuration": {"settings": {"target_language": "ru"}},
            **_retrieved_state(),
        }
    )

    assert result["response_text"].startswith("Хочу ответить")


@pytest.mark.asyncio
async def test_response_generator_rejects_missing_generation_mode_without_inference():
    llm = AsyncMock()
    llm.ainvoke = AsyncMock(
        return_value=SimpleNamespace(content=_structured_content("ok"))
    )
    node = create_response_generator_node(llm=llm, model_name="base-model")

    result = await node(
        {
            "decision": "LLM_GENERATE",
            "user_input": "action-only",
            "knowledge_chunks": [{"id": "entry-1", "score": 0.9, "content": "????."}],
            "knowledge_retrieval_status": "retrieved",
            "project_configuration": {"settings": {"target_language": "ru"}},
        }
    )

    assert result["fallback_reason"] == "generation_mode_contract_violation"
    assert result["model_answerability"] is None
    assert "???????????" not in result["response_text"].lower()
    llm.ainvoke.assert_not_called()


@pytest.mark.asyncio
async def test_response_generator_stale_tool_result_does_not_switch_knowledge_mode():
    llm = AsyncMock()
    llm.ainvoke = AsyncMock(
        return_value=SimpleNamespace(content=_structured_content("????? ?? KB."))
    )
    node = create_response_generator_node(llm=llm, model_name="base-model")

    result = await node(
        {
            "decision": "LLM_GENERATE",
            "generation_mode": "KNOWLEDGE_ANSWER",
            "user_input": "action-only",
            "tool_result": {"ok": True, "text": "stale"},
            **_retrieved_state("KB fact."),
            "project_configuration": {"settings": {"target_language": "ru"}},
        }
    )

    assert result["generation_mode"] == "KNOWLEDGE_ANSWER"
    assert result["response_text"] == "????? ?? KB."
    llm.ainvoke.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("retrieval_status", "chunks"),
    [
        ("skipped", []),
        ("unknown", [{"id": "entry-1", "score": 0.9, "content": "????."}]),
    ],
)
async def test_response_generator_rejects_invalid_knowledge_retrieval_invariants(
    retrieval_status, chunks
):
    llm = AsyncMock()
    node = create_response_generator_node(llm=llm, model_name="base-model")

    result = await node(
        {
            "decision": "LLM_GENERATE",
            "generation_mode": "KNOWLEDGE_ANSWER",
            "user_input": "action-only",
            "knowledge_chunks": chunks,
            "knowledge_retrieval_status": retrieval_status,
            "project_configuration": {"settings": {"target_language": "ru"}},
        }
    )

    assert result["fallback_reason"] == "retrieval_contract_violation"
    assert "?????????????" not in result["response_text"].lower()
    llm.ainvoke.assert_not_called()


@pytest.mark.asyncio
async def test_response_generator_replaces_cta_only_answer_with_non_action_fallback():
    llm = AsyncMock()
    llm.ainvoke = AsyncMock(
        return_value=SimpleNamespace(
            content=_structured_content("Can I call a manager?")
        )
    )
    node = create_response_generator_node(llm=llm, model_name="base-model")

    result = await node(
        {
            "decision": "LLM_GENERATE",
            "generation_mode": "KNOWLEDGE_ANSWER",
            "user_input": "action-only",
            "topic": "product",
            "cta": "none",
            **_retrieved_state(),
            "project_configuration": {"settings": {"target_language": "en"}},
        }
    )

    assert result["response_text"]
    assert result["response_text"] != "Can I call a manager?"
    assert result.get("cta") is None
    assert result["fallback_reason"] == "orphan_action_cta_removed"
    assert result["metadata"]["generated_action_cta_detected"] is True


@pytest.mark.asyncio
async def test_response_generator_rejects_success_without_payload_or_response_text():
    llm = AsyncMock()
    node = create_response_generator_node(llm=llm, model_name="base-model")

    result = await node(
        {
            "decision": "CALL_TOOL",
            "generation_mode": "TOOL_RESULT_RESPONSE",
            "tool_execution_status": "succeeded",
            "tool_result": None,
            "knowledge_chunks": [],
            "knowledge_retrieval_status": "skipped",
            "project_configuration": {"settings": {"target_language": "ru"}},
        }
    )

    assert result["fallback_reason"] == "tool_result_contract_violation"
    llm.ainvoke.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_result", [{}, [], ""])
async def test_response_generator_accepts_explicit_empty_tool_payloads(tool_result):
    llm = AsyncMock()
    llm.ainvoke = AsyncMock(
        return_value=SimpleNamespace(
            content=_structured_content(
                "Tool operation completed.",
                supporting_entry_ids=[],
            )
        )
    )
    node = create_response_generator_node(llm=llm, model_name="base-model")

    result = await node(
        {
            "decision": "CALL_TOOL",
            "generation_mode": "TOOL_RESULT_RESPONSE",
            "tool_execution_status": "succeeded",
            "tool_result": tool_result,
            "knowledge_chunks": [],
            "knowledge_retrieval_status": "skipped",
            "project_configuration": {"settings": {"target_language": "en"}},
        }
    )

    assert result["response_text"] == "Tool operation completed."
    assert result["fallback_reason"] is None
    llm.ainvoke.assert_awaited_once()


@pytest.mark.asyncio
async def test_response_generator_accepts_success_without_payload_with_response_text():
    llm = AsyncMock()
    node = create_response_generator_node(llm=llm, model_name="base-model")

    result = await node(
        {
            "decision": "CALL_TOOL",
            "generation_mode": "TOOL_RESULT_RESPONSE",
            "tool_execution_status": "succeeded",
            "tool_result": None,
            "tool_response_text": "Done.",
            "knowledge_chunks": [],
            "knowledge_retrieval_status": "skipped",
            "project_configuration": {"settings": {"target_language": "en"}},
        }
    )

    assert result["response_text"] == "Done."
    assert result["fallback_reason"] is None
    llm.ainvoke.assert_not_called()


@pytest.mark.asyncio
async def test_response_generator_accepts_scalar_tool_payload_when_status_succeeded():
    llm = AsyncMock()
    llm.ainvoke = AsyncMock(
        return_value=SimpleNamespace(
            content=_structured_content(
                "Tool value: done",
                supporting_entry_ids=[],
            )
        )
    )
    node = create_response_generator_node(llm=llm, model_name="base-model")

    result = await node(
        {
            "decision": "CALL_TOOL",
            "generation_mode": "TOOL_RESULT_RESPONSE",
            "tool_execution_status": "succeeded",
            "tool_result": "done",
            "knowledge_chunks": [],
            "knowledge_retrieval_status": "skipped",
            "project_configuration": {"settings": {"target_language": "en"}},
        }
    )

    assert result["response_text"] == "Tool value: done"
    assert result["evidence_reference_status"] == "not_applicable"
    llm.ainvoke.assert_awaited_once()


@pytest.mark.asyncio
async def test_response_generator_rejects_missing_or_unknown_tool_status():
    llm = AsyncMock()
    node = create_response_generator_node(llm=llm, model_name="base-model")

    for status in (None, "unknown"):
        result = await node(
            {
                "decision": "CALL_TOOL",
                "generation_mode": "TOOL_RESULT_RESPONSE",
                "tool_execution_status": status,
                "tool_result": {"value": 1},
                "knowledge_chunks": [],
                "knowledge_retrieval_status": "skipped",
                "project_configuration": {"settings": {"target_language": "ru"}},
            }
        )
        assert result["fallback_reason"] == "tool_result_contract_violation"

    llm.ainvoke.assert_not_called()


@pytest.mark.asyncio
async def test_response_generator_rejects_requires_human_tool_status_in_generator():
    llm = AsyncMock()
    node = create_response_generator_node(llm=llm, model_name="base-model")

    result = await node(
        {
            "decision": "CALL_TOOL",
            "generation_mode": "TOOL_RESULT_RESPONSE",
            "tool_execution_status": "requires_human",
            "tool_result": {"reason": "manual"},
            "knowledge_chunks": [],
            "knowledge_retrieval_status": "skipped",
            "project_configuration": {"settings": {"target_language": "ru"}},
        }
    )

    assert result["fallback_reason"] == "tool_result_contract_violation"
    llm.ainvoke.assert_not_called()


@pytest.mark.asyncio
async def test_response_generator_rejects_non_kb_response_with_supporting_refs():
    llm = AsyncMock()
    llm.ainvoke = AsyncMock(
        return_value=SimpleNamespace(
            content=_structured_content("??????.", supporting_entry_ids=["kb-entry"])
        )
    )
    node = create_response_generator_node(llm=llm, model_name="base-model")

    result = await node(
        {
            "decision": "CALL_TOOL",
            "generation_mode": "TOOL_RESULT_RESPONSE",
            "tool_execution_status": "succeeded",
            "tool_result": {"value": 1},
            "knowledge_chunks": [],
            "knowledge_retrieval_status": "skipped",
            "project_configuration": {"settings": {"target_language": "ru"}},
        }
    )

    assert result["fallback_reason"] == "non_kb_response_with_supporting_refs"
    assert result["evidence_reference_status"] == "not_applicable"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "answerability", ["partially_supported", "conflicting_evidence", "unsupported"]
)
async def test_response_generator_rejects_conversational_non_supported_answerability(
    answerability,
):
    llm = AsyncMock()
    llm.ainvoke = AsyncMock(
        return_value=SimpleNamespace(
            content=_structured_content(
                None if answerability != "partially_supported" else "partial",
                answerability=answerability,
                supporting_entry_ids=[],
                unsupported_aspects=["x"],
            )
        )
    )
    node = create_response_generator_node(llm=llm, model_name="base-model")

    result = await node(
        {
            "decision": "LLM_GENERATE",
            "generation_mode": "CONVERSATIONAL_RESPONSE",
            "user_input": "thanks",
            "knowledge_chunks": [],
            "knowledge_retrieval_status": "skipped",
            "project_configuration": {"settings": {"target_language": "en"}},
        }
    )

    assert result["fallback_reason"] == "non_kb_response_must_be_supported"


@pytest.mark.asyncio
async def test_response_generator_accepts_valid_tool_supported_response_with_no_ids():
    llm = AsyncMock()
    llm.ainvoke = AsyncMock(
        return_value=SimpleNamespace(
            content=_structured_content("Done.", supporting_entry_ids=[])
        )
    )
    node = create_response_generator_node(llm=llm, model_name="base-model")

    result = await node(
        {
            "decision": "CALL_TOOL",
            "generation_mode": "TOOL_RESULT_RESPONSE",
            "tool_execution_status": "succeeded",
            "tool_result": ["value"],
            "knowledge_chunks": [],
            "knowledge_retrieval_status": "skipped",
            "project_configuration": {"settings": {"target_language": "en"}},
        }
    )

    assert result["response_text"] == "Done."
    assert result["evidence_reference_status"] == "not_applicable"


@pytest.mark.asyncio
async def test_response_generator_repairs_legacy_supporting_entry_ids_once():
    llm = AsyncMock()
    llm.ainvoke = AsyncMock(
        side_effect=[
            SimpleNamespace(
                content=json.dumps(
                    {
                        "answerability": "supported",
                        "answer": "Факт подтверждён.",
                        "supporting_entry_ids": ["entry-1"],
                        "unsupported_aspects": [],
                    },
                    ensure_ascii=False,
                )
            ),
            SimpleNamespace(content=_structured_content("Факт подтверждён.")),
        ]
    )
    node = create_response_generator_node(llm=llm, model_name="base-model")

    result = await node(
        {
            "decision": "LLM_GENERATE",
            "generation_mode": "KNOWLEDGE_ANSWER",
            "user_input": "Что известно?",
            "project_configuration": {"settings": {"target_language": "ru"}},
            **_retrieved_state("Факт подтверждён в базе знаний."),
        }
    )

    assert result["response_text"] == "Факт подтверждён."
    assert result["model_evidence_refs"] == ["E1"]
    assert result["supporting_entry_ids"] == ["entry-1"]
    assert result["metadata"]["generation_attempt_count"] == 2
    assert result["metadata"]["initial_validation_failure_reason"] == (
        "legacy supporting_entry_ids field is forbidden"
    )
    assert result["metadata"]["repair_attempted"] is True
    assert result["metadata"]["repair_succeeded"] is True
    assert result["metadata"]["repair_validation_failure_reason"] is None
    llm.ainvoke.assert_awaited()
    assert llm.ainvoke.await_count == 2
    repair_prompt = llm.ainvoke.await_args_list[1].args[0][0][1]
    assert "Allowed evidence refs: E1" in repair_prompt
    repair_section = repair_prompt.split("The previous response did not satisfy", 1)[1]
    assert "entry-1" not in repair_section
    assert "supporting_entry_ids" in repair_section


@pytest.mark.asyncio
async def test_response_generator_repairs_unknown_evidence_ref_once():
    llm = AsyncMock()
    llm.ainvoke = AsyncMock(
        side_effect=[
            SimpleNamespace(
                content=_structured_content(
                    "Факт подтверждён.",
                    supporting_evidence_refs=["E9"],
                )
            ),
            SimpleNamespace(content=_structured_content("Факт подтверждён.")),
        ]
    )
    node = create_response_generator_node(llm=llm, model_name="base-model")

    result = await node(
        {
            "decision": "LLM_GENERATE",
            "generation_mode": "KNOWLEDGE_ANSWER",
            "user_input": "Что известно?",
            "project_configuration": {"settings": {"target_language": "ru"}},
            **_retrieved_state("Факт подтверждён в базе знаний."),
        }
    )

    assert result["response_text"] == "Факт подтверждён."
    assert result["evidence_reference_status"] == "valid"
    assert result["metadata"]["initial_validation_failure_reason"] == (
        "invalid_supporting_evidence_refs"
    )
    assert result["metadata"]["repair_attempted"] is True
    assert result["metadata"]["repair_succeeded"] is True
    assert llm.ainvoke.await_count == 2


@pytest.mark.asyncio
async def test_response_generator_fallback_after_failed_repair_has_attempt_metadata():
    llm = AsyncMock()
    llm.ainvoke = AsyncMock(
        side_effect=[
            SimpleNamespace(content="{not json"),
            SimpleNamespace(
                content=_structured_content(
                    "Факт без refs.", supporting_evidence_refs=[]
                )
            ),
        ]
    )
    node = create_response_generator_node(llm=llm, model_name="base-model")

    result = await node(
        {
            "decision": "LLM_GENERATE",
            "generation_mode": "KNOWLEDGE_ANSWER",
            "user_input": "Что известно?",
            "project_configuration": {"settings": {"target_language": "ru"}},
            **_retrieved_state("Факт подтверждён в базе знаний."),
        }
    )

    assert result["fallback_reason"] == "missing_supporting_evidence_refs"
    assert result["metadata"]["generation_attempt_count"] == 2
    assert result["metadata"]["initial_validation_failure_reason"] == "invalid_json"
    assert result["metadata"]["repair_attempted"] is True
    assert result["metadata"]["repair_succeeded"] is False
    assert result["metadata"]["repair_validation_failure_reason"] == (
        "missing_supporting_evidence_refs"
    )
    assert llm.ainvoke.await_count == 2


@pytest.mark.asyncio
async def test_response_generator_language_fallback_does_not_trigger_repair():
    llm = AsyncMock()
    llm.ainvoke = AsyncMock(
        return_value=SimpleNamespace(content=_structured_content("Answer in English."))
    )
    node = create_response_generator_node(llm=llm, model_name="base-model")

    result = await node(
        {
            "decision": "LLM_GENERATE",
            "generation_mode": "KNOWLEDGE_ANSWER",
            "user_input": "Расскажите",
            "project_configuration": {"settings": {"target_language": "ru"}},
            **_retrieved_state("Факт подтверждён в базе знаний."),
        }
    )

    assert result["fallback_reason"] == "language_validation_failed"
    assert result["metadata"]["repair_attempted"] is False
    assert result["metadata"]["generation_attempt_count"] == 1
    assert llm.ainvoke.await_count == 1
