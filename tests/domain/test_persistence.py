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
        "last_repeat_increment_reason": None,
        "last_repeat_reset_reason": None,
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
        "repeat_count": 0,
        "last_repeat_increment_reason": None,
        "last_repeat_reset_reason": None,
        "lifecycle": "warm",
        "handoff_confirmation_pending": False,
    }


def test_persistence_expires_pending_cta_when_current_turn_has_no_new_cta():
    context = PersistenceContext.from_state(
        {
            "thread_id": "thread-1",
            "project_id": "project-1",
            "user_input": "расскажите подробнее про цены",
            "intent": "pricing",
            "lifecycle": "warm",
            "cta": "none",
            "dialog_state": {
                "last_cta": "call_manager",
                "last_topic": "pricing",
                "lead_status": "warm",
                "lifecycle": "warm",
            },
        }
    )

    assert context.normalized_dialog_state()["last_cta"] is None


def test_persistence_expires_pending_cta_and_keeps_new_action_cta():
    context = PersistenceContext.from_state(
        {
            "thread_id": "thread-1",
            "project_id": "project-1",
            "user_input": "расскажите подробнее про цены",
            "intent": "pricing",
            "lifecycle": "warm",
            "cta": "book_consultation",
            "dialog_state": {
                "last_cta": "call_manager",
                "last_topic": "pricing",
                "lead_status": "warm",
                "lifecycle": "warm",
            },
        }
    )

    assert context.normalized_dialog_state()["last_cta"] == "book_consultation"


def test_persistence_saves_new_conversational_cta():
    context = PersistenceContext.from_state(
        {
            "thread_id": "thread-1",
            "project_id": "project-1",
            "user_input": "что умеет сервис?",
            "intent": "sales",
            "topic": "product",
            "lifecycle": "warm",
            "cta": "continue_explanation",
            "dialog_state": {
                "last_topic": "product",
                "lead_status": "warm",
                "lifecycle": "warm",
            },
        }
    )

    assert context.normalized_dialog_state()["last_cta"] == "continue_explanation"


def test_persistence_state_payload_does_not_persist_turn_scoped_knowledge_query():
    context = PersistenceContext.from_state(
        {
            "thread_id": "thread-1",
            "project_id": "project-1",
            "user_input": "Да",
            "knowledge_query": "подробнее как работает продукт и его возможности",
            "intent": "sales",
            "topic": "product",
            "cta": "continue_explanation",
            "dialog_state": {
                "last_cta": "continue_explanation",
                "last_topic": "product",
            },
        }
    )

    assert context.state_payload is not None
    assert "knowledge_query" not in context.state_payload


def test_persistence_state_payload_does_not_persist_ephemeral_intent_resolution_fields():
    context = PersistenceContext.from_state(
        {
            "thread_id": "thread-1",
            "project_id": "project-1",
            "user_input": "Да",
            "knowledge_query": "подробнее как работает продукт и его возможности",
            "resolved_cta": "call_manager",
            "resolved_cta_reply": "affirmative",
            "intent": "sales",
            "topic": "product",
            "cta": "call_manager",
            "dialog_state": {
                "last_cta": "call_manager",
                "last_topic": "product",
            },
        }
    )

    assert context.state_payload is not None
    assert "knowledge_query" not in context.state_payload
    assert "resolved_cta" not in context.state_payload
    assert "resolved_cta_reply" not in context.state_payload
    assert "knowledge_query" not in context.normalized_dialog_state()
    assert "resolved_cta" not in context.normalized_dialog_state()
    assert "resolved_cta_reply" not in context.normalized_dialog_state()

    memory_candidates = {
        candidate.key: candidate.value
        for candidate in context.memory_write_candidates()
    }
    assert "knowledge_query" not in memory_candidates
    assert "resolved_cta" not in memory_candidates
    assert "resolved_cta_reply" not in memory_candidates
    assert "knowledge_query" not in memory_candidates["dialog_state"]
    assert "resolved_cta" not in memory_candidates["dialog_state"]
    assert "resolved_cta_reply" not in memory_candidates["dialog_state"]


def test_persistence_consumes_conversational_cta_after_yes_no_or_other_reply():
    for user_input in ("Да", "Нет", "Расскажите подробнее про цены"):
        context = PersistenceContext.from_state(
            {
                "thread_id": "thread-1",
                "project_id": "project-1",
                "user_input": user_input,
                "intent": "sales",
                "topic": "product",
                "lifecycle": "warm",
                "cta": "continue_explanation" if user_input == "Да" else "none",
                "dialog_state": {
                    "last_cta": "continue_explanation",
                    "last_topic": "product",
                    "lead_status": "warm",
                    "lifecycle": "warm",
                },
            }
        )

        assert context.normalized_dialog_state()["last_cta"] is None


def test_persistence_clears_consumed_pending_cta_after_affirmative_reply():
    context = PersistenceContext.from_state(
        {
            "thread_id": "thread-1",
            "project_id": "project-1",
            "user_input": "Да",
            "intent": "sales",
            "topic": "product",
            "lifecycle": "warm",
            "cta": "call_manager",
            "dialog_state": {
                "last_cta": "call_manager",
                "last_topic": "product",
                "lead_status": "warm",
                "lifecycle": "warm",
            },
        }
    )

    assert context.normalized_dialog_state()["last_cta"] is None
    assert context.state_payload is not None
    assert context.state_payload["dialog_state"]["last_cta"] is None


def test_persistence_clears_consumed_pending_cta_after_negative_reply():
    context = PersistenceContext.from_state(
        {
            "thread_id": "thread-1",
            "project_id": "project-1",
            "user_input": "Нет",
            "intent": "sales",
            "topic": "product",
            "lifecycle": "warm",
            "cta": "none",
            "dialog_state": {
                "last_cta": "call_manager",
                "last_topic": "product",
                "lead_status": "warm",
                "lifecycle": "warm",
            },
        }
    )

    assert context.normalized_dialog_state()["last_cta"] is None


def test_persistence_shared_affirmative_vocabulary_clears_pending_cta():
    for user_input in ("Конечно", "Sure"):
        context = PersistenceContext.from_state(
            {
                "thread_id": "thread-1",
                "project_id": "project-1",
                "user_input": user_input,
                "intent": "sales",
                "topic": "product",
                "lifecycle": "warm",
                "cta": "call_manager",
                "dialog_state": {
                    "last_cta": "call_manager",
                    "last_topic": "product",
                    "lead_status": "warm",
                    "lifecycle": "warm",
                },
            }
        )

        assert context.normalized_dialog_state()["last_cta"] is None


def test_persistence_later_yes_cannot_confirm_stale_cta_after_topic_change():
    first_turn = PersistenceContext.from_state(
        {
            "thread_id": "thread-1",
            "project_id": "project-1",
            "user_input": "Расскажите подробнее про цены",
            "intent": "pricing",
            "topic": "pricing",
            "lifecycle": "warm",
            "cta": "none",
            "dialog_state": {
                "last_cta": "call_manager",
                "last_topic": "product",
                "lead_status": "warm",
                "lifecycle": "warm",
            },
        }
    )
    cleared = first_turn.normalized_dialog_state()

    later_yes = PersistenceContext.from_state(
        {
            "thread_id": "thread-1",
            "project_id": "project-1",
            "user_input": "Да",
            "intent": "unknown",
            "topic": "other",
            "lifecycle": "warm",
            "cta": "none",
            "dialog_state": cleared,
        }
    )

    assert cleared["last_cta"] is None
    assert later_yes.normalized_dialog_state()["last_cta"] is None


def test_persistence_keeps_pending_cta_without_user_input_or_during_technical_replay():
    without_input = PersistenceContext.from_state(
        {
            "thread_id": "thread-1",
            "project_id": "project-1",
            "user_input": "",
            "lifecycle": "warm",
            "cta": "none",
            "dialog_state": {
                "last_cta": "call_manager",
                "lead_status": "warm",
                "lifecycle": "warm",
            },
        }
    )
    technical_replay = PersistenceContext.from_state(
        {
            "thread_id": "thread-1",
            "project_id": "project-1",
            "user_input": "Да",
            "domain": "technical_failure",
            "technical_failure_stage": "intent_extractor",
            "lifecycle": "warm",
            "cta": "none",
            "dialog_state": {
                "last_cta": "call_manager",
                "lead_status": "warm",
                "lifecycle": "warm",
            },
        }
    )

    assert without_input.normalized_dialog_state()["last_cta"] == "call_manager"
    assert technical_replay.normalized_dialog_state()["last_cta"] == "call_manager"


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


def test_persistence_state_payload_does_not_persist_turn_scoped_tool_or_generation_fields():
    context = PersistenceContext.from_state(
        {
            "thread_id": "thread-",
            "project_id": "project-",
            "user_input": "tool result turn",
            "intent": "other",
            "topic": "support",
            "tool_name": "crm.lookup",
            "tool_args": {"name": "Alice"},
            "tool_result": {"text": "stale"},
            "tool_execution_status": "succeeded",
            "tool_execution_safe_error_code": "legacy",
            "tool_response_text": "stale done",
            "generation_mode": "TOOL_RESULT_RESPONSE",
            "knowledge_chunks": [{"id": "old", "content": "old"}],
            "knowledge_retrieval_status": "retrieved",
            "knowledge_retrieval_error_type": "old",
            "model_answerability": "supported",
            "supporting_entry_ids": [],
            "unsupported_aspects": [],
            "generation_output_parse_status": "valid",
            "generation_schema_status": "valid",
            "evidence_reference_status": "not_applicable",
            "semantic_grounding_status": "unchecked",
            "semantic_grounding_failure_reason": "old",
            "fallback_reason": None,
            "generated_action_cta_detected": False,
            "canonical_response_cta": None,
            "dialog_state": {"last_topic": "support"},
        }
    )

    assert context.state_payload is not None
    for key in (
        "tool_name",
        "tool_args",
        "tool_result",
        "tool_execution_status",
        "tool_execution_safe_error_code",
        "tool_response_text",
        "generation_mode",
        "knowledge_chunks",
        "knowledge_retrieval_status",
        "knowledge_retrieval_error_type",
        "model_answerability",
        "supporting_entry_ids",
        "unsupported_aspects",
        "generation_output_parse_status",
        "generation_schema_status",
        "evidence_reference_status",
        "semantic_grounding_status",
        "semantic_grounding_failure_reason",
        "fallback_reason",
        "generated_action_cta_detected",
        "canonical_response_cta",
    ):
        assert key not in context.state_payload


def test_persistence_round_trips_partial_handoff_ticket_identity():
    context = PersistenceContext.from_state(
        {
            "thread_id": "thread-1",
            "project_id": "project-1",
            "user_input": "handoff failed",
            "requires_human": False,
            "ticket_created": True,
            "handoff_ticket_id": "ticket-123",
            "escalation_failed": True,
            "handoff_completed": False,
            "thread_waiting_manager": False,
            "notification_degraded": False,
            "lifecycle": "active_client",
            "dialog_state": {
                "lifecycle": "active_client",
                "lead_status": "active_client",
            },
        }
    )

    assert context.state_payload is not None
    assert context.state_payload["ticket_created"] is True
    assert context.state_payload["handoff_ticket_id"] == "ticket-123"
    assert context.state_payload["escalation_failed"] is True
    assert context.state_payload["handoff_completed"] is False
    assert context.state_payload["thread_waiting_manager"] is False
    assert context.state_payload["notification_degraded"] is False
    assert context.state_payload["requires_human"] is False


def test_persistence_round_trips_successful_handoff_ticket_identity():
    context = PersistenceContext.from_state(
        {
            "thread_id": "thread-1",
            "project_id": "project-1",
            "user_input": "handoff success",
            "requires_human": True,
            "ticket_created": True,
            "handoff_ticket_id": "ticket-123",
            "escalation_failed": False,
            "handoff_completed": True,
            "thread_waiting_manager": True,
            "notification_degraded": False,
            "lifecycle": "handoff_to_manager",
            "dialog_state": {
                "lifecycle": "handoff_to_manager",
                "lead_status": "handoff_to_manager",
            },
        }
    )

    assert context.state_payload is not None
    assert context.state_payload["ticket_created"] is True
    assert context.state_payload["handoff_ticket_id"] == "ticket-123"
    assert context.state_payload["escalation_failed"] is False
    assert context.state_payload["handoff_completed"] is True
    assert context.state_payload["thread_waiting_manager"] is True
    assert context.state_payload["requires_human"] is True


def test_persistence_keeps_handoff_and_technical_ticket_ids_separate():
    context = PersistenceContext.from_state(
        {
            "thread_id": "thread-1",
            "project_id": "project-1",
            "user_input": "separate tickets",
            "ticket_created": True,
            "handoff_ticket_id": "manager-ticket-1",
            "technical_incident_created": True,
            "technical_ticket_id": "incident-ticket-1",
        }
    )

    assert context.state_payload is not None
    assert context.state_payload["handoff_ticket_id"] == "manager-ticket-1"
    assert context.state_payload["technical_ticket_id"] == "incident-ticket-1"
