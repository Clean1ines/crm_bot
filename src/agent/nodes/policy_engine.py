"""
Thin LangGraph adapter for the pure domain policy engine.
"""

from typing import Protocol, cast
from uuid import UUID

from src.agent.state import AgentState
from src.domain.runtime.policy.decision_engine import get_decision
from src.domain.runtime.policy.intent_topic import normalize_intent, resolve_topic
from src.domain.runtime.dialog_state import merge_dialog_state
from src.domain.runtime.policy.repeat_detection import build_dialog_state_update
from src.domain.runtime.policy.result import PolicyDecisionContext, PolicyDecisionResult
from src.domain.runtime.state_contracts import RuntimeStateInput
from src.domain.project_plane.json_types import JsonObject, json_object_from_unknown
from src.infrastructure.db.repositories.event_repository import EventRepository
from src.infrastructure.logging.logger import get_logger, log_node_execution


logger = get_logger(__name__)


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
        normalized_intent = normalize_intent(context.intent)
        topic = resolve_topic(normalized_intent, context.features)

        new_lifecycle, decision, cta = get_decision(
            context.lifecycle,
            normalized_intent,
            features=context.features,
            dialog_state=context.dialog_state,
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

        if event_repo and context.thread_id and context.project_id:
            try:
                appendable_event_repo = cast(PolicyEventAppender, event_repo)
                await appendable_event_repo.append(
                    stream_id=_event_id_for_append(context.thread_id),
                    project_id=_event_id_for_append(context.project_id),
                    event_type="policy_decision",
                    payload=json_object_from_unknown(
                        result.to_event_payload(confidence=context.confidence)
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

        logger.debug(
            "Policy decision finalized",
            extra={
                "old_lifecycle": context.lifecycle,
                "new_lifecycle": result.lifecycle,
                "intent": normalized_intent,
                "topic": result.topic,
                "decision": result.decision,
                "cta": result.cta,
                "repeat_count": result.dialog_state.get("repeat_count"),
                "lead_status": result.lead_status,
            },
        )
        return dict(result.to_state_patch(previous_lifecycle=context.lifecycle))

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
