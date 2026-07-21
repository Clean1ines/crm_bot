from src.domain.runtime.intent_extraction import (
    IntentExtractionContext,
    IntentExtractionResult,
)


def test_intent_extraction_context_normalizes_state():
    context = IntentExtractionContext.from_state(
        {
            "user_input": "hello",
            "conversation_summary": "summary",
            "history": [{"role": "user", "content": "prev"}],
            "user_memory": {"facts": []},
        }
    )

    assert context.user_input == "hello"
    assert context.conversation_summary == "summary"
    assert context.history == [{"role": "user", "content": "prev"}]
    assert context.user_memory == {"facts": []}


def test_intent_extraction_result_serializes_validated_payload():
    result = IntentExtractionResult.from_llm_payload(
        {
            "intent": "support",
            "cta": "none",
            "features": {"crm": 0.8},
            "topic": "support",
            "cta_hint": None,
            "emotion": "negative",
            "is_repeat_like": True,
        }
    )

    assert result.to_state_patch() == {
        "intent": "support",
        "cta": "none",
        "features": {"crm": 0.8},
        "topic": "support",
        "cta_hint": None,
        "emotion": "negative",
        "is_repeat_like": True,
        "domain": "business",
        "turn_relation": "unknown",
        "should_search_kb": True,
        "should_generate_answer": True,
        "should_offer_manager": False,
        "knowledge_query": None,
        "resolved_cta": None,
        "resolved_cta_reply": None,
    }


def test_intent_extraction_result_explicitly_clears_turn_scoped_knowledge_query():
    result = IntentExtractionResult.from_llm_payload(
        {
            "intent": "sales",
            "cta": "none",
            "features": {},
            "topic": "product",
        }
    )

    assert "knowledge_query" in result.to_state_patch()
    assert result.to_state_patch()["knowledge_query"] is None
    assert result.to_state_patch()["resolved_cta"] is None
    assert result.to_state_patch()["resolved_cta_reply"] is None


def test_intent_extraction_context_keeps_previous_topic_and_cta_signals():
    context = IntentExtractionContext.from_state(
        {
            "user_input": "да",
            "topic": "pricing",
            "cta": "call_manager",
            "dialog_state": {
                "last_intent": "pricing",
                "last_cta": "call_manager",
                "last_topic": "pricing",
                "repeat_count": 1,
                "lead_status": "warm",
                "lifecycle": "warm",
            },
        }
    )

    assert context.topic == "pricing"
    assert context.cta == "call_manager"
    assert context.dialog_state is not None
    assert context.dialog_state["last_topic"] == "pricing"


def test_intent_extraction_normalizes_affirmative_short_reply_from_previous_cta():
    context = IntentExtractionContext.from_state(
        {
            "user_input": "да",
            "topic": "pricing",
            "cta": "call_manager",
        }
    )
    result = IntentExtractionResult.from_llm_payload(
        {
            "intent": "other",
            "cta": "none",
            "features": {},
            "topic": "other",
            "cta_hint": None,
            "emotion": "neutral",
            "is_repeat_like": False,
        }
    ).normalized_for_context(context)

    assert result.intent == "sales"
    assert result.topic == "pricing"
    assert result.cta == "call_manager"


def test_intent_extraction_ignores_none_cta_and_uses_persisted_action_cta():
    context = IntentExtractionContext.from_state(
        {
            "user_input": "Да",
            "topic": "pricing",
            "cta": "none",
            "dialog_state": {
                "last_intent": "pricing",
                "last_cta": "call_manager",
                "last_topic": "pricing",
                "repeat_count": 1,
                "lead_status": "warm",
                "lifecycle": "warm",
            },
        }
    )
    result = IntentExtractionResult.from_llm_payload(
        {
            "intent": "other",
            "cta": "none",
            "features": {},
            "topic": "other",
            "cta_hint": None,
            "emotion": "neutral",
            "is_repeat_like": False,
        }
    ).normalized_for_context(context)

    assert context.user_input == "Да"
    assert context.cta is None
    assert result.intent == "sales"
    assert result.topic == "pricing"
    assert result.cta == "call_manager"
    assert result.resolved_cta == "call_manager"
    assert result.resolved_cta_reply == "affirmative"
    assert result.should_search_kb is False


def test_intent_extraction_normalizes_affirmative_reply_from_assistant_action_cta():
    context = IntentExtractionContext.from_state(
        {
            "user_input": "Да",
            "history": [
                {
                    "role": "assistant",
                    "content": "Могу передать вопрос менеджеру. Передать?",
                }
            ],
        }
    )
    result = IntentExtractionResult.from_llm_payload(
        {
            "intent": "unknown",
            "cta": "none",
            "features": {},
            "topic": "other",
            "cta_hint": None,
            "emotion": "neutral",
            "is_repeat_like": False,
        }
    ).normalized_for_context(context)

    assert result.intent == "sales"
    assert result.cta == "call_manager"
    assert result.should_search_kb is False


def test_intent_extraction_normalizes_shared_affirmative_vocabulary():
    for user_input in ("Конечно", "Sure"):
        context = IntentExtractionContext.from_state(
            {
                "user_input": user_input,
                "dialog_state": {
                    "last_cta": "call_manager",
                    "last_topic": "product",
                },
            }
        )
        result = IntentExtractionResult.from_llm_payload(
            {
                "intent": "unknown",
                "cta": "none",
                "features": {},
                "topic": "other",
                "cta_hint": None,
                "emotion": "neutral",
                "is_repeat_like": False,
            }
        ).normalized_for_context(context)

        assert result.intent == "sales"
        assert result.cta == "call_manager"
        assert result.should_search_kb is False


def test_intent_extraction_normalizes_negative_reply_from_action_cta():
    context = IntentExtractionContext.from_state(
        {
            "user_input": "Нет",
            "dialog_state": {
                "last_cta": "call_manager",
                "last_topic": "product",
            },
        }
    )
    result = IntentExtractionResult.from_llm_payload(
        {
            "intent": "unknown",
            "cta": "none",
            "features": {},
            "topic": "other",
            "cta_hint": None,
            "emotion": "neutral",
            "is_repeat_like": False,
        }
    ).normalized_for_context(context)

    assert result.cta == "none"
    assert result.resolved_cta == "call_manager"
    assert result.resolved_cta_reply == "negative"
    assert result.should_offer_manager is False


def test_intent_extraction_normalizes_affirmative_reply_from_continuation_cta():
    context = IntentExtractionContext.from_state(
        {
            "user_input": "Да",
            "dialog_state": {
                "last_cta": "continue_explanation",
                "last_topic": "product",
            },
        }
    )
    result = IntentExtractionResult.from_llm_payload(
        {
            "intent": "unknown",
            "cta": "none",
            "features": {},
            "topic": "other",
            "cta_hint": None,
            "emotion": "neutral",
            "is_repeat_like": False,
        }
    ).normalized_for_context(context)

    assert context.user_input == "Да"
    assert result.cta == "continue_explanation"
    assert result.resolved_cta == "continue_explanation"
    assert result.resolved_cta_reply == "affirmative"
    assert result.topic == "product"
    assert result.turn_relation == "continuation"
    assert result.should_search_kb is True
    assert result.knowledge_query is not None
    assert result.knowledge_query != "Да"
    assert "продукт" in result.knowledge_query


def test_intent_extraction_localizes_continuation_knowledge_query():
    cases = (
        ("Да", "подробнее как работает продукт"),
        ("Yes", "more details about how the product works"),
        ("Ja", "weitere Einzelheiten zur Funktionsweise"),
        ("Sí", "más detalles sobre cómo funciona"),
    )

    for user_input, expected_query_part in cases:
        context = IntentExtractionContext.from_state(
            {
                "user_input": user_input,
                "dialog_state": {
                    "last_cta": "continue_explanation",
                    "last_topic": "product",
                },
            }
        )
        result = IntentExtractionResult.from_llm_payload(
            {
                "intent": "unknown",
                "cta": "none",
                "features": {},
                "topic": "other",
                "cta_hint": None,
                "emotion": "neutral",
                "is_repeat_like": False,
            }
        ).normalized_for_context(context)

        assert result.cta == "continue_explanation"
        assert result.turn_relation == "continuation"
        assert result.knowledge_query is not None
        assert expected_query_part in result.knowledge_query


def test_intent_extraction_normalizes_negative_reply_from_continuation_cta():
    context = IntentExtractionContext.from_state(
        {
            "user_input": "Нет",
            "dialog_state": {
                "last_cta": "continue_explanation",
                "last_topic": "product",
            },
        }
    )
    result = IntentExtractionResult.from_llm_payload(
        {
            "intent": "unknown",
            "cta": "none",
            "features": {},
            "topic": "other",
            "cta_hint": None,
            "emotion": "neutral",
            "is_repeat_like": False,
        }
    ).normalized_for_context(context)

    assert result.cta == "none"
    assert result.resolved_cta == "continue_explanation"
    assert result.resolved_cta_reply == "negative"
    assert result.turn_relation == "short_reply"
    assert result.should_search_kb is False
    assert result.should_offer_manager is False


def test_intent_extraction_does_not_invent_action_cta_for_short_yes_without_pending_cta():
    context = IntentExtractionContext.from_state({"user_input": "Да"})
    result = IntentExtractionResult.from_llm_payload(
        {
            "intent": "unknown",
            "cta": "none",
            "features": {},
            "topic": "other",
            "cta_hint": None,
            "emotion": "neutral",
            "is_repeat_like": False,
        }
    ).normalized_for_context(context)

    assert context.user_input == "Да"
    assert result.cta == "none"
    assert result.intent == "unknown"
    assert result.should_search_kb is True


def test_intent_extraction_later_yes_cannot_confirm_expired_cta():
    expired_dialog_state = {
        "last_intent": "pricing",
        "last_cta": None,
        "last_topic": "pricing",
        "repeat_count": 1,
        "lead_status": "warm",
        "lifecycle": "warm",
    }
    context = IntentExtractionContext.from_state(
        {
            "user_input": "Да",
            "dialog_state": expired_dialog_state,
        }
    )
    result = IntentExtractionResult.from_llm_payload(
        {
            "intent": "unknown",
            "cta": "none",
            "features": {},
            "topic": "other",
            "cta_hint": None,
            "emotion": "neutral",
            "is_repeat_like": False,
        }
    ).normalized_for_context(context)

    assert result.cta == "none"
    assert result.intent == "sales"
    assert result.topic == "pricing"
    assert result.should_search_kb is True
    assert result.knowledge_query is None


def test_intent_extraction_normalizes_price_objection_short_reply():
    context = IntentExtractionContext.from_state({"user_input": "дорого"})
    result = IntentExtractionResult.from_llm_payload(
        {
            "intent": "other",
            "cta": "book_consultation",
            "features": {},
            "topic": "other",
            "cta_hint": None,
            "emotion": "neutral",
            "is_repeat_like": False,
        }
    ).normalized_for_context(context)

    assert result.intent == "pricing"
    assert result.topic == "pricing"
    assert result.cta == "none"
    assert result.emotion == "negative"
    assert result.is_repeat_like is True


def test_intent_extraction_normalizes_issue_reply_with_integration_context():
    context = IntentExtractionContext.from_state(
        {
            "user_input": "не работает",
            "topic": "integration",
        }
    )
    result = IntentExtractionResult.from_llm_payload(
        {
            "intent": "other",
            "cta": "none",
            "features": {},
            "topic": "other",
            "cta_hint": None,
            "emotion": "neutral",
            "is_repeat_like": False,
        }
    ).normalized_for_context(context)

    assert result.intent == "support"
    assert result.topic == "integration"
    assert result.emotion == "negative"
