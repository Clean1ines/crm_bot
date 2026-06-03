from __future__ import annotations

from pathlib import Path


GRAPH_CONTRACT = Path("src/application/workbench/processing_graph_contract.py")
SRC_ROOTS = (
    Path("src/application"),
    Path("src/infrastructure"),
)


def _read(path: Path) -> str:
    assert path.exists(), f"missing expected file: {path}"
    return path.read_text(encoding="utf-8")


def _production_sources_containing(*markers: str) -> dict[Path, str]:
    found: dict[Path, str] = {}

    for root in SRC_ROOTS:
        for path in root.rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            if all(marker in source for marker in markers):
                found[path] = source

    return found


def test_deterministic_dedup_is_declared_as_separate_graph_node() -> None:
    graph = _read(GRAPH_CONTRACT)

    assert "FAQ_DETERMINISTIC_DEDUP_NODE" in graph
    assert "ProcessingNodeName.DETERMINISTIC_DEDUP" in graph
    assert 'operation_name="deterministic_dedup"' in graph
    assert "FaqWorkbenchGraphNodeRole.DEDUPLICATION" in graph
    assert "FaqWorkbenchGraphExecutionMode.PER_SECTION_SEQUENTIAL" in graph
    assert "FaqWorkbenchArtifactContract.INPUT_SNAPSHOT" in graph
    assert "FaqWorkbenchArtifactContract.DETERMINISTIC_RESULT" in graph

    claim_observations_index = graph.index(
        "ProcessingNodeName.FAQ_SURFACE_SECTION_FINDINGS"
    )
    dedup_index = graph.index("ProcessingNodeName.DETERMINISTIC_DEDUP")
    registry_merge_index = graph.index("ProcessingNodeName.FAQ_SURFACE_REGISTRY_MERGE")

    assert claim_observations_index < dedup_index < registry_merge_index


def test_deterministic_dedup_has_dedicated_persisted_runtime_boundary() -> None:
    boundary_sources = _production_sources_containing(
        "ProcessingNodeName.DETERMINISTIC_DEDUP",
        "ProcessingNodeArtifactType.DETERMINISTIC_RESULT",
        "create_processing_node_run",
        "create_processing_node_artifact",
    )

    assert boundary_sources, (
        "DETERMINISTIC_DEDUP is a graph node, but no production service/runtime "
        "persists a dedicated ProcessingNodeRun + DETERMINISTIC_RESULT artifact "
        "for it yet."
    )

    combined = "\n".join(boundary_sources.values())

    assert "ProcessingNodeArtifactType.INPUT_SNAPSHOT" in combined
    assert "ProcessingNodeStatus.COMPLETED" in combined

    forbidden = (
        "LlmJsonInvocationRequest",
        "generate_registry_merge",
        "generate_claim_observations",
        "generate_final_reconciliation",
        "RegistryUpdateAppliedBy.LLM_ADVISORY",
        "apply_findings_to_registry",
        "create_registry_snapshot",
        "upsert_question_registry_entries",
    )
    for marker in forbidden:
        assert marker not in combined


def test_deterministic_dedup_boundary_is_not_satisfied_by_graph_contract_only() -> None:
    graph = _read(GRAPH_CONTRACT)
    boundary_sources = _production_sources_containing(
        "ProcessingNodeName.DETERMINISTIC_DEDUP",
        "create_processing_node_run",
    )

    assert "ProcessingNodeName.DETERMINISTIC_DEDUP" in graph
    assert set(boundary_sources) != {GRAPH_CONTRACT}
