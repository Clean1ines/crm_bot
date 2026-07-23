from __future__ import annotations

import pytest

from src.contexts.execution_runtime.domain.value_objects.work_kind import WorkKind
from src.contexts.knowledge_workbench.application.sagas.claim_builder_dispatch_preparation import (
    ClaimBuilderDispatchPreparationBuilder,
)
from src.contexts.knowledge_workbench.application.sagas.plan_claim_builder_section_work import (
    CLAIM_BUILDER_SECTION_WORK_KIND,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.workbench_rag_eval_dispatch_preparation import (
    WORKBENCH_RAG_EVAL_AUTOMATIC_FALLBACK_MODEL_REF,
    WORKBENCH_RAG_EVAL_PRIMARY_MODEL_REF,
    make_adjudication_dispatch_preparation_builder,
    make_question_generation_dispatch_preparation_builder,
    workbench_rag_eval_route_catalog,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.workbench_rag_eval_work_kinds import (
    WORKBENCH_RAG_EVAL_ADJUDICATION_WORK_KIND,
    WORKBENCH_RAG_EVAL_QUESTION_GENERATION_WORK_KIND,
)
from src.interfaces.composition.prepare_llm_dispatch_batch import (
    DispatchPreparationBuilderConfigurationError,
    DispatchPreparationBuilderRegistry,
)


def test_registry_keeps_claim_builder_explicitly_supported() -> None:
    registry = DispatchPreparationBuilderRegistry()

    builder = registry.builder_for(CLAIM_BUILDER_SECTION_WORK_KIND)

    assert isinstance(builder, ClaimBuilderDispatchPreparationBuilder)


def test_registry_fails_fast_for_unregistered_rag_eval_work_kind() -> None:
    registry = DispatchPreparationBuilderRegistry()

    with pytest.raises(
        DispatchPreparationBuilderConfigurationError,
        match="workbench_rag_eval.question_generation",
    ):
        registry.builder_for(WORKBENCH_RAG_EVAL_QUESTION_GENERATION_WORK_KIND)


def test_registry_fails_fast_for_any_unknown_llm_work_kind() -> None:
    registry = DispatchPreparationBuilderRegistry()

    with pytest.raises(
        DispatchPreparationBuilderConfigurationError,
        match="unknown.llm.operation",
    ):
        registry.builder_for(WorkKind("unknown.llm.operation"))


def test_registry_resolves_explicit_rag_eval_builders() -> None:
    qgen_builder = make_question_generation_dispatch_preparation_builder()
    adjudication_builder = make_adjudication_dispatch_preparation_builder()
    registry = DispatchPreparationBuilderRegistry(
        builders_by_work_kind={
            WORKBENCH_RAG_EVAL_QUESTION_GENERATION_WORK_KIND: qgen_builder,
            WORKBENCH_RAG_EVAL_ADJUDICATION_WORK_KIND: adjudication_builder,
        },
    )

    assert (
        registry.builder_for(WORKBENCH_RAG_EVAL_QUESTION_GENERATION_WORK_KIND)
        is qgen_builder
    )
    assert (
        registry.builder_for(WORKBENCH_RAG_EVAL_ADJUDICATION_WORK_KIND)
        is adjudication_builder
    )


def test_rag_eval_route_catalog_has_only_required_routes() -> None:
    catalog = workbench_rag_eval_route_catalog()

    assert catalog.primary_model_ref() == WORKBENCH_RAG_EVAL_PRIMARY_MODEL_REF
    assert catalog.automatic_fallback_model_refs() == (
        WORKBENCH_RAG_EVAL_AUTOMATIC_FALLBACK_MODEL_REF,
    )
    assert tuple(route.model_ref for route in catalog.routes) == (
        "qwen/qwen3.6-27b",
        "openai/gpt-oss-120b",
    )
    with pytest.raises(ValueError, match="no DEGRADED_USER_CHOICE"):
        catalog.degraded_user_choice_model_ref()
