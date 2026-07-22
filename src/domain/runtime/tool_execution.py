from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping

from src.domain.runtime.state_contracts import (
    RuntimeStateInput,
    RuntimeStatePatch,
    ToolArguments,
    ToolResultPayload,
)


class ToolExecutionStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REQUIRES_HUMAN = "requires_human"


TOOL_EXECUTION_STATUS_VALUES = frozenset(item.value for item in ToolExecutionStatus)


class ToolSafeErrorCode(StrEnum):
    TOOL_EXECUTION_FAILED = "tool_execution_failed"
    TOOL_TIMEOUT = "tool_timeout"
    TOOL_UNAVAILABLE = "tool_unavailable"
    INVALID_TOOL_OUTCOME = "invalid_tool_outcome"
    MISSING_TOOL_SELECTION = "missing_tool_selection"
    TOOL_BUSINESS_REJECTED = "tool_business_rejected"
    MANUAL_ACTION_REQUIRED = "manual_action_required"
    TELEGRAM_REQUEST_REJECTED = "telegram_request_rejected"
    TICKET_CREATION_FAILED = "ticket_creation_failed"
    KNOWLEDGE_SEARCH_FAILED = "knowledge_search_failed"
    HANDOFF_STATE_TRANSITION_FAILED = "handoff_state_transition_failed"
    HANDOFF_COMPENSATION_FAILED = "handoff_compensation_failed"


TOOL_SAFE_ERROR_CODE_VALUES = frozenset(item.value for item in ToolSafeErrorCode)


@dataclass(frozen=True, slots=True)
class ToolExecutionOutcome:
    status: ToolExecutionStatus
    payload: object | None = None
    safe_error_code: str | None = None
    response_text: str | None = None

    def __post_init__(self) -> None:
        normalized_status = normalize_tool_execution_status(self.status)
        if normalized_status is None:
            raise ValueError("Unknown tool execution status")
        object.__setattr__(self, "status", normalized_status)
        if normalized_status is ToolExecutionStatus.SUCCEEDED:
            if self.safe_error_code is not None:
                raise ValueError(
                    "Successful tool outcome must not have safe_error_code"
                )
            return
        if self.safe_error_code is None:
            fallback = (
                ToolSafeErrorCode.MANUAL_ACTION_REQUIRED
                if normalized_status is ToolExecutionStatus.REQUIRES_HUMAN
                else ToolSafeErrorCode.TOOL_EXECUTION_FAILED
            )
            object.__setattr__(self, "safe_error_code", fallback.value)
            return
        object.__setattr__(
            self, "safe_error_code", normalize_safe_error_code(self.safe_error_code)
        )

    @classmethod
    def succeeded(
        cls, *, payload: object | None = None, response_text: str | None = None
    ) -> "ToolExecutionOutcome":
        return cls(
            status=ToolExecutionStatus.SUCCEEDED,
            payload=payload,
            response_text=response_text,
        )

    @classmethod
    def failed(
        cls,
        *,
        safe_error_code: ToolSafeErrorCode
        | str = ToolSafeErrorCode.TOOL_EXECUTION_FAILED,
        response_text: str | None = None,
        payload: object | None = None,
    ) -> "ToolExecutionOutcome":
        return cls(
            status=ToolExecutionStatus.FAILED,
            payload=payload,
            safe_error_code=normalize_safe_error_code(safe_error_code),
            response_text=response_text,
        )

    @classmethod
    def requires_human(
        cls,
        *,
        safe_error_code: ToolSafeErrorCode
        | str = ToolSafeErrorCode.MANUAL_ACTION_REQUIRED,
        response_text: str | None = None,
        payload: object | None = None,
    ) -> "ToolExecutionOutcome":
        return cls(
            status=ToolExecutionStatus.REQUIRES_HUMAN,
            payload=payload,
            safe_error_code=normalize_safe_error_code(safe_error_code),
            response_text=response_text,
        )


def normalize_tool_execution_status(value: object) -> ToolExecutionStatus | None:
    text = str(value or "").strip().lower()
    for status in ToolExecutionStatus:
        if text == status.value:
            return status
    return None


def normalize_safe_error_code(value: object) -> str:
    text = str(value or "").strip().lower()
    return (
        text
        if text in TOOL_SAFE_ERROR_CODE_VALUES
        else ToolSafeErrorCode.TOOL_EXECUTION_FAILED.value
    )


def exception_safe_error_code(exc: BaseException) -> ToolSafeErrorCode:
    if isinstance(exc, TimeoutError):
        return ToolSafeErrorCode.TOOL_TIMEOUT
    return ToolSafeErrorCode.TOOL_EXECUTION_FAILED


@dataclass(slots=True)
class ToolExecutionContext:
    tool_name: str | None
    tool_args: ToolArguments
    project_id: str | None = None
    thread_id: str | None = None

    @classmethod
    def from_state(cls, state: RuntimeStateInput) -> "ToolExecutionContext":
        raw_args = state.get("tool_args")
        return cls(
            tool_name=state.get("tool_name"),
            tool_args=dict(raw_args) if isinstance(raw_args, Mapping) else {},
            project_id=state.get("project_id"),
            thread_id=state.get("thread_id"),
        )

    def execution_context(self) -> RuntimeStatePatch:
        return {
            "project_id": self.project_id,
            "thread_id": self.thread_id,
        }


@dataclass(slots=True)
class ToolExecutionResult:
    tool_result: ToolResultPayload | object | None = None
    requires_human: bool = False
    response_text: str | None = None
    status: ToolExecutionStatus | None = None
    safe_error_code: str | None = None
    tool_response_text: str | None = None

    def to_state_patch(self) -> RuntimeStatePatch:
        result: RuntimeStatePatch = {
            "tool_result": self.tool_result,
            "requires_human": self.requires_human,
        }
        if self.status is not None:
            result["tool_execution_status"] = self.status.value
        if self.safe_error_code is not None:
            result["tool_execution_safe_error_code"] = normalize_safe_error_code(
                self.safe_error_code
            )
        if self.tool_response_text is not None:
            result["tool_response_text"] = self.tool_response_text
        if self.response_text is not None:
            result["response_text"] = self.response_text
        return result
