from src.contexts.capacity_runtime.domain.capacity_decision import CapacityResourceKind
from src.contexts.llm_runtime.application.capacity.project_llm_capacity_to_capacity_runtime import (
    ProjectLlmCapacityToCapacityRuntime,
)
from src.contexts.llm_runtime.application.capacity.select_active_llm_model_capacity import (
    SelectActiveLlmModelCapacity,
    SelectActiveLlmModelCapacityCommand,
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
    model_ref: str,
    minute_tokens: int,
    minute_requests: int = 100,
    daily_requests: int = 100,
    daily_tokens: int = 50000,
) -> LlmProviderAccountCapacity:
    return LlmProviderAccountCapacity(
        provider="groq",
        account_ref=account_ref,
        model_ref=model_ref,
        remaining_minute_requests=minute_requests,
        remaining_minute_tokens=minute_tokens,
        remaining_daily_requests=daily_requests,
        remaining_daily_tokens=daily_tokens,
    )


def _selector() -> SelectActiveLlmModelCapacity:
    return SelectActiveLlmModelCapacity(projector=ProjectLlmCapacityToCapacityRuntime())


def test_active_qwen_selection_ignores_fallback_capacities() -> None:
    result = _selector().execute(
        SelectActiveLlmModelCapacityCommand(
            profile=_profile(),
            account_capacities=(
                _account(
                    account_ref="qwen-1",
                    model_ref="qwen/qwen3-32b",
                    minute_tokens=7000,
                ),
                _account(
                    account_ref="qwen-2",
                    model_ref="qwen/qwen3-32b",
                    minute_tokens=10500,
                ),
                _account(
                    account_ref="fallback-1",
                    model_ref="openai/gpt-oss-120b",
                    minute_tokens=35000,
                ),
                _account(
                    account_ref="fallback-2",
                    model_ref="llama-3.3-70b-versatile",
                    minute_tokens=35000,
                ),
            ),
            active_model_ref="qwen/qwen3-32b",
            requested_items=10,
        ),
    )

    assert tuple(account.account_ref for account in result.selected_accounts) == (
        "qwen-1",
        "qwen-2",
    )
    assert result.projection.max_projected_items == 5
    assert {slot.model_ref for slot in result.projection.allocations} == {
        "qwen/qwen3-32b",
    }


def test_active_fallback_selection_ignores_qwen_capacity() -> None:
    result = _selector().execute(
        SelectActiveLlmModelCapacityCommand(
            profile=_profile(),
            account_capacities=(
                _account(
                    account_ref="qwen-1",
                    model_ref="qwen/qwen3-32b",
                    minute_tokens=35000,
                ),
                _account(
                    account_ref="openai-1",
                    model_ref="openai/gpt-oss-120b",
                    minute_tokens=7000,
                ),
            ),
            active_model_ref="openai/gpt-oss-120b",
            requested_items=10,
        ),
    )

    assert tuple(account.account_ref for account in result.selected_accounts) == (
        "openai-1",
    )
    assert result.projection.max_projected_items == 2
    assert tuple(slot.account_ref for slot in result.projection.allocations) == (
        "openai-1",
        "openai-1",
    )


def test_no_accounts_for_active_model_returns_zero_capacity_projection() -> None:
    result = _selector().execute(
        SelectActiveLlmModelCapacityCommand(
            profile=_profile(),
            account_capacities=(
                _account(
                    account_ref="qwen-1",
                    model_ref="qwen/qwen3-32b",
                    minute_tokens=35000,
                ),
            ),
            active_model_ref="openai/gpt-oss-120b",
            requested_items=10,
        ),
    )

    assert result.selected_accounts == ()
    assert result.projection.max_projected_items == 0
    assert result.projection.allocations == ()
    assert (
        result.projection.capacity_snapshot.available_for(
            CapacityResourceKind.EXTERNAL_IO,
        )
        == 0
    )
