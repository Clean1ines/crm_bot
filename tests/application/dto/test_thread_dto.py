from src.application.dto.thread_dto import (
    ThreadInspectorStateDto,
    ThreadTimelineItemDto,
)
from src.domain.project_plane.event_views import EventTimelineItemView
from src.domain.project_plane.thread_views import (
    ThreadAnalyticsView,
    ThreadMessageCounts,
    ThreadWithProjectView,
)


def test_thread_timeline_item_dto_adds_readable_presentation_for_handoff_policy():
    item = ThreadTimelineItemDto.from_event(
        EventTimelineItemView(
            id=1,
            type="policy_decision",
            payload={"decision": "ESCALATE_TO_HUMAN", "requires_human": True},
            ts="2026-04-30T12:00:00Z",
        )
    )

    record = item.to_record()
    assert record["type"] == "policy_decision"
    assert record["presentation"] == {
        "label": "handoff requested",
        "summary": "The policy requested a manager handoff.",
        "accent": "warning",
    }


def test_thread_timeline_item_dto_uses_manager_reply_text():
    item = ThreadTimelineItemDto.from_event(
        EventTimelineItemView(
            id=2,
            type="manager_replied",
            payload={"text": "We will contact you today."},
            ts="2026-04-30T12:00:00Z",
        )
    )

    assert item.to_record()["presentation"]["label"] == "manager replied"
    assert item.to_record()["presentation"]["summary"] == "We will contact you today."


def test_thread_inspector_state_dto_merges_view_and_persisted_state():
    dto = ThreadInspectorStateDto.create(
        persisted_state={"key": "value"},
        thread_view=ThreadWithProjectView(
            thread_id="thread-1",
            client_id="client-1",
            status="manual",
            context_summary="Short summary",
            project_id="project-1",
            full_name="Ada Lovelace",
        ),
        analytics_view=ThreadAnalyticsView(
            intent="support",
            lifecycle="handoff_to_manager",
            cta="call_manager",
            decision="ESCALATE_TO_HUMAN",
        ),
        message_counts=ThreadMessageCounts(total=3, ai=1, manager=1),
    )

    state = dto.to_record()["state"]
    assert state["key"] == "value"
    assert state["status"] == "manual"
    assert state["conversation_summary"] == "Short summary"
    assert state["intent"] == "support"
    assert state["decision"] == "ESCALATE_TO_HUMAN"
    assert state["total_messages"] == 3
