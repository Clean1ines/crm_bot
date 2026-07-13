from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval_embedding_revision import (
    WORKBENCH_RUNTIME_EMBEDDING_DIMENSIONS,
)
from src.contexts.knowledge_workbench.rag_eval.application.use_cases.apply_workbench_rag_eval_promotion import (
    ApplyWorkbenchRagEvalPromotion,
)
from src.contexts.knowledge_workbench.rag_eval.application.use_cases.apply_workbench_rag_eval_promotions_batch import (
    ApplyWorkbenchRagEvalPromotionsBatch,
)
from src.interfaces.composition import workbench_rag_eval as composition


def test_single_and_batch_application_share_grouped_service(monkeypatch) -> None:
    settings = SimpleNamespace(
        local_model="model-1",
        vector_dimensions=WORKBENCH_RUNTIME_EMBEDDING_DIMENSIONS,
    )
    embedding_port = SimpleNamespace()

    monkeypatch.setattr(
        composition,
        "load_embedding_runtime_settings",
        lambda: settings,
    )
    monkeypatch.setattr(
        composition,
        "make_embedding_generation_port",
        lambda loaded: embedding_port if loaded is settings else None,
    )

    batch = composition.make_apply_workbench_rag_eval_promotions_batch(pool=object())
    single = composition.make_apply_workbench_rag_eval_promotion(pool=object())

    assert isinstance(batch, ApplyWorkbenchRagEvalPromotionsBatch)
    assert isinstance(single, ApplyWorkbenchRagEvalPromotion)
    assert isinstance(single.grouped_application, ApplyWorkbenchRagEvalPromotionsBatch)
    assert batch.embedding_dimensions == WORKBENCH_RUNTIME_EMBEDDING_DIMENSIONS
    assert (
        batch.application_policy.config.max_active_promoted_questions_per_runtime_entry
        == 12
    )
    assert (
        single.grouped_application.application_policy.config.max_active_promoted_questions_per_runtime_entry
        == 12
    )


def test_composition_rejects_non_384_embedding_settings(monkeypatch) -> None:
    settings = SimpleNamespace(
        local_model="model-1",
        vector_dimensions=3,
    )
    monkeypatch.setattr(
        composition,
        "load_embedding_runtime_settings",
        lambda: settings,
    )

    with pytest.raises(RuntimeError, match="must equal 384"):
        composition.make_apply_workbench_rag_eval_promotions_batch(pool=object())
