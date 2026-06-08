from __future__ import annotations

from types import MappingProxyType

import pytest

from src.contexts.llm_runtime.application.policies.llm_json_output_validation_policy import (
    EmptyJsonObjectPolicy,
    LlmJsonOutputContractSpec,
    LlmJsonOutputValidationPolicy,
)
from src.contexts.llm_runtime.application.ports.llm_output_validation_port import (
    LlmOutputValidationFailure,
    LlmOutputValidationSuccess,
)
from src.contexts.llm_runtime.domain.entities.llm_task import LlmTask
from src.contexts.llm_runtime.domain.value_objects.input_ref import LlmInputRef
from src.contexts.llm_runtime.domain.value_objects.llm_error_kind import LlmErrorKind
from src.contexts.llm_runtime.domain.value_objects.output_contract_ref import (
    OutputContractRef,
)
from src.contexts.llm_runtime.domain.value_objects.prompt_version import PromptVersion


def _contract_ref(value: str = "contract-1") -> OutputContractRef:
    return OutputContractRef(value)


def _task(contract_ref: OutputContractRef | None = None) -> LlmTask:
    return LlmTask(
        task_id="task-1",
        prompt_id="generic_prompt",
        prompt_version=PromptVersion("v1"),
        input_ref=LlmInputRef("input-1"),
        output_contract_ref=contract_ref or _contract_ref(),
    )


def _policy(
    spec: LlmJsonOutputContractSpec | None = None,
) -> LlmJsonOutputValidationPolicy:
    contract = spec or LlmJsonOutputContractSpec(
        contract_ref=_contract_ref(),
        required_top_level_keys=("result",),
    )
    return LlmJsonOutputValidationPolicy(
        contracts={
            contract.contract_ref: contract,
        },
    )


def test_valid_json_object_with_required_keys_succeeds() -> None:
    result = _policy().validate(
        task=_task(),
        raw_text='{"result": {"ok": true}}',
    )

    assert isinstance(result, LlmOutputValidationSuccess)


def test_invalid_json_returns_invalid_output_failure() -> None:
    result = _policy().validate(
        task=_task(),
        raw_text='{"result": ',
    )

    assert isinstance(result, LlmOutputValidationFailure)
    assert result.error_kind is LlmErrorKind.INVALID_OUTPUT
    assert result.error_codes == ("invalid_json",)


def test_top_level_array_returns_validation_failure() -> None:
    result = _policy().validate(
        task=_task(),
        raw_text='[{"result": true}]',
    )

    assert isinstance(result, LlmOutputValidationFailure)
    assert result.error_kind is LlmErrorKind.VALIDATION_FAILED
    assert result.error_codes == ("top_level_json_must_be_object",)


def test_unknown_contract_returns_validation_failure() -> None:
    result = _policy().validate(
        task=_task(contract_ref=OutputContractRef("missing-contract")),
        raw_text='{"result": true}',
    )

    assert isinstance(result, LlmOutputValidationFailure)
    assert result.error_kind is LlmErrorKind.VALIDATION_FAILED
    assert result.error_codes == ("unknown_output_contract",)


def test_missing_required_keys_return_validation_failure() -> None:
    result = _policy().validate(
        task=_task(),
        raw_text='{"other": true}',
    )

    assert isinstance(result, LlmOutputValidationFailure)
    assert result.error_kind is LlmErrorKind.VALIDATION_FAILED
    assert result.error_codes == ("missing_key:result",)


def test_empty_json_object_can_be_failure_or_success_by_contract_policy() -> None:
    fail_result = _policy(
        LlmJsonOutputContractSpec(
            contract_ref=_contract_ref(),
            empty_object_policy=EmptyJsonObjectPolicy.FAIL,
        ),
    ).validate(
        task=_task(),
        raw_text="{}",
    )

    assert isinstance(fail_result, LlmOutputValidationFailure)
    assert fail_result.error_kind is LlmErrorKind.EMPTY_OUTPUT
    assert fail_result.error_codes == ("empty_json_object",)

    success_result = _policy(
        LlmJsonOutputContractSpec(
            contract_ref=_contract_ref(),
            empty_object_policy=EmptyJsonObjectPolicy.ALLOW,
        ),
    ).validate(
        task=_task(),
        raw_text="{}",
    )

    assert isinstance(success_result, LlmOutputValidationSuccess)


def test_contract_spec_rejects_empty_required_keys() -> None:
    with pytest.raises(ValueError):
        LlmJsonOutputContractSpec(
            contract_ref=_contract_ref(),
            required_top_level_keys=("",),
        )


def test_policy_contracts_are_copied_and_read_only() -> None:
    contract = LlmJsonOutputContractSpec(contract_ref=_contract_ref())
    source = {contract.contract_ref: contract}

    policy = LlmJsonOutputValidationPolicy(contracts=source)
    source.clear()

    assert isinstance(policy.contracts, MappingProxyType)
    assert policy.contracts[contract.contract_ref] == contract
