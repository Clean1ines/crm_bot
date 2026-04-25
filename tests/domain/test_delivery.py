from src.domain.runtime.delivery import ResponseDeliveryContext, ResponseDeliveryResult


def test_response_delivery_context_prefers_tool_text():
    context = ResponseDeliveryContext.from_state(
        {
            "chat_id": 123,
            "response_text": "fallback",
            "tool_result": {"text": "tool reply"},
        }
    )

    assert context.resolve_response_text() == "tool reply"


def test_response_delivery_result_serializes_requires_human_only_when_needed():
    result = ResponseDeliveryResult(message_sent=False, response_text="error", requires_human=True)

    assert result.to_state_patch() == {
        "message_sent": False,
        "response_text": "error",
        "requires_human": True,
    }
