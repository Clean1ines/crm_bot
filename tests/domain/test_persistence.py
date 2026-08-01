import pytest

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


def test_persistence_context_writes_only_explicit_llm_memory_candidates():
    context = PersistenceContext.from_state(
        {
            "thread_id": "thread-1",
            "project_id": "project-1",
            "client_id": "client-1",
            "user_input": "Я использую AmoCRM и люблю писать в чат",
            "memory_candidates": [
                {
                    "key": "uses_crm",
                    "value": "AmoCRM",
                    "type": "profile",
                    "confidence": 0.95,
                    "evidence_quote": "Я использую AmoCRM",
                },
                {
                    "key": "preferred_channel",
                    "value": "chat",
                    "type": "preferences",
                    "confidence": 0.9,
                    "evidence_quote": "люблю писать в чат",
                },
            ],
        }
    )

    candidates = {
        (item.type, item.key): item.value for item in context.memory_write_candidates()
    }

    assert candidates[("dialog_state", "dialog_state")]["lifecycle"] == "active_client"
    assert candidates[("lifecycle", "stage")] == {"stage": "active_client"}
    assert candidates[("profile", "uses_crm")] == "AmoCRM"
    assert candidates[("preferences", "preferred_channel")] == "chat"


def test_persistence_context_writes_deterministic_issue_memory():
    context = PersistenceContext.from_state(
        {
            "thread_id": "thread-1",
            "project_id": "project-1",
            "client_id": "client-1",
            "user_input": "Ошибка в чате, моя карта 4111111111111111",
            "intent": "support",
            "topic": "support",
            "emotion": "negative",
        }
    )

    candidates = {
        (item.type, item.key): item.value for item in context.memory_write_candidates()
    }
    assert candidates[("issues", "active_issue")] == {
        "kind": "support",
        "emotion": "negative",
    }


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


def test_persistence_records_supported_answer_in_thread_conversation_context():
    context = PersistenceContext.from_state(
        {
            "thread_id": "thread-1",
            "project_id": "project-1",
            "client_id": "client-1",
            "user_input": "Вход в веб-панель",
            "knowledge_query": "Вход в веб-панель",
            "current_subject": "web_panel",
            "repeat_relation": "none",
            "response_text": "Да, веб-панель есть.",
            "model_answerability": "supported",
            "supporting_entry_ids": ["entry-1"],
            "unsupported_aspects": [],
            "knowledge_retrieval_status": "retrieved",
            "generation_output_parse_status": "valid",
        }
    )

    assert context.state_payload is not None
    conversation_context = context.state_payload["conversation_context"]
    assert "current_subject" not in context.state_payload
    assert "repeat_relation" not in context.state_payload
    assert "dissatisfaction" not in context.state_payload
    assert conversation_context["current_subject"] == "web_panel"
    assert conversation_context["repeat_relation"] == "none"
    assert conversation_context["dissatisfaction"] is False
    assert (
        conversation_context["answered_questions"][0]["standalone_query"]
        == "Вход в веб-панель"
    )
    assert conversation_context["answered_questions"][0]["supporting_entry_ids"] == [
        "entry-1"
    ]
    assert conversation_context["question_attempts"][0]["outcome"] == "supported"
    assert (
        conversation_context["question_attempts"][0]["standalone_query"]
        == "Вход в веб-панель"
    )


def test_persistence_does_not_record_unsupported_answer_as_answered():
    context = PersistenceContext.from_state(
        {
            "thread_id": "thread-1",
            "project_id": "project-1",
            "user_input": "Назови тариф",
            "response_text": "Точных цен нет.",
            "model_answerability": "unsupported",
            "knowledge_retrieval_status": "retrieved",
            "generation_output_parse_status": "valid",
        }
    )

    assert context.state_payload is not None
    conversation_context = context.state_payload["conversation_context"]
    assert conversation_context["answered_questions"] == []
    assert conversation_context["question_attempts"][0]["outcome"] == "unsupported"
    assert conversation_context["question_attempts"][0]["standalone_query"] == (
        "назови тариф"
    )


def test_persistence_question_attempt_outcome_mapping():
    cases = [
        (
            {"knowledge_retrieval_status": "failed"},
            "retrieval_failed",
        ),
        (
            {"knowledge_retrieval_status": "empty"},
            "unsupported",
        ),
        (
            {
                "knowledge_retrieval_status": "retrieved",
                "generation_output_parse_status": "invalid_json",
            },
            "generation_failed",
        ),
        (
            {
                "knowledge_retrieval_status": "retrieved",
                "generation_output_parse_status": "valid",
                "generation_schema_status": "invalid_payload",
            },
            "generation_failed",
        ),
        (
            {
                "knowledge_retrieval_status": "retrieved",
                "generation_output_parse_status": "valid",
                "generation_schema_status": "valid",
                "evidence_reference_status": "unknown_refs",
            },
            "generation_failed",
        ),
        (
            {
                "knowledge_retrieval_status": "retrieved",
                "fallback_reason": "invalid_generation",
            },
            "generation_failed",
        ),
        (
            {
                "knowledge_retrieval_status": "retrieved",
                "fallback_reason": "generation_exception",
            },
            "generation_failed",
        ),
        (
            {
                "knowledge_retrieval_status": "retrieved",
                "fallback_reason": "orphan_action_cta_removed",
            },
            "generation_failed",
        ),
        (
            {
                "knowledge_retrieval_status": "retrieved",
                "generation_output_parse_status": "valid",
                "generation_schema_status": "valid",
                "evidence_reference_status": "valid",
                "model_answerability": "supported",
                "response_text": "Подтверждено.",
            },
            "supported",
        ),
        (
            {
                "knowledge_retrieval_status": "retrieved",
                "generation_output_parse_status": "valid",
                "generation_schema_status": "valid",
                "evidence_reference_status": "valid",
                "model_answerability": "partially_supported",
                "response_text": "Частично подтверждено.",
            },
            "partially_supported",
        ),
    ]

    for extra_state, expected in cases:
        context = PersistenceContext.from_state(
            {
                "thread_id": "thread-1",
                "project_id": "project-1",
                "user_input": f"case {expected}",
                **extra_state,
            }
        )

        assert context.state_payload is not None
        assert (
            context.state_payload["conversation_context"]["question_attempts"][0][
                "outcome"
            ]
            == expected
        )


@pytest.mark.parametrize(
    "extra_state",
    [
        {
            "model_answerability": "supported",
            "generation_output_parse_status": "valid",
            "generation_schema_status": "invalid_payload",
        },
        {
            "model_answerability": "supported",
            "generation_output_parse_status": "valid",
            "generation_schema_status": "valid",
            "evidence_reference_status": "unknown_refs",
        },
        {
            "model_answerability": "supported",
            "fallback_reason": "invalid_generation",
        },
        {
            "model_answerability": "supported",
            "fallback_reason": "generation_exception",
        },
        {
            "model_answerability": "supported",
            "fallback_reason": "orphan_action_cta_removed",
        },
    ],
)
def test_persistence_answered_questions_use_final_outcome_contract(extra_state):
    context = PersistenceContext.from_state(
        {
            "thread_id": "thread-1",
            "project_id": "project-1",
            "user_input": "Есть веб-панель?",
            "response_text": "Да, веб-панель есть.",
            "knowledge_retrieval_status": "retrieved",
            **extra_state,
        }
    )

    assert context.state_payload is not None
    conversation_context = context.state_payload["conversation_context"]
    assert conversation_context["answered_questions"] == []
    assert (
        conversation_context["question_attempts"][0]["outcome"] == "generation_failed"
    )


@pytest.mark.parametrize(
    "schema_status",
    [
        "invalid_payload",
        "invalid_enum",
        "invalid_answerability_contract",
        "missing_required_answer",
        "unknown_status",
    ],
)
def test_persistence_invalid_schema_status_blocks_answered_questions(schema_status):
    context = PersistenceContext.from_state(
        {
            "thread_id": "thread-1",
            "project_id": "project-1",
            "user_input": "Выполни операцию",
            "response_text": "Операция выполнена.",
            "model_answerability": "supported",
            "knowledge_retrieval_status": "skipped",
            "generation_output_parse_status": "not_called",
            "generation_schema_status": schema_status,
            "evidence_reference_status": "not_applicable",
            "fallback_reason": None,
        }
    )

    assert context.state_payload is not None
    conversation_context = context.state_payload["conversation_context"]
    assert conversation_context["answered_questions"] == []
    assert (
        conversation_context["question_attempts"][0]["outcome"] == "generation_failed"
    )


@pytest.mark.parametrize("answerability", ["supported", "partially_supported"])
def test_persistence_successful_outcome_adds_answered_and_question_attempt(
    answerability,
):
    context = PersistenceContext.from_state(
        {
            "thread_id": "thread-1",
            "project_id": "project-1",
            "user_input": "Есть веб-панель?",
            "response_text": "Да, веб-панель есть.",
            "model_answerability": answerability,
            "knowledge_retrieval_status": "retrieved",
            "generation_output_parse_status": "valid",
            "generation_schema_status": "valid",
            "evidence_reference_status": "valid",
            "supporting_entry_ids": ["entry-1"],
        }
    )

    assert context.state_payload is not None
    conversation_context = context.state_payload["conversation_context"]
    assert conversation_context["answered_questions"][0]["answerability"] == (
        answerability
    )
    assert conversation_context["question_attempts"][0]["outcome"] == answerability


def test_persistence_successful_direct_tool_response_accepts_not_applicable_schema():
    context = PersistenceContext.from_state(
        {
            "thread_id": "thread-1",
            "project_id": "project-1",
            "user_input": "Выполни операцию",
            "response_text": "Операция выполнена.",
            "model_answerability": "supported",
            "knowledge_retrieval_status": "skipped",
            "generation_output_parse_status": "not_called",
            "generation_schema_status": "not_applicable",
            "evidence_reference_status": "not_applicable",
            "fallback_reason": None,
        }
    )

    assert context.state_payload is not None
    conversation_context = context.state_payload["conversation_context"]
    assert conversation_context["answered_questions"][0]["answerability"] == "supported"
    assert conversation_context["question_attempts"][0]["outcome"] == "supported"


def test_persistence_subject_reset_for_new_topic_without_current_subject():
    context = PersistenceContext.from_state(
        {
            "thread_id": "thread-1",
            "project_id": "project-1",
            "user_input": "новый вопрос",
            "repeat_relation": "none",
            "conversation_context": {"current_subject": "возврат"},
        }
    )

    assert context.state_payload is not None
    assert context.state_payload["conversation_context"]["current_subject"] is None


def test_persistence_subject_falls_back_for_clarification():
    context = PersistenceContext.from_state(
        {
            "thread_id": "thread-1",
            "project_id": "project-1",
            "user_input": "а через неё?",
            "repeat_relation": "clarification",
            "conversation_context": {"current_subject": "веб-панель"},
        }
    )

    assert context.state_payload is not None
    assert (
        context.state_payload["conversation_context"]["current_subject"] == "веб-панель"
    )


def test_persistence_subject_uses_current_subject_for_new_topic():
    context = PersistenceContext.from_state(
        {
            "thread_id": "thread-1",
            "project_id": "project-1",
            "user_input": "это конструктор ботов?",
            "current_subject": "конструктор ботов",
            "repeat_relation": "none",
            "conversation_context": {"current_subject": "возврат"},
        }
    )

    assert context.state_payload is not None
    assert (
        context.state_payload["conversation_context"]["current_subject"]
        == "конструктор ботов"
    )


def test_persistence_writes_only_explicit_memory_candidates():
    context = PersistenceContext.from_state(
        {
            "thread_id": "thread-1",
            "project_id": "project-1",
            "client_id": "client-1",
            "user_input": "Я использую AmoCRM",
            "memory_candidates": [
                {
                    "key": "uses_crm",
                    "value": "AmoCRM",
                    "type": "profile",
                    "confidence": 0.95,
                    "evidence_quote": "Я использую AmoCRM",
                }
            ],
        }
    )

    candidates = {
        (item.type, item.key): item.value for item in context.memory_write_candidates()
    }
    assert candidates[("dialog_state", "dialog_state")]["lifecycle"] == "active_client"
    assert candidates[("lifecycle", "stage")] == {"stage": "active_client"}
    assert candidates[("profile", "uses_crm")] == "AmoCRM"


def test_persistence_deterministic_memory_wins_over_llm_candidate_conflict():
    context = PersistenceContext.from_state(
        {
            "thread_id": "thread-1",
            "project_id": "project-1",
            "client_id": "client-1",
            "user_input": "Не звоните, только в чат",
            "memory_candidates": [
                {
                    "key": "contact_preference",
                    "value": "phone",
                    "type": "preferences",
                    "confidence": 0.95,
                    "evidence_quote": "Не звоните",
                }
            ],
        }
    )

    candidates = {
        (item.type, item.key): item.value for item in context.memory_write_candidates()
    }
    assert candidates[("preferences", "contact_preference")] == {
        "preferred_channel": "chat",
        "avoid_calls": True,
    }


def test_short_reply_preserves_previous_standalone_query_for_any_short_text():
    for user_input in ("Да", "Нет", "Ок", "Понял", "Спасибо", "Дорого", "Не работает"):
        context = PersistenceContext.from_state(
            {
                "thread_id": "thread-1",
                "project_id": "project-1",
                "user_input": user_input,
                "turn_relation": "short_reply",
                "conversation_context": {
                    "last_standalone_query": "Что умеет Axole?",
                    "answered_questions": [],
                },
            }
        )

        assert context.state_payload is not None
        assert (
            context.state_payload["conversation_context"]["last_standalone_query"]
            == "Что умеет Axole?"
        )


def test_short_reply_without_previous_query_uses_current_input():
    context = PersistenceContext.from_state(
        {
            "thread_id": "thread-1",
            "project_id": "project-1",
            "user_input": "Не работает",
            "turn_relation": "short_reply",
        }
    )

    assert context.state_payload is not None
    assert (
        context.state_payload["conversation_context"]["last_standalone_query"]
        == "не работает"
    )


def test_new_topic_replaces_previous_standalone_query():
    context = PersistenceContext.from_state(
        {
            "thread_id": "thread-1",
            "project_id": "project-1",
            "user_input": "Что такое Axole?",
            "turn_relation": "new_topic",
            "conversation_context": {"last_standalone_query": "Старый вопрос"},
        }
    )

    assert context.state_payload is not None
    assert (
        context.state_payload["conversation_context"]["last_standalone_query"]
        == "что такое axole?"
    )
