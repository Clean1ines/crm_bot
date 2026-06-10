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
        estimated_prompt_tokens=3000,
        estimated_completion_tokens=500,
    )


def _account(
    *,
    account_ref: str,
    minute_requests: int,
    minute_tokens: int,
    daily_requests: int,
    daily_tokens: int,
) -> LlmProviderAccountCapacity:
    return LlmProviderAccountCapacity(
        provider="groq",
        account_ref=account_ref,
        model_ref="qwen",
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
