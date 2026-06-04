from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from src.domain.project_plane.knowledge_workbench.nodes import (
    ProcessingNodeKind,
    ProcessingNodeName,
)
from src.domain.project_plane.llm_routing.invocations import (
    LlmJsonInvocationRequest,
)


FAQ_WORKBENCH_PROCESSING_METHOD = "faq_section_registry_v1"
FAQ_WORKBENCH_PROCESSING_GRAPH_VERSION = "v1"
FAQ_WORKBENCH_DEFAULT_LLM_CONCURRENCY = 3


class FaqWorkbenchGraphExecutionMode(StrEnum):
    ONCE_PER_RUN = "once_per_run"
    PER_SECTION_PARALLEL = "per_section_parallel"
    PER_SECTION_SEQUENTIAL = "per_section_sequential"
    PER_SECTION_SEQUENTIAL_ADVISORY = "per_section_sequential_advisory"
    FINAL_BOUNDED_ONCE = "final_bounded_once"


class FaqWorkbenchGraphNodeRole(StrEnum):
    INITIALIZATION = "initialization"
    CHECKPOINT_RESTORE = "checkpoint_restore"
    SECTION_BATCH_CONTROL = "section_batch_control"
    SECTION_FINDING = "section_finding"
    DEDUPLICATION = "deduplication"
    REGISTRY_MERGE_ADVICE = "registry_merge_advice"
    REGISTRY_MUTATION = "registry_mutation"
    SNAPSHOT = "snapshot"
    FINAL_RECONCILIATION = "final_reconciliation"
    MATERIALIZATION = "materialization"


class FaqWorkbenchArtifactContract(StrEnum):
    INPUT_SNAPSHOT = "input_snapshot"
    RAW_LLM_OUTPUT = "raw_llm_output"
    PARSED_LLM_OUTPUT = "parsed_llm_output"
    DETERMINISTIC_RESULT = "deterministic_result"
    APPLIED_RESULT = "applied_result"
    REGISTRY_SNAPSHOT = "registry_snapshot"
    ERROR_REPORT = "error_report"
    MODEL_ROUTE = "model_route"


@dataclass(frozen=True, slots=True)
class FaqWorkbenchProcessingGraphNodeSpec:
    node_name: ProcessingNodeName
    node_kind: ProcessingNodeKind
    role: FaqWorkbenchGraphNodeRole
    operation_name: str
    execution_mode: FaqWorkbenchGraphExecutionMode
    input_contract: tuple[str, ...]
    output_contract: tuple[str, ...]
    artifact_contract: tuple[FaqWorkbenchArtifactContract, ...]
    prompt_file_name: str | None = None
    prompt_marker: str | None = None
    route_purpose: str | None = None
    mutates_registry: bool = False
    requires_node_run: bool = True
    max_concurrency_default: int | None = None

    def __post_init__(self) -> None:
        if not self.operation_name.strip():
            raise ValueError("operation_name must not be blank")
        if not self.input_contract:
            raise ValueError(f"{self.node_name} input_contract must not be empty")
        if not self.output_contract:
            raise ValueError(f"{self.node_name} output_contract must not be empty")
        if not self.artifact_contract:
            raise ValueError(f"{self.node_name} artifact_contract must not be empty")

        if self.node_kind is ProcessingNodeKind.LLM_PROMPT:
            if not self.prompt_file_name or not self.prompt_file_name.strip():
                raise ValueError(f"{self.node_name} LLM node requires prompt_file_name")
            if not self.prompt_marker or not self.prompt_marker.strip():
                raise ValueError(f"{self.node_name} LLM node requires prompt_marker")
            if not self.route_purpose or not self.route_purpose.strip():
                raise ValueError(f"{self.node_name} LLM node requires route_purpose")
            if (
                FaqWorkbenchArtifactContract.RAW_LLM_OUTPUT
                not in self.artifact_contract
            ):
                raise ValueError(f"{self.node_name} LLM node must persist raw output")
            if self.mutates_registry:
                raise ValueError("LLM prompt nodes must not mutate registry directly")
        else:
            if self.prompt_file_name is not None:
                raise ValueError(
                    f"{self.node_name} non-LLM node must not own prompt file"
                )
            if self.route_purpose is not None:
                raise ValueError(
                    f"{self.node_name} non-LLM node must not own route purpose"
                )

        if (
            self.execution_mode is FaqWorkbenchGraphExecutionMode.PER_SECTION_PARALLEL
            and self.max_concurrency_default is None
        ):
            raise ValueError("parallel node must define max_concurrency_default")

    @property
    def is_llm_node(self) -> bool:
        return self.node_kind is ProcessingNodeKind.LLM_PROMPT

    def prompt_path(self, prompt_root: Path) -> Path:
        if self.prompt_file_name is None:
            raise ValueError(f"{self.node_name} is not a prompt node")
        return prompt_root / self.prompt_file_name

    def invocation_request(
        self,
        *,
        prompt: str,
        idempotency_key: str | None = None,
    ) -> LlmJsonInvocationRequest:
        if not self.is_llm_node or self.route_purpose is None:
            raise ValueError(f"{self.node_name} is not an LLM invocation node")
        return LlmJsonInvocationRequest(
            operation_name=self.operation_name,
            prompt=prompt,
            route_purpose=self.route_purpose,
            idempotency_key=idempotency_key,
        )


@dataclass(frozen=True, slots=True)
class FaqWorkbenchProcessingGraphEdge:
    from_node: ProcessingNodeName
    to_node: ProcessingNodeName
    payload_contract: tuple[str, ...]
    barrier_after_edge: bool = False

    def __post_init__(self) -> None:
        if self.from_node == self.to_node:
            raise ValueError("graph edge must connect distinct nodes")
        if not self.payload_contract:
            raise ValueError("payload_contract must not be empty")


@dataclass(frozen=True, slots=True)
class FaqWorkbenchProcessingGraphContract:
    processing_method: str
    graph_version: str
    node_order: tuple[ProcessingNodeName, ...]
    node_specs: tuple[FaqWorkbenchProcessingGraphNodeSpec, ...]
    edges: tuple[FaqWorkbenchProcessingGraphEdge, ...]
    default_llm_concurrency: int = FAQ_WORKBENCH_DEFAULT_LLM_CONCURRENCY

    def __post_init__(self) -> None:
        if self.processing_method != FAQ_WORKBENCH_PROCESSING_METHOD:
            raise ValueError("unexpected FAQ Workbench processing method")
        if not self.graph_version.strip():
            raise ValueError("graph_version must not be blank")
        if self.default_llm_concurrency != 3:
            raise ValueError("FAQ Workbench default LLM concurrency must be 3")

        spec_names = tuple(spec.node_name for spec in self.node_specs)
        if spec_names != self.node_order:
            raise ValueError("node_specs order must match node_order")

        expected_edges = tuple(zip(self.node_order, self.node_order[1:]))
        actual_edges = tuple((edge.from_node, edge.to_node) for edge in self.edges)
        if actual_edges != expected_edges:
            raise ValueError("edges must connect node_order sequentially")

        registry_mutators = tuple(
            spec for spec in self.node_specs if spec.mutates_registry
        )
        if registry_mutators != (
            self.spec_for(ProcessingNodeName.REGISTRY_UPDATE_APPLICATION),
        ):
            raise ValueError("only registry_update_application may mutate registry")

    def spec_for(
        self,
        node_name: ProcessingNodeName,
    ) -> FaqWorkbenchProcessingGraphNodeSpec:
        for spec in self.node_specs:
            if spec.node_name is node_name:
                return spec
        raise KeyError(node_name)

    def llm_node_specs(self) -> tuple[FaqWorkbenchProcessingGraphNodeSpec, ...]:
        return tuple(spec for spec in self.node_specs if spec.is_llm_node)

    def prompt_files(self) -> tuple[str, ...]:
        return tuple(
            spec.prompt_file_name
            for spec in self.llm_node_specs()
            if spec.prompt_file_name is not None
        )

    def validate_prompt_files(self, prompt_root: Path) -> None:
        for spec in self.llm_node_specs():
            path = spec.prompt_path(prompt_root)
            if not path.exists():
                raise FileNotFoundError(path)
            content = path.read_text(encoding="utf-8")
            if spec.prompt_marker is None or spec.prompt_marker not in content:
                raise ValueError(
                    f"{path} does not contain expected marker {spec.prompt_marker!r}"
                )


FAQ_INITIALIZE_REGISTRY_NODE = FaqWorkbenchProcessingGraphNodeSpec(
    node_name=ProcessingNodeName.INITIALIZE_REGISTRY,
    node_kind=ProcessingNodeKind.PERSISTENCE,
    role=FaqWorkbenchGraphNodeRole.INITIALIZATION,
    operation_name="initialize_registry",
    execution_mode=FaqWorkbenchGraphExecutionMode.ONCE_PER_RUN,
    input_contract=("document", "processing_run"),
    output_contract=("fact_registry", "initial_registry_snapshot"),
    artifact_contract=(
        FaqWorkbenchArtifactContract.INPUT_SNAPSHOT,
        FaqWorkbenchArtifactContract.APPLIED_RESULT,
    ),
)

FAQ_RESTORE_CHECKPOINT_NODE = FaqWorkbenchProcessingGraphNodeSpec(
    node_name=ProcessingNodeName.RESTORE_CHECKPOINT,
    node_kind=ProcessingNodeKind.PERSISTENCE,
    role=FaqWorkbenchGraphNodeRole.CHECKPOINT_RESTORE,
    operation_name="restore_checkpoint",
    execution_mode=FaqWorkbenchGraphExecutionMode.ONCE_PER_RUN,
    input_contract=("processing_run", "latest_registry_snapshot"),
    output_contract=("resume_cursor", "registry_snapshot"),
    artifact_contract=(
        FaqWorkbenchArtifactContract.INPUT_SNAPSHOT,
        FaqWorkbenchArtifactContract.APPLIED_RESULT,
    ),
)

FAQ_PROCESS_PARALLEL_SECTION_BATCH_NODE = FaqWorkbenchProcessingGraphNodeSpec(
    node_name=ProcessingNodeName.PROCESS_PARALLEL_SECTION_BATCH,
    node_kind=ProcessingNodeKind.CONTROL_FLOW,
    role=FaqWorkbenchGraphNodeRole.SECTION_BATCH_CONTROL,
    operation_name="process_parallel_section_batch",
    execution_mode=FaqWorkbenchGraphExecutionMode.ONCE_PER_RUN,
    input_contract=("document_sections", "resume_cursor"),
    output_contract=("section_batch_plan", "max_llm_concurrency"),
    artifact_contract=(
        FaqWorkbenchArtifactContract.INPUT_SNAPSHOT,
        FaqWorkbenchArtifactContract.DETERMINISTIC_RESULT,
    ),
)

FAQ_SURFACE_SECTION_FINDINGS_NODE = FaqWorkbenchProcessingGraphNodeSpec(
    node_name=ProcessingNodeName.FAQ_SURFACE_SECTION_FINDINGS,
    node_kind=ProcessingNodeKind.LLM_PROMPT,
    role=FaqWorkbenchGraphNodeRole.SECTION_FINDING,
    operation_name="faq_surface_claim_observations",
    execution_mode=FaqWorkbenchGraphExecutionMode.PER_SECTION_PARALLEL,
    input_contract=(
        "canonicalization_unit",
        "registry_snapshot_payload",
        "relevant_registry_state",
        "canonical_facts",
    ),
    output_contract=("claim_observations", "warnings", "metrics"),
    artifact_contract=(
        FaqWorkbenchArtifactContract.INPUT_SNAPSHOT,
        FaqWorkbenchArtifactContract.MODEL_ROUTE,
        FaqWorkbenchArtifactContract.RAW_LLM_OUTPUT,
        FaqWorkbenchArtifactContract.PARSED_LLM_OUTPUT,
        FaqWorkbenchArtifactContract.ERROR_REPORT,
    ),
    prompt_file_name="faq_surface_claim_observations.ru.txt",
    prompt_marker="NODE: faq_surface_claim_observations",
    route_purpose="workbench_claim_observations",
    max_concurrency_default=FAQ_WORKBENCH_DEFAULT_LLM_CONCURRENCY,
)

FAQ_DETERMINISTIC_DEDUP_NODE = FaqWorkbenchProcessingGraphNodeSpec(
    node_name=ProcessingNodeName.DETERMINISTIC_DEDUP,
    node_kind=ProcessingNodeKind.DETERMINISTIC_CODE,
    role=FaqWorkbenchGraphNodeRole.DEDUPLICATION,
    operation_name="deterministic_dedup",
    execution_mode=FaqWorkbenchGraphExecutionMode.PER_SECTION_SEQUENTIAL,
    input_contract=("claim_observations", "registry_snapshot"),
    output_contract=("dedup_result", "absorbed_role_labels", "kept_findings"),
    artifact_contract=(
        FaqWorkbenchArtifactContract.INPUT_SNAPSHOT,
        FaqWorkbenchArtifactContract.DETERMINISTIC_RESULT,
    ),
)

FAQ_SURFACE_REGISTRY_MERGE_NODE = FaqWorkbenchProcessingGraphNodeSpec(
    node_name=ProcessingNodeName.FAQ_SURFACE_REGISTRY_MERGE,
    node_kind=ProcessingNodeKind.LLM_PROMPT,
    role=FaqWorkbenchGraphNodeRole.REGISTRY_MERGE_ADVICE,
    operation_name="faq_surface_registry_merge",
    execution_mode=FaqWorkbenchGraphExecutionMode.PER_SECTION_SEQUENTIAL_ADVISORY,
    input_contract=(
        "canonicalization_unit",
        "registry_snapshot_payload",
        "relevant_registry_state",
        "canonical_facts",
    ),
    output_contract=(
        "fact_registry",
        "registry_update_summary",
        "warnings",
        "metrics",
    ),
    artifact_contract=(
        FaqWorkbenchArtifactContract.INPUT_SNAPSHOT,
        FaqWorkbenchArtifactContract.MODEL_ROUTE,
        FaqWorkbenchArtifactContract.RAW_LLM_OUTPUT,
        FaqWorkbenchArtifactContract.PARSED_LLM_OUTPUT,
        FaqWorkbenchArtifactContract.ERROR_REPORT,
    ),
    prompt_file_name="faq_surface_registry_merge.ru.txt",
    prompt_marker="FAQ_REGISTRY_MERGE_NODE_PROMPT_V2",
    route_purpose="workbench_fact_registry_canonicalization",
)

FAQ_REGISTRY_UPDATE_APPLICATION_NODE = FaqWorkbenchProcessingGraphNodeSpec(
    node_name=ProcessingNodeName.REGISTRY_UPDATE_APPLICATION,
    node_kind=ProcessingNodeKind.DETERMINISTIC_CODE,
    role=FaqWorkbenchGraphNodeRole.REGISTRY_MUTATION,
    operation_name="registry_update_application",
    execution_mode=FaqWorkbenchGraphExecutionMode.PER_SECTION_SEQUENTIAL,
    input_contract=(
        "registry_updates",
        "dedup_result",
        "registry_snapshot_payload",
        "claim_observations",
    ),
    output_contract=("registry_update_applications", "updated_registry"),
    artifact_contract=(
        FaqWorkbenchArtifactContract.INPUT_SNAPSHOT,
        FaqWorkbenchArtifactContract.APPLIED_RESULT,
    ),
    mutates_registry=True,
)

FAQ_REGISTRY_SNAPSHOT_NODE = FaqWorkbenchProcessingGraphNodeSpec(
    node_name=ProcessingNodeName.REGISTRY_SNAPSHOT,
    node_kind=ProcessingNodeKind.PERSISTENCE,
    role=FaqWorkbenchGraphNodeRole.SNAPSHOT,
    operation_name="registry_snapshot_payload",
    execution_mode=FaqWorkbenchGraphExecutionMode.PER_SECTION_SEQUENTIAL,
    input_contract=("updated_registry", "registry_update_applications"),
    output_contract=("registry_snapshot_payload",),
    artifact_contract=(
        FaqWorkbenchArtifactContract.INPUT_SNAPSHOT,
        FaqWorkbenchArtifactContract.REGISTRY_SNAPSHOT,
    ),
)

FAQ_SURFACE_FINAL_RECONCILIATION_NODE = FaqWorkbenchProcessingGraphNodeSpec(
    node_name=ProcessingNodeName.FAQ_SURFACE_FINAL_RECONCILIATION,
    node_kind=ProcessingNodeKind.LLM_PROMPT,
    role=FaqWorkbenchGraphNodeRole.FINAL_RECONCILIATION,
    operation_name="faq_surface_final_reconciliation",
    execution_mode=FaqWorkbenchGraphExecutionMode.FINAL_BOUNDED_ONCE,
    input_contract=(
        "registry_snapshot_payload",
        "proposed_final_surfaces",
        "proposed_relations",
        "proposed_merge_decisions",
        "aggregate_metrics",
    ),
    output_contract=(
        "surface_adjustments",
        "relations",
        "merge_decisions",
        "warnings",
        "metrics",
    ),
    artifact_contract=(
        FaqWorkbenchArtifactContract.INPUT_SNAPSHOT,
        FaqWorkbenchArtifactContract.MODEL_ROUTE,
        FaqWorkbenchArtifactContract.RAW_LLM_OUTPUT,
        FaqWorkbenchArtifactContract.PARSED_LLM_OUTPUT,
        FaqWorkbenchArtifactContract.ERROR_REPORT,
    ),
    prompt_file_name="faq_surface_final_reconciliation.ru.txt",
    prompt_marker="NODE: faq_surface_final_reconciliation",
    route_purpose="workbench_final_reconciliation",
)

FAQ_SURFACE_MATERIALIZATION_NODE = FaqWorkbenchProcessingGraphNodeSpec(
    node_name=ProcessingNodeName.SURFACE_MATERIALIZATION,
    node_kind=ProcessingNodeKind.MATERIALIZATION,
    role=FaqWorkbenchGraphNodeRole.MATERIALIZATION,
    operation_name="runtime_publication",
    execution_mode=FaqWorkbenchGraphExecutionMode.FINAL_BOUNDED_ONCE,
    input_contract=(
        "registry_snapshot_payload",
        "final_reconciliation_suggestions",
    ),
    output_contract=("runtime_publication_result", "runtime_retrieval_entries"),
    artifact_contract=(
        FaqWorkbenchArtifactContract.INPUT_SNAPSHOT,
        FaqWorkbenchArtifactContract.APPLIED_RESULT,
    ),
)

FAQ_WORKBENCH_PROCESSING_GRAPH_CONTRACT = FaqWorkbenchProcessingGraphContract(
    processing_method=FAQ_WORKBENCH_PROCESSING_METHOD,
    graph_version=FAQ_WORKBENCH_PROCESSING_GRAPH_VERSION,
    node_order=(
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
    ),
    node_specs=(
        FAQ_INITIALIZE_REGISTRY_NODE,
        FAQ_RESTORE_CHECKPOINT_NODE,
        FAQ_PROCESS_PARALLEL_SECTION_BATCH_NODE,
        FAQ_SURFACE_SECTION_FINDINGS_NODE,
        FAQ_DETERMINISTIC_DEDUP_NODE,
        FAQ_SURFACE_REGISTRY_MERGE_NODE,
        FAQ_REGISTRY_UPDATE_APPLICATION_NODE,
        FAQ_REGISTRY_SNAPSHOT_NODE,
        FAQ_SURFACE_FINAL_RECONCILIATION_NODE,
        FAQ_SURFACE_MATERIALIZATION_NODE,
    ),
    edges=(
        FaqWorkbenchProcessingGraphEdge(
            from_node=ProcessingNodeName.INITIALIZE_REGISTRY,
            to_node=ProcessingNodeName.RESTORE_CHECKPOINT,
            payload_contract=("fact_registry", "initial_registry_snapshot"),
        ),
        FaqWorkbenchProcessingGraphEdge(
            from_node=ProcessingNodeName.RESTORE_CHECKPOINT,
            to_node=ProcessingNodeName.PROCESS_PARALLEL_SECTION_BATCH,
            payload_contract=("resume_cursor", "registry_snapshot"),
        ),
        FaqWorkbenchProcessingGraphEdge(
            from_node=ProcessingNodeName.PROCESS_PARALLEL_SECTION_BATCH,
            to_node=ProcessingNodeName.FAQ_SURFACE_SECTION_FINDINGS,
            payload_contract=("section_batch_plan", "registry_snapshot"),
        ),
        FaqWorkbenchProcessingGraphEdge(
            from_node=ProcessingNodeName.FAQ_SURFACE_SECTION_FINDINGS,
            to_node=ProcessingNodeName.DETERMINISTIC_DEDUP,
            payload_contract=("claim_observations", "registry_snapshot"),
        ),
        FaqWorkbenchProcessingGraphEdge(
            from_node=ProcessingNodeName.DETERMINISTIC_DEDUP,
            to_node=ProcessingNodeName.FAQ_SURFACE_REGISTRY_MERGE,
            payload_contract=("kept_findings", "dedup_result", "registry_snapshot"),
        ),
        FaqWorkbenchProcessingGraphEdge(
            from_node=ProcessingNodeName.FAQ_SURFACE_REGISTRY_MERGE,
            to_node=ProcessingNodeName.REGISTRY_UPDATE_APPLICATION,
            payload_contract=("registry_updates", "dedup_result", "registry_snapshot"),
        ),
        FaqWorkbenchProcessingGraphEdge(
            from_node=ProcessingNodeName.REGISTRY_UPDATE_APPLICATION,
            to_node=ProcessingNodeName.REGISTRY_SNAPSHOT,
            payload_contract=("registry_update_applications", "updated_registry"),
        ),
        FaqWorkbenchProcessingGraphEdge(
            from_node=ProcessingNodeName.REGISTRY_SNAPSHOT,
            to_node=ProcessingNodeName.FAQ_SURFACE_FINAL_RECONCILIATION,
            payload_contract=("all_sections_processed", "registry_snapshot"),
            barrier_after_edge=True,
        ),
        FaqWorkbenchProcessingGraphEdge(
            from_node=ProcessingNodeName.FAQ_SURFACE_FINAL_RECONCILIATION,
            to_node=ProcessingNodeName.SURFACE_MATERIALIZATION,
            payload_contract=(
                "registry_snapshot_payload",
                "final_reconciliation_suggestions",
            ),
        ),
    ),
)


__all__ = [
    "FAQ_DETERMINISTIC_DEDUP_NODE",
    "FAQ_INITIALIZE_REGISTRY_NODE",
    "FAQ_PROCESS_PARALLEL_SECTION_BATCH_NODE",
    "FAQ_REGISTRY_SNAPSHOT_NODE",
    "FAQ_REGISTRY_UPDATE_APPLICATION_NODE",
    "FAQ_RESTORE_CHECKPOINT_NODE",
    "FAQ_SURFACE_FINAL_RECONCILIATION_NODE",
    "FAQ_SURFACE_MATERIALIZATION_NODE",
    "FAQ_SURFACE_REGISTRY_MERGE_NODE",
    "FAQ_SURFACE_SECTION_FINDINGS_NODE",
    "FAQ_WORKBENCH_DEFAULT_LLM_CONCURRENCY",
    "FAQ_WORKBENCH_PROCESSING_GRAPH_CONTRACT",
    "FAQ_WORKBENCH_PROCESSING_GRAPH_VERSION",
    "FAQ_WORKBENCH_PROCESSING_METHOD",
    "FaqWorkbenchArtifactContract",
    "FaqWorkbenchGraphExecutionMode",
    "FaqWorkbenchGraphNodeRole",
    "FaqWorkbenchProcessingGraphContract",
    "FaqWorkbenchProcessingGraphEdge",
    "FaqWorkbenchProcessingGraphNodeSpec",
]
