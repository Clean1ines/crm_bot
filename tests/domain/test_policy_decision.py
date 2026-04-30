from src.domain.runtime.dialog_state import default_dialog_state
from src.domain.runtime.policy.repeat_detection import build_dialog_state_update
from src.domain.runtime.policy_decision import (
    PolicyDecisionContext,
    PolicyDecisionResult,
)


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
        dialog_state={
            "last_intent": "handoff_request",
            "repeat_count": 3,
            "lead_status": "handoff_to_manager",
            "handoff_confirmation_pending": False,
        },
    )

    assert result.to_state_patch(previous_lifecycle="warm") == {
        "decision": "ESCALATE_TO_HUMAN",
        "cta": "call_manager",
        "topic": "handoff",
        "lead_status": "handoff_to_manager",
        "dialog_state": {
            "last_intent": "handoff_request",
            "repeat_count": 3,
            "lead_status": "handoff_to_manager",
            "handoff_confirmation_pending": False,
        },
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


def test_dialog_state_call_manager_cta_does_not_force_handoff_without_escalation():
    dialog_state = build_dialog_state_update(
        {},
        intent="sales",
        topic="product",
        cta="call_manager",
        lifecycle="warm",
        decision="LLM_GENERATE",
    )

    assert dialog_state["last_cta"] == "call_manager"
    assert dialog_state["lead_status"] == "warm"
    assert dialog_state["lifecycle"] == "warm"
