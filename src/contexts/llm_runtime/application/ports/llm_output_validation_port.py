from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from src.contexts.llm_runtime.domain.entities.llm_task import LlmTask
from src.contexts.llm_runtime.domain.value_objects.llm_error_kind import LlmErrorKind


@dataclass(frozen=True, slots=True)
class LlmOutputValidationSuccess:
    pass


@dataclass(frozen=True, slots=True)
class LlmOutputValidationFailure:
    error_kind: LlmErrorKind
    error_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.error_kind not in {
            LlmErrorKind.INVALID_OUTPUT,
            LlmErrorKind.VALIDATION_FAILED,
            LlmErrorKind.EMPTY_OUTPUT,
        }:
            raise ValueError(
                "Output validation failure must use an output-validation error kind"
            )

        for error_code in self.error_codes:
            if not error_code or not error_code.strip():
                raise ValueError("error_codes must contain only non-empty strings")


LlmOutputValidationResult = LlmOutputValidationSuccess | LlmOutputValidationFailure


class LlmOutputValidationPort(Protocol):
    def validate(self, *, task: LlmTask, raw_text: str) -> LlmOutputValidationResult:
        """Validate raw provider output against the task output contract."""
