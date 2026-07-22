"""
Thin LangGraph adapter for the pure domain policy engine.
"""

from collections.abc import Mapping
from typing import Protocol, cast
from uuid import UUID

from src.agent.state import AgentState
from src.domain.runtime.cta import (
    CONTINUE_EXPLANATION_CTA,
    normalize_cta,
)
from src.domain.runtime.policy.decision_engine import get_decision
from src.domain.runtime.policy.handoff_confirmation import (
    build_handoff_confirmation_text,
    is_handoff_confirmation_pending,
    with_handoff_confirmation_pending,
)
from src.domain.runtime.policy.handoff_request import is_explicit_handoff_request
from src.domain.runtime.policy.intent_topic import (
    feature_risk_detected,
    normalize_intent,
    resolve_current_topic,
)
from src.domain.runtime.dialog_state import merge_dialog_state
from src.domain.runtime.policy.repeat_detection import build_dialog_state_update
from src.domain.runtime.policy.result import PolicyDecisionContext, PolicyDecisionResult
from src.domain.runtime.state_contracts import RuntimeStateInput
from src.domain.project_plane.json_types import JsonObject, json_object_from_unknown
from src.infrastructure.db.repositories.event_repository import EventRepository
from src.infrastructure.logging.logger import get_logger, log_node_execution


logger = get_logger(__name__)

ACTION_CTA_DECLINED_TEXT = "Хорошо, не передаю менеджеру. Продолжу помогать здесь."
CONTINUATION_DECLINED_TEXT = (
    "Хорошо, без дополнительных подробностей. Если появится вопрос, напишите его здесь."
)


def _handoff_confirmation_result(
    context: PolicyDecisionContext,
    *,
    normalized_intent: str,
    topic: str,
    cta: str,
) -> PolicyDecisionResult:
    next_dialog_state = merge_dialog_state(
        build_dialog_state_update(
            context.dialog_state,
            intent=normalized_intent,
            topic=topic,
            cta=cta,
            lifecycle=context.lifecycle,
            decision="RESPOND",
            features=context.features,
        ),
        lifecycle=context.lifecycle,
    )

    next_dialog_state = with_handoff_confirmation_pending(next_dialog_state)
    return PolicyDecisionResult(
        lifecycle=context.lifecycle,
        decision="RESPOND",
        cta=cta,
        topic=topic,
        lead_status=str(next_dialog_state.get("lead_status") or context.lifecycle),
        dialog_state=next_dialog_state,
        response_text=build_handoff_confirmation_text(context.user_input),
        requires_human=False,
    )


def _template_policy_result(
    context: PolicyDecisionContext,
    *,
    domain: str,
    turn_relation: str,
) -> PolicyDecisionResult:
    topic = "other"
    normalized_intent = "other"
    cta = "none"

    if domain == "greeting":
        topic = "other"
    elif domain == "out_of_domain":
        topic = "other"
    elif domain == "ambiguous":
        topic = str(context.dialog_state.get("last_topic") or "other")

    next_dialog_state = merge_dialog_state(
        build_dialog_state_update(
            context.dialog_state,
            intent=normalized_intent,
            topic=topic,
            cta=cta,
            lifecycle=context.lifecycle,
            decision="RESPOND_TEMPLATE",
            features=context.features,
        ),
        lifecycle=context.lifecycle,
    )

    return PolicyDecisionResult(
        lifecycle=context.lifecycle,
        decision="RESPOND_TEMPLATE",
        cta=cta,
        topic=topic,
        lead_status=str(next_dialog_state.get("lead_status") or context.lifecycle),
        dialog_state=next_dialog_state,
        requires_human=False,
    )


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _resolved_cta_reply(state: AgentState) -> str | None:
    value = str(state.get("resolved_cta_reply") or "").strip().lower()
    return value if value in {"affirmative", "negative"} else None


def _resolved_cta(state: AgentState) -> str | None:
    return normalize_cta(state.get("resolved_cta"))


def _merge_intent_and_policy_state(
    state: AgentState,
    policy_patch: dict[str, object],
) -> dict[str, object]:
    """Apply explicit current-turn intent signals over derived policy signals."""
    resolved_cta = _resolved_cta(state)
    resolved_reply = _resolved_cta_reply(state)

    if resolved_cta == "call_manager":
        if resolved_reply == "affirmative":
            patch = dict(policy_patch)
            patch.update(
                {
                    "decision": "ESCALATE",
                    "requires_human": True,
                    "cta": resolved_cta,
                    "turn_relation": state.get("turn_relation"),
                    "knowledge_query": None,
                    "should_search_kb": False,
                    "should_generate_answer": False,
                    "should_offer_manager": False,
                }
            )
            return patch

        if resolved_reply == "negative":
            patch = dict(policy_patch)
            patch.update(
                {
                    "decision": "RESPOND",
                    "response_text": ACTION_CTA_DECLINED_TEXT,
                    "requires_human": False,
                    "cta": "none",
                    "turn_relation": state.get("turn_relation"),
                    "knowledge_query": None,
                    "should_search_kb": False,
                    "should_generate_answer": False,
                    "should_offer_manager": False,
                }
            )
            return patch

    if resolved_cta == "book_consultation":
        if resolved_reply == "affirmative":
            patch = dict(policy_patch)
            patch.update(
                {
                    "decision": "ESCALATE",
                    "requires_human": True,
                    "cta": resolved_cta,
                    "turn_relation": state.get("turn_relation"),
                    "knowledge_query": None,
                    "should_search_kb": False,
                    "should_generate_answer": False,
                    "should_offer_manager": False,
                }
            )
            return patch

        if resolved_reply == "negative":
            patch = dict(policy_patch)
            patch.update(
                {
                    "decision": "RESPOND",
                    "response_text": ACTION_CTA_DECLINED_TEXT,
                    "requires_human": False,
                    "cta": "none",
                    "turn_relation": state.get("turn_relation"),
                    "knowledge_query": None,
                    "should_search_kb": False,
                    "should_generate_answer": False,
                    "should_offer_manager": False,
                }
            )
            return patch

    if resolved_cta == CONTINUE_EXPLANATION_CTA:
        if resolved_reply == "affirmative":
            patch = dict(policy_patch)
            patch.update(
                {
                    "decision": "LLM_GENERATE",
                    "cta": CONTINUE_EXPLANATION_CTA,
                    "topic": state.get("topic") or policy_patch.get("topic"),
                    "turn_relation": "continuation",
                    "knowledge_query": _optional_text(state.get("knowledge_query")),
                    "should_search_kb": True,
                    "should_generate_answer": True,
                    "should_offer_manager": False,
                    "requires_human": False,
                }
            )
            return patch

        if resolved_reply == "negative":
            patch = dict(policy_patch)
            patch.update(
                {
                    "decision": "RESPOND",
                    "response_text": CONTINUATION_DECLINED_TEXT,
                    "requires_human": False,
                    "cta": "none",
                    "turn_relation": "short_reply",
                    "knowledge_query": None,
                    "should_search_kb": False,
                    "should_generate_answer": False,
                    "should_offer_manager": False,
                }
            )
            return patch

    patch = dict(policy_patch)
    patch["knowledge_query"] = None
    if "turn_relation" in state:
        patch["turn_relation"] = state.get("turn_relation")
    if patch.get("decision") != "LLM_GENERATE":
        patch["should_search_kb"] = False
        patch["should_generate_answer"] = False
        patch["should_offer_manager"] = False
    return patch


def _risk_features(features: object) -> list[str]:
    if not isinstance(features, Mapping):
        return []
    return [
        str(key)
        for key, value in features.items()
        if isinstance(value, (int, float)) and float(value) >= 0.8
    ]


def _handoff_signal_source(
    *,
    lifecycle: str,
    normalized_intent: str,
    resolved_topic: str,
    previous_repeat_count: int,
    final_repeat_count: object,
    features: object,
    decision: str,
    resolved_cta: str | None,
    resolved_reply: str | None,
    user_input: str,
) -> str:
    if resolved_cta in {"call_manager", "book_consultation"} and resolved_reply:
        return "resolved_action_cta"
    if lifecycle in {"handoff_to_manager", "angry"}:
        return "existing_handoff_lifecycle"
    if is_explicit_handoff_request(user_input):
        return "rules_explicit_request"
    if normalized_intent == "handoff_request" or resolved_topic == "handoff":
        return "intent_classified_handoff"
    if normalized_intent == "angry" or resolved_topic == "angry":
        return "anger"
    if feature_risk_detected(features):
        return "complaint_or_refund_risk"
    try:
        repeat_count = int(final_repeat_count or 0)
    except (TypeError, ValueError):
        repeat_count = 0
    if decision in {"ESCALATE", "ESCALATE_TO_HUMAN", "RESPOND"}:
        if previous_repeat_count >= 2 and repeat_count >= 3:
            return "repeat_escalation"
    return "none"


class PolicyEventAppender(Protocol):
    async def append(
        self,
        stream_id: UUID | str,
        project_id: UUID | str,
        event_type: str,
        payload: JsonObject,
    ) -> int: ...


def _event_id_for_append(value: str) -> UUID | str:
    try:
        return UUID(value)
    except ValueError:
        return value


def create_policy_engine_node(
    event_repo: EventRepository | None = None,
):
    async def _policy_engine_node_impl(state: AgentState) -> dict[str, object]:
        context = PolicyDecisionContext.from_state(cast(RuntimeStateInput, state))

        # Preserve deterministic response patches produced before policy_engine,
        # especially technical failures from intent_extractor.
        if state.get("decision") == "RESPOND" and state.get("response_text"):
            return {
                "decision": "RESPOND",
                "response_text": state.get("response_text"),
                "requires_human": False,
                "domain": state.get("domain"),
                "turn_relation": state.get("turn_relation"),
                "should_search_kb": False,
                "should_generate_answer": False,
                "should_offer_manager": state.get("should_offer_manager") or False,
                "technical_failure_count": state.get("technical_failure_count") or 0,
                "technical_failure_stage": state.get("technical_failure_stage"),
                "technical_failure_error": state.get("technical_failure_error"),
                "technical_incident_created": state.get("technical_incident_created")
                or False,
            }

        domain = str(state.get("domain") or "business").strip().lower()
        turn_relation = str(state.get("turn_relation") or "unknown").strip().lower()
        should_generate_answer = bool(state.get("should_generate_answer", True))

        if (
            domain in {"greeting", "out_of_domain", "ambiguous"}
            or not should_generate_answer
        ):
            result = _template_policy_result(
                context,
                domain=domain,
                turn_relation=turn_relation,
            )
            patch = dict(result.to_state_patch(previous_lifecycle=context.lifecycle))
            patch.update(
                {
                    "domain": domain,
                    "turn_relation": turn_relation,
                    "should_search_kb": False,
                    "should_generate_answer": False,
                    "requires_human": False,
                }
            )
            return patch

        normalized_intent = normalize_intent(context.intent)
        input_topic = state.get("topic")
        topic = resolve_current_topic(
            normalized_intent,
            context.features,
            current_topic=str(input_topic) if input_topic is not None else None,
        )
        previous_repeat_count = int(context.dialog_state.get("repeat_count") or 0)

        new_lifecycle, decision, cta = get_decision(
            context.lifecycle,
            normalized_intent,
            features=context.features,
            dialog_state=context.dialog_state,
            current_topic=topic,
        )

        next_dialog_state = merge_dialog_state(
            build_dialog_state_update(
                context.dialog_state,
                intent=normalized_intent,
                topic=topic,
                cta=cta,
                lifecycle=new_lifecycle,
                decision=decision,
                features=context.features,
            )
        )
        result = PolicyDecisionResult(
            lifecycle=new_lifecycle,
            decision=decision,
            cta=cta,
            topic=topic,
            lead_status=str(next_dialog_state.get("lead_status") or ""),
            dialog_state=next_dialog_state,
        )
        if decision == "ESCALATE_TO_HUMAN" and not is_handoff_confirmation_pending(
            context.dialog_state
        ):
            result = _handoff_confirmation_result(
                context,
                normalized_intent=normalized_intent,
                topic=topic,
                cta=cta,
            )

        policy_patch = dict(result.to_state_patch(previous_lifecycle=context.lifecycle))
        final_patch = _merge_intent_and_policy_state(state, policy_patch)
        final_dialog_state = final_patch.get("dialog_state")
        if not isinstance(final_dialog_state, dict):
            final_dialog_state = result.dialog_state

        if event_repo and context.thread_id and context.project_id:
            try:
                appendable_event_repo = cast(PolicyEventAppender, event_repo)
                await appendable_event_repo.append(
                    stream_id=_event_id_for_append(context.thread_id),
                    project_id=_event_id_for_append(context.project_id),
                    event_type="policy_decision",
                    payload=json_object_from_unknown(
                        {
                            "decision": final_patch.get("decision"),
                            "intent": final_dialog_state.get("last_intent"),
                            "lifecycle": final_patch.get("lifecycle", result.lifecycle),
                            "cta": final_patch.get("cta"),
                            "topic": final_patch.get("topic"),
                            "repeat_count": final_dialog_state.get("repeat_count"),
                            "lead_status": final_patch.get("lead_status"),
                            "confidence": context.confidence,
                        }
                    ),
                )
                logger.debug(
                    "Policy decision event emitted",
                    extra={"thread_id": context.thread_id},
                )
            except Exception as exc:
                logger.warning(
                    "Failed to emit policy_decision event", extra={"error": str(exc)}
                )

        logger.info(
            "Policy routing trace",
            extra={
                "thread_id": context.thread_id,
                "project_id": context.project_id,
                "domain": domain,
                "normalized_intent": normalized_intent,
                "input_topic": input_topic,
                "resolved_topic": topic,
                "old_lifecycle": context.lifecycle,
                "new_lifecycle": final_patch.get("lifecycle", result.lifecycle),
                "previous_repeat_count": previous_repeat_count,
                "final_repeat_count": final_dialog_state.get("repeat_count"),
                "risk_features": _risk_features(context.features),
                "handoff_signal_source": _handoff_signal_source(
                    lifecycle=context.lifecycle,
                    normalized_intent=normalized_intent,
                    resolved_topic=topic,
                    previous_repeat_count=previous_repeat_count,
                    final_repeat_count=final_dialog_state.get("repeat_count"),
                    features=context.features,
                    decision=str(final_patch.get("decision") or ""),
                    resolved_cta=_resolved_cta(state),
                    resolved_reply=_resolved_cta_reply(state),
                    user_input=context.user_input,
                ),
                "raw_policy_decision": decision,
                "final_decision": final_patch.get("decision"),
                "cta": final_patch.get("cta"),
                "requires_human": final_patch.get("requires_human", False),
                "should_search_kb": final_patch.get("should_search_kb"),
                "should_generate_answer": final_patch.get("should_generate_answer"),
                "should_offer_manager": final_patch.get("should_offer_manager"),
                "response_kind": "template"
                if final_patch.get("decision") == "RESPOND_TEMPLATE"
                else ("deterministic" if final_patch.get("response_text") else "llm"),
            },
        )
        return final_patch

    def _get_policy_input_size(state: AgentState) -> int:
        return (
            len(str(state.get("features") or ""))
            + len(str(state.get("intent") or ""))
            + len(str(state.get("dialog_state") or ""))
            + len(str((state.get("user_memory") or {}).get("dialog_state") or ""))
        )

    def _get_policy_output_size(result: dict[str, object]) -> int:
        return len(str(result))

    async def policy_engine_node(state: AgentState) -> dict[str, object]:
        return await log_node_execution(
            "policy_engine",
            _policy_engine_node_impl,
            state,
            get_input_size=_get_policy_input_size,
            get_output_size=_get_policy_output_size,
        )

    return policy_engine_node
