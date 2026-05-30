from __future__ import annotations

import pytest

from src.domain.project_plane.production_retrieval import (
    ProductionRetrievalCaller,
    ProductionRetrievalMode,
    resolve_production_retrieval_policy,
)


@pytest.mark.parametrize(
    ("caller", "expected_mode"),
    (
        (
            ProductionRetrievalCaller.ASSISTANT_RUNTIME,
            ProductionRetrievalMode.RUNTIME,
        ),
        (
            ProductionRetrievalCaller.KNOWLEDGE_PREVIEW,
            ProductionRetrievalMode.RUNTIME_EQUIVALENT_PREVIEW,
        ),
        (
            ProductionRetrievalCaller.RAG_EVAL,
            ProductionRetrievalMode.RUNTIME_EQUIVALENT_PREVIEW,
        ),
    ),
)
def test_runtime_equivalent_callers_use_retrieval_surface(
    caller: ProductionRetrievalCaller,
    expected_mode: ProductionRetrievalMode,
) -> None:
    policy = resolve_production_retrieval_policy(caller)

    assert policy.mode == expected_mode
    assert policy.runtime_equivalent is True
    assert policy.production_safe is True
    assert policy.diagnostic is False
    assert policy.source_name == "knowledge_retrieval_surface"
    assert policy.requires_retrieval_surface is True


def test_lexical_debug_is_diagnostic_not_runtime_equivalent() -> None:
    policy = resolve_production_retrieval_policy(
        ProductionRetrievalCaller.CURATION_DEBUG,
    )

    assert policy.mode == ProductionRetrievalMode.LEXICAL_DEBUG
    assert policy.runtime_equivalent is False
    assert policy.production_safe is False
    assert policy.diagnostic is True
    assert policy.source_name == "diagnostic_lexical_debug"
    assert policy.requires_retrieval_surface is False
