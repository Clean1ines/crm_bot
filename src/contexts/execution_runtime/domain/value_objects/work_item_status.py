from __future__ import annotations

from enum import StrEnum


class WorkItemStatus(StrEnum):
    """Canonical Execution Runtime lifecycle status.

    These statuses are deliberately generic. They must encode only execution
    lifecycle semantics.
    """

    READY = "ready"
    LEASED = "leased"
    COMPLETED = "completed"
    RETRYABLE_FAILED = "retryable_failed"
    TERMINAL_FAILED = "terminal_failed"
    CANCELLED = "cancelled"
    SPLIT_SUPERSEDED = "split_superseded"
    USER_ACTION_REQUIRED = "user_action_required"

    @property
    def is_terminal(self) -> bool:
        return self in {
            WorkItemStatus.COMPLETED,
            WorkItemStatus.TERMINAL_FAILED,
            WorkItemStatus.CANCELLED,
            WorkItemStatus.SPLIT_SUPERSEDED,
            WorkItemStatus.USER_ACTION_REQUIRED,
        }

    @property
    def is_waiting(self) -> bool:
        return self in {
            WorkItemStatus.READY,
            WorkItemStatus.RETRYABLE_FAILED,
        }
