from __future__ import annotations

from pathlib import Path


GRAPH_CONTRACT = Path("src/application/workbench/processing_graph_contract.py")
NODE_DOMAIN = Path("src/domain/project_plane/knowledge_workbench/nodes.py")
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


def test_registry_snapshot_is_declared_as_separate_graph_node() -> None:
    graph = _read(GRAPH_CONTRACT)

    assert "FAQ_REGISTRY_SNAPSHOT_NODE" in graph
    assert "ProcessingNodeName.REGISTRY_SNAPSHOT" in graph
    assert "REGISTRY_SNAPSHOT" in graph
    assert '"registry_snapshot"' in graph
    assert "FaqWorkbenchGraphNodeRole.SNAPSHOT" in graph
    assert "FaqWorkbenchGraphExecutionMode.PER_SECTION_SEQUENTIAL" in graph
    assert "FaqWorkbenchArtifactContract.INPUT_SNAPSHOT" in graph
    assert "FaqWorkbenchArtifactContract.REGISTRY_SNAPSHOT" in graph

    registry_application_index = graph.index(
        "ProcessingNodeName.REGISTRY_UPDATE_APPLICATION"
    )
    registry_snapshot_index = graph.index("ProcessingNodeName.REGISTRY_SNAPSHOT")
    final_reconciliation_index = graph.index(
        "ProcessingNodeName.FAQ_SURFACE_FINAL_RECONCILIATION"
    )

    assert registry_application_index < registry_snapshot_index
    assert registry_snapshot_index < final_reconciliation_index


def test_registry_snapshot_artifact_type_exists_in_runtime_domain() -> None:
    node_domain = _read(NODE_DOMAIN)

    assert 'REGISTRY_SNAPSHOT = "registry_snapshot"' in node_domain


def test_registry_snapshot_has_dedicated_persisted_runtime_boundary() -> None:
    boundary_sources = _production_sources_containing(
        "ProcessingNodeName.REGISTRY_SNAPSHOT",
        "ProcessingNodeArtifactType.REGISTRY_SNAPSHOT",
        "create_processing_node_run",
        "create_processing_node_artifact",
    )

    assert boundary_sources, (
        "REGISTRY_SNAPSHOT is a graph node, but no production service/runtime "
        "persists a dedicated ProcessingNodeRun + REGISTRY_SNAPSHOT artifact "
        "for it yet."
    )

    combined = "\n".join(boundary_sources.values())

    assert "ProcessingNodeArtifactType.INPUT_SNAPSHOT" in combined
    assert "ProcessingNodeStatus.COMPLETED" in combined
    assert "create_registry_snapshot" in combined

    forbidden = (
        "LlmJsonInvocationRequest",
        "generate_registry_merge",
        "generate_claim_observations",
        "generate_final_reconciliation",
        "RegistryUpdateAppliedBy.LLM_ADVISORY",
        "upsert_question_registry_entries",
    )
    for marker in forbidden:
        assert marker not in combined


def test_registry_snapshot_boundary_is_not_satisfied_by_graph_contract_only() -> None:
    graph = _read(GRAPH_CONTRACT)
    boundary_sources = _production_sources_containing(
        "ProcessingNodeName.REGISTRY_SNAPSHOT",
        "create_processing_node_run",
    )

    assert "ProcessingNodeName.REGISTRY_SNAPSHOT" in graph
    assert set(boundary_sources) != {GRAPH_CONTRACT}
