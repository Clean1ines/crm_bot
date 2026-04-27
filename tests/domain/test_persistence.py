from src.domain.runtime.persistence import (
    PersistenceContext,
    extract_dialog_state_from_memory,
    infer_topic_from_intent,
)


def test_infer_topic_from_intent_maps_known_sales_intents():
    assert infer_topic_from_intent("ask_price") == "pricing"
    assert infer_topic_from_intent("support") == "support"


def test_extract_dialog_state_from_memory_reads_stored_snapshot():
    dialog_state = extract_dialog_state_from_memory(
        {"dialog_state": [{"key": "dialog_state", "value": {"repeat_count": 2}}]}
    )

    assert dialog_state == {
        "last_intent": None,
        "last_cta": None,
        "last_topic": None,
        "repeat_count": 2,
        "lead_status": "active_client",
        "lifecycle": "active_client",
    }


def test_persistence_context_builds_normalized_dialog_state():
    context = PersistenceContext.from_state(
        {
            "thread_id": "thread-1",
            "project_id": "project-1",
            "intent": "ask_integration",
            "lifecycle": "warm",
            "cta": "call_manager",
            "dialog_state": {"repeat_count": 0},
            "user_memory": {
                "dialog_state": [
                    {"key": "dialog_state", "value": {"lead_status": "interested"}}
                ]
            },
        }
    )

    assert context.normalized_dialog_state() == {
        "lead_status": "warm",
        "last_intent": "ask_integration",
        "last_cta": "call_manager",
        "last_topic": "integration",
        "repeat_count": 1,
        "lifecycle": "warm",
    }
