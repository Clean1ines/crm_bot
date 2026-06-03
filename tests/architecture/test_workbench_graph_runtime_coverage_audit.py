from __future__ import annotations

import ast
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class RuntimeCoverageStatus(StrEnum):
    IMPLEMENTED_CONNECTED = "implemented_connected"
    PARTIAL_EMBEDDED = "partial_embedded"
    CONTRACT_ONLY = "contract_only"


@dataclass(frozen=True, slots=True)
class RuntimeNodeCoverage:
    node_name: str
    status: RuntimeCoverageStatus
    evidence: tuple[tuple[Path, tuple[str, ...]], ...]
    missing_runtime_boundary: str | None = None

    def assert_current(self) -> None:
        for path, markers in self.evidence:
            assert path.exists(), f"{self.node_name}: missing evidence file {path}"
            source = path.read_text(encoding="utf-8")
            for marker in markers:
                assert marker in source, (
                    f"{self.node_name}: marker {marker!r} missing from {path}"
                )

        if self.status is RuntimeCoverageStatus.IMPLEMENTED_CONNECTED:
            assert self.missing_runtime_boundary is None, self.node_name
        else:
            assert self.missing_runtime_boundary, self.node_name


ROOT = Path(".")
GRAPH_CONTRACT = Path("src/application/workbench/processing_graph_contract.py")
ORCH = Path(
    "src/application/services/faq_workbench_document_processing_orchestrator.py"
)
FRESH_UPLOAD_SERVICE = Path(
    "src/application/services/faq_workbench_fresh_upload_service.py"
)
RESTORE_CHECKPOINT_SERVICE = Path(
    "src/application/services/faq_workbench_restore_checkpoint_service.py"
)
SECTION_BATCH_PLANNING_SERVICE = Path(
    "src/application/services/faq_workbench_section_batch_planning_service.py"
)
SECTION_FINDINGS_GENERATOR = Path(
    "src/infrastructure/llm/faq_workbench_claim_observations_generator.py"
)
SECTION_FINDINGS_SERVICE = Path(
    "src/application/services/faq_workbench_claim_observations_service.py"
)
REGISTRY_MERGE_GENERATOR = Path(
    "src/infrastructure/llm/faq_workbench_registry_merge_generator.py"
)
REGISTRY_MERGE_SERVICE = Path(
    "src/application/services/faq_workbench_registry_merge_service.py"
)
FINAL_RECONCILIATION_GENERATOR = Path(
    "src/infrastructure/llm/faq_workbench_final_reconciliation_generator.py"
)
FINAL_RECONCILIATION_SERVICE = Path(
    "src/application/services/faq_workbench_final_reconciliation_service.py"
)
REGISTRY_APPLICATION_SERVICE = Path(
    "src/application/services/faq_workbench_registry_application_service.py"
)
SURFACE_MATERIALIZATION_SERVICE = Path(
    "src/application/services/faq_workbench_surface_materialization_service.py"
)
QUEUE_HANDLER = Path("src/infrastructure/queue/handlers/workbench_document.py")
ADVISORY_GUARD = Path(
    "tests/architecture/test_workbench_registry_merge_advisory_truth_guard.py"
)
NODE_CONTRACT_GUARD = Path(
    "tests/architecture/test_workbench_registry_merge_node_contract.py"
)

SECTION_BATCH_CHECKPOINT_GUARD = Path(
    "tests/architecture/test_workbench_section_batch_checkpoint_boundary.py"
)


def _function_source(path: Path, function_name: str) -> str:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    lines = source.splitlines(keepends=True)

    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == function_name
        ):
            if node.end_lineno is None:
                raise AssertionError(f"{function_name} has no end_lineno")
            return "".join(lines[node.lineno - 1 : node.end_lineno])

    raise AssertionError(f"{function_name} not found in {path}")


def _graph_contract_source() -> str:
    assert GRAPH_CONTRACT.exists(), (
        f"FAQ_WORKBENCH_PROCESSING_GRAPH_CONTRACT source not found: {GRAPH_CONTRACT}"
    )
    source = GRAPH_CONTRACT.read_text(encoding="utf-8")
    assert "FAQ_WORKBENCH_PROCESSING_GRAPH_CONTRACT" in source
    return source


EXPECTED_GRAPH_NODE_NAMES = (
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
)


RUNTIME_COVERAGE = (
    RuntimeNodeCoverage(
        node_name="INITIALIZE_REGISTRY",
        status=RuntimeCoverageStatus.PARTIAL_EMBEDDED,
        evidence=(
            (
                FRESH_UPLOAD_SERVICE,
                (
                    "class FaqWorkbenchFreshUploadService",
                    "start_fresh_upload",
                    "create_question_registry",
                    "create_registry_snapshot",
                ),
            ),
            (ORCH, ("_fresh_upload_service.start_fresh_upload",)),
        ),
        missing_runtime_boundary=(
            "Fresh upload initializes document/registry/snapshot, but it is not yet "
            "persisted as a dedicated ProcessingNodeRun INITIALIZE_REGISTRY with "
            "input/applied artifacts."
        ),
    ),
    RuntimeNodeCoverage(
        node_name="RESTORE_CHECKPOINT",
        status=RuntimeCoverageStatus.IMPLEMENTED_CONNECTED,
        evidence=(
            (
                RESTORE_CHECKPOINT_SERVICE,
                (
                    "class FaqWorkbenchRestoreCheckpointService",
                    "restore_checkpoint",
                    "ProcessingNodeName.RESTORE_CHECKPOINT",
                    "ProcessingNodeArtifactType.INPUT_SNAPSHOT",
                    "ProcessingNodeArtifactType.APPLIED_RESULT",
                ),
            ),
            (
                ORCH,
                (
                    "_restore_checkpoint_service.restore_checkpoint",
                    "RestoreWorkbenchCheckpointCommand",
                    "restore_checkpoint.pending_sections",
                ),
            ),
        ),
    ),
    RuntimeNodeCoverage(
        node_name="PROCESS_PARALLEL_SECTION_BATCH",
        status=RuntimeCoverageStatus.PARTIAL_EMBEDDED,
        evidence=(
            (
                SECTION_BATCH_PLANNING_SERVICE,
                (
                    "class FaqWorkbenchSectionBatchPlanningService",
                    "process_parallel_section_batch",
                    "ProcessingNodeName.PROCESS_PARALLEL_SECTION_BATCH",
                    "create_section_batch_plan",
                    "create_section_work_items",
                    "restore_stale_section_work_item_leases",
                ),
            ),
            (
                ORCH,
                (
                    "_process_parallel_section_batch_checkpoint",
                    "_section_batch_planning_service.process_parallel_section_batch",
                    "ProcessParallelSectionBatchCommand",
                    "for section in sections:",
                ),
            ),
        ),
        missing_runtime_boundary=(
            "Section batch plan/work-item checkpoint is wired before the current "
            "section loop. No real parallel worker leasing, fan-out/fan-in, or "
            "single-writer registry application queue execution is not yet connected."
        ),
    ),
    RuntimeNodeCoverage(
        node_name="FAQ_SURFACE_SECTION_FINDINGS",
        status=RuntimeCoverageStatus.IMPLEMENTED_CONNECTED,
        evidence=(
            (
                SECTION_FINDINGS_GENERATOR,
                (
                    "class FaqWorkbenchClaimObservationsGenerator",
                    "workbench_claim_observations",
                    "faq_surface_claim_observations",
                ),
            ),
            (
                SECTION_FINDINGS_SERVICE,
                (
                    "class FaqWorkbenchClaimObservationsService",
                    "persist_claim_observations",
                    "persist_claim_observations_generation_error",
                    "ProcessingNodeName.FAQ_SURFACE_SECTION_FINDINGS",
                ),
            ),
            (
                QUEUE_HANDLER,
                (
                    "make_workbench_claim_observations_generator",
                    "claim_observations_generator=make_workbench_claim_observations_generator()",
                ),
            ),
        ),
    ),
    RuntimeNodeCoverage(
        node_name="DETERMINISTIC_DEDUP",
        status=RuntimeCoverageStatus.PARTIAL_EMBEDDED,
        evidence=(
            (
                ORCH,
                (
                    "resolve_section_finding_target",
                    "resolved_findings",
                ),
            ),
            (
                REGISTRY_APPLICATION_SERVICE,
                (
                    "apply_findings_to_registry",
                    "RegistryUpdateAppliedBy.DETERMINISTIC_CODE",
                ),
            ),
        ),
        missing_runtime_boundary=(
            "Dedup/target resolution exists as embedded deterministic code, but there "
            "is no dedicated DETERMINISTIC_DEDUP node run/artifact output yet."
        ),
    ),
    RuntimeNodeCoverage(
        node_name="FAQ_SURFACE_REGISTRY_MERGE",
        status=RuntimeCoverageStatus.IMPLEMENTED_CONNECTED,
        evidence=(
            (
                REGISTRY_MERGE_GENERATOR,
                (
                    "class FaqWorkbenchRegistryMergeGenerator",
                    "workbench_registry_merge",
                    "faq_surface_registry_merge",
                    "parse_registry_updates_payload",
                ),
            ),
            (
                REGISTRY_MERGE_SERVICE,
                (
                    "class FaqWorkbenchRegistryMergeService",
                    "persist_registry_merge_output",
                    "persist_registry_merge_generation_error",
                    "ProcessingNodeName.FAQ_SURFACE_REGISTRY_MERGE",
                    "create_registry_update_proposals",
                ),
            ),
            (
                ORCH,
                (
                    "_persist_registry_merge_advice_for_section",
                    "generate_registry_updates",
                    "persist_registry_merge_output",
                ),
            ),
            (
                QUEUE_HANDLER,
                (
                    "make_workbench_registry_merge_generator",
                    "registry_merge_generator=make_workbench_registry_merge_generator()",
                ),
            ),
        ),
    ),
    RuntimeNodeCoverage(
        node_name="REGISTRY_UPDATE_APPLICATION",
        status=RuntimeCoverageStatus.PARTIAL_EMBEDDED,
        evidence=(
            (
                REGISTRY_APPLICATION_SERVICE,
                (
                    "class FaqWorkbenchRegistryApplicationService",
                    "apply_findings_to_registry",
                    "RegistryUpdateAppliedBy.DETERMINISTIC_CODE",
                    "upsert_question_registry_entries",
                    "create_registry_update_applications",
                ),
            ),
            (
                ORCH,
                (
                    "_registry_application_service.apply_findings_to_registry",
                    "ApplyRegistryFindingsCommand",
                ),
            ),
        ),
        missing_runtime_boundary=(
            "Deterministic registry mutation is implemented and connected, but it is "
            "not yet persisted as a dedicated ProcessingNodeRun "
            "REGISTRY_UPDATE_APPLICATION with input/applied artifacts."
        ),
    ),
    RuntimeNodeCoverage(
        node_name="REGISTRY_SNAPSHOT",
        status=RuntimeCoverageStatus.PARTIAL_EMBEDDED,
        evidence=(
            (
                REGISTRY_APPLICATION_SERVICE,
                (
                    "create_registry_snapshot",
                    "previous_snapshot_id",
                    "previous_snapshot_sequence_number",
                ),
            ),
            (ORCH, ("latest_snapshot = registry_application_result.snapshot",)),
        ),
        missing_runtime_boundary=(
            "Registry snapshots are created in the deterministic application flow, "
            "but no separate REGISTRY_SNAPSHOT ProcessingNodeRun/artifact boundary "
            "exists yet."
        ),
    ),
    RuntimeNodeCoverage(
        node_name="FAQ_SURFACE_FINAL_RECONCILIATION",
        status=RuntimeCoverageStatus.IMPLEMENTED_CONNECTED,
        evidence=(
            (
                FINAL_RECONCILIATION_GENERATOR,
                (
                    "class FaqWorkbenchFinalReconciliationGenerator",
                    "workbench_final_reconciliation",
                    "faq_surface_final_reconciliation",
                    "parse_final_reconciliation_payload",
                ),
            ),
            (
                FINAL_RECONCILIATION_SERVICE,
                (
                    "class FaqWorkbenchFinalReconciliationService",
                    "persist_final_reconciliation_output",
                    "persist_final_reconciliation_generation_error",
                    "ProcessingNodeName.FAQ_SURFACE_FINAL_RECONCILIATION",
                ),
            ),
            (
                ORCH,
                (
                    "_persist_final_reconciliation_advice",
                    "generate_final_reconciliation",
                    "persist_final_reconciliation_output",
                ),
            ),
            (
                QUEUE_HANDLER,
                (
                    "make_workbench_final_reconciliation_generator",
                    "final_reconciliation_generator=make_workbench_final_reconciliation_generator()",
                ),
            ),
        ),
    ),
    RuntimeNodeCoverage(
        node_name="SURFACE_MATERIALIZATION",
        status=RuntimeCoverageStatus.IMPLEMENTED_CONNECTED,
        evidence=(
            (
                SURFACE_MATERIALIZATION_SERVICE,
                (
                    "class FaqWorkbenchSurfaceMaterializationService",
                    "materialize_surfaces",
                    "SurfaceMaterializationResult",
                ),
            ),
            (
                ORCH,
                (
                    "_surface_materialization_service.materialize_surfaces",
                    "MaterializeRegistrySurfacesCommand",
                ),
            ),
        ),
    ),
)


def test_graph_contract_declares_expected_processing_nodes() -> None:
    graph_source = _graph_contract_source()

    for node_name in EXPECTED_GRAPH_NODE_NAMES:
        assert f"ProcessingNodeName.{node_name}" in graph_source

    assert "FAQ_WORKBENCH_PROCESSING_GRAPH_CONTRACT" in graph_source
    assert "FAQ_SURFACE_FINAL_RECONCILIATION_NODE" in graph_source
    assert "FAQ_SURFACE_REGISTRY_MERGE_NODE" in graph_source
    assert "FAQ_SURFACE_SECTION_FINDINGS_NODE" in graph_source


def test_runtime_coverage_audit_covers_every_graph_contract_node() -> None:
    covered_names = tuple(item.node_name for item in RUNTIME_COVERAGE)

    assert covered_names == EXPECTED_GRAPH_NODE_NAMES
    assert len(set(covered_names)) == len(EXPECTED_GRAPH_NODE_NAMES)

    for item in RUNTIME_COVERAGE:
        item.assert_current()


def test_runtime_connected_nodes_are_the_only_nodes_claimed_as_done() -> None:
    implemented = {
        item.node_name
        for item in RUNTIME_COVERAGE
        if item.status is RuntimeCoverageStatus.IMPLEMENTED_CONNECTED
    }

    assert implemented == {
        "RESTORE_CHECKPOINT",
        "FAQ_SURFACE_SECTION_FINDINGS",
        "FAQ_SURFACE_REGISTRY_MERGE",
        "FAQ_SURFACE_FINAL_RECONCILIATION",
        "SURFACE_MATERIALIZATION",
    }


def test_partial_or_contract_only_nodes_are_explicitly_documented() -> None:
    incomplete = {
        item.node_name: item.missing_runtime_boundary
        for item in RUNTIME_COVERAGE
        if item.status is not RuntimeCoverageStatus.IMPLEMENTED_CONNECTED
    }

    assert set(incomplete) == {
        "INITIALIZE_REGISTRY",
        "PROCESS_PARALLEL_SECTION_BATCH",
        "DETERMINISTIC_DEDUP",
        "REGISTRY_UPDATE_APPLICATION",
        "REGISTRY_SNAPSHOT",
    }

    for reason in incomplete.values():
        assert reason
        assert "not yet" in reason or "No " in reason or "no " in reason


def test_current_runtime_order_matches_implemented_subset_with_final_reconciliation() -> (
    None
):
    section_loop_source = _function_source(ORCH, "_process_sections_against_registry")
    process_markdown_source = _function_source(ORCH, "process_markdown_document")
    process_existing_source = _function_source(
        ORCH,
        "process_existing_document_sections",
    )

    claim_observations_index = section_loop_source.index(
        "_claim_observations_service.persist_claim_observations("
    )
    registry_merge_index = section_loop_source.index(
        "await self._persist_registry_merge_advice_for_section("
    )
    deterministic_application_index = section_loop_source.index(
        "await self._registry_application_service.apply_findings_to_registry("
    )

    assert (
        claim_observations_index < registry_merge_index < deterministic_application_index
    )

    markdown_processing_index = process_markdown_source.index(
        "await self._process_sections_against_registry("
    )
    markdown_final_index = process_markdown_source.index(
        "await self._persist_final_reconciliation_advice("
    )
    markdown_materialization_index = process_markdown_source.index(
        "_surface_materialization_service.materialize_surfaces("
    )
    assert (
        markdown_processing_index
        < markdown_final_index
        < markdown_materialization_index
    )

    existing_processing_index = process_existing_source.index(
        "await self._process_sections_against_registry("
    )
    existing_final_index = process_existing_source.index(
        "await self._persist_final_reconciliation_advice("
    )
    existing_materialization_index = process_existing_source.index(
        "_surface_materialization_service.materialize_surfaces("
    )
    assert (
        existing_processing_index
        < existing_final_index
        < existing_materialization_index
    )


def test_registry_merge_advisory_guard_remains_active() -> None:
    assert ADVISORY_GUARD.exists()
    assert NODE_CONTRACT_GUARD.exists()
    assert SECTION_BATCH_CHECKPOINT_GUARD.exists()

    advisory_source = ADVISORY_GUARD.read_text(encoding="utf-8")
    node_contract_source = NODE_CONTRACT_GUARD.read_text(encoding="utf-8")

    assert "registry_update_proposals" in advisory_source
    assert "LLM_ADVISORY" in advisory_source
    assert "deterministic_application" in advisory_source
    assert "FaqWorkbenchRegistryMergeGenerator" in node_contract_source
    assert "persist_registry_merge_generation_error" in node_contract_source
