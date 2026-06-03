from __future__ import annotations

from pathlib import Path

import pytest

from src.application.workbench.processing_graph_contract import (
    FAQ_SURFACE_SECTION_FINDINGS_NODE,
    FAQ_WORKBENCH_PROCESSING_GRAPH_CONTRACT,
    FAQ_WORKBENCH_PROCESSING_METHOD,
    FaqWorkbenchArtifactContract,
    FaqWorkbenchGraphExecutionMode,
    FaqWorkbenchProcessingGraphContract,
)
from src.domain.project_plane.knowledge_workbench.nodes import (
    ProcessingNodeKind,
    ProcessingNodeName,
)


def test_processing_graph_contract_declares_full_faq_workbench_pipeline() -> None:
    assert FAQ_WORKBENCH_PROCESSING_GRAPH_CONTRACT.processing_method == (
        FAQ_WORKBENCH_PROCESSING_METHOD
    )
    assert FAQ_WORKBENCH_PROCESSING_GRAPH_CONTRACT.node_order == (
        ProcessingNodeName.INITIALIZE_REGISTRY,
        ProcessingNodeName.RESTORE_CHECKPOINT,
        ProcessingNodeName.PROCESS_PARALLEL_SECTION_BATCH,
        ProcessingNodeName.FAQ_SURFACE_SECTION_FINDINGS,
        ProcessingNodeName.DETERMINISTIC_DEDUP,
        ProcessingNodeName.FAQ_SURFACE_REGISTRY_MERGE,
        ProcessingNodeName.REGISTRY_UPDATE_APPLICATION,
        ProcessingNodeName.REGISTRY_SNAPSHOT,
        ProcessingNodeName.FAQ_SURFACE_FINAL_RECONCILIATION,
        ProcessingNodeName.SURFACE_MATERIALIZATION,
    )


def test_processing_graph_has_exact_three_llm_prompt_nodes() -> None:
    llm_nodes = FAQ_WORKBENCH_PROCESSING_GRAPH_CONTRACT.llm_node_specs()

    assert tuple(spec.node_name for spec in llm_nodes) == (
        ProcessingNodeName.FAQ_SURFACE_SECTION_FINDINGS,
        ProcessingNodeName.FAQ_SURFACE_REGISTRY_MERGE,
        ProcessingNodeName.FAQ_SURFACE_FINAL_RECONCILIATION,
    )
    assert all(spec.node_kind is ProcessingNodeKind.LLM_PROMPT for spec in llm_nodes)


def test_processing_graph_prompt_nodes_own_prompt_files_and_markers() -> None:
    FAQ_WORKBENCH_PROCESSING_GRAPH_CONTRACT.validate_prompt_files(
        Path("src/agent/prompts")
    )

    assert FAQ_WORKBENCH_PROCESSING_GRAPH_CONTRACT.prompt_files() == (
        "faq_surface_claim_observations.ru.txt",
        "faq_surface_registry_merge.ru.txt",
        "faq_surface_final_reconciliation.ru.txt",
    )


def test_processing_graph_declares_parallel_claim_observations_with_three_keys() -> None:
    spec = FAQ_WORKBENCH_PROCESSING_GRAPH_CONTRACT.spec_for(
        ProcessingNodeName.FAQ_SURFACE_SECTION_FINDINGS
    )

    assert spec.execution_mode is FaqWorkbenchGraphExecutionMode.PER_SECTION_PARALLEL
    assert spec.max_concurrency_default == 3
    assert FAQ_WORKBENCH_PROCESSING_GRAPH_CONTRACT.default_llm_concurrency == 3


def test_processing_graph_registry_merge_is_advisory_and_not_mutating() -> None:
    spec = FAQ_WORKBENCH_PROCESSING_GRAPH_CONTRACT.spec_for(
        ProcessingNodeName.FAQ_SURFACE_REGISTRY_MERGE
    )

    assert (
        spec.execution_mode
        is FaqWorkbenchGraphExecutionMode.PER_SECTION_SEQUENTIAL_ADVISORY
    )
    assert spec.mutates_registry is False
    assert "registry_updates" in spec.output_contract


def test_processing_graph_only_registry_update_application_mutates_registry() -> None:
    mutators = tuple(
        spec.node_name
        for spec in FAQ_WORKBENCH_PROCESSING_GRAPH_CONTRACT.node_specs
        if spec.mutates_registry
    )

    assert mutators == (ProcessingNodeName.REGISTRY_UPDATE_APPLICATION,)


def test_processing_graph_persists_prompt_outputs_as_artifacts() -> None:
    for spec in FAQ_WORKBENCH_PROCESSING_GRAPH_CONTRACT.llm_node_specs():
        assert FaqWorkbenchArtifactContract.INPUT_SNAPSHOT in spec.artifact_contract
        assert FaqWorkbenchArtifactContract.MODEL_ROUTE in spec.artifact_contract
        assert FaqWorkbenchArtifactContract.RAW_LLM_OUTPUT in spec.artifact_contract
        assert FaqWorkbenchArtifactContract.PARSED_LLM_OUTPUT in spec.artifact_contract
        assert FaqWorkbenchArtifactContract.ERROR_REPORT in spec.artifact_contract


def test_processing_graph_final_reconciliation_is_barriered_before_materialization() -> (
    None
):
    edges = FAQ_WORKBENCH_PROCESSING_GRAPH_CONTRACT.edges
    barrier_edges = tuple(edge for edge in edges if edge.barrier_after_edge)

    assert len(barrier_edges) == 1
    assert barrier_edges[0].from_node is ProcessingNodeName.REGISTRY_SNAPSHOT
    assert (
        barrier_edges[0].to_node is ProcessingNodeName.FAQ_SURFACE_FINAL_RECONCILIATION
    )

    assert FAQ_WORKBENCH_PROCESSING_GRAPH_CONTRACT.node_order.index(
        ProcessingNodeName.FAQ_SURFACE_FINAL_RECONCILIATION
    ) < FAQ_WORKBENCH_PROCESSING_GRAPH_CONTRACT.node_order.index(
        ProcessingNodeName.SURFACE_MATERIALIZATION
    )


def test_processing_graph_llm_node_creates_provider_agnostic_invocation_request() -> (
    None
):
    request = FAQ_SURFACE_SECTION_FINDINGS_NODE.invocation_request(
        prompt="Return JSON.",
        idempotency_key="run:section",
    )

    assert request.operation_name == "faq_surface_claim_observations"
    assert request.route_purpose == "workbench_claim_observations"
    assert request.prompt == "Return JSON."
    assert request.idempotency_key == "run:section"


def test_processing_graph_rejects_wrong_registry_mutator() -> None:
    bad_specs = tuple(
        spec
        if spec.node_name is not ProcessingNodeName.DETERMINISTIC_DEDUP
        else type(spec)(
            node_name=spec.node_name,
            node_kind=spec.node_kind,
            role=spec.role,
            operation_name=spec.operation_name,
            execution_mode=spec.execution_mode,
            input_contract=spec.input_contract,
            output_contract=spec.output_contract,
            artifact_contract=spec.artifact_contract,
            mutates_registry=True,
        )
        for spec in FAQ_WORKBENCH_PROCESSING_GRAPH_CONTRACT.node_specs
    )

    with pytest.raises(ValueError, match="only registry_update_application"):
        FaqWorkbenchProcessingGraphContract(
            processing_method=FAQ_WORKBENCH_PROCESSING_GRAPH_CONTRACT.processing_method,
            graph_version=FAQ_WORKBENCH_PROCESSING_GRAPH_CONTRACT.graph_version,
            node_order=FAQ_WORKBENCH_PROCESSING_GRAPH_CONTRACT.node_order,
            node_specs=bad_specs,
            edges=FAQ_WORKBENCH_PROCESSING_GRAPH_CONTRACT.edges,
        )
