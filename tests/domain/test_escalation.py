from src.domain.runtime.escalation import EscalationContext, EscalationResult


def test_escalation_context_extracts_client_id_and_payloads():
    context = EscalationContext.from_state(
        {
            "thread_id": "thread-1",
            "project_id": "project-1",
            "user_input": "need help",
            "client_profile": {"id": "client-1"},
        }
    )

    assert context.client_id == "client-1"
    assert context.ticket_payload()["title"] == "Escalation: user requested human help"
    assert context.notification_payload() == {
        "thread_id": "thread-1",
        "project_id": "project-1",
        "message": "need help",
    }


def test_escalation_result_serializes_state_patch():
    result = EscalationResult()

    assert result.to_state_patch() == {
        "requires_human": True,
        "response_text": "Передал обращение менеджеру. Он ответит здесь, как только подключится.",
        "tool_result": None,
    }
