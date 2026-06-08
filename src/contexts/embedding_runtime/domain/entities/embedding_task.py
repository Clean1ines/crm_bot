from __future__ import annotations

from dataclasses import dataclass

from src.contexts.embedding_runtime.domain.value_objects.embedding_input_ref import (
    EmbeddingInputRef,
)
from src.contexts.embedding_runtime.domain.value_objects.embedding_model_id import (
    EmbeddingModelId,
)
from src.contexts.embedding_runtime.domain.value_objects.embedding_task_status import (
    EmbeddingTaskStatus,
)


@dataclass(frozen=True, slots=True)
class EmbeddingTask:
    task_id: str
    input_ref: EmbeddingInputRef
    model_id: EmbeddingModelId
    status: EmbeddingTaskStatus = EmbeddingTaskStatus.READY
    last_error_kind: str | None = None

    def __post_init__(self) -> None:
        if not self.task_id or not self.task_id.strip():
            raise ValueError("EmbeddingTask.task_id must be non-empty")
        if self.last_error_kind is not None and not self.last_error_kind.strip():
            raise ValueError("EmbeddingTask.last_error_kind must be non-empty when set")
        if (
            self.status
            in {
                EmbeddingTaskStatus.RETRYABLE_FAILED,
                EmbeddingTaskStatus.TERMINAL_FAILED,
            }
            and self.last_error_kind is None
        ):
            raise ValueError("failed EmbeddingTask must have last_error_kind")
        if (
            self.status
            not in {
                EmbeddingTaskStatus.RETRYABLE_FAILED,
                EmbeddingTaskStatus.TERMINAL_FAILED,
            }
            and self.last_error_kind is not None
        ):
            raise ValueError("only failed EmbeddingTask may carry last_error_kind")
