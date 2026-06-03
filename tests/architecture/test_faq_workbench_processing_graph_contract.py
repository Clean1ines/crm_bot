from __future__ import annotations

from pathlib import Path

from src.application.workbench.processing_graph_contract import (
    FAQ_WORKBENCH_PROCESSING_GRAPH_CONTRACT,
)
from src.domain.project_plane.knowledge_workbench.nodes import (
    ProcessingNodeName,
)


def test_processing_graph_contract_is_provider_agnostic_not_groq_specific() -> None:
    source = Path("src/application/workbench/processing_graph_contract.py").read_text(
        encoding="utf-8"
    )

    forbidden = (
        "Groq",
        "AsyncGroq",
        "GROQ_API_KEY",
        "RotatingAsyncGroq",
        "GroqLlmJsonInvocationAdapter",
    )
    for marker in forbidden:
        assert marker not in source


def test_processing_graph_contract_does_not_restore_old_compiler_domain() -> None:
    source = Path("src/application/workbench/processing_graph_contract.py").read_text(
        encoding="utf-8"
    )

    forbidden = (
        "knowledge_surface_" + "economy_instant",
        "knowledge_surface_" + "parallel_graph_compiler",
        "KnowledgeSurfaceCompilerPort",
        "RetrievalSurfaceCandidate",
        "SurfaceDiscoveryResult",
        "LocalSurfaceRelation",
        "knowledge_compilation",
        "CanonicalKnowledgeEntry",
        "AnswerCandidate",
        "CandidateCluster",
    )
    for marker in forbidden:
        assert marker not in source


def test_processing_graph_contract_owns_all_prompt_files() -> None:
    assert FAQ_WORKBENCH_PROCESSING_GRAPH_CONTRACT.prompt_files() == (
        "faq_surface_claim_observations.ru.txt",
        "faq_surface_registry_merge.ru.txt",
        "faq_surface_final_reconciliation.ru.txt",
    )


def test_processing_node_name_enum_contains_real_graph_node_names() -> None:
    required = (
        "INITIALIZE_REGISTRY",
        "RESTORE_CHECKPOINT",
        "PROCESS_PARALLEL_SECTION_BATCH",
        "FAQ_SURFACE_SECTION_FINDINGS",
        "DETERMINISTIC_DEDUP",
        "FAQ_SURFACE_REGISTRY_MERGE",
        "REGISTRY_UPDATE_APPLICATION",
        "REGISTRY_SNAPSHOT",
        "FAQ_SURFACE_FINAL_RECONCILIATION",
        "SURFACE_MATERIALIZATION",
        "MODEL_ROUTE",
    )

    for name in required:
        assert hasattr(ProcessingNodeName, name)


def test_processing_graph_node_names_are_not_fake_metrics_only() -> None:
    source = Path("src/application/workbench/processing_graph_contract.py").read_text(
        encoding="utf-8"
    )

    assert "ProcessingNodeName.FAQ_SURFACE_SECTION_FINDINGS" in source
    assert "ProcessingNodeName.FAQ_SURFACE_REGISTRY_MERGE" in source
    assert "ProcessingNodeName.FAQ_SURFACE_FINAL_RECONCILIATION" in source
    assert "ProcessingNodeName.REGISTRY_UPDATE_APPLICATION" in source
    assert "ProcessingNodeName.SURFACE_MATERIALIZATION" in source
