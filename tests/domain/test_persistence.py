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
        "handoff_confirmation_pending": False,
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
        "handoff_confirmation_pending": False,
    }


def test_persistence_context_builds_conservative_memory_candidates():
    context = PersistenceContext.from_state(
        {
            "thread_id": "thread-1",
            "project_id": "project-1",
            "client_id": "client-1",
            "user_input": "Слишком дорого, только в чат, и интеграция не работает",
            "intent": "pricing",
            "topic": "integration",
            "emotion": "negative",
            "lifecycle": "warm",
            "cta": "none",
        }
    )

    candidates = {
        (item.type, item.key): item.value for item in context.memory_write_candidates()
    }

    assert ("dialog_state", "dialog_state") in candidates
    assert ("lifecycle", "stage") in candidates
    assert candidates[("preferences", "contact_preference")] == {
        "preferred_channel": "chat",
        "avoid_calls": True,
    }
    assert candidates[("behavior", "price_sensitivity")] == "high"
    assert candidates[("rejections", "pricing_objection")] == "too_expensive"
    assert candidates[("issues", "active_issue")] == {
        "kind": "integration",
        "emotion": "negative",
    }


def test_persistence_context_does_not_store_raw_issue_text():
    context = PersistenceContext.from_state(
        {
            "thread_id": "thread-1",
            "project_id": "project-1",
            "client_id": "client-1",
            "user_input": "Ошибка в счете, вот номер карты 4111111111111111",
            "intent": "support",
            "topic": "support",
            "emotion": "negative",
        }
    )

    issue_candidate = next(
        item
        for item in context.memory_write_candidates()
        if item.type == "issues" and item.key == "active_issue"
    )

    assert issue_candidate.value == {"kind": "support", "emotion": "negative"}


def test_persistence_context_detects_repeated_technical_failure_incident():
    context = PersistenceContext.from_state(
        {
            "thread_id": "thread-1",
            "project_id": "project-1",
            "client_id": "client-1",
            "technical_failure_count": 2,
            "technical_failure_stage": "response_generator",
            "technical_failure_error": "PermissionDeniedError",
            "technical_incident_created": False,
        }
    )

    assert context.should_create_technical_incident() is True
    payload = context.technical_incident_payload()
    assert payload["priority"] == "high"
    assert "LLM response generation failed" in payload["title"]
    assert "PermissionDeniedError" in payload["description"]


def test_persistence_context_skips_already_created_technical_incident():
    context = PersistenceContext.from_state(
        {
            "thread_id": "thread-1",
            "project_id": "project-1",
            "technical_failure_count": 3,
            "technical_incident_created": True,
        }
    )

    assert context.should_create_technical_incident() is False
