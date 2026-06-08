from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.contexts.llm_runtime.domain.value_objects.input_ref import LlmInputRef
from src.contexts.llm_runtime.domain.value_objects.llm_error_kind import LlmErrorKind
from src.contexts.llm_runtime.domain.value_objects.llm_route import LlmRoute
from src.contexts.llm_runtime.domain.value_objects.llm_task_status import LlmTaskStatus
from src.contexts.llm_runtime.domain.value_objects.output_contract_ref import (
    OutputContractRef,
)
from src.contexts.llm_runtime.domain.value_objects.prompt_version import PromptVersion


@dataclass(frozen=True, slots=True)
class LlmTask:
    task_id: str
    prompt_id: str
    prompt_version: PromptVersion
    input_ref: LlmInputRef
    output_contract_ref: OutputContractRef
    status: LlmTaskStatus = LlmTaskStatus.READY
    attempt_count: int = 0
    selected_route: LlmRoute | None = None
    wait_until: datetime | None = None
    last_error_kind: LlmErrorKind | None = None

    def __post_init__(self) -> None:
        if not self.task_id or not self.task_id.strip():
            raise ValueError("LlmTask.task_id must be non-empty")
        if not self.prompt_id or not self.prompt_id.strip():
            raise ValueError("LlmTask.prompt_id must be non-empty")
        if self.attempt_count < 0:
            raise ValueError("LlmTask.attempt_count must be >= 0")

        if self.status is LlmTaskStatus.RUNNING and self.selected_route is None:
            raise ValueError("RUNNING LlmTask must have selected_route")

        if self.status is LlmTaskStatus.DEFERRED:
            if self.wait_until is None:
                raise ValueError("DEFERRED LlmTask must have wait_until")
            if self.wait_until.tzinfo is None or self.wait_until.utcoffset() is None:
                raise ValueError("wait_until must be timezone-aware")

        if self.status is not LlmTaskStatus.DEFERRED and self.wait_until is not None:
            raise ValueError("Only DEFERRED LlmTask may carry wait_until")

        if self.status.is_terminal and self.wait_until is not None:
            raise ValueError("Terminal LlmTask must not carry wait_until")
