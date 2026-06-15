from __future__ import annotations

from src.contexts.knowledge_workbench.rag_eval.application.policies.workbench_rag_eval_question_generation_route_policy import (
    WORKBENCH_RAG_EVAL_DEGRADED_MODEL_REF,
    WORKBENCH_RAG_EVAL_PRIMARY_MODEL_REF,
    WorkbenchRagEvalQuestionGenerationRoutePolicy,
)


def test_policy_uses_qwen_primary_and_excludes_openai_named_automatic_fallback() -> (
    None
):
    policy = WorkbenchRagEvalQuestionGenerationRoutePolicy.default()

    assert policy.primary_model_ref == WORKBENCH_RAG_EVAL_PRIMARY_MODEL_REF
    assert policy.primary_model_ref == "qwen/qwen3-32b"
    assert policy.automatic_model_refs()[0] == "qwen/qwen3-32b"
    assert "openai/gpt-oss-120b" not in policy.automatic_model_refs()


def test_policy_does_not_include_llama_instant_without_manual_flag() -> None:
    policy = WorkbenchRagEvalQuestionGenerationRoutePolicy.default()

    automatic_chain = policy.candidate_chain(
        entry_index=0,
        allow_degraded_llama_instant=False,
    )
    degraded_chain = policy.candidate_chain(
        entry_index=0,
        allow_degraded_llama_instant=True,
    )

    assert WORKBENCH_RAG_EVAL_DEGRADED_MODEL_REF == "llama-3.1-8b-instant"
    assert all(
        candidate.model_ref != WORKBENCH_RAG_EVAL_DEGRADED_MODEL_REF
        for candidate in automatic_chain
    )
    assert degraded_chain[-1].model_ref == WORKBENCH_RAG_EVAL_DEGRADED_MODEL_REF
    assert degraded_chain[-1].degraded is True


def test_policy_rotates_accounts_by_entry_index() -> None:
    policy = WorkbenchRagEvalQuestionGenerationRoutePolicy.default()

    first = policy.candidate_chain(
        entry_index=0,
        allow_degraded_llama_instant=False,
    )[0]
    second = policy.candidate_chain(
        entry_index=1,
        allow_degraded_llama_instant=False,
    )[0]

    assert first.account_ref == "groq_org_primary"
    assert first.slot_index == 0
    assert second.account_ref == "groq_org_secondary"
    assert second.slot_index == 1
    assert policy.max_parallel_lanes == 4
