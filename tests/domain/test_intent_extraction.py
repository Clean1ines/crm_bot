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
