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
            "features": {"complaint": 0.8},
            "topic": "support",
            "cta_hint": None,
            "emotion": "negative",
            "is_repeat_like": True,
        }
    )

    assert result.to_state_patch() == {
        "intent": "support",
        "cta": "none",
        "features": {"complaint": 0.8},
        "topic": "support",
        "cta_hint": None,
        "emotion": "negative",
        "is_repeat_like": False,
        "domain": "business",
        "turn_relation": "unknown",
        "should_search_kb": True,
        "should_generate_answer": True,
        "should_offer_manager": False,
        "knowledge_query": None,
        "knowledge_query_source": "none",
        "resolved_cta": None,
        "resolved_cta_reply": None,
        "current_subject": None,
        "repeat_relation": "none",
        "dissatisfaction": False,
        "memory_candidates": [],
        "normalization_flags": {},
    }


def test_intent_extraction_filters_unrecognized_features():
    result = IntentExtractionResult.from_llm_payload(
        {
            "intent": "support",
            "cta": "none",
            "features": {"Axole": 1.0, "complaint": 0.9},
            "topic": "support",
        }
    )

    assert result.features == {"complaint": 0.9}


def test_intent_extraction_overrides_false_routing_flags_for_business_question():
    context = IntentExtractionContext.from_state(
        {"user_input": "Это обычный конструктор Telegram-ботов с кнопками?"}
    )
    result = IntentExtractionResult.from_llm_payload(
        {
            "domain": "business",
            "intent": "other",
            "topic": "product",
            "cta": "none",
            "features": {},
            "should_search_kb": False,
            "should_generate_answer": False,
        }
    ).normalized_for_context(context)

    assert result.should_search_kb is True
    assert result.should_generate_answer is True
    assert result.normalization_flags["routing_flag_override_reason"] == (
        "ordinary_business_question"
    )


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
    assert result.to_state_patch()["knowledge_query_source"] == "none"
    assert result.to_state_patch()["resolved_cta"] is None
    assert result.to_state_patch()["resolved_cta_reply"] is None


def test_intent_extraction_accepts_model_contextual_knowledge_query_for_continuation():
    context = IntentExtractionContext.from_state(
        {"user_input": "А роли?", "topic": "product"}
    )
    result = IntentExtractionResult.from_llm_payload(
        {
            "domain": "business",
            "intent": "other",
            "topic": "product",
            "cta": "none",
            "turn_relation": "continuation",
            "should_search_kb": True,
            "should_generate_answer": True,
            "knowledge_query": "какие роли есть в продукте",
        }
    ).normalized_for_context(context)

    assert result.knowledge_query == "какие роли есть в продукте"
    assert result.knowledge_query_source.value == "model_contextual"
    assert result.normalization_flags["knowledge_query_source"] == "model_contextual"
    assert result.to_state_patch()["knowledge_query_source"] == "model_contextual"


def test_intent_extraction_rejects_llm_knowledge_query_for_new_topic():
    result = IntentExtractionResult.from_llm_payload(
        {
            "domain": "business",
            "intent": "other",
            "topic": "product",
            "cta": "none",
            "turn_relation": "new_topic",
            "should_search_kb": True,
            "should_generate_answer": True,
            "knowledge_query": "какие роли есть в продукте",
        }
    )

    assert result.knowledge_query is None
    assert result.knowledge_query_source.value == "none"
    assert result.normalization_flags["knowledge_query_rejected_reason"] == (
        "not_contextual_turn"
    )


def test_intent_extraction_rejects_llm_knowledge_query_equal_to_user_input():
    context = IntentExtractionContext.from_state({"user_input": "Какие роли?"})
    result = IntentExtractionResult.from_llm_payload(
        {
            "domain": "business",
            "intent": "other",
            "topic": "product",
            "cta": "none",
            "turn_relation": "continuation",
            "should_search_kb": True,
            "should_generate_answer": True,
            "knowledge_query": " Какие   роли? ",
        }
    ).normalized_for_context(context)

    assert result.knowledge_query is None
    assert result.knowledge_query_source.value == "none"
    assert result.normalization_flags["knowledge_query_rejected_reason"] == (
        "same_as_user_input"
    )


def test_intent_extraction_rejects_too_long_llm_knowledge_query():
    result = IntentExtractionResult.from_llm_payload(
        {
            "domain": "business",
            "intent": "other",
            "topic": "product",
            "cta": "none",
            "turn_relation": "continuation",
            "should_search_kb": True,
            "should_generate_answer": True,
            "knowledge_query": "x" * 241,
        }
    )

    assert result.knowledge_query is None
    assert result.knowledge_query_source.value == "none"
    assert result.normalization_flags["knowledge_query_rejected_reason"] == "too_long"


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


def test_intent_extraction_price_objection_is_not_repeat_without_repeat_relation():
    result = IntentExtractionResult.from_llm_payload(
        {
            "intent": "pricing",
            "cta": "none",
            "features": {},
            "topic": "pricing",
            "emotion": "negative",
            "is_repeat_like": True,
            "repeat_relation": "none",
        }
    ).normalized_for_context(
        IntentExtractionContext.from_state({"user_input": "Дорого"})
    )

    assert result.intent == "pricing"
    assert result.is_repeat_like is False


def test_intent_extraction_issue_report_is_not_repeat_without_repeat_relation():
    result = IntentExtractionResult.from_llm_payload(
        {
            "intent": "support",
            "cta": "none",
            "features": {},
            "topic": "support",
            "emotion": "negative",
            "is_repeat_like": True,
            "repeat_relation": "none",
        }
    ).normalized_for_context(
        IntentExtractionContext.from_state({"user_input": "Не работает"})
    )

    assert result.intent == "support"
    assert result.is_repeat_like is False


def test_intent_extraction_price_objection_keeps_repeat_unresolved_true():
    result = IntentExtractionResult.from_llm_payload(
        {
            "intent": "pricing",
            "cta": "none",
            "features": {},
            "topic": "pricing",
            "is_repeat_like": False,
            "repeat_relation": "repeat_unresolved",
        }
    ).normalized_for_context(
        IntentExtractionContext.from_state({"user_input": "Дорого"})
    )

    assert result.repeat_relation == "repeat_unresolved"
    assert result.is_repeat_like is True


def test_intent_extraction_clarification_is_not_repeat_like():
    result = IntentExtractionResult.from_llm_payload(
        {
            "intent": "sales",
            "cta": "none",
            "features": {},
            "topic": "product",
            "is_repeat_like": True,
            "repeat_relation": "clarification",
        }
    ).normalized_for_context(
        IntentExtractionContext.from_state({"user_input": "А через неё?"})
    )

    assert result.repeat_relation == "clarification"
    assert result.is_repeat_like is False


def test_intent_extraction_repeat_relation_invariant_overrides_llm_contradiction():
    answered = IntentExtractionResult.from_llm_payload(
        {
            "intent": "sales",
            "cta": "none",
            "features": {},
            "topic": "product",
            "is_repeat_like": False,
            "repeat_relation": "repeat_answered",
        }
    ).normalized_for_context(
        IntentExtractionContext.from_state({"user_input": "Ещё раз"})
    )
    none = IntentExtractionResult.from_llm_payload(
        {
            "intent": "sales",
            "cta": "none",
            "features": {},
            "topic": "product",
            "is_repeat_like": True,
            "repeat_relation": "none",
        }
    ).normalized_for_context(
        IntentExtractionContext.from_state({"user_input": "Новая тема"})
    )

    assert answered.is_repeat_like is True
    assert none.is_repeat_like is False


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
    assert result.knowledge_query_source.value == "canonical_continue_explanation"
    assert result.to_state_patch()["knowledge_query_source"] == (
        "canonical_continue_explanation"
    )


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
        assert result.knowledge_query_source.value == "canonical_continue_explanation"
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
    assert result.knowledge_query is None
    assert result.knowledge_query_source.value == "none"


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


def test_intent_extraction_downgrades_non_explicit_handoff_classification():
    context = IntentExtractionContext.from_state(
        {"user_input": "Как менеджер работает с обращениями?"}
    )
    result = IntentExtractionResult.from_llm_payload(
        {
            "domain": "business",
            "intent": "handoff_request",
            "cta": "call_manager",
            "features": {"handoff": 0.9},
            "topic": "handoff",
            "cta_hint": None,
            "emotion": "neutral",
            "is_repeat_like": False,
            "should_search_kb": False,
            "should_generate_answer": False,
            "should_offer_manager": True,
        }
    ).normalized_for_context(context)

    assert result.intent == "support"
    assert result.topic == "support"
    assert result.cta == "none"
    assert result.should_search_kb is True
    assert result.should_generate_answer is True
    assert result.should_offer_manager is False
    assert result.normalization_flags == {
        "unrecognized_feature_keys": ["handoff"],
        "handoff_intent_downgraded": True,
        "handoff_intent_downgrade_reason": "mention_without_explicit_request",
    }


def test_intent_extraction_keeps_advisory_manager_offer_without_explicit_request():
    context = IntentExtractionContext.from_state(
        {"user_input": "Можно ли получить персональный расчёт?"}
    )
    result = IntentExtractionResult.from_llm_payload(
        {
            "domain": "business",
            "intent": "support",
            "cta": "call_manager",
            "features": {},
            "topic": "support",
            "cta_hint": None,
            "emotion": "neutral",
            "is_repeat_like": False,
            "should_search_kb": True,
            "should_generate_answer": True,
            "should_offer_manager": True,
        }
    ).normalized_for_context(context)

    assert result.intent == "support"
    assert result.topic == "support"
    assert result.cta == "call_manager"
    assert result.should_search_kb is True
    assert result.should_generate_answer is True
    assert result.should_offer_manager is True
    assert result.normalization_flags == {}


def test_intent_extraction_keeps_explicit_handoff_classification():
    context = IntentExtractionContext.from_state({"user_input": "Позови менеджера"})
    result = IntentExtractionResult.from_llm_payload(
        {
            "domain": "business",
            "intent": "handoff_request",
            "cta": "call_manager",
            "features": {"handoff": 0.9},
            "topic": "handoff",
            "cta_hint": None,
            "emotion": "neutral",
            "is_repeat_like": False,
            "should_search_kb": False,
            "should_generate_answer": False,
            "should_offer_manager": True,
        }
    ).normalized_for_context(context)

    assert result.intent == "handoff_request"
    assert result.topic == "handoff"
    assert result.cta == "call_manager"
    assert result.normalization_flags == {"unrecognized_feature_keys": ["handoff"]}


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
    assert result.is_repeat_like is False


def test_repeat_answered_relation_overrides_contradictory_repeat_flag():
    result = IntentExtractionResult.from_llm_payload(
        {
            "repeat_relation": "repeat_answered",
            "is_repeat_like": False,
        }
    )

    assert result.repeat_relation == "repeat_answered"
    assert result.is_repeat_like is True


def test_clarification_relation_overrides_contradictory_repeat_flag():
    result = IntentExtractionResult.from_llm_payload(
        {
            "repeat_relation": "clarification",
            "is_repeat_like": True,
        }
    )

    assert result.repeat_relation == "clarification"
    assert result.is_repeat_like is False


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
