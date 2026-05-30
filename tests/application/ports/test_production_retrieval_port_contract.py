from __future__ import annotations

from src.application.ports.knowledge import (
    ProductionRetrievalPort,
    ProductionRetrievalRequest,
    ProductionRetrievalResult,
    ProductionRetrievalResultItem,
)
from src.domain.project_plane.production_retrieval import (
    ProductionRetrievalCaller,
    ProductionRetrievalMode,
)


def test_production_retrieval_port_exports_contract_types() -> None:
    request = ProductionRetrievalRequest(
        project_id="project-1",
        query="как оформить заказ?",
        caller=ProductionRetrievalCaller.KNOWLEDGE_PREVIEW,
    )
    item = ProductionRetrievalResultItem(
        id="entry-1",
        document_id="doc-1",
        surface_id="surface-1",
        title="Заказ",
        answer="Ответ",
        short_answer="Коротко",
        score=0.9,
        source_refs=("chunk:1",),
    )
    result = ProductionRetrievalResult(
        request=request,
        items=(item,),
        policy=request.policy,
    )

    assert ProductionRetrievalPort is not None
    assert result.policy.mode == ProductionRetrievalMode.RUNTIME_EQUIVALENT_PREVIEW
    assert result.policy.source_name == "knowledge_retrieval_surface"
    assert result.items[0].surface_id == "surface-1"


def test_explicit_mode_override_is_diagnostic_only() -> None:
    request = ProductionRetrievalRequest(
        project_id="project-1",
        query="debug",
        caller=ProductionRetrievalCaller.KNOWLEDGE_PREVIEW,
        mode=ProductionRetrievalMode.LEXICAL_DEBUG,
    )

    assert request.policy.diagnostic is True
    assert request.policy.runtime_equivalent is False
    assert request.policy.production_safe is False
