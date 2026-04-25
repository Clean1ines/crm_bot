from src.domain.runtime.dialog_state import default_dialog_state
from src.domain.runtime.policy_decision import PolicyDecisionContext, PolicyDecisionResult


def test_policy_decision_context_loads_dialog_state_from_memory():
    context = PolicyDecisionContext.from_state(
        {
            "lifecycle": "warm",
            "intent": "pricing",
            "user_memory": {
                "dialog_state": [
                    {
                        "key": "dialog_state",
                        "value": {"last_intent": "support", "repeat_count": 2},
                    }
                ]
            },
        }
    )

    assert context.lifecycle == "warm"
    assert context.intent == "pricing"
    assert context.dialog_state["last_intent"] == "support"
    assert context.dialog_state["repeat_count"] == 2
    assert context.dialog_state["lead_status"] == default_dialog_state()["lead_status"]


def test_policy_decision_result_serializes_state_patch_and_event_payload():
    result = PolicyDecisionResult(
        lifecycle="handoff_to_manager",
        decision="ESCALATE_TO_HUMAN",
        cta="call_manager",
        topic="handoff",
        lead_status="handoff_to_manager",
        dialog_state={"last_intent": "handoff_request", "repeat_count": 3, "lead_status": "handoff_to_manager"},
    )

    assert result.to_state_patch(previous_lifecycle="warm") == {
        "decision": "ESCALATE_TO_HUMAN",
        "cta": "call_manager",
        "topic": "handoff",
        "lead_status": "handoff_to_manager",
        "dialog_state": {"last_intent": "handoff_request", "repeat_count": 3, "lead_status": "handoff_to_manager"},
        "lifecycle": "handoff_to_manager",
    }
    assert result.to_event_payload(confidence=0.8) == {
        "decision": "ESCALATE_TO_HUMAN",
        "intent": "handoff_request",
        "lifecycle": "handoff_to_manager",
        "cta": "call_manager",
        "topic": "handoff",
        "repeat_count": 3,
        "lead_status": "handoff_to_manager",
        "confidence": 0.8,
    }
