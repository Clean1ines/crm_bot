from __future__ import annotations

import pytest

from src.contexts.llm_runtime.application.ports.llm_output_validation_port import (
    LlmOutputValidationFailure,
    LlmOutputValidationSuccess,
)
from src.contexts.llm_runtime.domain.value_objects.llm_error_kind import LlmErrorKind


def test_validation_success_has_no_payload() -> None:
    assert isinstance(LlmOutputValidationSuccess(), LlmOutputValidationSuccess)


def test_validation_failure_accepts_only_output_validation_error_kinds() -> None:
    failure = LlmOutputValidationFailure(
        error_kind=LlmErrorKind.VALIDATION_FAILED,
        error_codes=("missing_field",),
    )

    assert failure.error_kind is LlmErrorKind.VALIDATION_FAILED
    assert failure.error_codes == ("missing_field",)

    with pytest.raises(ValueError):
        LlmOutputValidationFailure(error_kind=LlmErrorKind.NETWORK_ERROR)

    with pytest.raises(ValueError):
        LlmOutputValidationFailure(
            error_kind=LlmErrorKind.INVALID_OUTPUT,
            error_codes=("",),
        )
