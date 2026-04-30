from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Mapping

from src.domain.display_names import build_display_name
from src.domain.project_plane.event_views import EventTimelineItemView
from src.domain.project_plane.json_types import JsonObject, json_object_from_unknown
from src.domain.project_plane.thread_views import (
    ThreadAnalyticsView,
    ThreadMessageCounts,
    ThreadWithProjectView,
)

ESCALATION_DECISIONS = frozenset({"ESCALATE", "ESCALATE_TO_HUMAN"})


def _string(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _timestamp(value: datetime | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return value.isoformat()


def _payload_text(payload: Mapping[str, object], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _payload_flag(payload: Mapping[str, object], key: str) -> bool:
    value = payload.get(key)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes"}
    return bool(value)


@dataclass(frozen=True, slots=True)
class ThreadTimelinePresentationDto:
    label: str
    summary: str
    accent: str = "neutral"

    def to_record(self) -> JsonObject:
        return {
            "label": self.label,
            "summary": self.summary,
            "accent": self.accent,
        }


@dataclass(frozen=True, slots=True)
class ThreadTimelineItemDto:
    id: int
    type: str
    payload: JsonObject
    ts: str | None = None
    stream_id: str | None = None
    presentation: ThreadTimelinePresentationDto = field(
        default_factory=lambda: ThreadTimelinePresentationDto(
            label="event recorded",
            summary="The system stored an internal event.",
        )
    )

    @classmethod
    def from_event(cls, event: EventTimelineItemView) -> "ThreadTimelineItemDto":
        return cls(
            id=event.id,
            type=event.type,
            payload=json_object_from_unknown(event.payload),
            ts=_timestamp(event.ts),
            stream_id=event.stream_id,
            presentation=_present_event(event),
        )

    def to_record(self) -> JsonObject:
        record: JsonObject = {
            "id": self.id,
            "type": self.type,
            "payload": dict(self.payload),
            "ts": self.ts,
            "presentation": self.presentation.to_record(),
        }
        if self.stream_id is not None:
            record["stream_id"] = self.stream_id
        return record


@dataclass(frozen=True, slots=True)
class ThreadInspectorStateDto:
    state: JsonObject

    @classmethod
    def create(
        cls,
        *,
        persisted_state: Mapping[str, object] | None,
        thread_view: ThreadWithProjectView | None,
        analytics_view: ThreadAnalyticsView | None,
        message_counts: ThreadMessageCounts,
    ) -> "ThreadInspectorStateDto":
        state = json_object_from_unknown(persisted_state or {})

        if thread_view is not None:
            display_name = build_display_name(
                full_name=thread_view.full_name,
                username=thread_view.username,
                email=thread_view.email,
                fallback="Клиент",
            )
            state["client"] = {
                "id": thread_view.client_id,
                "full_name": thread_view.full_name,
                "username": thread_view.username,
                "email": thread_view.email,
                "display_name": display_name,
                "chat_id": thread_view.chat_id,
            }
            state["status"] = thread_view.status
            state["created_at"] = _timestamp(thread_view.created_at)
            state["updated_at"] = _timestamp(thread_view.updated_at)
            state["conversation_summary"] = thread_view.context_summary

        if analytics_view is not None:
            if analytics_view.intent is not None:
                state["intent"] = analytics_view.intent
            if analytics_view.lifecycle is not None:
                state["lifecycle"] = analytics_view.lifecycle
            if analytics_view.cta is not None:
                state["cta"] = analytics_view.cta
            if analytics_view.decision is not None:
                state["decision"] = analytics_view.decision

        state["total_messages"] = message_counts.total
        state["ai_messages"] = message_counts.ai
        state["manager_messages"] = message_counts.manager
        return cls(state=state)

    def to_record(self) -> JsonObject:
        return {"state": dict(self.state)}


def _present_event(event: EventTimelineItemView) -> ThreadTimelinePresentationDto:
    payload = json_object_from_unknown(event.payload)
    event_type = event.type

    if event_type == "message_received":
        return ThreadTimelinePresentationDto(
            label="client message received",
            summary=_payload_text(payload, "text") or "The client sent a new message.",
        )

    if event_type == "ai_response":
        return ThreadTimelinePresentationDto(
            label="AI replied",
            summary=_payload_text(payload, "response_text")
            or _payload_text(payload, "text")
            or "The assistant sent a reply.",
        )

    if event_type == "ticket_created":
        return ThreadTimelinePresentationDto(
            label="ticket created",
            summary=_payload_text(payload, "title")
            or "A manager ticket was created for this conversation.",
            accent="warning",
        )

    if event_type == "manager_claimed":
        manager_name = _manager_name(payload)
        return ThreadTimelinePresentationDto(
            label="manager claimed",
            summary=f"{manager_name} took this ticket into work.",
            accent="info",
        )

    if event_type == "manager_replied":
        manager_name = _manager_name(payload)
        return ThreadTimelinePresentationDto(
            label="manager replied",
            summary=_payload_text(payload, "text")
            or f"{manager_name} replied to the client.",
            accent="info",
        )

    if event_type == "ticket_closed":
        reason = _payload_text(payload, "reason")
        summary = "The manager ticket was closed."
        if reason:
            summary = f"{summary} Reason: {reason}."
        return ThreadTimelinePresentationDto(
            label="ticket closed",
            summary=summary,
        )

    if event_type == "policy_decision":
        decision = _string(payload.get("decision"))
        if decision in ESCALATION_DECISIONS or _payload_flag(payload, "requires_human"):
            return ThreadTimelinePresentationDto(
                label="handoff requested",
                summary="The policy requested a manager handoff.",
                accent="warning",
            )

    return ThreadTimelinePresentationDto(
        label=event_type.replace("_", " "),
        summary="The system stored an internal event.",
    )


def _manager_name(payload: Mapping[str, object]) -> str:
    identity = payload.get("manager_identity")
    if isinstance(identity, Mapping):
        display_name = _payload_text(identity, "display_name")
        if display_name:
            return display_name
    display_name = _payload_text(payload, "manager_display_name")
    if display_name:
        return display_name
    return "Manager"
