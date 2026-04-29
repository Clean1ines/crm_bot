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
    }


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
