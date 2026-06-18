from __future__ import annotations

from dataclasses import dataclass

from src.domain.project_plane.json_types import JsonObject


@dataclass(frozen=True, slots=True)
class DraftClaimCompactionProgressSummary:
    workflow_run_id: str
    group_count: int
    done_group_count: int
    waiting_user_model_choice_group_count: int
    active_group_count: int
    active_node_count: int
    pending_comparison_count: int
    active_component_count: int = 0
    component_incompatibility_count: int = 0
    active_work_item_count: int = 0
    completed_work_item_count: int = 0
    failed_work_item_count: int = 0
    ready_work_item_count: int = 0
    leased_work_item_count: int = 0
    deferred_work_item_count: int = 0
    retryable_failed_work_item_count: int = 0
    terminal_failed_work_item_count: int = 0
    due_waiting_work_item_count: int = 0

    def __post_init__(self) -> None:
        _text(self.workflow_run_id, "workflow_run_id")
        for field_name, value in (
            ("group_count", self.group_count),
            ("done_group_count", self.done_group_count),
            (
                "waiting_user_model_choice_group_count",
                self.waiting_user_model_choice_group_count,
            ),
            ("active_group_count", self.active_group_count),
            ("active_node_count", self.active_node_count),
            ("pending_comparison_count", self.pending_comparison_count),
            ("active_component_count", self.active_component_count),
            (
                "component_incompatibility_count",
                self.component_incompatibility_count,
            ),
            ("active_work_item_count", self.active_work_item_count),
            ("completed_work_item_count", self.completed_work_item_count),
            ("failed_work_item_count", self.failed_work_item_count),
            ("ready_work_item_count", self.ready_work_item_count),
            ("leased_work_item_count", self.leased_work_item_count),
            ("deferred_work_item_count", self.deferred_work_item_count),
            (
                "retryable_failed_work_item_count",
                self.retryable_failed_work_item_count,
            ),
            ("terminal_failed_work_item_count", self.terminal_failed_work_item_count),
            ("due_waiting_work_item_count", self.due_waiting_work_item_count),
        ):
            _non_negative_int(value, field_name)

        if self.done_group_count > self.group_count:
            raise ValueError("done_group_count must be <= group_count")
        if self.waiting_user_model_choice_group_count > self.group_count:
            raise ValueError(
                "waiting_user_model_choice_group_count must be <= group_count"
            )
        if self.active_group_count > self.group_count:
            raise ValueError("active_group_count must be <= group_count")

    @property
    def all_groups_done(self) -> bool:
        return self.group_count > 0 and self.done_group_count == self.group_count

    @property
    def has_waiting_user_model_choice(self) -> bool:
        return self.waiting_user_model_choice_group_count > 0

    @property
    def has_due_compaction_work_items(self) -> bool:
        return self.due_waiting_work_item_count > 0

    @property
    def has_active_compaction_work_items(self) -> bool:
        return self.active_work_item_count > 0

    def to_payload(self) -> JsonObject:
        return {
            "workflow_run_id": self.workflow_run_id,
            "group_count": self.group_count,
            "done_group_count": self.done_group_count,
            "waiting_user_model_choice_group_count": (
                self.waiting_user_model_choice_group_count
            ),
            "active_group_count": self.active_group_count,
            "active_node_count": self.active_node_count,
            "pending_comparison_count": self.pending_comparison_count,
            "active_component_count": self.active_component_count,
            "component_incompatibility_count": self.component_incompatibility_count,
            "active_work_item_count": self.active_work_item_count,
            "completed_work_item_count": self.completed_work_item_count,
            "failed_work_item_count": self.failed_work_item_count,
            "ready_work_item_count": self.ready_work_item_count,
            "leased_work_item_count": self.leased_work_item_count,
            "deferred_work_item_count": self.deferred_work_item_count,
            "retryable_failed_work_item_count": self.retryable_failed_work_item_count,
            "terminal_failed_work_item_count": self.terminal_failed_work_item_count,
            "due_waiting_work_item_count": self.due_waiting_work_item_count,
        }


def _text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


def _non_negative_int(value: int, field_name: str) -> None:
    if not isinstance(value, int):
        raise TypeError(f"{field_name} must be int")
    if value < 0:
        raise ValueError(f"{field_name} must be >= 0")
