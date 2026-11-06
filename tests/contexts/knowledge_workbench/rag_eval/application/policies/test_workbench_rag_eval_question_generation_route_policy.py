from __future__ import annotations

import pytest

from src.contexts.knowledge_workbench.rag_eval.application.policies.workbench_rag_eval_question_generation_route_policy import (
    WORKBENCH_RAG_EVAL_ACCOUNT_REFS,
    WorkbenchRagEvalQuestionGenerationRoutePolicy,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.workbench_rag_eval_dispatch_preparation import (
    WORKBENCH_RAG_EVAL_PRIMARY_MODEL_REF,
    workbench_rag_eval_route_catalog,
)
from src.contexts.llm_runtime.domain.capacity.llm_model_route_catalog import (
    LlmModelCapacityLimits,
    LlmModelExecutionSettings,
    LlmModelRoute,
    LlmModelRouteCatalog,
    LlmModelRouteRole,
)


def test_default_policy_uses_only_gpt_oss_120b() -> None:
    policy = WorkbenchRagEvalQuestionGenerationRoutePolicy.default()

    assert policy.primary_model_ref == "openai/gpt-oss-120b"
    assert policy.automatic_model_refs() == ("openai/gpt-oss-120b",)
    assert policy.route_catalog.automatic_fallback_model_refs() == ()
    assert all(
        route.role is not LlmModelRouteRole.DEGRADED_USER_CHOICE
        for route in policy.route_catalog.routes
    )


def test_candidate_chain_uses_primary_model_and_rotates_accounts() -> None:
    policy = WorkbenchRagEvalQuestionGenerationRoutePolicy.default()

    chain = policy.candidate_chain(entry_index=2)

    assert len(chain) == 1
    primary = chain[0]

    assert primary.model_ref == WORKBENCH_RAG_EVAL_PRIMARY_MODEL_REF
    assert primary.role is LlmModelRouteRole.PRIMARY
    assert primary.account_ref == WORKBENCH_RAG_EVAL_ACCOUNT_REFS[2]
    assert primary.slot_index == 2
    assert primary.execution_settings.reasoning_enabled is True
    assert primary.execution_settings.reasoning_effort == "low"


def test_candidate_chain_wraps_account_lane_index() -> None:
    policy = WorkbenchRagEvalQuestionGenerationRoutePolicy.default()

    candidate = policy.candidate_chain(entry_index=4)[0]

    assert candidate.account_ref == WORKBENCH_RAG_EVAL_ACCOUNT_REFS[0]
    assert candidate.slot_index == 0


def test_policy_rejects_any_automatic_fallback_route() -> None:
    reasoning_enabled = LlmModelExecutionSettings(
        reasoning_enabled=True,
        reasoning_effort="low",
    )
    catalog = LlmModelRouteCatalog(
        routes=(
            LlmModelRoute(
                model_ref=WORKBENCH_RAG_EVAL_PRIMARY_MODEL_REF,
                role=LlmModelRouteRole.PRIMARY,
                order=0,
                execution_settings=reasoning_enabled,
                capacity_limits=LlmModelCapacityLimits(
                    input_token_limit=6_000,
                    output_token_limit=8_192,
                ),
            ),
            LlmModelRoute(
                model_ref="openai/gpt-oss-20b",
                role=LlmModelRouteRole.AUTOMATIC_FALLBACK,
                order=1,
                execution_settings=reasoning_enabled,
                capacity_limits=LlmModelCapacityLimits(
                    input_token_limit=128_000,
                    output_token_limit=32_768,
                ),
            ),
        ),
        require_degraded_user_choice=False,
    )

    with pytest.raises(
        ValueError,
        match="must not configure automatic fallback routes",
    ):
        WorkbenchRagEvalQuestionGenerationRoutePolicy(
            route_catalog=catalog,
        )


def test_policy_rejects_any_degraded_user_choice_route() -> None:
    base = workbench_rag_eval_route_catalog()
    routes = tuple(base.routes) + (
        LlmModelRoute(
            model_ref="llama-3.1-8b-instant",
            role=LlmModelRouteRole.DEGRADED_USER_CHOICE,
            order=2,
            execution_settings=LlmModelExecutionSettings(
                reasoning_enabled=False,
            ),
            capacity_limits=LlmModelCapacityLimits(
                input_token_limit=131_072,
                output_token_limit=131_072,
            ),
        ),
    )
    catalog = LlmModelRouteCatalog(routes=routes)

    with pytest.raises(
        ValueError,
        match="must not expose a degraded user-choice route",
    ):
        WorkbenchRagEvalQuestionGenerationRoutePolicy(
            route_catalog=catalog,
        )


def test_route_policy_source_contains_no_legacy_degraded_flag() -> None:
    import inspect

    source = inspect.getsource(
        WorkbenchRagEvalQuestionGenerationRoutePolicy,
    )

    assert "allow_degraded_llama_instant" not in source
    assert "llama-3.1-8b-instant" not in source
