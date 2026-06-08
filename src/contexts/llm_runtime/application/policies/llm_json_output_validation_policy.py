from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from json import JSONDecodeError
from types import MappingProxyType
from typing import Mapping

from src.contexts.llm_runtime.application.ports.llm_output_validation_port import (
    LlmOutputValidationFailure,
    LlmOutputValidationResult,
    LlmOutputValidationSuccess,
)
from src.contexts.llm_runtime.domain.entities.llm_task import LlmTask
from src.contexts.llm_runtime.domain.value_objects.llm_error_kind import LlmErrorKind
from src.contexts.llm_runtime.domain.value_objects.output_contract_ref import (
    OutputContractRef,
)


class EmptyJsonObjectPolicy(StrEnum):
    ALLOW = "allow"
    FAIL = "fail"


@dataclass(frozen=True, slots=True)
class LlmJsonOutputContractSpec:
    contract_ref: OutputContractRef
    required_top_level_keys: tuple[str, ...] = ()
    empty_object_policy: EmptyJsonObjectPolicy = EmptyJsonObjectPolicy.FAIL

    def __post_init__(self) -> None:
        for key in self.required_top_level_keys:
            if not key or not key.strip():
                raise ValueError(
                    "required_top_level_keys must contain only non-empty strings"
                )


@dataclass(frozen=True, slots=True)
class LlmJsonOutputValidationPolicy:
    """Generic JSON output validator.

    This policy validates only provider-neutral JSON structure. It does not know
    caller business meaning.
    """

    contracts: Mapping[OutputContractRef, LlmJsonOutputContractSpec]

    def __post_init__(self) -> None:
        object.__setattr__(self, "contracts", MappingProxyType(dict(self.contracts)))

    def validate(self, *, task: LlmTask, raw_text: str) -> LlmOutputValidationResult:
        contract = self.contracts.get(task.output_contract_ref)

        if contract is None:
            return LlmOutputValidationFailure(
                error_kind=LlmErrorKind.VALIDATION_FAILED,
                error_codes=("unknown_output_contract",),
            )

        try:
            parsed = json.loads(raw_text)
        except JSONDecodeError:
            return LlmOutputValidationFailure(
                error_kind=LlmErrorKind.INVALID_OUTPUT,
                error_codes=("invalid_json",),
            )

        if not isinstance(parsed, dict):
            return LlmOutputValidationFailure(
                error_kind=LlmErrorKind.VALIDATION_FAILED,
                error_codes=("top_level_json_must_be_object",),
            )

        if not parsed and contract.empty_object_policy is EmptyJsonObjectPolicy.FAIL:
            return LlmOutputValidationFailure(
                error_kind=LlmErrorKind.EMPTY_OUTPUT,
                error_codes=("empty_json_object",),
            )

        missing_keys = tuple(
            key for key in contract.required_top_level_keys if key not in parsed
        )

        if missing_keys:
            return LlmOutputValidationFailure(
                error_kind=LlmErrorKind.VALIDATION_FAILED,
                error_codes=tuple(f"missing_key:{key}" for key in missing_keys),
            )

        return LlmOutputValidationSuccess()
