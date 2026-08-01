from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Mapping, Sequence, cast

from src.domain.runtime.cta import (
    is_pending_cta,
    normalize_cta,
    normalize_short_reply_kind,
)
from src.domain.runtime.dialog_state import (
    DialogState,
    dialog_state_from_memory,
    merge_dialog_state,
)
from src.domain.project_plane.json_types import JsonValue, json_value_from_unknown
from src.domain.runtime.state_contracts import (
    ANSWERED_QUESTIONS_LIMIT,
    AnsweredQuestionEntry,
    ConversationContextState,
    MemoryCandidateState,
    RuntimeMemory,
    RuntimeStateInput,
    RuntimeStatePatch,
    ToolArguments,
)
from src.domain.runtime.value_parsing import coerce_bool, coerce_int

NO_CALL_PHRASES = (
    "не звоните",
    "не звони",
    "не хочу звонок",
    "не хочу созвон",
    "без звонка",
    "только в чат",
    "only chat",
    "dont call",
    "don't call",
    "no calls",
)
PRICE_OBJECTION_PHRASES = (
    "дорого",
    "слишком дорого",
    "высокая цена",
    "не по бюджету",
    "too expensive",
    "expensive",
    "over budget",
)
ISSUE_PHRASES = (
    "не работает",
    "ошибка",
    "сломал",
    "сломалось",
    "баг",
    "не могу",
    "не получается",
    "cannot",
    "can't",
    "error",
    "issue",
    "problem",
)
QUESTION_ATTEMPTS_LIMIT = 10


@dataclass(frozen=True, slots=True)
class MemoryWriteCandidate:
    key: str
    value: JsonValue
    type: str


def infer_topic_from_intent(intent: str | None) -> str | None:
    value = (intent or "").strip().lower()
    mapping = {
        "ask_price": "pricing",
        "ask_features": "product",
        "ask_integration": "integration",
        "pricing": "pricing",
        "sales": "product",
        "support": "support",
        "feedback": "feedback",
        "handoff_request": "handoff",
        "angry": "angry",
    }
    return mapping.get(value)


def extract_dialog_state_from_memory(user_memory: RuntimeMemory | None) -> DialogState:
    return dialog_state_from_memory(user_memory, lifecycle="active_client")


@dataclass(slots=True)
class PersistenceContext:
    thread_id: str | None
    project_id: str | None
    response_text: str | None
    user_input: str
    client_id: str | None
    close_ticket: bool
    technical_failure_count: int = 0
    technical_failure_stage: str | None = None
    technical_failure_error: str | None = None
    technical_incident_created: bool = False
    technical_ticket_id: str | None = None
    intent: str | None = None
    lifecycle: str | None = None
    cta: str | None = None
    decision: str | None = None
    confidence: float | None = None
    requires_human: bool = False
    tool_name: str | None = None
    tool_args: ToolArguments | None = None
    tool_result: object | None = None
    dialog_state: DialogState | None = None
    lead_status: str | None = None
    topic: str | None = None
    emotion: str | None = None
    domain: str | None = None
    turn_relation: str | None = None
    should_search_kb: bool = True
    should_generate_answer: bool = True
    should_offer_manager: bool = False
    current_subject: str | None = None
    repeat_relation: str | None = None
    dissatisfaction: bool = False
    memory_candidates: list[MemoryCandidateState] | None = None
    knowledge_query: str | None = None
    model_answerability: str | None = None
    supporting_entry_ids: list[str] | None = None
    unsupported_aspects: list[str] | None = None
    knowledge_retrieval_status: str | None = None
    generation_output_parse_status: str | None = None
    generation_schema_status: str | None = None
    evidence_reference_status: str | None = None
    fallback_reason: str | None = None
    state_payload: RuntimeStatePatch | None = None
    user_memory: RuntimeMemory | None = None

    @classmethod
    def from_state(cls, state: RuntimeStateInput) -> "PersistenceContext":
        state_copy = _state_payload_from_runtime_state(state)
        dialog_state = _dialog_state_or_none(state.get("dialog_state"))
        tool_args = _tool_args_or_none(state.get("tool_args"))

        context = cls(
            thread_id=state.get("thread_id"),
            project_id=state.get("project_id"),
            response_text=state.get("response_text"),
            user_input=str(state.get("user_input") or "").lower(),
            client_id=state.get("client_id"),
            close_ticket=coerce_bool(state.get("close_ticket"), False),
            technical_failure_count=coerce_int(state.get("technical_failure_count"), 0),
            technical_failure_stage=_optional_text(
                state.get("technical_failure_stage")
            ),
            technical_failure_error=_optional_text(
                state.get("technical_failure_error")
            ),
            technical_incident_created=coerce_bool(
                state.get("technical_incident_created"), False
            ),
            technical_ticket_id=_optional_text(state.get("technical_ticket_id")),
            intent=state.get("intent"),
            lifecycle=state.get("lifecycle"),
            cta=state.get("cta"),
            decision=state.get("decision"),
            confidence=state.get("confidence"),
            requires_human=coerce_bool(state.get("requires_human"), False),
            tool_name=state.get("tool_name"),
            tool_args=tool_args,
            tool_result=state.get("tool_result"),
            dialog_state=dialog_state,
            lead_status=state.get("lead_status"),
            topic=state.get("topic"),
            emotion=state.get("emotion"),
            domain=_optional_text(state.get("domain")),
            turn_relation=_optional_text(state.get("turn_relation")),
            should_search_kb=coerce_bool(state.get("should_search_kb"), True),
            should_generate_answer=coerce_bool(
                state.get("should_generate_answer"), True
            ),
            should_offer_manager=coerce_bool(state.get("should_offer_manager"), False),
            current_subject=_optional_text(state.get("current_subject")),
            repeat_relation=_optional_text(state.get("repeat_relation")) or "none",
            dissatisfaction=coerce_bool(state.get("dissatisfaction"), False),
            memory_candidates=_memory_candidate_list(state.get("memory_candidates")),
            knowledge_query=_optional_text(state.get("knowledge_query")),
            model_answerability=_optional_text(state.get("model_answerability")),
            supporting_entry_ids=_string_list(state.get("supporting_entry_ids")),
            unsupported_aspects=_string_list(state.get("unsupported_aspects")),
            knowledge_retrieval_status=_optional_text(
                state.get("knowledge_retrieval_status")
            ),
            generation_output_parse_status=_optional_text(
                state.get("generation_output_parse_status")
            ),
            generation_schema_status=_optional_text(
                state.get("generation_schema_status")
            ),
            evidence_reference_status=_optional_text(
                state.get("evidence_reference_status")
            ),
            fallback_reason=_optional_text(state.get("fallback_reason")),
            state_payload=state_copy,
            user_memory=state.get("user_memory"),
        )
        if context.state_payload is not None:
            context.state_payload["dialog_state"] = context.normalized_dialog_state()
            context.state_payload["conversation_context"] = (
                context.updated_conversation_context()
            )
        return context

    def normalized_dialog_state(self) -> DialogState:
        fallback_lifecycle = self._fallback_lifecycle()
        existing = merge_dialog_state(self.dialog_state, lifecycle=fallback_lifecycle)
        dialog_state = self._dialog_state_from_existing(existing)
        memory_dialog_state = dialog_state_from_memory(
            self.user_memory, lifecycle=fallback_lifecycle
        )

        merged: dict[str, object] = dict(memory_dialog_state)
        merged.update(dialog_state)
        return merge_dialog_state(merged, lifecycle=fallback_lifecycle)

    def _fallback_lifecycle(self) -> str:
        return str(self.lifecycle or self.lead_status or "active_client")

    def _dialog_state_from_existing(self, existing: DialogState) -> DialogState:
        dialog_state: DialogState = {
            "last_intent": existing.get("last_intent") or self.intent,
            "last_cta": self._next_last_cta(existing),
            "last_topic": existing.get("last_topic")
            or infer_topic_from_intent(self.intent),
            "repeat_count": coerce_int(existing.get("repeat_count"), 0),
            "last_repeat_increment_reason": existing.get(
                "last_repeat_increment_reason"
            ),
            "last_repeat_reset_reason": existing.get("last_repeat_reset_reason"),
            "lead_status": self._lead_status(existing),
            "lifecycle": self._lifecycle(existing),
            "handoff_confirmation_pending": bool(
                existing.get("handoff_confirmation_pending")
            ),
        }
        return _ensure_repeat_count(dialog_state)

    def _next_last_cta(self, existing: DialogState) -> str | None:
        existing_cta = normalize_cta(existing.get("last_cta"))
        current_cta = normalize_cta(self.cta)

        if not existing_cta:
            return current_cta if is_pending_cta(current_cta) else None

        if not self._has_substantive_user_turn() or self._is_technical_replay():
            return current_cta if is_pending_cta(current_cta) else existing_cta

        if self._resolves_existing_pending_cta(existing_cta):
            return None

        return current_cta if is_pending_cta(current_cta) else None

    def _resolves_existing_pending_cta(self, existing_cta: str) -> bool:
        if not is_pending_cta(existing_cta):
            return False
        return normalize_short_reply_kind(self.user_input) in {
            "affirmative",
            "negative",
        }

    def _has_substantive_user_turn(self) -> bool:
        return bool(" ".join(str(self.user_input).split()))

    def _is_technical_replay(self) -> bool:
        return (
            self.domain == "technical_failure"
            or self.technical_failure_stage is not None
            or self.technical_failure_error is not None
        )

    def _lead_status(self, existing: DialogState) -> str:
        return (
            existing.get("lead_status")
            or self.lead_status
            or self.lifecycle
            or "active_client"
        )

    def _lifecycle(self, existing: DialogState) -> str:
        return (
            self.lifecycle
            or existing.get("lifecycle")
            or self.lead_status
            or "active_client"
        )

    def memory_write_candidates(self) -> list[MemoryWriteCandidate]:
        dialog_state = self.normalized_dialog_state()
        candidates: list[MemoryWriteCandidate] = [
            MemoryWriteCandidate(
                key="dialog_state",
                value=json_value_from_unknown(dialog_state),
                type="dialog_state",
            )
        ]

        lifecycle_stage = dialog_state.get("lifecycle") or dialog_state.get(
            "lead_status"
        )
        if lifecycle_stage:
            candidates.append(
                MemoryWriteCandidate(
                    key="stage",
                    value={"stage": lifecycle_stage},
                    type="lifecycle",
                )
            )

        if self.user_input:
            if _contains_phrase(self.user_input, NO_CALL_PHRASES):
                candidates.append(
                    MemoryWriteCandidate(
                        key="contact_preference",
                        value={"preferred_channel": "chat", "avoid_calls": True},
                        type="preferences",
                    )
                )

            if _contains_price_objection(
                self.user_input,
                topic=self.topic,
                intent=self.intent,
            ):
                candidates.extend(
                    (
                        MemoryWriteCandidate(
                            key="price_sensitivity",
                            value="high",
                            type="behavior",
                        ),
                        MemoryWriteCandidate(
                            key="pricing_objection",
                            value="too_expensive",
                            type="rejections",
                        ),
                    )
                )

            issue_kind = _detect_issue_kind(
                self.user_input,
                topic=self.topic,
                emotion=self.emotion,
            )
            if issue_kind is not None:
                candidates.append(
                    MemoryWriteCandidate(
                        key="active_issue",
                        value={
                            "kind": issue_kind,
                            "emotion": self.emotion or "negative",
                        },
                        type="issues",
                    )
                )

        seen = {(candidate.type, candidate.key) for candidate in candidates}
        for candidate in self.memory_candidates or []:
            key = str(candidate.get("key") or "").strip()
            type_ = str(candidate.get("type") or "").strip()
            value = candidate.get("value")
            if not key or not type_ or value in (None, ""):
                continue
            if (type_, key) in seen:
                continue
            seen.add((type_, key))
            candidates.append(
                MemoryWriteCandidate(
                    key=key,
                    value=json_value_from_unknown(value),
                    type=type_,
                )
            )
        return candidates

    def updated_conversation_context(self) -> ConversationContextState:
        existing = _conversation_context_from_payload(
            (self.state_payload or {}).get("conversation_context")
        )
        repeat_relation = _repeat_relation(self.repeat_relation)
        existing_subject = existing.get("current_subject")
        if repeat_relation in {
            "clarification",
            "repeat_answered",
            "repeat_unresolved",
        }:
            subject = self.current_subject or existing_subject
        else:
            subject = self.current_subject
        standalone_query = self._standalone_query(existing)
        answered_questions: list[AnsweredQuestionEntry] = list(
            existing.get("answered_questions") or []
        )
        question_attempts = _question_attempts_from_context(existing)
        entry = self._answered_question_entry(
            subject=subject,
            standalone_query=standalone_query,
        )
        if entry is not None and not _is_duplicate_answered_question(
            answered_questions,
            entry,
        ):
            answered_questions.append(entry)
            answered_questions = answered_questions[-ANSWERED_QUESTIONS_LIMIT:]

        attempt = self._question_attempt_entry(
            subject=subject,
            standalone_query=standalone_query,
        )
        if attempt is not None:
            question_attempts.append(attempt)
            question_attempts = question_attempts[-QUESTION_ATTEMPTS_LIMIT:]

        return ConversationContextState(
            current_subject=subject,
            last_standalone_query=standalone_query,
            repeat_relation=repeat_relation,
            dissatisfaction=self.dissatisfaction,
            answered_questions=answered_questions,
            question_attempts=question_attempts,
        )

    def _standalone_query(self, existing: ConversationContextState) -> str:
        if not self.knowledge_query and self.turn_relation == "short_reply":
            previous = _optional_text(existing.get("last_standalone_query"))
            if previous:
                return previous
        return _bounded_text(self.knowledge_query or self.user_input, 240)

    def _answered_question_entry(
        self,
        *,
        subject: str | None,
        standalone_query: str,
    ) -> AnsweredQuestionEntry | None:
        outcome = self._question_attempt_outcome()
        if outcome not in {"supported", "partially_supported"}:
            return None
        if not self.response_text:
            return None
        return AnsweredQuestionEntry(
            standalone_query=standalone_query,
            subject=subject,
            answerability=outcome,
            answer_preview=_bounded_text(self.response_text, 500),
            supporting_entry_ids=list(self.supporting_entry_ids or [])[:8],
            unsupported_aspects=list(self.unsupported_aspects or [])[:8],
            answered_at=datetime.now(UTC).isoformat(),
        )

    def _question_attempt_entry(
        self,
        *,
        subject: str | None,
        standalone_query: str,
    ) -> dict[str, object] | None:
        outcome = self._question_attempt_outcome()
        if outcome is None:
            return None
        return {
            "standalone_query": standalone_query,
            "subject": subject,
            "outcome": outcome,
            "answer_preview": _bounded_text(self.response_text, 500)
            if self.response_text
            else None,
            "unsupported_aspects": list(self.unsupported_aspects or [])[:8],
            "supporting_entry_ids": list(self.supporting_entry_ids or [])[:8],
            "attempted_at": datetime.now(UTC).isoformat(),
        }

    def _question_attempt_outcome(self) -> str | None:
        if (
            self.knowledge_retrieval_status == "failed"
            or self.fallback_reason == "retrieval_failed"
        ):
            return "retrieval_failed"
        if (
            self.knowledge_retrieval_status == "empty"
            or self.fallback_reason == "no_evidence"
        ):
            return "unsupported"
        if self._has_generation_failure_outcome():
            return "generation_failed"
        answerability = (self.model_answerability or "").strip()
        if answerability in {"supported", "partially_supported"}:
            return answerability
        if answerability in {"unsupported", "conflicting_evidence"}:
            return "unsupported"
        return None

    def _has_generation_failure_outcome(self) -> bool:
        parse_status = (self.generation_output_parse_status or "").strip()
        if parse_status and parse_status not in {"valid", "not_called"}:
            return True

        schema_status = (self.generation_schema_status or "").strip()
        if schema_status and schema_status not in {
            "valid",
            "not_called",
            "not_applicable",
        }:
            return True

        evidence_status = (self.evidence_reference_status or "").strip()
        if evidence_status in {
            "missing_required_refs",
            "unknown_refs",
            "invalid_for_answerability",
        }:
            return True

        return self.fallback_reason in {
            "invalid_generation",
            "generation_exception",
            "generation_mode_contract_violation",
            "orphan_action_cta_removed",
            "retrieval_contract_violation",
            "tool_result_contract_violation",
        }

    def should_create_technical_incident(self) -> bool:
        return (
            self.technical_failure_count >= 2
            and not self.technical_incident_created
            and bool(self.project_id)
            and bool(self.thread_id)
        )

    def technical_incident_payload(self) -> dict[str, object]:
        return {
            "title": "Technical incident: LLM response generation failed",
            "description": (
                "The assistant failed at an LLM-dependent stage at least twice.\n"
                f"Stage: {self.technical_failure_stage or 'unknown'}\n"
                f"Error: {self.technical_failure_error or 'unknown'}\n"
                f"Thread ID: {self.thread_id or 'unknown'}\n"
                f"Client ID: {self.client_id or 'unknown'}"
            ),
            "priority": "high",
        }


def _ensure_repeat_count(dialog_state: DialogState) -> DialogState:
    return dialog_state


def _contains_phrase(text: str, phrases: tuple[str, ...]) -> bool:
    return any(phrase in text for phrase in phrases)


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _contains_price_objection(
    text: str,
    *,
    topic: str | None,
    intent: str | None,
) -> bool:
    if not _contains_phrase(text, PRICE_OBJECTION_PHRASES):
        return False

    return topic == "pricing" or intent in {"pricing", "ask_price"}


def _detect_issue_kind(
    text: str,
    *,
    topic: str | None,
    emotion: str | None,
) -> str | None:
    if not _contains_phrase(text, ISSUE_PHRASES):
        return None

    if topic == "integration":
        return "integration"

    return (
        _access_issue_kind(text)
        or _billing_issue_kind(text)
        or _support_issue_kind(topic=topic, emotion=emotion)
        or "general"
    )


def _state_payload_from_runtime_state(state: RuntimeStateInput) -> RuntimeStatePatch:
    state_copy: RuntimeStatePatch = {}
    _copy_core_state_fields(state, state_copy)
    _copy_runtime_signal_fields(state, state_copy)
    # Execution-scoped tool/retrieval/generation fields are intentionally omitted
    # so the next turn cannot reconstruct stale factual or tool state.
    return state_copy


def _dialog_state_or_none(value: object) -> DialogState | None:
    if not isinstance(value, dict):
        return None
    return cast(DialogState, value)


def _tool_args_or_none(value: object) -> ToolArguments | None:
    if not isinstance(value, Mapping):
        return None
    return dict(value)


def _copy_core_state_fields(
    state: RuntimeStateInput,
    state_copy: RuntimeStatePatch,
) -> None:
    if "thread_id" in state:
        state_copy["thread_id"] = state["thread_id"]
    if "project_id" in state:
        state_copy["project_id"] = state["project_id"]
    if "client_id" in state:
        state_copy["client_id"] = state["client_id"]
    # response_text is persisted as an assistant message, not reconstructed as
    # executable state for the next user turn.
    if "metadata" in state:
        state_copy["metadata"] = state["metadata"]


def _copy_runtime_signal_fields(
    state: RuntimeStateInput,
    state_copy: RuntimeStatePatch,
) -> None:
    _copy_decision_fields(state, state_copy)
    _copy_runtime_flags(state, state_copy)


def _copy_decision_fields(
    state: RuntimeStateInput,
    state_copy: RuntimeStatePatch,
) -> None:
    if "decision" in state:
        state_copy["decision"] = state["decision"]
    if "intent" in state:
        state_copy["intent"] = state["intent"]
    if "lifecycle" in state:
        state_copy["lifecycle"] = state["lifecycle"]
    if "lead_status" in state:
        state_copy["lead_status"] = state["lead_status"]
    if "cta" in state:
        state_copy["cta"] = state["cta"]
    if "topic" in state:
        state_copy["topic"] = state["topic"]
    if "cta_hint" in state:
        state_copy["cta_hint"] = state["cta_hint"]
    if "emotion" in state and state["emotion"] is not None:
        state_copy["emotion"] = state["emotion"]


def _copy_runtime_flags(
    state: RuntimeStateInput,
    state_copy: RuntimeStatePatch,
) -> None:
    if "is_repeat_like" in state:
        state_copy["is_repeat_like"] = state["is_repeat_like"]
    if "confidence" in state:
        state_copy["confidence"] = state["confidence"]
    if "requires_human" in state:
        state_copy["requires_human"] = state["requires_human"]
    if "ticket_created" in state:
        state_copy["ticket_created"] = state["ticket_created"]
    if "handoff_ticket_id" in state:
        state_copy["handoff_ticket_id"] = state["handoff_ticket_id"]
    if "escalation_failed" in state:
        state_copy["escalation_failed"] = state["escalation_failed"]
    if "handoff_completed" in state:
        state_copy["handoff_completed"] = state["handoff_completed"]
    if "thread_waiting_manager" in state:
        state_copy["thread_waiting_manager"] = state["thread_waiting_manager"]
    if "notification_degraded" in state:
        state_copy["notification_degraded"] = state["notification_degraded"]
    if "close_ticket" in state:
        state_copy["close_ticket"] = state["close_ticket"]
    if "features" in state:
        state_copy["features"] = state["features"]
    if "dialog_state" in state:
        state_copy["dialog_state"] = state["dialog_state"]

    if "technical_failure_count" in state:
        state_copy["technical_failure_count"] = state["technical_failure_count"]
    if "technical_failure_stage" in state:
        state_copy["technical_failure_stage"] = state["technical_failure_stage"]
    if "technical_failure_error" in state:
        state_copy["technical_failure_error"] = state["technical_failure_error"]
    if "technical_incident_created" in state:
        state_copy["technical_incident_created"] = state["technical_incident_created"]
    if "technical_ticket_id" in state:
        state_copy["technical_ticket_id"] = state["technical_ticket_id"]

    if "domain" in state:
        state_copy["domain"] = state["domain"]
    if "turn_relation" in state:
        state_copy["turn_relation"] = state["turn_relation"]
    if "conversation_context" in state:
        state_copy["conversation_context"] = state["conversation_context"]
    if "should_search_kb" in state:
        state_copy["should_search_kb"] = state["should_search_kb"]
    if "should_generate_answer" in state:
        state_copy["should_generate_answer"] = state["should_generate_answer"]
    if "should_offer_manager" in state:
        state_copy["should_offer_manager"] = state["should_offer_manager"]


def _access_issue_kind(text: str) -> str | None:
    if "не могу войти" in text or "login" in text or "sign in" in text:
        return "access"
    return None


def _billing_issue_kind(text: str) -> str | None:
    if "оплат" in text or "billing" in text or "invoice" in text:
        return "billing"
    return None


def _support_issue_kind(*, topic: str | None, emotion: str | None) -> str | None:
    if topic == "support" or emotion in {"negative", "angry"}:
        return "support"
    return None


def _conversation_context_from_payload(value: object) -> ConversationContextState:
    if not isinstance(value, Mapping):
        return ConversationContextState(
            current_subject=None,
            last_standalone_query=None,
            repeat_relation="none",
            dissatisfaction=False,
            answered_questions=[],
            question_attempts=[],
        )
    answered = value.get("answered_questions")
    attempts = value.get("question_attempts")
    answered_questions = cast(
        list[AnsweredQuestionEntry],
        [
            {str(key): item_value for key, item_value in item.items()}
            for item in answered
            if isinstance(item, Mapping)
        ][-ANSWERED_QUESTIONS_LIMIT:]
        if isinstance(answered, list)
        else [],
    )
    question_attempts = (
        _question_attempts_from_payload(attempts)
        if isinstance(attempts, list)
        else _attempts_from_legacy_answered_questions(answered_questions)
    )
    return ConversationContextState(
        current_subject=_optional_text(value.get("current_subject")),
        last_standalone_query=_optional_text(value.get("last_standalone_query")),
        repeat_relation=_repeat_relation(value.get("repeat_relation")),
        dissatisfaction=coerce_bool(value.get("dissatisfaction"), False),
        answered_questions=answered_questions,
        question_attempts=question_attempts,
    )


def _question_attempts_from_context(
    context: ConversationContextState,
) -> list[dict[str, object]]:
    return _question_attempts_from_payload(context.get("question_attempts"))


def _question_attempts_from_payload(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    attempts: list[dict[str, object]] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        query = _optional_text(item.get("standalone_query"))
        outcome = _optional_text(item.get("outcome"))
        if not query or outcome not in {
            "supported",
            "partially_supported",
            "unsupported",
            "retrieval_failed",
            "generation_failed",
        }:
            continue
        attempts.append(
            {
                "standalone_query": query,
                "subject": _optional_text(item.get("subject")),
                "outcome": outcome,
                "answer_preview": _optional_text(item.get("answer_preview")),
                "unsupported_aspects": _string_list(item.get("unsupported_aspects"))[
                    :8
                ],
                "supporting_entry_ids": _string_list(item.get("supporting_entry_ids"))[
                    :8
                ],
                "attempted_at": _optional_text(item.get("attempted_at")) or "",
            }
        )
    return attempts[-QUESTION_ATTEMPTS_LIMIT:]


def _attempts_from_legacy_answered_questions(
    answered_questions: list[AnsweredQuestionEntry],
) -> list[dict[str, object]]:
    attempts: list[dict[str, object]] = []
    for item in answered_questions[-QUESTION_ATTEMPTS_LIMIT:]:
        query = _optional_text(item.get("standalone_query"))
        answerability = _optional_text(item.get("answerability"))
        if not query or answerability not in {"supported", "partially_supported"}:
            continue
        attempts.append(
            {
                "standalone_query": query,
                "subject": _optional_text(item.get("subject")),
                "outcome": answerability,
                "answer_preview": _optional_text(item.get("answer_preview")),
                "unsupported_aspects": _string_list(item.get("unsupported_aspects"))[
                    :8
                ],
                "supporting_entry_ids": _string_list(item.get("supporting_entry_ids"))[
                    :8
                ],
                "attempted_at": _optional_text(item.get("answered_at")) or "",
            }
        )
    return attempts


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item is not None]


def _memory_candidate_list(value: object) -> list[MemoryCandidateState]:
    if not isinstance(value, list):
        return []
    return [
        MemoryCandidateState(**dict(item))
        for item in value
        if isinstance(item, Mapping)
    ]


def _bounded_text(value: object, limit: int) -> str:
    text = " ".join(str(value or "").split())
    return text[:limit].strip()


def _is_duplicate_answered_question(
    entries: Sequence[Mapping[str, object]],
    candidate: Mapping[str, object],
) -> bool:
    if not entries:
        return False
    last = entries[-1]
    return _normalized_text(last.get("standalone_query")) == _normalized_text(
        candidate.get("standalone_query")
    ) and _string_list(last.get("supporting_entry_ids")) == _string_list(
        candidate.get("supporting_entry_ids")
    )


def _normalized_text(value: object) -> str:
    return " ".join(str(value or "").split()).lower()


def _repeat_relation(
    value: object,
) -> Literal["none", "clarification", "repeat_answered", "repeat_unresolved"]:
    text = _optional_text(value) or "none"
    if text in {"none", "clarification", "repeat_answered", "repeat_unresolved"}:
        return cast(
            Literal["none", "clarification", "repeat_answered", "repeat_unresolved"],
            text,
        )
    return "none"


def _object_list(value: object) -> list[object]:
    if not isinstance(value, list):
        return []
    return list(value)
