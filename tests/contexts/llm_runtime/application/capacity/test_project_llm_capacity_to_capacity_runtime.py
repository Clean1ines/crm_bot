import pytest

from src.contexts.capacity_runtime.domain.capacity_decision import (
    CapacityRequest,
    CapacityResourceKind,
    CapacityWorkClass,
)
from src.contexts.capacity_runtime.domain.capacity_policy import CapacityAdmissionPolicy
from src.contexts.llm_runtime.application.capacity.project_llm_capacity_to_capacity_runtime import (
    LlmCapacityProjectionCommand,
    ProjectLlmCapacityToCapacityRuntime,
)
from src.contexts.llm_runtime.domain.capacity.llm_provider_account_capacity import (
    LlmProviderAccountCapacity,
)
from src.contexts.llm_runtime.domain.capacity.llm_task_capacity_profile import (
    LlmTaskCapacityProfile,
)


def _profile() -> LlmTaskCapacityProfile:
    return LlmTaskCapacityProfile(
        profile_id="prompt-a",
        input_tokens=3000,
        artifact_tokens=500,
    )


def _account(
    *,
    account_ref: str,
    minute_requests: int,
    minute_tokens: int,
    daily_requests: int,
    daily_tokens: int,
    model_ref: str = "qwen/qwen3-32b",
    provider: str = "groq",
) -> LlmProviderAccountCapacity:
    return LlmProviderAccountCapacity(
        provider=provider,
        account_ref=account_ref,
        model_ref=model_ref,
        remaining_minute_requests=minute_requests,
        remaining_minute_tokens=minute_tokens,
        remaining_daily_requests=daily_requests,
        remaining_daily_tokens=daily_tokens,
    )


def test_one_account_projects_external_io_availability() -> None:
    result = ProjectLlmCapacityToCapacityRuntime().execute(
        LlmCapacityProjectionCommand(
            profile=_profile(),
            accounts=(
                _account(
                    account_ref="org-1",
                    minute_requests=10,
                    minute_tokens=9000,
                    daily_requests=100,
                    daily_tokens=50000,
                ),
            ),
            requested_items=8,
        ),
    )

    assert result.max_projected_items == 2
    assert result.requested_items == 8
    assert result.capacity_needs[0].resource_kind is CapacityResourceKind.EXTERNAL_IO
    assert result.capacity_needs[0].amount == 1
    assert result.capacity_snapshot.available_for(CapacityResourceKind.EXTERNAL_IO) == 2


def test_four_accounts_sum_max_items_for() -> None:
    result = ProjectLlmCapacityToCapacityRuntime().execute(
        LlmCapacityProjectionCommand(
            profile=_profile(),
            accounts=(
                _account(
                    account_ref="org-1",
                    minute_requests=10,
                    minute_tokens=7000,
                    daily_requests=100,
                    daily_tokens=50000,
                ),
                _account(
                    account_ref="org-2",
                    minute_requests=10,
                    minute_tokens=7000,
                    daily_requests=100,
                    daily_tokens=50000,
                ),
                _account(
                    account_ref="org-3",
                    minute_requests=10,
                    minute_tokens=7000,
                    daily_requests=100,
                    daily_tokens=50000,
                ),
                _account(
                    account_ref="org-4",
                    minute_requests=10,
                    minute_tokens=7000,
                    daily_requests=100,
                    daily_tokens=50000,
                ),
            ),
            requested_items=10,
        ),
    )

    assert result.max_projected_items == 8
    assert result.capacity_snapshot.available_for(CapacityResourceKind.EXTERNAL_IO) == 8


def test_requested_items_caps_max_projected_items() -> None:
    result = ProjectLlmCapacityToCapacityRuntime().execute(
        LlmCapacityProjectionCommand(
            profile=_profile(),
            accounts=(
                _account(
                    account_ref="org-1",
                    minute_requests=10,
                    minute_tokens=35000,
                    daily_requests=100,
                    daily_tokens=50000,
                ),
            ),
            requested_items=3,
        ),
    )

    assert result.max_projected_items == 3


def test_exhausted_accounts_contribute_zero() -> None:
    result = ProjectLlmCapacityToCapacityRuntime().execute(
        LlmCapacityProjectionCommand(
            profile=_profile(),
            accounts=(
                _account(
                    account_ref="org-1",
                    minute_requests=10,
                    minute_tokens=7000,
                    daily_requests=100,
                    daily_tokens=50000,
                ),
                _account(
                    account_ref="org-2",
                    minute_requests=10,
                    minute_tokens=0,
                    daily_requests=100,
                    daily_tokens=50000,
                ),
            ),
            requested_items=10,
        ),
    )

    assert result.max_projected_items == 2


def test_projection_result_can_be_consumed_by_capacity_policy() -> None:
    result = ProjectLlmCapacityToCapacityRuntime().execute(
        LlmCapacityProjectionCommand(
            profile=_profile(),
            accounts=(
                _account(
                    account_ref="org-1",
                    minute_requests=10,
                    minute_tokens=9000,
                    daily_requests=100,
                    daily_tokens=50000,
                ),
            ),
            requested_items=8,
        ),
    )

    decision = CapacityAdmissionPolicy().decide(
        request=CapacityRequest(
            work_class=CapacityWorkClass.LLM_BOUND,
            needs=result.capacity_needs,
            requested_items=result.requested_items,
        ),
        snapshot=result.capacity_snapshot,
    )

    assert decision.max_admissible_items == 2


def test_rejects_empty_accounts() -> None:
    with pytest.raises(ValueError, match="accounts must be non-empty"):
        LlmCapacityProjectionCommand(
            profile=_profile(),
            accounts=(),
            requested_items=1,
        )


def test_projection_returns_allocation_per_projected_item() -> None:
    result = ProjectLlmCapacityToCapacityRuntime().execute(
        LlmCapacityProjectionCommand(
            profile=_profile(),
            accounts=(
                _account(
                    account_ref="org-1",
                    minute_requests=3,
                    minute_tokens=10500,
                    daily_requests=10,
                    daily_tokens=50000,
                ),
            ),
            requested_items=3,
        ),
    )

    assert result.max_projected_items == 3
    assert len(result.allocations) == 3
    assert tuple(slot.slot_index for slot in result.allocations) == (0, 1, 2)
    assert tuple(slot.provider for slot in result.allocations) == (
        "groq",
        "groq",
        "groq",
    )
    assert tuple(slot.account_ref for slot in result.allocations) == (
        "org-1",
        "org-1",
        "org-1",
    )
    assert tuple(slot.model_ref for slot in result.allocations) == (
        "qwen/qwen3-32b",
        "qwen/qwen3-32b",
        "qwen/qwen3-32b",
    )


def test_four_accounts_allocations_preserve_account_order() -> None:
    result = ProjectLlmCapacityToCapacityRuntime().execute(
        LlmCapacityProjectionCommand(
            profile=_profile(),
            accounts=(
                _account(
                    account_ref="account_1",
                    minute_requests=2,
                    minute_tokens=7000,
                    daily_requests=10,
                    daily_tokens=50000,
                ),
                _account(
                    account_ref="account_2",
                    minute_requests=1,
                    minute_tokens=3500,
                    daily_requests=10,
                    daily_tokens=50000,
                ),
                _account(
                    account_ref="account_3",
                    minute_requests=10,
                    minute_tokens=0,
                    daily_requests=10,
                    daily_tokens=50000,
                ),
                _account(
                    account_ref="account_4",
                    minute_requests=3,
                    minute_tokens=10500,
                    daily_requests=10,
                    daily_tokens=50000,
                ),
            ),
            requested_items=5,
        ),
    )

    assert result.max_projected_items == 5
    assert [slot.account_ref for slot in result.allocations] == [
        "account_1",
        "account_1",
        "account_2",
        "account_4",
        "account_4",
    ]
    assert tuple(slot.slot_index for slot in result.allocations) == (0, 1, 2, 3, 4)


def test_requested_items_caps_allocations() -> None:
    result = ProjectLlmCapacityToCapacityRuntime().execute(
        LlmCapacityProjectionCommand(
            profile=_profile(),
            accounts=(
                _account(
                    account_ref="org-1",
                    minute_requests=10,
                    minute_tokens=35000,
                    daily_requests=10,
                    daily_tokens=50000,
                ),
            ),
            requested_items=4,
        ),
    )

    assert result.max_projected_items == 4
    assert len(result.allocations) == 4


def test_fully_exhausted_accounts_produce_no_allocations() -> None:
    result = ProjectLlmCapacityToCapacityRuntime().execute(
        LlmCapacityProjectionCommand(
            profile=_profile(),
            accounts=(
                _account(
                    account_ref="org-1",
                    minute_requests=0,
                    minute_tokens=0,
                    daily_requests=0,
                    daily_tokens=0,
                ),
            ),
            requested_items=4,
        ),
    )

    assert result.max_projected_items == 0
    assert result.allocations == ()
    assert result.capacity_snapshot.available_for(CapacityResourceKind.EXTERNAL_IO) == 0


def test_allocation_payload_is_json_compatible() -> None:
    result = ProjectLlmCapacityToCapacityRuntime().execute(
        LlmCapacityProjectionCommand(
            profile=_profile(),
            accounts=(
                _account(
                    account_ref="org-1",
                    minute_requests=1,
                    minute_tokens=3500,
                    daily_requests=10,
                    daily_tokens=50000,
                ),
            ),
            requested_items=1,
        ),
    )

    assert result.allocations[0].to_payload() == {
        "provider": "groq",
        "account_ref": "org-1",
        "model_ref": "qwen/qwen3-32b",
        "slot_index": 0,
    }


def test_projection_rejects_mixed_model_ref_accounts() -> None:
    with pytest.raises(
        ValueError,
        match="capacity projection accounts must use one active model_ref",
    ):
        ProjectLlmCapacityToCapacityRuntime().execute(
            LlmCapacityProjectionCommand(
                profile=_profile(),
                accounts=(
                    _account(
                        account_ref="org-1",
                        minute_requests=10,
                        minute_tokens=7000,
                        daily_requests=100,
                        daily_tokens=50000,
                        model_ref="qwen/qwen3-32b",
                    ),
                    _account(
                        account_ref="org-2",
                        minute_requests=10,
                        minute_tokens=7000,
                        daily_requests=100,
                        daily_tokens=50000,
                        model_ref="openai/gpt-oss-120b",
                    ),
                ),
                requested_items=8,
            ),
        )


def test_projection_allows_same_model_ref_across_multiple_accounts() -> None:
    result = ProjectLlmCapacityToCapacityRuntime().execute(
        LlmCapacityProjectionCommand(
            profile=_profile(),
            accounts=(
                _account(
                    account_ref="org-1",
                    minute_requests=10,
                    minute_tokens=7000,
                    daily_requests=100,
                    daily_tokens=50000,
                    model_ref="qwen/qwen3-32b",
                ),
                _account(
                    account_ref="org-2",
                    minute_requests=10,
                    minute_tokens=7000,
                    daily_requests=100,
                    daily_tokens=50000,
                    model_ref="qwen/qwen3-32b",
                ),
            ),
            requested_items=8,
        ),
    )

    assert result.max_projected_items == 4
    assert tuple(slot.model_ref for slot in result.allocations) == (
        "qwen/qwen3-32b",
        "qwen/qwen3-32b",
        "qwen/qwen3-32b",
        "qwen/qwen3-32b",
    )


def test_projection_rejects_mixed_provider_accounts() -> None:
    with pytest.raises(
        ValueError,
        match="capacity projection accounts must use one provider",
    ):
        ProjectLlmCapacityToCapacityRuntime().execute(
            LlmCapacityProjectionCommand(
                profile=_profile(),
                accounts=(
                    _account(
                        account_ref="org-1",
                        minute_requests=10,
                        minute_tokens=7000,
                        daily_requests=100,
                        daily_tokens=50000,
                        provider="groq",
                    ),
                    _account(
                        account_ref="org-2",
                        minute_requests=10,
                        minute_tokens=7000,
                        daily_requests=100,
                        daily_tokens=50000,
                        provider="other",
                    ),
                ),
                requested_items=8,
            ),
        )
